"""Проверка правдоподобия значений (отдельно от проверки по КТРУ).

Правило не исключает позиции и не исправляет значение («45 м» не превращается в «45 см»).
Срабатывание даёт предупреждение; если подозрительное значение участвует в подборе,
автоматическое завершение блокируется до подтверждения пользователем (ключ предупреждения
передаётся в `SearchRequest.confirmed`). Диапазоны одного направления не переносятся на другое:
у правила есть область `scope`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from .config import ROOT
from .models import Feature
from .text import content_lemmas, lemma
from .units import Unit, fmt, lookup


@dataclass(frozen=True)
class Rule:
    id: str
    scope: tuple[str, ...]
    cores: tuple[str, ...]
    unit: Unit | None
    max: Decimal | None
    min: Decimal | None
    min_inclusive: bool
    severity: str
    status: str
    basis: str


@dataclass
class Finding:
    key: str
    rule: Rule
    feature_id: str
    message: str


@lru_cache(maxsize=1)
def load_rules() -> tuple[str, tuple[Rule, ...]]:
    raw = json.loads((ROOT / "data" / "plausibility_rules.json").read_text(encoding="utf-8"))
    rules = []
    for r in raw["rules"]:
        # ядра сравниваются через ту же нормализацию слов, что и названия свойств (лемма или основа)
        rules.append(Rule(r["id"], tuple(r["scope"]), tuple(lemma(w) for w in r["property_core"]),
                          lookup(r["unit"]) if r.get("unit") else None,
                          Decimal(r["max"]) if "max" in r else None, Decimal(r["min"]) if "min" in r else None,
                          bool(r.get("min_inclusive", False)), r["severity"], r["status"], r["basis"]))
    return raw["version"], tuple(rules)


def _value(f: Feature) -> list[Decimal]:
    out = []
    for v in (f.value, f.value_to):
        if v is None:
            continue
        try:
            out.append(Decimal(v.replace(",", ".")))
        except InvalidOperation:
            pass
    return out


def check(features: list[Feature], categories: set[str]) -> list[Finding]:
    _, rules = load_rules()
    out: list[Finding] = []
    for f in features:
        if f.status != "bound" or not f.property_name or f.op == "ne":
            continue
        vals = _value(f)
        if not vals:
            continue
        lems = set(content_lemmas(f.property_name))
        fu = lookup(f.unit) if f.unit else None
        for r in rules:
            if not (set(r.scope) & categories) or not (lems & set(r.cores)):
                continue
            if r.unit is not None:
                if fu is None or fu.dimension != r.unit.dimension:
                    continue
                conv = [v * fu.factor / r.unit.factor for v in vals]
            else:
                conv = vals
            bad = None
            if r.max is not None and any(v > r.max for v in conv):
                bad = f"больше {fmt(r.max)} {r.unit.title if r.unit else ''}".strip()
            if r.min is not None and any(v < r.min or (v == r.min and r.min_inclusive) for v in conv):
                bad = f"не больше {fmt(r.min)}" if r.min_inclusive else f"меньше {fmt(r.min)}"
            if bad is None:
                continue
            shown = f"{f.value}{'–' + f.value_to if f.value_to else ''}{' ' + f.unit if f.unit else ''}"
            key = f"plaus:{r.id}:{f.property_code or f.property_name}:{shown}"
            out.append(Finding(key, r, f.id, (
                f"«{f.property_name}» = {shown}: значение {bad} — подозрительно ({r.basis}). "
                "Это не ограничение КТРУ, значение не исправлено автоматически. "
                "Подтвердите значение или исправьте описание.")))
    return out


def rules_version() -> str:
    return load_rules()[0]
