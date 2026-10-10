"""Выбор уточняющего вопроса по реальным схемам оставшихся кандидатов.

С версии 2.0 вопросов не больше двух; вопрос выбирается полным перебором двух ступеней так, чтобы позиция
определилась с наибольшей вероятностью (ktru_assist/qplan.py, docs/QUESTIONS_PLAN.md); наименование позиции — такой же
кандидат в вопросы, как характеристика. Ниже — прежнее описание вариантов ответа, оно в силе.

Для каждого ещё не заданного свойства (и псевдосвойства «тип товара» — наименование позиции)
строятся варианты ответа из допустимых значений кандидатов. Для каждого варианта считается,
сколько кандидатов останется совместимыми (кандидат без этого свойства остаётся при любом
ответе; пересекающиеся допустимые значения учитываются — кандидат попадает во все варианты,
с которыми пересекается). Сначала спрашиваются характеристики, которые есть у всех оставшихся позиций (у карточек КТРУ одного товара
наборы характеристик бывают разными): пока общие, сужающие список, не кончились, частные не спрашиваются.
Внутри группы: обязательное свойство (тип считается обязательным и общим), затем минимальный худший случаем
(max по вариантам), затем код.
Если ни одно свойство не сокращает множество — ручной выбор из списка кандидатов.
"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog.repository import AllowedValue, Interval, Position, Prop
from .catalog.scope import ref
from .models import Constraint, Question, QuestionOption
from .text import content_lemmas, norm
from .units import Unit

TYPE_PROP = "__type__"
MAX_OPTIONS = 60


def _property_key(p, strict_refs):
    return ref("characteristic", p.code, p.name) if strict_refs else p.norm_name


@dataclass
class _Opt:
    label: str
    answer: Constraint
    key: tuple


def _interval_constraint(code: str, iv: Interval, unit: Unit | None) -> Constraint:
    u = unit.title if unit else None
    from .units import fmt
    if iv.lo is not None and iv.hi is not None and iv.lo == iv.hi:
        return Constraint(property=code, op="eq", value=fmt(iv.lo).replace(",", "."), unit=u)
    if iv.lo is not None and iv.hi is not None:
        return Constraint(property=code, op="between", value=fmt(iv.lo).replace(",", "."),
                          value_to=fmt(iv.hi).replace(",", "."), min_inclusive=iv.lo_incl,
                          max_inclusive=iv.hi_incl, unit=u)
    if iv.lo is not None:
        return Constraint(property=code, op="ge" if iv.lo_incl else "gt", value=fmt(iv.lo).replace(",", "."),
                          unit=u)
    return Constraint(property=code, op="le" if iv.hi_incl else "lt", value=fmt(iv.hi).replace(",", "."), unit=u)


def _value_compatible(prop: Prop, opt_value: AllowedValue) -> bool:
    if opt_value.kind == "quality":
        n = norm(opt_value.text or "")
        return any(v.kind == "quality" and norm(v.text or "") == n for v in prop.values)
    iv = opt_value.interval
    for v in prop.values:
        if v.interval is None:
            continue
        a, b = v.unit, opt_value.unit
        if (a is None) != (b is None):
            continue
        if a is not None and b is not None:
            if a.dimension != b.dimension:
                continue
            cand_iv = v.interval.scaled(a.factor / b.factor)
        else:
            cand_iv = v.interval
        if cand_iv.intersects(iv):
            return True
    return False


def _options_for(name_key: str, cands: list[Position], strict_refs: bool = False) -> tuple[list[_Opt], Prop | None]:
    seen: dict[tuple, _Opt] = {}
    sample: Prop | None = None
    for c in cands:
        p = next((p for p in c.props.values() if _property_key(p, strict_refs) == name_key), None)
        if p is None:
            continue
        sample = sample or p
        for v in p.values:
            if v.kind == "quality" and v.text:
                key = ("q", norm(v.text))
                if key not in seen:
                    # ответ несёт ключ-название характеристики, а не код: у позиций разных наименований одна
                    # характеристика бывает под разными кодами, и после вопроса о наименовании ответ терялся
                    seen[key] = _Opt(v.text, Constraint(property=name_key, op="eq", value=v.text), key)
            elif v.interval is not None:
                key = ("n", v.unit.key if v.unit else "", v.interval)
                if key not in seen:
                    seen[key] = _Opt(v.label, _interval_constraint(name_key, v.interval, v.unit), key)
    return list(seen.values()), sample


def _count(name_key: str, opt: _Opt, cands: list[Position], sample_values: dict, strict_refs: bool = False) -> int:
    n = 0
    av = sample_values[opt.key]
    for c in cands:
        p = next((p for p in c.props.values() if _property_key(p, strict_refs) == name_key), None)
        if p is None or _value_compatible(p, av):
            n += 1
    return n


def _value_key(v: AllowedValue):
    return ("q", norm(v.text or "")) if v.kind == "quality" else ("n", v.unit.key if v.unit else "", v.interval)


def build_plans(cands: list[Position], constrained: set[str], with_type: bool, strict_refs: bool = False,
                weights=None) -> tuple[list, dict]:
    """Кандидаты в вопросы для планировщика (ktru_assist/qplan.py): наименование (with_type) и все не заданные
    характеристики. Ветка ответа — как в ядре: позиция без характеристики остаётся для чисел и «Да/Нет», а для
    текстового значения — если оно есть у неё в другой характеристике (engine._value_support)."""
    from .qplan import BETA, Q
    names = {c.name for c in cands}
    # кандидаты в вопросы: наименование (если не задано) и все не заданные характеристики
    plans: list[Q] = []
    built: dict[str, tuple] = {}
    if with_type:
        plans.append(Q(key=TYPE_PROP, members={nm: frozenset(c.code for c in cands if c.name == nm) for nm in sorted(names)},
                       own={c.code: frozenset({c.name}) for c in cands}, required=True, tie=(1,)))
    keys = sorted({_property_key(p, strict_refs) for c in cands for p in c.props.values()} - constrained)
    for key in keys:
        opts, sample = _options_for(key, cands, strict_refs)
        if not opts or sample is None:
            continue
        values, own, members = {}, {}, {}
        props = {c.code: next((p for p in c.props.values() if _property_key(p, strict_refs) == key), None)
                 for c in cands}
        for c in cands:
            p = props[c.code]
            if p is None:
                continue
            own[c.code] = frozenset(_value_key(v) for v in p.values if v.kind == "quality" or v.interval is not None)
            for v in p.values:
                values.setdefault(_value_key(v), v)
        for o in opts:
            v = values[o.key]
            # как в ядре (engine._value_support): текстовое значение, которого у позиции без этой характеристики нет
            # ни в одной другой, её исключает; числа и «Да/Нет» позицию без характеристики не исключают
            lem = set(content_lemmas(v.text or "")) if v.kind == "quality" and norm(v.text or "") not in ("да", "нет")                 else None
            members[o.key] = frozenset(
                c.code for c in cands
                if (props[c.code] is not None and _value_compatible(props[c.code], v))
                or (props[c.code] is None and (not lem or any(
                    x.kind == "quality" and x.lemmas and lem <= set(x.lemmas) for pr in c.props.values() for x in pr.values))))
        weight = {}
        if weights is not None:
            for o in opts:
                share = weights(sample.name, o.label)
                weight[o.key] = 1.0 + BETA * share if share else 1.0
        required = any(p is not None and p.required for p in props.values())
        code = key if strict_refs else sample.code
        plans.append(Q(key=key, members=members, own=own, weight=weight, required=required, tie=(0, len(opts), code)))
        built[key] = (opts, sample, members, code, required)
    return plans, built


def choose_question(cands: list[Position], constrained: set[str], type_fixed: bool,
                    required_unknown: list[Prop] | None = None, type_first: bool = False,
                    strict_refs: bool = False, weights=None, budget: int = 2) -> Question | None:
    """Вопрос с минимальным ожидаемым числом вопросов до конечного кода (ktru_assist/qplan.py).

    type_first — сначала подтвердить тип (разговорное слово с несколькими трактовками).
    budget — сколько вопросов ещё можно задать (всего два; дальше — список характеристик, которые осталось заполнить).
    weights(имя характеристики, вариант) → доля варианта в выгрузках СТЕ (0…1) или None — слабая поправка
    к вероятностям ответов."""
    from .qplan import Planner
    n = len(cands)
    if budget <= 0:
        return None
    codes = frozenset(c.code for c in cands)
    names: dict[str, int] = {}
    for c in cands:
        names[c.name] = names.get(c.name, 0) + 1
    type_q = None
    if not type_fixed:
        if len(names) > 1:
            worst = max(names.values())
            opts = [QuestionOption(label=nm, remaining=cnt,
                                   answer=Constraint(property=TYPE_PROP, op="eq", value=nm))
                    for nm, cnt in sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))]
            type_q = Question(kind="type", text="Уточните тип товара (наименование позиции КТРУ)", required=True,
                              worst_case_remaining=worst, current_remaining=n,
                              options=opts if strict_refs else opts[:MAX_OPTIONS],
                              reason=f"кандидаты относятся к {len(names)} разным наименованиям")
            if type_first:
                return type_q
        elif len(names) == 1 and type_first:
            # единственное наименование, но описание его не подкрепляет — подтвердить тип до вопросов о свойствах
            nm = next(iter(names))
            return Question(kind="type", text=f"Ваш товар — «{nm}»? Если нет, уточните описание.", required=True,
                            worst_case_remaining=n, current_remaining=n,
                            options=[QuestionOption(label=nm, remaining=n,
                                                    answer=Constraint(property=TYPE_PROP, op="eq", value=nm))],
                            reason="в области одно наименование, но в описании есть только его главное слово")
    plans, built = build_plans(cands, constrained, type_q is not None, strict_refs, weights)
    best, value, _ = Planner(plans, codes).choose(codes, budget)
    explain = (f"после {budget} вопр. позиция определится с вероятностью {value[0]:.0%}"
               if value is not None else "")
    if best is not None and best.key == TYPE_PROP:
        type_q.reason += "; " + explain
        return type_q
    if best is not None:
        opts, sample, members, code, required = built[best.key]
        counts = [(o, len(members[o.key])) for o in opts]
        worst = max(cnt for _, cnt in counts)
        unit = next((v.unit for v in sample.values if v.unit), None)
        weight = best.weight
        # варианты: все значения КТРУ оставшихся позиций; сначала частые в выгрузках, затем сильнее сужающие
        ordered = sorted(counts, key=lambda oc: (-weight.get(oc[0].key, 1.0), oc[1], oc[0].label))
        return Question(kind="property", property_code=code, property_name=sample.name,
                        text=_question_text(sample), required=required, worst_case_remaining=worst,
                        current_remaining=n, allows_number=sample.is_numeric,
                        unit=unit.title if unit else None,
                        options=[QuestionOption(label=o.label, remaining=cnt, answer=o.answer)
                                 for o, cnt in ordered][:None if strict_refs else MAX_OPTIONS],
                        reason=f"{explain}; в худшем случае останется {worst} из {n}")
    if n == 1 and required_unknown:
        p = sorted(required_unknown, key=lambda p: p.code)[0]
        opts, _ = _options_for(_property_key(p, strict_refs), cands, strict_refs)
        unit = next((v.unit for v in p.values if v.unit), None)
        return Question(kind="property", property_code=_property_key(p, strict_refs) if strict_refs else p.code,
                        property_name=p.name, text=_question_text(p),
                        required=True, worst_case_remaining=1, current_remaining=1,
                        allows_number=p.is_numeric, unit=unit.title if unit else None,
                        options=[QuestionOption(label=o.label, remaining=1, answer=o.answer)
                                 for o in sorted(opts, key=lambda o: o.label)][:None if strict_refs else MAX_OPTIONS],
                        reason="позиция определена, но обязательное свойство не заполнено")
    if n > 1:
        return Question(kind="manual_choice", text="Доступные свойства не различают оставшиеся позиции — "
                        "выберите позицию вручную или уточните тип товара", worst_case_remaining=n,
                        current_remaining=n,
                        options=[QuestionOption(label=f"{c.code} — {c.name}", remaining=1,
                                                answer=Constraint(property=TYPE_PROP, op="eq", value=c.code))
                                 for c in sorted(cands, key=lambda c: c.code)][:None if strict_refs else MAX_OPTIONS],
                        reason="ни одно свойство не сокращает множество кандидатов")
    return None


def _question_text(p: Prop) -> str:
    if p.is_boolean:
        return f"{p.name}?"
    if p.is_numeric:
        return f"Укажите значение «{p.name}»"
    return f"Какое значение «{p.name}»?"
