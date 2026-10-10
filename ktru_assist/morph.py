"""Бесловарная нормализация словоформ: правила русского стеммера Портера/Snowball.

Используется вместо словаря pymorphy3 при KTRU_MORPH=snowball. Словаря нет: окончания отсекаются
по правилам в области RV (после первой гласной). Части речи не определяются, поэтому главное слово
наименования — первое значимое слово, не похожее на прилагательное.

Служебные слова грамматики (сравнения, отрицания, «наличие») не изменяются: код ядра сравнивает их
как строки. Это не предметный словарь.
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
ADJ_END = re.compile(r"(ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ых|их)$")


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


def stem(word: str) -> str:
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


def looks_adjective(word: str) -> bool:
    return bool(ADJ_END.search(word))
