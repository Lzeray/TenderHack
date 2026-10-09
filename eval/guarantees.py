"""Независимая перепроверка гарантий `matched` (для метрики unsafe_matched).

Не доверяет полям ответа: заново берёт из каталога все активные позиции с тем же главным словом,
что у выданной позиции, и проверяет их признаками ответа через validate.evaluate.
"""
from __future__ import annotations

from ktru_assist.models import SearchResponse
from ktru_assist.validate import evaluate


def check_matched(engine, resp: SearchResponse) -> list[str]:
    """Пустой список — гарантии соблюдены; иначе — перечень нарушений."""
    if resp.status != "matched":
        return []
    bad = []
    p = engine.catalog.get(resp.final_code or "")
    if p is None:
        return ["выданного кода нет в снимке"]
    if not p.active:
        bad.append("позиция неактивна на дату снимка")
    if p.is_template:
        bad.append("выдан шаблон (укрупнённая позиция)")
    if any(f.status == "bound" and f.confirmation == "tentative" for f in resp.features):
        bad.append("есть неподтверждённые гипотезы моделей")
    if not resp.completeness.type_domain_complete:
        bad.append("область типа проверена не полностью")
    res = engine.backend.by_heads([p.head], 100000) if p.head else None
    if res is None or not res.complete:
        bad.append("не удалось получить полную область типа")
        return bad
    domain = engine.catalog.get_many([h.code for h in res.hits])
    feats = [f for f in resp.features if f.status == "bound"]
    # тип, выбранный пользователем, сужает область до наименования; иначе — все наименования с этим словом,
    # кроме исключённых по полному совпадению наименования (этап «тип по наименованию»)
    names = {p.name}
    if not any(s.stage in ("тип выбран пользователем", "тип по наименованию") for s in resp.stages):
        names = {q.name for q in domain.values()}
    finals = []
    for q in domain.values():
        if q.is_template or not q.active or q.name not in names:
            continue
        ev = evaluate(q, feats)
        if ev.invalid == 0:
            finals.append(q.code)
    if finals != [resp.final_code]:
        bad.append(f"в области совместимы {len(finals)} конечных позиций: {', '.join(sorted(finals)[:5])}")
    return bad
