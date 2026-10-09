"""AssertionResolver: согласование признаков из разных источников.

Приоритет (план, п. 5.1):
1. ручные правки и ответы пользователя;
2. однозначный разбор правилами — его числа, единицы и операторы модель молча не меняет;
3. предложения моделей (A-semantic, B-llm) — только гипотезы: применяются в пересчёте
   со статусом «предложено» (confirmation=tentative) и не дают автоматического завершения
   без подтверждения пользователем.

Расхождение модели с правилами не скрывается: значение правил остаётся, расхождение
выносится в предупреждение и требует подтверждения. Отклонённые пользователем
предложения (`SearchRequest.rejected`) не применяются повторно.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .models import Feature, Issue
from .text import norm, tokenize
from .units import lookup


@dataclass
class Disagreement:
    key: str
    rule_feature: Feature
    model_feature: Feature
    message: str


@dataclass
class MergeResult:
    features: list[Feature]
    disagreements: list[Disagreement] = field(default_factory=list)
    rejected: list[tuple[Feature, str]] = field(default_factory=list)


def _group_key(name: str | None) -> str:
    return " ".join(tokenize(name or ""))


def _num(v: str | None, unit: str | None) -> Decimal | None:
    try:
        x = Decimal((v or "").replace(",", "."))
    except InvalidOperation:
        return None
    u = lookup(unit) if unit else None
    return x * u.factor if u else x


def same_value(a: Feature, b: Feature) -> bool:
    if a.op != b.op:
        return False
    ua, ub = lookup(a.unit) if a.unit else None, lookup(b.unit) if b.unit else None
    if (ua is None) != (ub is None) or (ua and ub and ua.dimension != ub.dimension):
        return norm(a.value or "") == norm(b.value or "") and a.unit == b.unit
    na, nb = _num(a.value, a.unit), _num(b.value, b.unit)
    if na is not None and nb is not None:
        if _num(a.value_to, a.unit) != _num(b.value_to, b.unit):
            return False
        return na == nb
    return norm(a.value or "").strip() == norm(b.value or "").strip()


def describe(f: Feature) -> str:
    ops = {"eq": "", "ne": "не ", "ge": "≥ ", "gt": "> ", "le": "≤ ", "lt": "< "}
    v = f"{f.value}–{f.value_to}" if f.op == "between" else f"{ops.get(f.op, '')}{f.value}"
    return f"{f.property_name} = {v}{' ' + f.unit if f.unit else ''}"


def merge_model_features(features: list[Feature], model: list[Feature], group_names: dict[str, str],
                         rejected: set[str], issues: list[Issue]) -> MergeResult:
    """features — признаки правил и пользователя; model — признаки моделей с property_code из области.

    group_names: код свойства → нормализованное название группы области (для сравнения).
    """
    res = MergeResult(list(features))
    for mf in model:
        if mf.proposal_key and mf.proposal_key in rejected:
            res.rejected.append((mf, "отклонено пользователем"))
            continue
        gkey = group_names.get(mf.property_code or "") or _group_key(mf.property_name)
        if gkey not in group_names.values():
            res.rejected.append((mf, "свойства нет у позиций области"))
            continue
        same_group = [f for f in res.features if f.property_name and _group_key(f.property_name) == gkey
                      and f.source != "model"]
        manual = [f for f in same_group if f.source in ("override", "answer") and f.status == "bound"]
        rule = [f for f in same_group if f.source == "text" and f.status == "bound"]
        if manual:
            if any(same_value(f, mf) for f in manual):
                for f in manual:
                    if same_value(f, mf) and mf.origin not in f.supported_by:
                        f.supported_by.append(mf.origin)
            else:
                res.rejected.append((mf, "ручное значение пользователя имеет приоритет"))
            continue
        if rule:
            agree = [f for f in rule if same_value(f, mf)]
            if agree:
                for f in agree:
                    if mf.origin not in f.supported_by:
                        f.supported_by.append(mf.origin)
                continue
            r = rule[0]
            msg = (f"Разбор правилами: {describe(r)} («{r.evidence}»); модель ({mf.origin}) предлагает: "
                   f"{describe(mf)} («{mf.evidence}»). Оставлено значение правил — подтвердите или замените.")
            issues.append(Issue(level="warning", code="model_disagreement", message=msg))
            res.disagreements.append(Disagreement(f"disagree:{mf.proposal_key}", r, mf, msg))
            continue
        # неоднозначный признак правил, который модель предлагает разрешить
        for f in res.features:
            if f.status == "ambiguous" and f.source == "text" and any(
                    _group_key(o.get("property_name")) == gkey for o in f.options):
                if mf.evidence and f.evidence and (mf.evidence in f.evidence or f.evidence in mf.evidence):
                    f.status = "overridden"
                    f.note += f"; трактовку предложила модель ({mf.origin}) — требуется подтверждение"
        mf.status = "bound"
        mf.confirmation = "tentative"
        res.features.append(mf)
    return res
