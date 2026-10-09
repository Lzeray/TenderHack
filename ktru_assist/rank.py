"""Ранжирование совместимых кандидатов по фиксированному ключу (не вероятность).

Ключ сортировки (по порядку важности):
  1. уровень совпадения наименования/типа (name_tier: 3 — все слова наименования есть в запросе,
     2 — главное слово и часть остальных, 1 — только главное слово, 0 — нет главного слова);
  2. доля слов наименования, найденных в запросе (name_coverage);
  3. покрытие значимых терминов запроса (term_coverage) наименованием и подтверждёнными признаками;
  4. число проверенных условий (valid) — больше лучше;
  5. число непроверенных условий (unknown) — меньше лучше;
  6. код КТРУ — по возрастанию.
Дроби считаются точно (fractions.Fraction).
"""
from __future__ import annotations

from fractions import Fraction

from .catalog.repository import Position
from .models import RankComponents
from .nlp.normalize import Token
from .text import fuzzy_equal


def name_match(pos: Position, query_lemmas: list[str]) -> tuple[int, Fraction, set[str]]:
    names = pos.name_lemmas or []
    if not names:
        return 0, Fraction(0), set()
    matched = {n for n in names if any(fuzzy_equal(n, q) for q in query_lemmas)}
    head_parts = set((pos.head or "").split("-")) | {pos.head or ""}
    head_hit = any(any(fuzzy_equal(h, q) for q in query_lemmas) for h in head_parts if h)
    cov = Fraction(len(matched), len(set(names)))
    if matched >= set(names):
        tier = 3
    elif head_hit and len(matched) >= 2:
        tier = 2
    elif head_hit:
        tier = 1
    else:
        tier = 0
    return tier, cov, matched


def term_coverage(tokens: list[Token], name_matched: set[str], explained_feature_ids: set[str]) -> Fraction:
    sig = [t for t in tokens if t.significant or t.kind == "number"]
    if not sig:
        return Fraction(0)
    ok = 0
    for t in sig:
        if t.used_by and t.used_by in explained_feature_ids:
            ok += 1
        elif t.kind in ("word", "code") and any(fuzzy_equal(t.lemma, n) for n in name_matched):
            ok += 1
    return Fraction(ok, len(sig))


def fmt_fraction(fr: Fraction) -> str:
    return f"{fr.numerator}/{fr.denominator}" if fr.denominator != 1 else str(fr.numerator)


def rank_key(c: RankComponents, raw: tuple) -> tuple:
    tier, ncov, tcov, valid, unknown, code = raw
    return (-tier, -ncov, -tcov, -valid, unknown, code)


def components(pos: Position, tier: int, ncov: Fraction, tcov: Fraction, valid: int, unknown: int,
               score: float | None) -> tuple[RankComponents, tuple]:
    rc = RankComponents(name_tier=tier, name_coverage=fmt_fraction(ncov), term_coverage=fmt_fraction(tcov),
                        valid_conditions=valid, unknown_conditions=unknown, code=pos.code, search_score=score)
    return rc, (-tier, -ncov, -tcov, -valid, unknown, pos.code)
