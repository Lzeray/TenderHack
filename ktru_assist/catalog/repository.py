"""Доступ к импортированному каталогу (SQLite только на чтение) и доменные объекты."""
from __future__ import annotations

import re

import json
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from pathlib import Path

from ..config import unpack_gz
from ..text import MORPH_MODE, content_lemmas, norm, tokenize
from ..units import Unit, fmt, from_okei, unit_from_char_name

YES_NO = {"да", "нет"}


@dataclass(frozen=True)
class Interval:
    lo: Decimal | None
    lo_incl: bool
    hi: Decimal | None
    hi_incl: bool

    def contains_point(self, x: Decimal) -> bool:
        if self.lo is not None and (x < self.lo or (x == self.lo and not self.lo_incl)):
            return False
        if self.hi is not None and (x > self.hi or (x == self.hi and not self.hi_incl)):
            return False
        return True

    def intersects(self, o: "Interval") -> bool:
        # пересечение пусто, если один заканчивается до начала другого
        def before(a: Interval, b: Interval) -> bool:
            if a.hi is None or b.lo is None:
                return False
            return a.hi < b.lo or (a.hi == b.lo and not (a.hi_incl and b.lo_incl))
        return not before(self, o) and not before(o, self)

    @property
    def is_point(self) -> bool:
        return self.lo is not None and self.lo == self.hi

    def overlaps_more_than_point(self, o: "Interval") -> bool:
        """Пересечение содержит больше одной точки. Касание границей («до 140» и «≥ 140») — не пересечение
        для диапазона (решение команды, docs/DIMENSIONS_PLAN.md)."""
        if not self.intersects(o):
            return False
        lo = max((x for x in (self.lo, o.lo) if x is not None), default=None)
        hi = min((x for x in (self.hi, o.hi) if x is not None), default=None)
        return lo is None or hi is None or lo < hi

    def subset_of(self, o: "Interval") -> bool:
        if o.lo is not None:
            if self.lo is None or self.lo < o.lo or (self.lo == o.lo and self.lo_incl and not o.lo_incl):
                return False
        if o.hi is not None:
            if self.hi is None or self.hi > o.hi or (self.hi == o.hi and self.hi_incl and not o.hi_incl):
                return False
        return True

    def scaled(self, k: Decimal) -> "Interval":
        return Interval(None if self.lo is None else self.lo * k, self.lo_incl,
                        None if self.hi is None else self.hi * k, self.hi_incl)

    def label(self, unit: str | None = None) -> str:
        u = f" {unit}" if unit else ""
        if self.lo is not None and self.hi is not None and self.lo == self.hi:
            return f"{fmt(self.lo)}{u}"
        parts = []
        if self.lo is not None:
            parts.append(("≥ " if self.lo_incl else "> ") + fmt(self.lo))
        if self.hi is not None:
            parts.append(("≤ " if self.hi_incl else "< ") + fmt(self.hi))
        return " и ".join(parts) + u if parts else "любое"


def merge_intervals(items: list[Interval]) -> list[Interval]:
    """Объединение смежных/пересекающихся интервалов: [160,180) ∪ [180,200) = [160,200)."""
    def key(i: Interval):
        return (i.lo is not None, i.lo if i.lo is not None else Decimal(0), not i.lo_incl)
    out: list[Interval] = []
    for it in sorted(items, key=key):
        if out:
            last = out[-1]
            touch = (last.hi is None or it.lo is None or it.lo < last.hi
                     or (it.lo == last.hi and (last.hi_incl or it.lo_incl)))
            if touch:
                if last.hi is None or (it.hi is not None and it.hi < last.hi):
                    hi, hi_incl = last.hi, last.hi_incl
                elif it.hi is None or it.hi > last.hi:
                    hi, hi_incl = it.hi, it.hi_incl
                else:
                    hi, hi_incl = last.hi, last.hi_incl or it.hi_incl
                out[-1] = Interval(last.lo, last.lo_incl, hi, hi_incl)
                continue
        out.append(it)
    return out


@dataclass(frozen=True)
class AllowedValue:
    kind: str                       # quality | range | concrete | empty
    text: str | None
    interval: Interval | None
    unit: Unit | None
    unit_name: str | None
    value_code: str | None

    @property
    def label(self) -> str:
        if self.kind == "quality":
            return self.text or ""
        if self.interval is not None:
            return self.interval.label(self.unit.title if self.unit else self.unit_name)
        return "—"

    @cached_property
    def lemmas(self) -> tuple[str, ...]:
        return tuple(content_lemmas(self.text or ""))


@dataclass
class Prop:
    code: str
    name: str
    char_type: int | None
    kind: int | None
    required: bool
    values: list[AllowedValue]

    @property
    def is_numeric(self) -> bool:
        return any(v.kind in ("range", "concrete") for v in self.values)

    @property
    def is_boolean(self) -> bool:
        texts = {norm(v.text or "") for v in self.values if v.kind == "quality"}
        return bool(texts) and texts <= YES_NO and not self.is_numeric

    @property
    def name_unit(self) -> Unit | None:
        return unit_from_char_name(self.name)

    @property
    def units(self) -> list[Unit]:
        us = {v.unit.key: v.unit for v in self.values if v.unit}
        if not us and self.name_unit:
            us[self.name_unit.key] = self.name_unit
        return [us[k] for k in sorted(us)]

    @property
    def norm_name(self) -> str:
        return " ".join(tokenize(self.name))


@dataclass
class Position:
    code: str
    name: str
    version: int
    okpd2_code: str | None
    okpd2_name: str | None
    status: str
    is_template: bool
    parent_code: str | None
    parent_version: int | None
    no_new_features: bool | None
    application_start: str | None
    application_end: str | None
    category: str | None
    active: bool
    inactive_reason: str | None
    head: str | None
    name_lemmas: list[str]
    rubrics: list
    okeis: list
    props: dict[str, Prop] = field(default_factory=dict)

    @property
    def norm_name(self) -> str:
        return " ".join(tokenize(self.name))


ITEM_STOP = frozenset({"для", "под", "к", "ко", "с", "со", "на", "из", "от", "по", "в", "во", "без", "при", "над",
                       "о", "об", "у", "за", "до"})


def item_words(name: str, heads: set[str]) -> set[str]:
    """Слова типа в наименовании, которые называют сам товар, а не его назначение: слово не стоит после предлога
    в своей группе (назад — до запятой, «/», скобки или начала). «Шаблон для заточки спиральных сверл» — не
    «сверло», «Ножи и лезвия режущие» — и «лезвие»."""
    from ..text import lemma
    parts = re.findall(r"[а-яёa-z]+(?:-[а-яёa-z]+)*|[,/()]", name.lower())
    out = set()
    for i, w in enumerate(parts):
        lem = lemma(w) if w not in ",/()" else w
        if lem not in heads:
            continue
        j, ok = i - 1, True
        while j >= 0 and parts[j] not in ",/()":
            if parts[j] in ITEM_STOP:
                ok = False
                break
            j -= 1
        if ok:
            out.add(lem)
    return out


class Catalog:
    """SQLite в режиме только чтения; соединение на поток не разделяется (check_same_thread=False
    допустим, так как запись невозможна)."""

    def __init__(self, db_path: Path | str):
        self.db_path = unpack_gz(Path(db_path))
        if not self.db_path.exists():
            raise FileNotFoundError(f"База каталога не найдена: {self.db_path}. Выполните импорт.")
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        self.con = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self._cache: dict[str, Position] = {}
        built = self.meta.get("morph", "pymorphy")
        if built != MORPH_MODE:
            raise RuntimeError(f"База {self.db_path} собрана с KTRU_MORPH={built}, а сейчас KTRU_MORPH={MORPH_MODE}: "
                               "леммы наименований не совпадут. Переимпортируйте каталог или смените режим.")

    # --- метаданные --------------------------------------------------------
    @cached_property
    def meta(self) -> dict:
        return {r["key"]: json.loads(r["value"]) for r in self.con.execute("SELECT key, value FROM meta")}

    # --- позиции -----------------------------------------------------------
    def _row_to_position(self, r: sqlite3.Row) -> Position:
        return Position(
            code=r["code"], name=r["name"], version=r["version"], okpd2_code=r["okpd2_code"],
            okpd2_name=r["okpd2_name"], status=r["status"], is_template=bool(r["is_template"]),
            parent_code=r["parent_code"], parent_version=r["parent_version"],
            no_new_features=None if r["no_new_features"] is None else bool(r["no_new_features"]),
            application_start=r["application_start"], application_end=r["application_end"],
            category=r["category"], active=bool(r["active"]), inactive_reason=r["inactive_reason"],
            head=r["head"], name_lemmas=(r["name_lemmas"] or "").split(),
            rubrics=json.loads(r["rubrics"] or "[]"), okeis=json.loads(r["okeis"] or "[]"))

    def get(self, code: str) -> Position | None:
        got = self.get_many([code])
        return got.get(code)

    def get_many(self, codes: list[str]) -> dict[str, Position]:
        missing = [c for c in codes if c not in self._cache]
        for i in range(0, len(missing), 500):
            chunk = missing[i:i + 500]
            ph = ",".join("?" * len(chunk))
            for r in self.con.execute(f"SELECT * FROM positions WHERE code IN ({ph})", chunk):
                self._cache[r["code"]] = self._row_to_position(r)
            props: dict[tuple, Prop] = {}
            for r in self.con.execute(
                    f"SELECT * FROM characteristics WHERE position_code IN ({ph}) ORDER BY position_code, ord", chunk):
                p = Prop(r["char_code"], r["name"], r["char_type"], r["kind"], bool(r["is_required"]), [])
                props[(r["position_code"], r["char_code"])] = p
                if r["position_code"] in self._cache:
                    self._cache[r["position_code"]].props[r["char_code"]] = p
            for r in self.con.execute(
                    f"SELECT * FROM char_values WHERE position_code IN ({ph}) ORDER BY position_code, char_code, ord",
                    chunk):
                p = props.get((r["position_code"], r["char_code"]))
                if p is None:
                    continue
                interval = None
                if r["value_kind"] == "range":
                    interval = Interval(
                        Decimal(r["min_value"]) if r["min_value"] is not None else None, bool(r["min_inclusive"]),
                        Decimal(r["max_value"]) if r["max_value"] is not None else None, bool(r["max_inclusive"]))
                elif r["value_kind"] == "concrete" and r["concrete_value"] is not None:
                    c = Decimal(r["concrete_value"])
                    interval = Interval(c, True, c, True)
                unit = from_okei(r["okei_code"], r["okei_name"])
                if unit is None and interval is not None:
                    unit = p.name_unit
                p.values.append(AllowedValue(r["value_kind"], r["text"], interval, unit, r["okei_name"],
                                             r["value_code"]))
        return {c: self._cache[c] for c in codes if c in self._cache}

    def inactive_count_by_heads(self, heads: list[str]) -> int:
        if not heads:
            return 0
        ph = ",".join("?" * len(heads))
        return self.con.execute(
            f"SELECT count(*) FROM positions WHERE category IS NOT NULL AND active=0 AND head IN ({ph})",
            heads).fetchone()[0]

    # --- данные для поиска и словарей -------------------------------------
    def search_documents(self) -> list[dict]:
        rows = self.con.execute(
            "SELECT code, name, name_lemmas, head, category, active, is_template, okpd2_name "
            "FROM positions WHERE category IS NOT NULL ORDER BY code").fetchall()
        heads = {r["head"] for r in rows if r["head"]}
        return [{
            "code": r["code"], "name": r["name"], "name_lemmas": (r["name_lemmas"] or "").split(),
            "head": r["head"],
            # тип позиции — главное слово и другие слова типа в наименовании не после предлога: «Секция стульев
            # многоместная» — и «стул», «Пара кожаных перчаток» — и «перчатка»; «Шкаф для одежды» — не «одежда»
            # (docs/QUESTIONS_PLAN.md, Q1)
            "head_parts": sorted({r["head"], *(r["head"] or "").split("-"), *item_words(r["name"], heads)} - {""}),
            "category": r["category"], "active": bool(r["active"]), "is_template": bool(r["is_template"]),
            "okpd2_lemmas": content_lemmas(r["okpd2_name"] or ""),
        } for r in rows]

    def vocabulary_texts(self) -> list[str]:
        """Тексты каталога MVP для словаря опечаток: наименования, характеристики, значения."""
        out = [r[0] for r in self.con.execute(
            "SELECT name FROM positions WHERE category IS NOT NULL AND active=1")]
        out += [r[0] for r in self.con.execute(
            "SELECT DISTINCT c.name FROM characteristics c JOIN positions p ON p.code=c.position_code "
            "WHERE p.category IS NOT NULL AND p.active=1")]
        out += [r[0] for r in self.con.execute(
            "SELECT DISTINCT v.text FROM char_values v JOIN positions p ON p.code=v.position_code "
            "WHERE p.category IS NOT NULL AND p.active=1 AND v.text IS NOT NULL")]
        return out

    def property_core_terms(self) -> set[str]:
        """Первые ключевые слова названий характеристик MVP («Длина режущей части» → «длина»)."""
        from ..nlp.extract import GENERIC_NAME_WORDS, _core_noun
        out = set()
        for (name,) in self.con.execute(
                "SELECT DISTINCT c.name FROM characteristics c JOIN positions p ON p.code=c.position_code "
                "WHERE p.category IS NOT NULL"):
            core = _core_noun(name)
            if core:
                out.add(core)
        return out

    def quality_values(self) -> list[tuple[str, str, str]]:
        """(главное слово, название характеристики, качественное значение) активных позиций MVP."""
        rows = self.con.execute(
            "SELECT DISTINCT p.head, c.name, v.text FROM char_values v "
            "JOIN characteristics c ON c.position_code=v.position_code AND c.char_code=v.char_code "
            "JOIN positions p ON p.code=v.position_code "
            "WHERE p.category IS NOT NULL AND p.active=1 AND v.value_kind='quality' AND v.text IS NOT NULL "
            "ORDER BY p.head, c.name, v.text").fetchall()
        return [(r[0] or "", r[1], r[2]) for r in rows]

    def catalog_summary(self) -> dict:
        m = self.meta
        return {
            "snapshot": m.get("snapshot"), "as_of": m.get("as_of"), "imported_at": m.get("imported_at"),
            "importer_version": m.get("importer_version"), "positions": m.get("positions"),
            "files_actual": m.get("files_actual"), "files_skipped": m.get("files_skipped"),
            "dropped_records": m.get("dropped_records"), "status_counts": m.get("status_counts"),
            "coverage": m.get("coverage"), "issues": m.get("issues"),
            "characteristics_scope": m.get("characteristics_scope"),
        }
