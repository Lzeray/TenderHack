"""Подстановка единицы измерения к числу без единицы (docs/UNITS_PLAN.md, шаги U1–U2).

Число без единицы у числового свойства — несколько гипотез «число + единица той же размерности, что у свойства
в КТРУ». Свидетельства:
1. единственная единица размерности в справочнике или единица в названии свойства («Крутящий момент (Нм)»);
2. единица соседних признаков того же описания (той же размерности) — множитель SIBLING_BOOST;
3. допустимость по КТРУ (уровень 1): гипотеза, при которой значение не подходит ни одной позиции, отбрасывается;
4. типичность по выгрузкам (уровень 2): доля моделей со значением в пределах ±10 % (dims._density);
5. запись числа: дробное меньше 10 — скорее крупная единица (1,8 м), от 1000 — мелкая (1800 мм); слабый множитель;
6. без выгрузок — единица, в которой КТРУ хранит значения свойства (слабый множитель).
Подстановка — если лучшая гипотеза правдоподобнее следующей не меньше чем в RATIO раз; иначе вопрос.
Числа пользователя не меняются («1,8» остаётся «1,8 м»). Единицы другой размерности не рассматриваются.
"""
from __future__ import annotations

from decimal import Decimal

from .dims import axis_of, context_of, share_satisfying
from .units import UNITS, lookup

VERSION = "1.0"
RATIO = 10.0
SIBLING_BOOST = 10.0
NOTATION_BOOST = 2.0
STORAGE_BOOST = 3.0
# единицы, которые подставляем; редкие в описаниях (дюйм, км, дм, т, мг, м³, кВ) — нет
CANDIDATES = {u.key for u in UNITS} - {"inch", "km", "dm", "t", "mg", "m3", "kv", "pcs", "mm2", "cm2"}
SMALL = {"mm", "cm", "g", "w", "ml", "mah"}       # мелкие единицы своей размерности
LARGE = {"m", "kg", "kw", "l", "ah"}


def _num(s: str | None) -> Decimal | None:
    try:
        return Decimal((s or "").replace(",", "."))
    except Exception:
        return None


def _props(positions, f):
    from .validate import find_prop
    return [p for p in (find_prop(pos, f) for pos in positions) if p is not None]


def hypotheses(f, positions, heads, stats, sibling_units: dict[str, str]):
    """[(score, unit_title, basis)] по убыванию; пустой список — подставлять нечего (не число, штуки, нет свойства)."""
    from .validate import check_feature, user_interval
    props = _props(positions, f)
    if not props or not all(p.is_numeric for p in props):
        return []
    dims = {u.dimension for p in props for u in p.units}
    if len(dims) != 1:
        return []
    dim = next(iter(dims))
    if dim == "count":
        return []
    name_units = {p.name_unit.key for p in props if p.name_unit}
    stored = {u.key for p in props for u in p.units}
    cands = [u for u in UNITS if u.dimension == dim and (u.key in CANDIDATES or u.key in stored)]
    if name_units:
        cands = [u for u in cands if u.key in name_units]
    values = [v for v in (_num(f.value), _num(f.value_to)) if v is not None]
    if not values or not cands:
        return []
    if len(cands) == 1:
        return [(1.0, cands[0].title, "единственная единица этой величины" if not name_units
                 else "единица указана в названии свойства КТРУ")]
    out = []
    for u in cands:
        probe = f.model_copy(update={"unit": u.title})
        if not any(check_feature(pos, probe)[0] == "valid" for pos in positions):
            continue
        score, basis = 1.0, []
        dens = None
        name = f.property_name or ""
        ax = None
        for pos in positions[:1]:
            ax = axis_of(name, context_of(pos.name_lemmas, [pos.head] if pos.head else []))
        U = user_interval(probe)
        dens = share_satisfying(stats, heads, name, ax or name, U, u.title) if U is not None else None
        if dens is not None:
            score *= dens
            basis.append("типичность по выгрузкам")
        elif u.key in stored:
            score *= STORAGE_BOOST
            basis.append("единица значений КТРУ")
        if sibling_units.get(dim) == u.key:
            score *= SIBLING_BOOST
            basis.append("единица соседних характеристик")
        v0 = values[0]
        if v0 != v0.to_integral_value() and v0 < 10 and u.key in LARGE:
            score *= NOTATION_BOOST
        if v0 >= 1000 and u.key in SMALL:
            score *= NOTATION_BOOST
        out.append((score, u.title, ", ".join(basis) or "допустимо по КТРУ"))
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def infer(features, positions, heads, stats):
    """Подставить единицы; вернуть вопрос по первому неоднозначному признаку или None."""
    from .models import Constraint, Question, QuestionOption
    sibling: dict[str, str] = {}
    for f in features:
        u = lookup(f.unit) if f.unit else None
        if f.status == "bound" and u is not None and f.source == "text":
            sibling.setdefault(u.dimension, u.key)
    question = None
    for f in features:
        if f.status != "bound" or f.unit or f.source != "text" or f.op in ("ne", "in") or _num(f.value) is None:
            continue
        hyp = hypotheses(f, positions, heads, stats, sibling)
        if not hyp:
            continue
        best = hyp[0]
        second = hyp[1][0] if len(hyp) > 1 else 0.0
        if second == 0.0 or best[0] >= RATIO * second:
            f.unit = best[1]
            f.unit_inferred = True
            f.note = (f.note + "; " if f.note else "") + f"единица подставлена: {best[1]} ({best[2]})"
            continue
        if question is None:
            shown = f.value + (f"–{f.value_to}" if f.value_to else "")
            opts = []
            for score, unit, basis in hyp[:4]:
                c = Constraint(property=f.property_code or f.property_name or "", op=f.op, value=f.value,
                               value_to=f.value_to, unit=unit, min_inclusive=f.min_inclusive,
                               max_inclusive=f.max_inclusive)
                opts.append(QuestionOption(label=f"{shown} {unit}", remaining=len(positions), answer=c, answers=[c]))
            question = Question(kind="property", property_code=f.property_code, property_name=f.property_name,
                                text=f"В каких единицах «{f.property_name}» = {shown}?", required=True,
                                worst_case_remaining=len(positions), current_remaining=len(positions),
                                options=opts, reason="число без единицы: подходят несколько единиц")
            f.note = (f.note + "; " if f.note else "") + "единица не указана — подходят несколько, нужен выбор"
    return question


__all__ = ["infer", "hypotheses", "VERSION"]
