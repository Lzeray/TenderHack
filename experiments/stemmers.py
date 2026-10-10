"""Бесловарные замены лемматизатора pymorphy3 для экспериментов.

snowball  — правила русского стеммера Портера/Snowball (окончания в области RV, без словаря);
trunc5    — первые 5 букв слова;
identity  — слово как есть (только нижний регистр и ё→е).
Служебные слова грамматики (сравнения, отрицания, «наличие») не изменяются: это не предметный словарь,
код ядра сравнивает их как леммы.
"""
from __future__ import annotations

import re

VOWELS = "аеиоуыэюя"
PROTECTED = {"менее", "более", "меньше", "больше", "свыше", "ниже", "выше", "минимум", "максимум", "наличие",
             "отсутствие", "есть", "нет", "без", "не", "от", "до", "да", "или", "для"}

_PG1 = ("вшись", "вши", "в")
_PG2 = ("ившись", "ывшись", "ивши", "ывши", "ив", "ыв")
_ADJ = ("ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие", "ые", "ое", "ей", "ий", "ый", "ой", "ем", "им", "ым",
        "ом", "их", "ых", "ую", "юю", "ая", "яя", "ою", "ею")
_PART1 = ("ем", "нн", "вш", "ющ", "щ")
_PART2 = ("ивш", "ывш", "ующ")
_REFL = ("ся", "сь")
_VERB1 = ("ете", "йте", "ешь", "нно", "ла", "на", "ли", "ем", "ло", "но", "ет", "ют", "ны", "ть", "й", "л", "н")
_VERB2 = ("ейте", "уйте", "ила", "ыла", "ена", "ите", "или", "ыли", "ило", "ыло", "ено", "ует", "уют", "ены", "ить",
          "ыть", "ишь", "ей", "уй", "ил", "ыл", "им", "ым", "ен", "ят", "ит", "ыт", "ую", "ю")
_NOUN = ("иями", "ями", "ами", "ией", "иям", "ием", "иях", "ев", "ов", "ие", "ье", "еи", "ии", "ей", "ой", "ий", "ям",
         "ем", "ам", "ом", "ах", "ях", "ию", "ью", "ия", "ья", "а", "е", "и", "й", "о", "у", "ы", "ь", "ю", "я")


def _strip(word: str, rv: int, endings, after_ay: bool = False) -> str | None:
    for e in sorted(endings, key=len, reverse=True):
        if word.endswith(e) and len(word) - len(e) >= rv:
            if after_ay:
                k = len(word) - len(e)
                if k - 1 >= rv and word[k - 1] in "ая":
                    return word[:k]
                continue
            return word[: len(word) - len(e)]
    return None


def snowball(word: str) -> str:
    w = word.lower().replace("ё", "е")
    if w in PROTECTED or len(w) <= 3 or not re.fullmatch("[а-я]+", w):
        return w
    m = re.search(f"[{VOWELS}]", w)
    if not m:
        return w
    rv = m.end()
    r = _strip(w, rv, _PG1, after_ay=True) or _strip(w, rv, _PG2)
    if r is None:
        w2 = _strip(w, rv, _REFL) or w
        adj = _strip(w2, rv, _ADJ)
        if adj is not None:
            r = _strip(adj, rv, _PART1, after_ay=True) or _strip(adj, rv, _PART2) or adj
        else:
            r = _strip(w2, rv, _VERB1, after_ay=True) or _strip(w2, rv, _VERB2) or _strip(w2, rv, _NOUN) or w2
    if r.endswith("и") and len(r) - 1 >= rv:
        r = r[:-1]
    if r.endswith("нн"):
        r = r[:-1]
    elif r.endswith("ь"):
        r = r[:-1]
    return r


def trunc5(word: str) -> str:
    w = word.lower().replace("ё", "е")
    return w if w in PROTECTED else w[:5]


def identity(word: str) -> str:
    return word.lower().replace("ё", "е")


STEMMERS = {"snowball": snowball, "trunc5": trunc5, "identity": identity}
_ADJ_END = re.compile(r"(ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ых|их)$")


def install(name: str) -> None:
    """Подменить лемматизацию в ktru_assist.text ДО импорта остальных модулей ktru_assist."""
    from functools import lru_cache
    import ktru_assist.text as text
    stem = STEMMERS[name]

    @lru_cache(maxsize=200_000)
    def lemma(word: str) -> str:
        w = text.norm(word)
        if not re.search("[а-я]", w):
            return w
        if "-" in w:
            return "-".join(lemma(p) for p in w.split("-") if p)
        return stem(w)

    def head_lemma(name: str) -> str | None:
        # без морфологии: первое значимое слово, не похожее на прилагательное
        words = [t for t in text.tokenize(name) if not t[0].isdigit() and t not in text.STOPWORDS]
        for t in words:
            if not _ADJ_END.search(t):
                return lemma(t)
        return lemma(words[0]) if words else None

    text.lemma = lemma
    text.head_lemma = head_lemma
    text.is_known_word = lambda word: False
    # леммы стоп-слов и отрицаний сравниваются в коде как строки — приводим их тем же стеммером
    text.STOPWORDS |= {stem(s) for s in list(text.STOPWORDS)}
