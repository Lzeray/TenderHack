"""Исправление опечаток по словарю каталога.

Правила:
* исправляются только слова (не числа, не единицы, не коды/модели);
* слово, известное каталогу или словарю русского языка, не исправляется;
* кандидаты — словоформы каталога на расстоянии Дамерау–Левенштейна ≤ 1 (длина ≤ 5)
  или ≤ 2 (длина ≥ 6), найденные через индекс удалений (SymSpell);
* исправление применяется, только если все ближайшие кандидаты имеют одну лемму;
  иначе возвращаются варианты для выбора пользователем.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from ..models import Correction
from ..text import STOPWORDS, damerau_levenshtein, is_known_word, lemma, tokenize
from .normalize import Token


def _deletes(word: str, max_d: int) -> set[str]:
    out = {word}
    n = len(word)
    for d in range(1, max_d + 1):
        if n - d < 2:
            break
        for idx in combinations(range(n), d):
            out.add("".join(c for k, c in enumerate(word) if k not in idx))
    return out


def max_distance(word: str) -> int:
    return 1 if len(word) <= 5 else 2


class TypoCorrector:
    def __init__(self, texts: list[str]):
        forms: set[str] = set()
        for t in texts:
            for w in tokenize(t):
                if len(w) >= 3 and w.isalpha() and w not in STOPWORDS:
                    forms.add(w)
        self.forms = forms
        self.lemmas = {lemma(w) for w in forms}
        self.index: dict[str, set[str]] = defaultdict(set)
        for w in forms:
            for d in _deletes(w, 2):
                self.index[d].add(w)

    def known(self, word: str) -> bool:
        return word in self.forms or lemma(word) in self.lemmas

    def candidates(self, word: str) -> list[tuple[int, str]]:
        md = max_distance(word)
        found: set[str] = set()
        for d in _deletes(word, md):
            found |= self.index.get(d, set())
        out = []
        for c in found:
            dist = damerau_levenshtein(word, c, md)
            if dist <= md:
                out.append((dist, c))
        return sorted(out)

    def correct(self, tokens: list[Token], user_choices: dict[str, str]) -> list[Correction]:
        result: list[Correction] = []
        for t in tokens:
            if t.kind != "word" or len(t.text) < 4 or t.lemma in STOPWORDS:
                continue
            if t.text in user_choices:
                choice = user_choices[t.text].lower()
                if choice != t.text:
                    result.append(Correction(original=t.text, status="user_choice", corrected=choice,
                                             note="выбрано пользователем"))
                    t.text, t.lemma = choice, lemma(choice)
                continue
            if self.known(t.text) or is_known_word(t.text):
                continue
            cands = self.candidates(t.text)
            if not cands:
                continue
            best = cands[0][0]
            nearest = [c for d, c in cands if d == best]
            lems = sorted({lemma(c) for c in nearest})
            if len(lems) == 1:
                chosen = sorted(nearest)[0]
                result.append(Correction(original=t.text, status="corrected", corrected=chosen, distance=best,
                                         options=sorted(nearest), note="однозначное совпадение со словарём каталога"))
                t.text, t.lemma = chosen, lems[0]
            else:
                opts = []
                for c in sorted(nearest):
                    if lemma(c) not in [lemma(o) for o in opts]:
                        opts.append(c)
                result.append(Correction(original=t.text, status="ambiguous", distance=best, options=opts,
                                         note="несколько вариантов на одинаковом расстоянии — нужен выбор"))
        return result
