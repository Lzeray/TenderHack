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
from .models import Feature, Issue, PropertyCheck
from .dims import axis_of, context_of
from .text import content_lemmas, norm, tokenize
from .units import lookup, fmt


def user_interval(f: Feature) -> Interval | None:
    try:
        v = Decimal((f.value or "").replace(",", "."))
    except InvalidOperation:
        return None
    if not v.is_finite():
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
        if not v2.is_finite() or v > v2:
            return None
        lo, hi = min(v, v2), max(v, v2)
        return Interval(lo, f.min_inclusive, hi, f.max_inclusive)
    return None


def describe_user(f: Feature) -> str:
    if f.op == "in":
        return "один из: " + ", ".join(f.values)
    u = f" {f.unit}" if f.unit else ""
    ops = {"eq": "", "ne": "не ", "ge": "≥ ", "gt": "> ", "le": "≤ ", "lt": "< "}
    if f.op == "between":
        return f"{f.value}–{f.value_to}{u}"
    return f"{ops.get(f.op, '')}{f.value}{u}"


def find_prop(pos: Position, f: Feature) -> Prop | None:
    if f.strict_ref:
        p = pos.props.get(f.property_code or "")
        return p if p and (f.property_name is None or p.name == f.property_name) else None
    if f.property_code and f.property_code in pos.props:
        p = pos.props[f.property_code]
        if f.property_name is None or p.norm_name == " ".join(tokenize(f.property_name)):
            return p
    if f.property_name:
        key = " ".join(tokenize(f.property_name))
        for p in pos.props.values():
            if p.norm_name == key:
                return p
        # одна ось — разные названия у позиций одного типа («Высота шкафа» / «Высота»): единственное числовое
        # свойство той же общей оси (docs/DIMENSIONS_PLAN.md, D3)
        ctx = context_of(pos.name_lemmas, [pos.head] if pos.head else [])
        ax = axis_of(f.property_name, ctx)
        if ax is not None:
            same = [p for p in pos.props.values() if p.is_numeric and axis_of(p.name, ctx) == ax]
            if len(same) == 1:
                return same[0]
    return None


def conflicting_conditions(features: list[Feature], positions: list[Position], text: str = "") -> list[Issue]:
    """Check the request itself, even if some catalogue positions lack the property.

    Different parts and explicit alternatives are not treated as contradictions.
    A categorical clash is an ambiguity to clarify, not proof a combined material is impossible.
    """
    import re
    active = [f for f in features if f.status == "bound" and f.confirmation == "confirmed"
              and f.intent != "preference" and f.property_name and f.value is not None]
    issues, seen = [], set()
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            key = (norm(a.property_name), a.component)
            if key != (norm(b.property_name), b.component) or key in seen:
                continue
            if a.raw_span and b.raw_span:
                left, right = sorted([a.raw_span, b.raw_span])
                between = text[left[1]:right[0]]
                if re.search(r"\bили\b|/", between, re.I):
                    continue
            ia, ib = user_interval(a), user_interval(b)
            ua, ub = lookup(a.unit or ""), lookup(b.unit or "")
            clash = False
            if ia is not None and ib is not None:
                if ua and ub and ua.dimension == ub.dimension:
                    clash = not ia.intersects(ib.scaled(ub.factor / ua.factor))
                elif not a.unit and not b.unit:
                    clash = not ia.intersects(ib)
            elif a.op == b.op == "eq" and norm(a.value) != norm(b.value):
                props = [p for pos in positions for p in pos.props.values() if p.name == a.property_name]
                # Frame/material/type describe the same part here; colour can legitimately be mixed.
                clash = any(p.is_boolean for p in props) or any(w in norm(a.property_name) for w in ("тип", "материал"))
            if clash:
                seen.add(key)
                av, bv = describe_user(a), describe_user(b)
                message = (f"Для характеристики «{a.property_name}» указаны разные значения: «{av}» и «{bv}». "
                           "Оставьте один вариант или уточните, к каким частям товара относится каждый.")
                issues.append(Issue(level="error", code="conflicting_conditions", message=message))
    return issues


WIDER_MARK = "значение КТРУ шире запроса"


def _num(s: str | None) -> Decimal | None:
    try:
        return Decimal((s or "").replace(",", ".").strip())
    except InvalidOperation:
        return None


def numeric_steps(comparable: list[Interval], U: Interval) -> tuple[list[Interval], list[Interval]]:
    """Ступени КТРУ для диапазона пользователя: (целиком внутри, пересекаются частично).
    Касание одной граничной точкой не считается пересечением."""
    full = [i for i in comparable if i.subset_of(U) and (i.is_point or U.overlaps_more_than_point(i))]
    part = [i for i in comparable if i not in full and not i.is_point and U.overlaps_more_than_point(i)]
    return full, part


def _steps_txt(items: list[Interval], unit: str | None, limit: int = 4) -> str:
    out = ", ".join(f"«{i.label(unit)}»" for i in items[:limit])
    return out + (f" и ещё {len(items) - limit}" if len(items) > limit else "")


def check_numeric(prop: Prop, f: Feature, U: Interval) -> tuple[str, str]:
    uu = lookup(f.unit) if f.unit else None
    if f.unit and uu is None:
        return "unknown", "единица измерения не распознана; выберите её вручную"
    count_default = False
    if uu is None and not f.strict_ref and any(v.unit is not None and v.unit.dimension == "count" for v in prop.values):
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
    if not U.is_point:
        # Диапазон («от 180 до 250 мм», «не менее 140 см», «около 140» = ±5 %) против ступеней КТРУ
        # (docs/DIMENSIONS_PLAN.md): подходят все ступени, пересекающиеся с диапазоном больше чем в одной точке.
        # Ступень целиком внутри диапазона — «подходит»; если таких нет, а есть пересекающиеся частично — позиция
        # совместима, но значение КТРУ шире запроса (пометка). Касание только границей не считается.
        full, part = numeric_steps(comparable, U)
        if full:
            return "valid", (f"{user_txt}: подходит {_steps_txt(full, unit_t)}"
                             + (f"; частично — {_steps_txt(part, unit_t)}" if part else ""))
        if part:
            return "valid", (f"{user_txt}: {WIDER_MARK} — {_steps_txt(part, unit_t)} "
                             "(включает значения вне диапазона)")
        if any(U.intersects(i) for i in comparable):
            return "unknown", f"{user_txt} совпадает с допустимым ({allowed_txt}) только граничной точкой"
    if exact:
        return "valid", f"{user_txt} входит в допустимое значение «{exact[0].label(unit_t)}»"
    if any(U.subset_of(m) for m in merged):
        return "valid", f"{user_txt} входит в объединение смежных допустимых значений: {allowed_txt}"
    if not any(U.intersects(m) for m in merged):
        if no_unit:
            return "unknown", f"{user_txt} вне сравнимых значений ({allowed_txt}); часть значений без единиц"
        return "invalid", f"{user_txt} вне допустимого: {allowed_txt}"
    return "unknown", f"{user_txt} частично пересекается с допустимым ({allowed_txt}) — нужно точное значение"


def _quality_match(prop: Prop, value: str, strict: bool = False) -> bool:
    n = norm(value).strip()
    if any(v.kind == "quality" and norm(v.text or "").strip() == n for v in prop.values):
        return True
    if strict:
        return False
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
    if f.op == "in":
        if not f.values:
            return "unknown", "не указан набор значений", prop
        statuses = [check_feature(pos, f.model_copy(update={"op": "eq", "value": v}))[0] for v in f.values]
        if all(s == "valid" for s in statuses):
            return "valid", "весь подтверждённый набор значений допустим", prop
        if all(s == "invalid" for s in statuses):
            return "invalid", "ни одно значение подтверждённого набора не допустимо", prop
        return "unknown", "набор значений соответствует лишь частично; уточните выбор", prop
    U = user_interval(f) if f.op != "ne" else None
    quality_values = [v for v in prop.values if v.kind == "quality"]
    if U is not None and prop.is_numeric:
        st, why = check_numeric(prop, f, U)
        return st, why, prop
    if U is not None and not U.is_point and quality_values and not prop.is_boolean:
        # дискретное свойство с числовыми значениями («Российский размер»: 44, 46 …): диапазон «48-50»
        # подходит, если хотя бы одно значение позиции внутри него (docs/DIMENSIONS_PLAN.md, D5)
        nums = [(v.text, _num(v.text)) for v in quality_values]
        if all(x is not None for _, x in nums):
            inside = [t for t, x in nums if U.contains_point(x)]
            if inside:
                return "valid", f"{describe_user(f)}: подходят значения КТРУ {', '.join(inside[:8])}", prop
            return "invalid", f"{describe_user(f)}: среди допустимых ({', '.join(allowed[:12])}) нет значений в диапазоне", prop
    if f.op == "ne":
        others = [v for v in quality_values if not _quality_match(Prop("", "", None, None, False, [v]), f.value or "", f.strict_ref)]
        if quality_values and not others:
            return "invalid", f"позиция допускает только «{', '.join(allowed)}», а указано «не {f.value}»", prop
        return "unknown", "отрицание не определяет значение однозначно", prop
    if quality_values:
        if _quality_match(prop, f.value or "", f.strict_ref):
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
    for f in features:
        if f.strict_ref and f.confirmation == "tentative" and f.status in ("bound", "proposed", "unknown_property"):
            prop = find_prop(pos, f)
            ev.checks.append(PropertyCheck(property_code=f.property_code or "", property_name=f.property_name or "Не привязано",
                required=bool(prop and prop.required), kind=prop.kind if prop else None, status="unknown",
                reason="модельная трактовка не подтверждена; не используется для исключения", feature_id=f.id,
                unknown_reason="unconfirmed",
                user_value=describe_user(f)))
            ev.unknown += 1
    active = [f for f in features if f.status == "bound" and not (f.strict_ref and f.confirmation == "tentative")]
    for i, f in enumerate(active):
        if not f.strict_ref:
            continue
        a = user_interval(f)
        for other in active[i + 1:]:
            if (f.property_code, f.property_name) != (other.property_code, other.property_name):
                continue
            b = user_interval(other)
            ua, ub = lookup(f.unit or ""), lookup(other.unit or "")
            if a is not None and b is not None and ua and ub and ua.dimension == ub.dimension:
                if not a.intersects(b.scaled(ub.factor / ua.factor)):
                    ev.invalid += 1
                    ev.invalid_reasons.append(f"{f.property_name}: противоречивые ограничения пользователя")
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
            unknown_reason=None if st != "unknown" else "property_absent" if prop is None else "not_comparable",
            wider=st == "valid" and WIDER_MARK in why,
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
            if prop is not None or f.strict_ref:
                ev.blocking.append(f"{name}: {why}")
    ambiguous = [f for f in features if f.status == "ambiguous"]
    for prop in pos.props.values():
        if prop.required and prop.code not in covered:
            # слово из описания подходит к нескольким свойствам области, и одно из них — это: не «не указано»
            amb = next((f for f in ambiguous if any(prop.code in o.get("codes", [o.get("property_code")])
                                                    for o in f.options)), None)
            if amb is not None:
                names = sorted({o["property_name"] for o in amb.options if o.get("property_name")})
                reason = (f"в описании есть «{amb.evidence or amb.value}», но это слово подходит к нескольким "
                          f"свойствам ({', '.join(names)}) — подтвердите привязку")
            else:
                reason = "обязательное свойство не заполнено"
            ev.checks.append(PropertyCheck(
                property_code=prop.code, property_name=prop.name, required=True, kind=prop.kind,
                status="unknown", reason=reason, unknown_reason="ambiguous" if amb is not None else "not_specified",
                user_value=(amb.evidence or amb.value) if amb is not None else None,
                allowed=[v.label for v in prop.values][:30]))
            ev.blocking.append(f"{prop.name}: обязательное свойство не заполнено")
    return ev


__all__ = ["evaluate", "check_feature", "user_interval", "describe_user", "fmt"]
