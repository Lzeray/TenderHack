"""Уровень 2: насколько значение признака типично для реальных товаров этого типа (выгрузки СТЕ).

Читает артефакт `data/ste_stats.sqlite` (сборка — `ktru_assist.catalog.ste_stats`). Вердикт относится к признаку,
а не к паре «признак × позиция», поэтому не может участвовать в отборе позиций и выборе кода (уровень 1).
Без артефакта или при другом снимке КТРУ — `not_assessed` с причиной, остальное работает как раньше.

Статусы:
* typical — значение в зоне типичных значений (или условию удовлетворяет заметная доля моделей);
* rare — встречается, но редко / вне зон внутри наблюдаемого диапазона;
* unseen — не встречается ни у одной модели (только числа и только при поддержке не ниже N2);
* not_assessed — нет артефакта, тип или свойство не найдены, мало данных, открытый словарь значений.
Пороги — `THRESHOLDS`; решения и замеры — docs/LEVELS_PLAN.md (шаг B3).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from .catalog.ste_stats import prop_key, zones_from_freq
from .catalog.ste_importer import key as ste_key
from .models import EmpiricalCheck, Feature
from .text import content_lemmas
from .units import fmt, lookup
from .validate import user_interval

VERSION = "1.4"   # 1.4 в памяти только свойства с поддержкой, порог «обычного свойства»; 1.3 общие свойства не называются «чужими»; 1.2 вердикты для свойств вне КТРУ; 1.1 текст: леммы, наборы по значениям, без unseen
THRESHOLDS = {
    "n1_models": 30, "n1_manufacturers": 3,      # ниже — уровень 2 молчит
    "n2_models": 60, "n2_manufacturers": 5,      # ниже — только положительные утверждения
    "typical_share": Decimal("0.05"),            # доля моделей, удовлетворяющих условию, для «типично»
    "rare_share": Decimal("0.01"),               # текстовые значения: реже — «редко»
    "discrete_max": 12,                          # не больше стольких различных чисел — перечисляем частые
    "open_vocab_ratio": Decimal("0.5"),          # различных значений на модель больше — открытый словарь
    "universal_types": 10,
    "common_property_share": Decimal("0.1"),     # «обычное свойство» — указано не меньше чем у 10 % моделей типа                       # свойство есть у стольких типов и больше — общее (цвет, вес)
}
# реквизиты карточки, а не характеристики: в выгрузках это отдельные столбцы
UNIVERSAL_PROPS = {"страна происхождения", "страна", "производитель", "модель", "бренд", "торговая марка"}


@dataclass
class PropStats:
    prop_id: int
    type_key: str
    display_name: str
    kind: str
    dimension: str | None
    n_models: int
    n_manufacturers: int
    n_distinct: int
    quantiles: dict
    min_value: Decimal | None
    max_value: Decimal | None


class SteStats:
    """Артефакт статистики. Открывается только на чтение; несовместимый снимок — уровень 2 выключен."""

    def __init__(self, path: Path | str, ktru_snapshot: str | None):
        self.path = Path(path)
        self.available = False
        self.reason = "no_artifact"
        self.manifest: dict = {}
        self.props: dict[tuple, PropStats] = {}
        self.types: dict[str, dict] = {}
        if not self.path.exists():
            return
        try:
            self.con = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
            self.manifest = {k: json.loads(v) for k, v in self.con.execute("SELECT key, value FROM manifest")}
        except sqlite3.Error:
            self.reason = "unreadable"
            return
        if self.manifest.get("ktru_snapshot") != ktru_snapshot:
            self.reason = "stale_snapshot"
            return
        # в памяти — только свойства с поддержкой не ниже N1 (≈ 7 % строк); для остальных — только ключи,
        # чтобы отвечать «мало данных», а не «свойство не найдено»
        self.weak: set[tuple] = set()
        n1, m1 = THRESHOLDS["n1_models"], THRESHOLDS["n1_manufacturers"]
        for r in self.con.execute("SELECT prop_id, type_key, prop_key, display_name, kind, dimension, n_models, "
                                  "n_manufacturers, n_distinct, quantiles, min_value, max_value FROM props"):
            k = (r[1], r[2], r[4], r[5])
            if r[6] < n1 or r[7] < m1:
                self.weak.add(k)
                continue
            self.props[k] = PropStats(r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8] or 0,
                                      json.loads(r[9]) if r[9] else {},
                                      Decimal(r[10]) if r[10] else None, Decimal(r[11]) if r[11] else None)
        for r in self.con.execute("SELECT type_key, n_models, n_manufacturers FROM types"):
            self.types[r[0]] = {"n_models": r[1], "n_manufacturers": r[2]}
        self.available = True
        self.reason = ""

    @property
    def version(self) -> str:
        return (self.manifest.get("content_hash") or "")[:12]

    def find(self, heads: list[str], prop_name: str, kind: str, dimension: str | None) -> PropStats | None:
        pk = prop_key(prop_name)
        for tk in self.type_keys(heads):
            ps = self.props.get((tk, pk, kind, dimension))
            if ps is not None:
                return ps
        return None

    def is_weak(self, heads: list[str], prop_name: str, kind: str, dimension: str | None) -> bool:
        """Свойство есть в выгрузках, но с поддержкой ниже N1."""
        pk = prop_key(prop_name)
        return any((tk, pk, kind, dimension) in self.weak for tk in self.type_keys(heads))

    @staticmethod
    def type_keys(heads: list[str]) -> list[str]:
        """Тот же ключ, что при сборке («дрель|шуруповерт»), затем каждое главное слово отдельно."""
        keys = ["|".join(sorted(heads))] if heads else []
        return keys + [h for h in sorted(heads) if h not in keys]

    @lru_cache(maxsize=4096)
    def values(self, prop_id: int) -> tuple[tuple[Decimal, int], ...]:
        return tuple((Decimal(v), n) for v, n in self.con.execute(
            "SELECT value, n_models FROM value_freq WHERE prop_id=? ORDER BY CAST(value AS REAL)", (prop_id,)))

    @lru_cache(maxsize=4096)
    def zones(self, prop_id: int) -> tuple[tuple[Decimal, Decimal, int, bool], ...]:
        """Зоны считаются по частотам при загрузке (правило — ste_stats.zones_from_freq), чтобы изменение
        правила не требовало пересборки артефакта."""
        return tuple(zones_from_freq(sorted(self.values(prop_id))))

    @lru_cache(maxsize=1024)
    def axis_orders(self, type_key: str, axes: str) -> dict[str, int]:
        """Порядок осей по величине у моделей типа (axes — оси через запятую по алфавиту). Пусто, если таблицы
        нет (артефакт старой схемы) или данных нет."""
        try:
            return {o: n for o, n in self.con.execute(
                "SELECT order_desc, n_models FROM axis_order WHERE type_key=? AND axes=?", (type_key, axes))}
        except sqlite3.Error:
            return {}

    @lru_cache(maxsize=256)
    def pair_rules(self, type_key: str) -> tuple[tuple[str, str, str, int, Decimal], ...]:
        """Пары «A ≤ B» (≥ 99 % моделей). Пусто для артефакта старой схемы."""
        try:
            return tuple((a, b, d, n, Decimal(h)) for a, b, d, n, h in self.con.execute(
                "SELECT a_key, b_key, dimension, n_models, holds FROM pair_le WHERE type_key=?", (type_key,)))
        except sqlite3.Error:
            return ()

    @lru_cache(maxsize=256)
    def by_lemmas(self, type_key: str) -> dict[tuple, PropStats]:
        """Свойства типа по лемматизированному названию (для свойств, названных в тексте своими словами)."""
        out: dict[tuple, PropStats] = {}
        for (t, pk, kind, dim), ps in self.props.items():
            if t != type_key:
                continue
            k = (tuple(content_lemmas(pk)), kind, dim)
            if k not in out or out[k].n_models < ps.n_models:
                out[k] = ps
        return out

    @lru_cache(maxsize=4096)
    def text_lemmas(self, prop_id: int) -> dict[tuple[str, ...], int]:
        """Число моделей по лемматизированному значению («мужская» = «мужской»)."""
        out: dict[tuple[str, ...], int] = {}
        for v, _, n in self.texts(prop_id):
            k = tuple(content_lemmas(v))
            out[k] = out.get(k, 0) + n
        return out

    @lru_cache(maxsize=4096)
    def texts(self, prop_id: int) -> tuple[tuple[str, str, int], ...]:
        return tuple(self.con.execute(
            "SELECT value_norm, display, n_models FROM text_freq WHERE prop_id=? ORDER BY n_models DESC, value_norm",
            (prop_id,)))


def _support(ps: PropStats, level: str) -> bool:
    t = THRESHOLDS
    return ps.n_models >= t[f"{level}_models"] and ps.n_manufacturers >= t[f"{level}_manufacturers"]


def _show(v: Decimal, factor: Decimal, unit: str | None) -> str:
    return fmt(v / factor) + (f" {unit}" if unit else "")


def _na(f: Feature, reason: str, ps: PropStats | None = None) -> EmpiricalCheck:
    return EmpiricalCheck(feature_id=f.id, property_name=f.property_name or "", status="not_assessed",
                          reason=reason, type_key=ps.type_key if ps else None)


def assess(f: Feature, heads: list[str], stats: SteStats | None) -> EmpiricalCheck | None:
    if f.status != "bound" or not f.property_name or f.op == "ne":
        return None
    if stats is None or not stats.available:
        return _na(f, stats.reason if stats else "no_artifact")
    U = user_interval(f)
    if U is not None:
        return _numeric(f, U, heads, stats)
    if f.value is None:
        return None
    return _text(f, heads, stats)


def _numeric(f: Feature, U, heads, stats: SteStats, ps: PropStats | None = None) -> EmpiricalCheck:
    u = lookup(f.unit) if f.unit else None
    if u is None:
        # без единицы — только счётные свойства («количество полок 3»)
        ps = ps or stats.find(heads, f.property_name, "number", "count")
        factor, unit_title = Decimal(1), None
    else:
        ps = ps or stats.find(heads, f.property_name, "number", u.dimension)
        factor, unit_title = u.factor, u.title
    if ps is None:
        dim = u.dimension if u else "count"
        return _na(f, "low_support" if stats.is_weak(heads, f.property_name, "number", dim) else "property_unmapped")
    if not _support(ps, "n1"):
        return _na(f, "low_support", ps)
    Ub = U.scaled(factor)
    vals = stats.values(ps.prop_id)
    n_sat = sum(n for v, n in vals if Ub.contains_point(v))
    zones = [z for z in stats.zones(ps.prop_id) if not z[3]]
    discrete = ps.n_distinct <= THRESHOLDS["discrete_max"]
    point = U.lo is not None and U.lo == U.hi
    ev = {"n_models": ps.n_models, "n_manufacturers": ps.n_manufacturers, "n_matching": n_sat,
          "type": ps.type_key, "property": ps.display_name}
    if discrete:
        top = sorted(vals, key=lambda x: (-x[1], x[0]))[:5]
        ev["frequent"] = [_show(v, factor, unit_title) for v, _ in top]
        typical_txt = "частые значения: " + ", ".join(ev["frequent"])
    else:
        ev["zones"] = [f"{_show(lo, factor, unit_title)}–{_show(hi, factor, unit_title)}" for lo, hi, _, _ in zones]
        q = ps.quantiles
        ev["p05_p95"] = [_show(Decimal(q["p05"]), factor, unit_title), _show(Decimal(q["p95"]), factor, unit_title)]
        typical_txt = f"у 90 % моделей от {ev['p05_p95'][0]} до {ev['p05_p95'][1]}"
        if len(zones) > 1:
            typical_txt += "; группы значений: " + "; ".join(ev["zones"][:3])
    share = Decimal(n_sat) / ps.n_models
    if point and not discrete:
        v = U.lo * factor
        in_zone = any(lo <= v <= hi for lo, hi, _, _ in zones)
        status = "typical" if in_zone else "rare" if ps.min_value <= v <= ps.max_value else "unseen"
    else:
        status = "typical" if share >= THRESHOLDS["typical_share"] else "rare" if n_sat else "unseen"
    if status == "unseen" and not _support(ps, "n2"):
        return _na(f, "low_support_negative", ps)
    who = f"{ps.n_models} моделей от {ps.n_manufacturers} производителей"
    msg = {"typical": f"обычное значение: у {who} {typical_txt}",
           "rare": f"встречается редко: подходит {n_sat} из {ps.n_models} моделей; {typical_txt}",
           "unseen": f"не встречается ни у одной из {ps.n_models} моделей в выгрузках; {typical_txt}"}[status]
    return EmpiricalCheck(feature_id=f.id, property_name=f.property_name or "", status=status, reason=msg,
                          type_key=ps.type_key, evidence=ev)


def presence(f: Feature, heads: list[str], stats: SteStats | None) -> EmpiricalCheck | None:
    """Свойство, которого нет в позициях КТРУ области (unknown_property с названием из текста).

    known_for_type — в выгрузках у этого типа есть свойство с тем же названием (по леммам) и достаточной
    поддержкой: свойство реальное, на код не влияет; значение оценивается по выгрузкам.
    known_elsewhere — у этого типа его нет ни у одной модели (поддержка типа не ниже N2), но есть у других типов."""
    if f.status != "unknown_property" or not f.named_property or stats is None or not stats.available:
        return None
    lem = _lemkey(f.named_property)
    if not lem:
        return None
    U = user_interval(f)
    u = lookup(f.unit) if f.unit else None
    kind = "number" if U is not None else "text"
    dim = (u.dimension if u else "count") if kind == "number" else None
    for tk in stats.type_keys(heads):
        ps = stats.by_lemmas(tk).get((lem, kind, dim))
        if ps is None or not _support(ps, "n1"):
            continue
        total = stats.types.get(tk, {}).get("n_models", ps.n_models)
        common = Decimal(ps.n_models) / max(1, total) >= THRESHOLDS["common_property_share"]
        base = (f"«{f.named_property}» нет в позициях КТРУ этого типа — на выбор кода не влияет. В выгрузках СТЕ "
                + ("это обычное свойство таких товаров: " if common else "") + f"указано у {ps.n_models} из {total} моделей")
        e = _numeric(f, U, heads, stats, ps) if U is not None else None
        if e is not None and e.status in ("typical", "rare", "unseen"):
            e.reason = base + "; значение — " + e.reason
            e.presence = "known_for_type"
            return e
        return EmpiricalCheck(feature_id=f.id, property_name=f.named_property, status="not_assessed",
                              reason=base + ".", type_key=tk, presence="known_for_type",
                              evidence={"n_models": ps.n_models, "property": ps.display_name})
    tks = stats.type_keys(heads)
    own = max((stats.types.get(tk, {}).get("n_models", 0) for tk in tks), default=0)
    if own < THRESHOLDS["n2_models"]:
        return None
    if prop_key(f.named_property) in UNIVERSAL_PROPS or " ".join(lem) in UNIVERSAL_PROPS:
        return None
    stem = lem[0][:4]      # кандидаты по началу слова, затем точное сравнение по леммам
    holders = sorted(((ps.n_models, t) for (t, k, kd, d), ps in stats.props.items()
                      if k.startswith(stem) and t not in tks and _support(ps, "n1") and _lemkey(k) == lem),
                     reverse=True)
    # свойство, указанное у многих типов (цвет, вес), — общее: «чужим» его не называем
    if not holders or len({t for _, t in holders}) >= THRESHOLDS["universal_types"]:
        return None
    elsewhere = holders[:3]
    where = ", ".join(t.replace("|", "-") for _, t in elsewhere)
    return EmpiricalCheck(
        feature_id=f.id, property_name=f.named_property, status="not_assessed", presence="known_elsewhere",
        type_key=tks[0], evidence={"n_models_type": own, "elsewhere": [t for _, t in elsewhere]},
        reason=f"«{f.named_property}» нет ни в КТРУ этого типа, ни у одной из {own} моделей в выгрузках. "
               f"Свойство встречается у: {where}. Проверьте, к тому ли товару оно относится.")


def _lemkey(s: str) -> tuple[str, ...]:
    return tuple(content_lemmas(s))


def _text(f: Feature, heads, stats: SteStats) -> EmpiricalCheck:
    """Текстовые значения. Уровень 1 уже проверил их по закрытому списку КТРУ, а формулировки выгрузок с КТРУ
    не сопоставлены («от аккумуляторных батарей» / «от аккумулятора», «Тип» молотка = «молоток слесарный»).
    Поэтому здесь только положительные утверждения: найдено — typical/rare с числами; не найдено —
    not_assessed (text_not_found), а не unseen. Сравнение — по леммам; набор «X и Y» — по каждому значению."""
    ps = stats.find(heads, f.property_name, "text", None)
    if ps is None:
        return _na(f, "low_support" if stats.is_weak(heads, f.property_name, "text", None) else "property_unmapped")
    if not _support(ps, "n1"):
        return _na(f, "low_support", ps)
    if Decimal(ps.n_distinct) / ps.n_models > THRESHOLDS["open_vocab_ratio"]:
        return _na(f, "open_vocab", ps)
    rows = stats.texts(ps.prop_id)
    by_lem = stats.text_lemmas(ps.prop_id)
    wanted = list(f.values) if f.op == "in" and f.values else [f.value or ""]
    counts = [by_lem.get(_lemkey(w), 0) for w in wanted]
    if not all(counts):
        return _na(f, "text_not_found", ps)
    n = min(counts)
    ev = {"n_models": ps.n_models, "n_manufacturers": ps.n_manufacturers, "n_matching": n, "type": ps.type_key,
          "property": ps.display_name, "frequent": [d for _, d, _ in rows[:5]]}
    share = Decimal(n) / ps.n_models
    status = "typical" if share >= THRESHOLDS["rare_share"] else "rare"
    freq = ", ".join(ev["frequent"])
    msg = {"typical": f"обычное значение: у {n} из {ps.n_models} моделей",
           "rare": f"встречается редко: у {n} из {ps.n_models} моделей; чаще: {freq}"}[status]
    return EmpiricalCheck(feature_id=f.id, property_name=f.property_name or "", status=status, reason=msg,
                          type_key=ps.type_key, evidence=ev)


__all__ = ["SteStats", "assess", "presence", "THRESHOLDS", "VERSION"]
