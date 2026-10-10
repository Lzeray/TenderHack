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


MAX_STEM_LEMMAS = 3


def _stem(word: str) -> str:
    from ..morph import stem
    return stem(word)


def _common_suffix(a: str, b: str) -> int:
    """Длина общего окончания — только из окончаний русских слов (прилагательные, существительные): хвост основы
    («шкрф» / «шарф» → «-рф») окончанием не считается."""
    from ..morph import _ADJ, _NOUN
    best = 0
    for e in _ADJ + _NOUN:
        if len(e) >= 2 and a.endswith(e) and b.endswith(e) and len(a) > len(e) + 2:
            best = max(best, len(e))
    return best


def _forms_of(lem: str) -> list[str]:
    """Формы леммы, порождённые в момент запроса (pymorphy3); без словаря — сама лемма."""
    from ..text import MORPH_MODE, _morph
    if MORPH_MODE != "pymorphy":
        return [lem]
    out = set()
    for p in _morph().parse(lem)[:2]:
        if p.normal_form == lem:
            out |= {f.word.replace("ё", "е") for f in p.lexeme}
    return sorted(out) or [lem]


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
        # Индекс основ (docs/SPELLING_VALIDATION.md, шаг 3): основа → леммы каталога. Словарь форм не расширяется:
        # для слова в форме, которой нет в текстах КТРУ («офиссное», «кругой»), ищется близкая основа, а формы
        # 1–3 лемм-кандидатов порождаются в момент запроса.
        self.stem_lemmas: dict[str, set[str]] = defaultdict(set)
        self.stem_index: dict[str, set[str]] = defaultdict(set)
        for w in forms:
            st = _stem(w)
            if len(st) >= 3:
                self.stem_lemmas[st].add(lemma(w))
                for d in _deletes(st, 1):
                    self.stem_index[d].add(st)

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

    def stem_candidates(self, word: str) -> list[tuple[int, str]]:
        """Кандидаты через основу: близкая основа каталога (≤ 1 правка) → её леммы → их формы, порождённые сейчас;
        берутся формы на расстоянии не больше допустимого для слова."""
        st = _stem(word)
        if len(st) < 3:
            return []
        stems: set[str] = set()
        for d in _deletes(st, 1):
            stems |= self.stem_index.get(d, set())
        stems = {x for x in stems if damerau_levenshtein(st, x, 1) <= 1}
        lems = sorted({l for x in stems for l in self.stem_lemmas[x]})[:MAX_STEM_LEMMAS]
        md = max_distance(word)
        out = set()
        for lem in lems:
            for f in _forms_of(lem):
                dist = damerau_levenshtein(word, f, md)
                if dist <= md:
                    out.add((dist, f))
        return sorted(out)

    @staticmethod
    def _decide(word: str, cands, type_heads):
        """None — кандидатов нет; (лемма | None, расстояние, ближайшие, леммы, леммы-типы); лемма None — выбрать нельзя."""
        if not cands:
            return None
        best = cands[0][0]
        nearest = [c for d, c in cands if d == best]
        lems = sorted({lemma(c) for c in nearest})
        typed = sorted({l for l in lems if l in type_heads})
        if len(lems) == 1:
            return lems[0], best, nearest, lems, typed
        if len(typed) == 1:
            return typed[0], best, nearest, lems, typed
        # равноудалённые варианты разных лемм: выбирается тот, чьё окончание совпадает с набранным
        # («кругой» → «круглой», а не «кругом»), если такой один
        # окончание сравнивается только у вариантов с той же первой буквой (опечатка почти всегда её сохраняет):
        # иначе «кругой» → «дугой» по общему хвосту «-угой»
        by_lem = {l: max(_common_suffix(word, c) for c in nearest if lemma(c) == l) for l in lems
                  if any(c[:1] == word[:1] for c in nearest if lemma(c) == l)}
        top = max(by_lem.values(), default=0)
        winners = [l for l, v in by_lem.items() if v == top]
        if top >= 2 and len(winners) == 1:
            return winners[0], best, nearest, lems, typed
        return None, best, nearest, lems, typed

    def correct(self, tokens: list[Token], user_choices: dict[str, str],
                type_heads: set[str] | frozenset[str] = frozenset()) -> list[Correction]:
        """type_heads — главные слова типов: если из равноудалённых вариантов ровно один — тип товара,
        выбирается он («куркта» → «куртка», а не «курка»)."""
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
            # обычный поиск по словоформам; поиск по основе — запасной путь, если кандидатов нет или выбрать нельзя
            dec = self._decide(t.text, self.candidates(t.text), type_heads)
            if dec is None or dec[0] is None:
                merged = sorted(set(self.candidates(t.text)) | set(self.stem_candidates(t.text)))
                dec2 = self._decide(t.text, merged, type_heads)
                if dec2 is not None and (dec is None or dec2[0] is not None):
                    dec = dec2
            if dec is None:
                continue
            lem, best, nearest, lems, typed = dec
            if lem is not None:
                chosen = sorted((c for c in nearest if lemma(c) == lem),
                                key=lambda c: (-_common_suffix(t.text, c), c))[0]
                note = "однозначное совпадение со словарём каталога" if len(lems) == 1 else \
                    "из равноудалённых вариантов только этот — тип товара" if len(typed) == 1 else \
                    "из равноудалённых вариантов только у этого то же окончание"
                result.append(Correction(original=t.text, status="corrected", corrected=chosen, distance=best,
                                         options=sorted(nearest), note=note))
                t.text, t.lemma = chosen, lem
            else:
                opts = []
                for c in sorted(nearest):
                    if lemma(c) not in [lemma(o) for o in opts]:
                        opts.append(c)
                result.append(Correction(original=t.text, status="ambiguous", distance=best, options=opts,
                                         note="несколько вариантов на одинаковом расстоянии — нужен выбор"))
        return result
