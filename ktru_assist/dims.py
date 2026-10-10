"""Геометрические размеры: общие оси товара (docs/DIMENSIONS_PLAN.md, шаги D3–D4).

Свойство КТРУ — «общий размер» по оси, если его название — слово-ось (длина, ширина, глубина, высота, диаметр),
после которого идут только название самого товара («Высота шкафа»), «столешница» («Длина столешницы»,
«Высота до столешницы») или пояснение в скобках («Высота (без учета регулировки)»). Размеры частей
(«Глубина секции стеллажа», «Длина полки», «Высота антресоли») и толщины общими не считаются.

Нужно, чтобы одна ось с разными названиями у позиций одного типа («Высота» / «Высота шкафа») проверялась
одинаково, и чтобы габариты «80х50х180» раскладывались только по общим осям.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .text import content_lemmas, lemma_of_literal

AXES = tuple(lemma_of_literal(w) for w in ("длина", "ширина", "глубина", "высота", "диаметр"))
OVERALL_QUALIFIERS = frozenset(lemma_of_literal(w) for w in ("столешница", "изделие", "товар", "габаритный",
                                                              "общий"))


@lru_cache(maxsize=20_000)
def axis_of(prop_name: str, context: frozenset[str] = frozenset()) -> str | None:
    """Ось общего размера или None (размер части, толщина, не размер).

    context — леммы наименования позиции или главные слова типа: «Длина разводного ключа» у «Ключ разводной»."""
    base = re.sub(r"\([^)]*\)", " ", prop_name or "")
    lem = content_lemmas(base)
    if not lem or lem[0] not in AXES:
        return None
    rest = set(lem[1:]) - context - OVERALL_QUALIFIERS
    return lem[0] if not rest else None


def context_of(name_lemmas, heads=()) -> frozenset[str]:
    out = set(name_lemmas or ())
    for h in heads:
        out |= set(h.split("-")) | {h}
    return frozenset(out)


__all__ = ["AXES", "axis_of"]
