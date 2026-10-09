"""CatalogContextBuilder: контекст для разбора B строится из снимка КТРУ, а не из догадок моделей.

Этап A лишь предлагает области (главные слова типа). Для каждой области берутся ВСЕ активные
позиции снимка, их характеристики объединяются только по точному совпадению названия
(как в ядре, nlp.extract.build_groups). Модель получает явный список property_ref и допустимые
значения. Если контекст пришлось обрезать (лимиты длины), это фиксируется в context_complete
и omitted — проверка ядра при этом не ограничивается: ядро пересчитывает всю область.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from ..nlp.extract import PropGroup, build_groups
from ..units import BY_KEY

MAX_TYPES = 30
MAX_HEADS = 4
# Бюджет контекста в символах JSON (≈ 2,1 символа на токен Qwen3 для русского текста, замер на «шкаф»):
# 12 000 символов ≈ 5,7 тыс. токенов, с запасом в окне 12 288 под системный промпт и ответ.
MAX_CHARS = 12000
# ступени сокращения: (свойств, значений на свойство)
LIMITS = [(60, 40), (60, 20), (40, 12), (30, 8), (20, 5)]


@dataclass
class CatalogContext:
    payload: dict
    context_id: str
    prop_refs: dict[str, PropGroup]          # property_ref → группа свойств области
    type_refs: dict[str, str]                # type_ref → наименование позиции
    heads: list[str]
    scope_complete: bool
    context_complete: bool
    omitted: list[str] = field(default_factory=list)


def _allowed(g: PropGroup, positions) -> list[str]:
    labels: list[str] = []
    for p in positions:
        for pr in p.props.values():
            if " ".join(pr.norm_name.split()) != g.key:
                continue
            for v in pr.values:
                lab = v.label
                if lab and lab not in labels:
                    labels.append(lab)
    return labels


def build_context(engine, heads: list[str], basis: dict[str, str], snapshot: str, effective_at: str | None,
                  draft: dict | None = None) -> CatalogContext:
    omitted: list[str] = []
    if len(heads) > MAX_HEADS:
        omitted.append(f"типы сверх лимита {MAX_HEADS}: {', '.join(heads[MAX_HEADS:])}")
        heads = heads[:MAX_HEADS]
    res = engine.backend.by_heads(heads, engine.settings.type_fetch_limit)
    domain = engine.catalog.get_many([h.code for h in res.hits])
    positions = [domain[c] for c in sorted(domain)]
    scope_complete = res.complete
    finals = [p for p in positions if not p.is_template]
    names = sorted({p.name for p in finals})
    if len(names) > MAX_TYPES:
        omitted.append(f"наименований сверх лимита {MAX_TYPES}: {len(names) - MAX_TYPES}")
    type_refs = {f"t{i + 1}": n for i, n in enumerate(names[:MAX_TYPES])}
    groups = build_groups(positions)
    ordered = sorted(groups.values(), key=lambda g: (-g.positions, g.key))
    allowed_all = {g.key: _allowed(g, positions) for g in ordered}
    base_omitted = list(omitted)
    for max_props, max_values in LIMITS:
        omitted = list(base_omitted)
        if len(ordered) > max_props:
            omitted.append(f"свойств сверх лимита {max_props}: "
                           + ", ".join(g.name for g in ordered[max_props:][:20]))
        prop_refs: dict[str, PropGroup] = {}
        props = []
        for i, g in enumerate(ordered[:max_props]):
            ref = f"p{i + 1}"
            prop_refs[ref] = g
            allowed = allowed_all[g.key]
            if len(allowed) > max_values:
                omitted.append(f"значений свойства «{g.name}» сверх лимита {max_values}: {len(allowed) - max_values}")
            props.append({
                "property_ref": ref, "name": g.name, "component": g.component,
                "kind": "number" if g.numeric else ("bool" if g.boolean else "enum"),
                "required": g.required, "units": sorted(BY_KEY[k].title for k in g.unit_keys),
                "allowed": allowed[:max_values],
            })
        if len(json.dumps(props, ensure_ascii=False)) <= MAX_CHARS:
            break
    payload = {
        "snapshot": snapshot, "effective_at": effective_at,
        "types": [{"type_ref": r, "name": n, "basis": basis.get(n, "главное слово типа в описании")}
                  for r, n in type_refs.items()],
        "properties": props,
        "allowed_property_refs": list(prop_refs),
        "scope_complete": scope_complete, "context_complete": not omitted,
    }
    if draft is not None:
        payload["draft_hypothesis"] = draft
    cid = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    payload["context_id"] = cid
    return CatalogContext(payload, cid, prop_refs, type_refs, heads, scope_complete, not omitted, omitted)
