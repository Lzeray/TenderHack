"""Проверка совместимости признаков с характеристиками кандидата.

Для каждого признака и каждого кандидата: valid (соответствие доказано),
invalid (есть противоречие), unknown (данных недостаточно). unknown ≠ valid.

Числа: значение пользователя — интервал U (точка, луч или отрезок). Допустимые значения
позиции — объединение интервалов A (смежные объединяются). U ⊆ A → valid; U ∩ A = ∅ → invalid;
иначе unknown. Для требования («не менее 600 Вт», intent=requirement) дополнительно valid,
если какое-то допустимое значение КТРУ целиком лежит в U: заказчик может выбрать его. Перевод единиц — только внутри одной размерности (units.convert), точный.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .catalog.repository import Interval, Position, Prop, merge_intervals
from .models import Feature, PropertyCheck
from .text import content_lemmas, norm, tokenize
from .units import lookup, fmt


def user_interval(f: Feature) -> Interval | None:
    try:
        v = Decimal((f.value or "").replace(",", "."))
    except InvalidOperation:
        return None
    if f.op == "eq":
        return Interval(v, True, v, True)
    if f.op == "ge":
        return Interval(v, True, None, False)
    if f.op == "gt":
        return Interval(v, False, None, False)
    if f.op == "le":
        return Interval(None, False, v, True)
    if f.op == "lt":
        return Interval(None, False, v, False)
    if f.op == "between":
        try:
            v2 = Decimal((f.value_to or "").replace(",", "."))
        except InvalidOperation:
            return None
        lo, hi = min(v, v2), max(v, v2)
        return Interval(lo, f.min_inclusive, hi, f.max_inclusive)
    return None


def describe_user(f: Feature) -> str:
    u = f" {f.unit}" if f.unit else ""
    ops = {"eq": "", "ne": "не ", "ge": "≥ ", "gt": "> ", "le": "≤ ", "lt": "< "}
    if f.op == "between":
        return f"{f.value}–{f.value_to}{u}"
    return f"{ops.get(f.op, '')}{f.value}{u}"


def find_prop(pos: Position, f: Feature) -> Prop | None:
    if f.property_code and f.property_code in pos.props:
        p = pos.props[f.property_code]
        if f.property_name is None or p.norm_name == " ".join(tokenize(f.property_name)):
            return p
    if f.property_name:
        key = " ".join(tokenize(f.property_name))
        for p in pos.props.values():
            if p.norm_name == key:
                return p
    return None


def check_numeric(prop: Prop, f: Feature, U: Interval) -> tuple[str, str]:
    uu = lookup(f.unit) if f.unit else None
    count_default = False
    if uu is None and any(v.unit is not None and v.unit.dimension == "count" for v in prop.values):
        # число без единицы у счётного свойства («2 аккумулятора») — это штуки; иные размерности не додумываются
        uu, count_default = lookup("шт"), True
    comparable: list[Interval] = []
    incompatible, no_unit = [], 0
    for v in prop.values:
        if v.interval is None:
            continue
        vu = v.unit
        if uu is not None and vu is not None:
            if uu.dimension != vu.dimension:
                incompatible.append(vu.title)
                continue
            comparable.append(v.interval.scaled(vu.factor / uu.factor))  # всё в единицах пользователя
        elif uu is None and vu is None:
            comparable.append(v.interval)
        else:
            no_unit += 1
    user_txt = describe_user(f)
    if not comparable:
        if incompatible and not no_unit:
            return "invalid", (f"несовместимая размерность: указано «{f.unit}», в КТРУ — "
                               f"«{', '.join(sorted(set(incompatible)))}»")
        if uu is None:
            return "unknown", "не указана единица измерения, а в КТРУ значения заданы в единицах"
        return "unknown", "в КТРУ у значения нет единицы измерения — сравнение невозможно"
    merged = merge_intervals(comparable)
    unit_t = uu.title if uu else None
    allowed_txt = "; ".join(i.label(unit_t) for i in comparable[:12]) + ("…" if len(comparable) > 12 else "")
    exact = [i for i in comparable if U.subset_of(i)]
    if f.intent == "requirement" and f.op in ("ge", "gt", "le", "lt", "between"):
        # требование к будущему товару выполнимо, если хотя бы одно допустимое значение КТРУ
        # целиком ему удовлетворяет (заказчик выберет это значение)
        sat = [i for i in comparable if i.subset_of(U)]
        if sat and not exact:
            return "valid", (f"требование {user_txt} выполнимо: допустимое значение «{sat[0].label(uu.title if uu else None)}»"
                             " целиком ему удовлетворяет")
    if exact:
        return "valid", f"{user_txt} входит в допустимое значение «{exact[0].label(unit_t)}»"
    if any(U.subset_of(m) for m in merged):
        return "valid", f"{user_txt} входит в объединение смежных допустимых значений: {allowed_txt}"
    if not any(U.intersects(m) for m in merged):
        if no_unit:
            return "unknown", f"{user_txt} вне сравнимых значений ({allowed_txt}); часть значений без единиц"
        return "invalid", f"{user_txt} вне допустимого: {allowed_txt}"
    return "unknown", f"{user_txt} частично пересекается с допустимым ({allowed_txt}) — нужно точное значение"


def _quality_match(prop: Prop, value: str) -> bool:
    n = norm(value).strip()
    lem = tuple(content_lemmas(value))
    for v in prop.values:
        if v.kind != "quality" or v.text is None:
            continue
        if norm(v.text).strip() == n or (lem and v.lemmas == lem):
            return True
    return False


def check_feature(pos: Position, f: Feature) -> tuple[str, str, Prop | None]:
    prop = find_prop(pos, f)
    if prop is None:
        if pos.no_new_features:
            return "unknown", ("свойства нет в позиции, а дополнительные характеристики запрещены "
                               "(noNewFeatures) — указать его в закупке нельзя"), None
        if pos.no_new_features is False:
            return "unknown", "свойства нет в позиции; дополнительная характеристика допускается", None
        return "unknown", "свойства нет в позиции; признак запрета доп. характеристик не задан", None
    allowed = [v.label for v in prop.values]
    U = user_interval(f) if f.op != "ne" else None
    quality_values = [v for v in prop.values if v.kind == "quality"]
    if U is not None and prop.is_numeric:
        st, why = check_numeric(prop, f, U)
        return st, why, prop
    if f.op == "ne":
        others = [v for v in quality_values if not _quality_match(Prop("", "", None, None, False, [v]), f.value or "")]
        if quality_values and not others:
            return "invalid", f"позиция допускает только «{', '.join(allowed)}», а указано «не {f.value}»", prop
        return "unknown", "отрицание не определяет значение однозначно", prop
    if quality_values:
        if _quality_match(prop, f.value or ""):
            return "valid", f"«{f.value}» есть среди допустимых", prop
        return "invalid", f"«{f.value}» нет среди допустимых: {', '.join(allowed[:12])}" + \
            ("…" if len(allowed) > 12 else ""), prop
    if U is None and prop.is_numeric:
        return "invalid", f"ожидается число, указано «{f.value}»", prop
    return "unknown", "у свойства нет допустимых значений в КТРУ", prop


@dataclass
class CandidateEval:
    checks: list[PropertyCheck] = field(default_factory=list)
    valid: int = 0
    unknown: int = 0
    invalid: int = 0
    blocking: list[str] = field(default_factory=list)
    invalid_reasons: list[str] = field(default_factory=list)
    explained_props: set[str] = field(default_factory=set)


def evaluate(pos: Position, features: list[Feature]) -> CandidateEval:
    ev = CandidateEval()
    active = [f for f in features if f.status == "bound"]
    covered: set[str] = set()
    for f in active:
        st, why, prop = check_feature(pos, f)
        name = prop.name if prop else (f.property_name or "")
        code = prop.code if prop else (f.property_code or "")
        if prop:
            covered.add(prop.code)
        ev.checks.append(PropertyCheck(
            property_code=code, property_name=name, required=bool(prop and prop.required),
            kind=prop.kind if prop else None, status=st, reason=why,
            allowed=[v.label for v in prop.values][:30] if prop else [],
            user_value=describe_user(f), feature_id=f.id))
        if st == "valid":
            ev.valid += 1
            ev.explained_props.add(code)
        elif st == "invalid":
            ev.invalid += 1
            ev.invalid_reasons.append(f"{name}: {why}")
        else:
            ev.unknown += 1
            if prop is not None:  # отсутствующее свойство — предупреждение, а не блокировка
                ev.blocking.append(f"{name}: {why}")
    for prop in pos.props.values():
        if prop.required and prop.code not in covered:
            ev.checks.append(PropertyCheck(
                property_code=prop.code, property_name=prop.name, required=True, kind=prop.kind,
                status="unknown", reason="обязательное свойство не заполнено",
                allowed=[v.label for v in prop.values][:30]))
            ev.blocking.append(f"{prop.name}: обязательное свойство не заполнено")
    return ev


__all__ = ["evaluate", "check_feature", "user_interval", "describe_user", "fmt"]
