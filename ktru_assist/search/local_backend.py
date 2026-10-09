"""Встроенный BM25-поиск (резервный бэкенд, когда OpenSearch недоступен).

Используются те же поля и веса, что и в OpenSearch-индексе: леммы наименования,
части главного слова, леммы наименования ОКПД2. Порядок при равных оценках — по коду.
В ответе API бэкенд всегда указан явно.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from .base import Hit, SearchResult

FIELDS = {"name_lemmas": 2.0, "head_parts": 3.0, "okpd2_lemmas": 0.5}
K1, B = 1.2, 0.75


class LocalBM25Backend:
    name = "local-bm25"

    def __init__(self, docs: list[dict]):
        self.docs = {d["code"]: d for d in docs if d["active"]}
        self.postings: dict[str, dict[str, dict[str, int]]] = {f: defaultdict(dict) for f in FIELDS}
        self.avglen: dict[str, float] = {}
        for f in FIELDS:
            total = 0
            for code, d in self.docs.items():
                terms = d.get(f) or []
                total += len(terms)
                for term, tf in Counter(terms).items():
                    self.postings[f][term][code] = tf
            self.avglen[f] = total / max(1, len(self.docs))
        self.heads: dict[str, list[str]] = defaultdict(list)
        for code, d in sorted(self.docs.items()):
            for h in d["head_parts"]:
                self.heads[h].append(code)

    def _idf(self, f: str, term: str) -> float:
        n = len(self.postings[f].get(term, {}))
        N = len(self.docs)
        return math.log(1 + (N - n + 0.5) / (n + 0.5))

    def search(self, terms: list[str], size: int) -> SearchResult:
        scores: dict[str, float] = defaultdict(float)
        for f, w in FIELDS.items():
            for term in sorted(set(terms)):
                post = self.postings[f].get(term)
                if not post:
                    continue
                idf = self._idf(f, term)
                for code, tf in post.items():
                    dl = len(self.docs[code].get(f) or [])
                    denom = tf + K1 * (1 - B + B * dl / (self.avglen[f] or 1))
                    scores[code] += w * idf * tf * (K1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda kv: (-round(kv[1], 9), kv[0]))
        return SearchResult([Hit(c, round(s, 6)) for c, s in ranked[:size]], len(ranked), self.name)

    def by_heads(self, heads: list[str], size: int) -> SearchResult:
        codes = sorted({c for h in heads for c in self.heads.get(h, [])})
        return SearchResult([Hit(c, 0.0) for c in codes[:size]], len(codes), self.name)
