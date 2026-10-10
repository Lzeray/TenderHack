"""Выбор уточняющего вопроса по реальным схемам оставшихся кандидатов.

Для каждого ещё не заданного свойства (и псевдосвойства «тип товара» — наименование позиции)
строятся варианты ответа из допустимых значений кандидатов. Для каждого варианта считается,
сколько кандидатов останется совместимыми (кандидат без этого свойства остаётся при любом
ответе; пересекающиеся допустимые значения учитываются — кандидат попадает во все варианты,
с которыми пересекается). Выбирается свойство с минимальным худшим случаем (max по вариантам).
При равенстве: обязательное свойство (тип считается обязательным и идёт первым), затем код.
Если ни одно свойство не сокращает множество — ручной выбор из списка кандидатов.
"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog.repository import AllowedValue, Interval, Position, Prop
from .catalog.scope import ref
from .models import Constraint, Question, QuestionOption
from .text import norm
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
                    seen[key] = _Opt(v.text, Constraint(property=name_key if strict_refs else p.code, op="eq", value=v.text), key)
            elif v.interval is not None:
                key = ("n", v.unit.key if v.unit else "", v.interval)
                if key not in seen:
                    seen[key] = _Opt(v.label, _interval_constraint(name_key if strict_refs else p.code, v.interval, v.unit), key)
    return list(seen.values()), sample


def _count(name_key: str, opt: _Opt, cands: list[Position], sample_values: dict, strict_refs: bool = False) -> int:
    n = 0
    av = sample_values[opt.key]
    for c in cands:
        p = next((p for p in c.props.values() if _property_key(p, strict_refs) == name_key), None)
        if p is None or _value_compatible(p, av):
            n += 1
    return n


def choose_question(cands: list[Position], constrained: set[str], type_fixed: bool,
                    required_unknown: list[Prop] | None = None, type_first: bool = False,
                    strict_refs: bool = False) -> Question | None:
    """type_first — сначала подтвердить тип (разговорное слово с несколькими трактовками)."""
    n = len(cands)
    best = None  # (worst, not_required, code_key, question)
    if not type_fixed:
        names: dict[str, int] = {}
        for c in cands:
            names[c.name] = names.get(c.name, 0) + 1
        if len(names) > 1:
            worst = max(names.values())
            opts = [QuestionOption(label=nm, remaining=cnt,
                                   answer=Constraint(property=TYPE_PROP, op="eq", value=nm))
                    for nm, cnt in sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))]
            q = Question(kind="type", text="Уточните тип товара (наименование позиции КТРУ)", required=True,
                          worst_case_remaining=worst, current_remaining=n, options=opts if strict_refs else opts[:MAX_OPTIONS],
                         reason=f"кандидаты относятся к {len(names)} разным наименованиям")
            best = (worst, 0, "", q)
            if type_first:
                return q
        elif len(names) == 1 and type_first:
            # единственное наименование, но описание его не подкрепляет — подтвердить тип до вопросов о свойствах
            nm = next(iter(names))
            return Question(kind="type", text=f"Ваш товар — «{nm}»? Если нет, уточните описание.", required=True,
                            worst_case_remaining=n, current_remaining=n,
                            options=[QuestionOption(label=nm, remaining=n,
                                                    answer=Constraint(property=TYPE_PROP, op="eq", value=nm))],
                            reason="в области одно наименование, но в описании есть только его главное слово")
    keys = sorted({_property_key(p, strict_refs) for c in cands for p in c.props.values()} - constrained)
    for key in keys:
        opts, sample = _options_for(key, cands, strict_refs)
        if not opts or sample is None:
            continue
        values = {}
        for c in cands:
            p = next((p for p in c.props.values() if _property_key(p, strict_refs) == key), None)
            if p is None:
                continue
            for v in p.values:
                k = ("q", norm(v.text or "")) if v.kind == "quality" else ("n", v.unit.key if v.unit else "", v.interval)
                values.setdefault(k, v)
        counts = [(o, _count(key, o, cands, values, strict_refs)) for o in opts]
        worst = max(cnt for _, cnt in counts)
        if worst >= n:
            continue
        required = any(p.required for c in cands for p in c.props.values() if _property_key(p, strict_refs) == key)
        code = key if strict_refs else sample.code
        cand_key = (worst, 0 if required else 1, "1" + code)
        if best is None or cand_key < best[:3]:
            unit = next((v.unit for v in sample.values if v.unit), None)
            q = Question(kind="property", property_code=code, property_name=sample.name,
                         text=_question_text(sample), required=required, worst_case_remaining=worst,
                         current_remaining=n, allows_number=sample.is_numeric,
                         unit=unit.title if unit else None,
                         options=[QuestionOption(label=o.label, remaining=cnt, answer=o.answer)
                                   for o, cnt in sorted(counts, key=lambda oc: (oc[1], oc[0].label))][:None if strict_refs else MAX_OPTIONS],
                         reason=f"в худшем случае останется {worst} из {n}")
            best = (*cand_key, q)
    if best is not None:
        return best[3]
    if n == 1 and required_unknown:
        p = sorted(required_unknown, key=lambda p: p.code)[0]
        opts, _ = _options_for(_property_key(p, strict_refs), cands, strict_refs)
        unit = next((v.unit for v in p.values if v.unit), None)
        return Question(kind="property", property_code=_property_key(p, strict_refs) if strict_refs else p.code, property_name=p.name, text=_question_text(p),
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
