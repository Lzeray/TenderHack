"""Уровень 3: сомнительные значения — вероятная ошибка единицы или лишний ноль, заглушка.

Работает после проверки по КТРУ (уровень 1) и не влияет на неё: только предлагает исправление,
которое пользователь принимает («Заменить» — новый ввод, заново проходящий уровень 1) или отклоняет.
Подробности и замеры — docs/LEVELS_PLAN.md.

Правило `scale` срабатывает, только если значение не подходит НИ ОДНОЙ позиции области, у которой
есть это свойство. Перебираются варианты:
* та же цифра в другой единице той же размерности («75 мм» → «75 см»);
* лишний или пропущенный ноль в той же единице (×10, ÷10).
Если по КТРУ подходит ровно один вариант — он предлагается; если несколько — перечисляются без готового
исправления; если ни одного — молчим (настоящее несоответствие, его объясняет уровень 1).

Правило `unit_missing`: число без единицы у свойства, значения которого заданы в единицах. Предлагаются
единицы, в которых число подходит хотя бы одной позиции.

Правило `placeholder`: ноль у положительной физической величины — вероятно, значение не заполнено.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .catalog.repository import Position
from .models import Feature, Suggestion
from .units import BY_KEY, UNITS, fmt, lookup
from .empirical import SteStats, assess
from .validate import check_feature, find_prop

VERSION = "1.1"   # 1.1 scale по выгрузкам СТЕ: КТРУ допускает, выгрузки — нет; выбор из нескольких вариантов КТРУ
# Единицы, которые не предлагаем как «перепутанные»: дюймы и километры в описаниях почти не встречаются
NOT_PROPOSED = {"inch", "km", "dm", "t", "m3", "kv", "mg"}
POSITIVE_DIMENSIONS = {"length", "area", "mass", "volume", "power", "voltage", "current", "charge", "torque",
                       "frequency", "rotation", "time", "flow"}
MAX_ALTERNATIVES = 4


def _num(s: str | None) -> Decimal | None:
    try:
        return Decimal((s or "").replace(",", "."))
    except InvalidOperation:
        return None


def _status_counts(f: Feature, positions: list[Position]) -> tuple[int, int, int]:
    """(позиций со свойством, valid, invalid) для признака по уровню 1."""
    have = ok = bad = 0
    for p in positions:
        if find_prop(p, f) is None:
            continue
        have += 1
        st, _, _ = check_feature(p, f)
        ok += st == "valid"
        bad += st == "invalid"
    return have, ok, bad


def _quantity(f: Feature) -> tuple:
    """Физическая величина признака в базовой единице (для склейки равнозначных вариантов)."""
    u = lookup(f.unit) if f.unit else None
    k = u.factor if u else Decimal(1)
    dim = u.dimension if u else None
    lo, hi = _num(f.value), _num(f.value_to) if f.value_to else None
    return dim, (lo * k).normalize() if lo is not None else None, (hi * k).normalize() if hi is not None else None


def _label(value: str, value_to: str | None, unit: str | None) -> str:
    v = value + (f"–{value_to}" if value_to else "")
    return f"{v} {unit}" if unit else v


def _variants(f: Feature) -> list[tuple[str, Feature, int]]:
    """(описание варианта, изменённый признак, предпочтение: 0 — другая единица, 1 — ×10/÷10)."""
    out = []
    unit = lookup(f.unit) if f.unit else None
    v, v2 = _num(f.value), _num(f.value_to) if f.value_to else None
    if v is None:
        return out
    if unit is not None:
        for u in UNITS:
            if u.dimension == unit.dimension and u.key != unit.key and u.key not in NOT_PROPOSED:
                g = f.model_copy(update={"unit": u.title})
                out.append((_label(f.value, f.value_to, u.title), g, 0))
    if unit is None or unit.dimension in POSITIVE_DIMENSIONS or unit.dimension == "count":
        for k in (Decimal(10), Decimal("0.1")):
            nv = fmt(v * k)
            nv2 = fmt(v2 * k) if v2 is not None else None
            g = f.model_copy(update={"value": nv, "value_to": nv2})
            out.append((_label(nv, nv2, f.unit), g, 1))
    return out


def _replacement(raw: str, f: Feature, new_value: str, new_value_to: str | None, new_unit: str | None
                 ) -> tuple[tuple[int, int], str] | None:
    """Где в исходном тексте заменить число (и единицу) и на что. None — не нашли однозначно."""
    if not f.raw_span:
        return None
    a, b = f.raw_span
    seg = raw[a:b]
    num = re.escape(f.value or "").replace(r"\.", "[.,]")
    pat = num + (r"\s*[-–]\s*" + re.escape(f.value_to).replace(r"\.", "[.,]") if f.value_to else "")
    unit = lookup(f.unit) if f.unit else None
    if unit is not None:
        aliases = sorted(unit.aliases + (unit.title,), key=len, reverse=True)
        pat += r"(\s*(?:" + "|".join(re.escape(x) for x in aliases) + r")\.?)?(?![а-яa-z])"
    hits = list(re.finditer(pat, seg, re.I))
    if len(hits) != 1:
        return None
    m = hits[0]
    text = new_value + (f"–{new_value_to}" if new_value_to else "") + (f" {new_unit}" if new_unit else "")
    return (a + m.start(), a + m.end()), text


def check(features: list[Feature], positions: list[Position], raw_text: str,
          dismissed: set[str] | frozenset[str] = frozenset(), heads: list[str] | None = None,
          stats: "SteStats | None" = None) -> list[Suggestion]:
    """stats/heads — статистика выгрузок (уровень 2); без неё правила работают только по КТРУ."""
    heads = heads or []
    out: list[Suggestion] = []
    for f in features:
        if f.status != "bound" or f.source != "text" or f.op == "ne" or _num(f.value) is None:
            continue
        unit = lookup(f.unit) if f.unit else None
        # placeholder: ноль у положительной физической величины
        if _num(f.value) == 0 and f.value_to is None and unit is not None and unit.dimension in POSITIVE_DIMENSIONS:
            sid = f"placeholder:{f.property_name}:{f.value}"
            if sid not in dismissed:
                out.append(Suggestion(
                    id=sid, rule="placeholder", feature_id=f.id, property_name=f.property_name or "",
                    original=_label(f.value, None, f.unit),
                    message=f"«{f.property_name}» = 0 {f.unit}: похоже, значение не заполнено. "
                            "Укажите настоящее значение или уберите характеристику.",
                    evidence={"source": "rule"}))
            continue
        have, ok, bad = _status_counts(f, positions)
        if have == 0:
            continue
        if f.unit is None:
            # unit_missing: у свойства значения в единицах, а в описании единицы нет
            if ok or bad:
                continue
            fits, tried = [], 0
            dims = {v.unit.dimension for p in positions for pr in [find_prop(p, f)] if pr
                    for v in pr.values if v.unit is not None}
            for u in UNITS:
                if u.dimension not in dims or u.key in NOT_PROPOSED:
                    continue
                tried += 1
                g = f.model_copy(update={"unit": u.title})
                _, gok, _ = _status_counts(g, positions)
                if gok:
                    fits.append((u.title, gok))
            # подсказка полезна, только если КТРУ различает единицы: подходят не все
            if not fits or len(fits) == tried:
                continue
            sid = f"unit_missing:{f.property_name}:{f.value}"
            if sid in dismissed:
                continue
            proposed = fits[0][0] if len(fits) == 1 else None
            rep = _replacement(raw_text, f, f.value, f.value_to, proposed) if proposed else None
            opts = ", ".join(f"{_label(f.value, f.value_to, u)} — подходит {n} поз." for u, n in fits[:MAX_ALTERNATIVES])
            out.append(Suggestion(
                id=sid, rule="unit_missing", feature_id=f.id, property_name=f.property_name or "",
                original=_label(f.value, f.value_to, None),
                proposed=_label(f.value, f.value_to, proposed) if proposed else None,
                alternatives=[_label(f.value, f.value_to, u) for u, _ in fits[:MAX_ALTERNATIVES]],
                replace_span=rep[0] if rep else None, replacement_text=rep[1] if rep else None,
                message=f"«{f.property_name}» = {f.value}: не указана единица измерения. В единицах КТРУ: {opts}.",
                evidence={"source": "ktru", "positions_with_property": have}))
            continue
        # scale: значение не подходит ни одной позиции со свойством (КТРУ) или по КТРУ допустимо, но не встречается
        # ни у одной модели в выгрузках (СТЕ, уровень 2)
        ktru_invalid = not ok and bad == have
        emp = assess(f, heads, stats) if stats is not None else None
        # счётные свойства по выгрузкам не правим: распределение зависит от подтипа («фреза дисковая, 40 зубьев»
        # — реальное значение, хотя у большинства фрез 2–6 зубьев)
        ste_unseen = emp is not None and emp.status == "unseen" and (unit is None or unit.dimension != "count")             and f.unit is not None
        if not ktru_invalid and not ste_unseen:
            continue
        fits = []
        for label, g, pref in _variants(f):
            _, gok, gbad = _status_counts(g, positions)
            if ktru_invalid and not gok:
                continue
            if not ktru_invalid and gbad == have:
                continue                  # вариант не должен противоречить всем позициям КТРУ
            ge = assess(g, heads, stats) if stats is not None else None
            typical = ge is not None and ge.status == "typical"
            if not ktru_invalid and not typical:
                continue
            fits.append((pref, label, g, gok, typical))
        if not fits:
            continue
        sid = f"scale:{f.property_name}:{_label(f.value, f.value_to, f.unit)}"
        if sid in dismissed:
            continue
        # варианты с одной физической величиной — одно объяснение («170 см» = «1700 мм»); показываем запись
        # с другой единицей. Исправление предлагаем, только если величина одна; если по КТРУ подходят
        # несколько, выгрузки выбирают единственную обычную.
        fits.sort(key=lambda x: (x[0], -x[3], x[1]))
        by_qty: dict = {}
        for x in fits:
            by_qty.setdefault(_quantity(x[2]), x)
        fits = list(by_qty.values())
        narrowed = [x for x in fits if x[4]]
        single = fits[0] if len(fits) == 1 else narrowed[0] if len(narrowed) == 1 else None
        source = "ste" if not ktru_invalid else "ktru+ste" if single is not None and len(fits) > 1 else "ktru"
        rep = None
        if single is not None:
            g = single[2]
            rep = _replacement(raw_text, f, g.value, g.value_to, g.unit)
        why = "та же цифра в другой единице" if single and single[0] == 0 else "возможно, лишний или пропущенный ноль"
        orig = _label(f.value, f.value_to, f.unit)
        if ktru_invalid:
            head = f"«{f.property_name}» = {orig} не подходит ни одной из {have} позиций КТРУ с этим свойством. "
        else:
            head = f"«{f.property_name}» = {orig} по КТРУ допустимо, но {emp.reason}. "
        if single is not None:
            tail = f"Возможно, имелось в виду {single[1]} ({why})"
            tail += f": подходит {single[3]} поз. КТРУ" if single[3] else ""
            tail += " и это обычное значение по выгрузкам." if single[4] else "."
        else:
            tail = "Подходят варианты: " + "; ".join(label for _, label, _, _, _ in fits[:MAX_ALTERNATIVES]) +                 ". Уточните значение."
        out.append(Suggestion(
            id=sid, rule="scale", feature_id=f.id, property_name=f.property_name or "",
            original=orig, proposed=single[1] if single else None,
            alternatives=[label for _, label, _, _, _ in fits[:MAX_ALTERNATIVES]],
            replace_span=rep[0] if rep else None, replacement_text=rep[1] if rep else None,
            message=head + tail, evidence={"source": source, "positions_with_property": have,
                                           "fits": {label: n for _, label, _, n, _ in fits[:MAX_ALTERNATIVES]},
                                           "ste": emp.evidence if emp is not None else {}}))
    return out


def relations(features: list[Feature], heads: list[str], stats, dismissed=frozenset()) -> list[Suggestion]:
    """Связи между названными характеристиками (docs/UNITS_PLAN.md, U4): если у ≥ 99 % моделей выгрузок
    «A ≤ B» (высота сиденья ≤ высоты, масса нетто ≤ брутто), а в описании A > B — предупреждение
    «возможно, перепутаны значения». Без исправления и без влияния на подбор."""
    from .catalog.ste_stats import prop_key
    if stats is None or not getattr(stats, "available", False):
        return []
    pts = {}
    for f in features:
        u = lookup(f.unit) if f.unit else None
        v = _num(f.value)
        # свойства КТРУ и названные в тексте, но отсутствующие в КТРУ («глубина сидения» у стула) — связи из выгрузок
        name = f.property_name if f.status == "bound" else f.named_property if f.status == "unknown_property" else None
        if name and f.op == "eq" and f.value_to is None and u is not None and v is not None:
            pts[prop_key(name)] = (f.model_copy(update={"property_name": name}), v * u.factor, u.dimension)
    if len(pts) < 2:
        return []
    out = []
    for tk in stats.type_keys(heads):
        for a, b, dim, n, holds in stats.pair_rules(tk):
            if a in pts and b in pts and pts[a][2] == dim == pts[b][2] and pts[a][1] > pts[b][1]:
                fa, fb = pts[a][0], pts[b][0]
                sid = f"relation:{a}:{b}"
                if sid in dismissed or any(s.id == sid for s in out):
                    continue
                pct = fmt(((1 - holds) * 100).quantize(Decimal("0.1"))) if holds < 1 else "0"
                out.append(Suggestion(
                    id=sid, rule="relation", feature_id=fa.id, property_name=fa.property_name or "",
                    original=f"{fa.property_name} {_label(fa.value, None, fa.unit)} > {fb.property_name} "
                             f"{_label(fb.value, None, fb.unit)}",
                    message=(f"«{fa.property_name}» ({_label(fa.value, None, fa.unit)}) больше, чем "
                             f"«{fb.property_name}» ({_label(fb.value, None, fb.unit)}). У таких товаров в выгрузках "
                             f"так бывает у {pct} % из {n} моделей — возможно, значения перепутаны."),
                    evidence={"source": "ste", "n_models": n, "holds": str(holds)}))
        if out:
            break
    return out


__all__ = ["check", "relations", "VERSION", "BY_KEY"]
