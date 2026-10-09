"""Общие текстовые утилиты: токенизация, лемматизация, расстояние редактирования.

Лемматизация — словарная (pymorphy3, OpenCorpora), без нейросетей. Если у слова
несколько разборов, берётся первый (pymorphy3 упорядочивает их детерминированно).
"""
from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

_MORPH = pymorphy3.MorphAnalyzer()

TOKEN_RE = re.compile(
    r"\d+(?:[.,]\d+)?"          # число
    r"|[a-zа-яё]+(?:[-][a-zа-яё0-9]+)*"  # слово (с дефисами)
    r"|[a-zа-яё0-9]+",
    re.IGNORECASE,
)

# Служебные слова, не несущие признаков товара.
STOPWORDS = {
    "и", "или", "в", "во", "на", "с", "со", "для", "по", "из", "к", "ко", "от", "до", "за",
    "о", "об", "у", "а", "но", "что", "это", "как", "при", "под", "над", "же", "ли", "то",
    "так", "также", "который", "этот", "тот", "весь", "свой", "мой", "наш", "быть",
    "нужно", "нужен", "нужный", "надо", "требоваться", "купить", "закупка", "шт", "штука",
    "около", "примерно", "более", "менее", "чем", "вид", "тип",
}
NEGATIONS = {"не", "без", "нет", "кроме", "отсутствие"}


def norm(s: str) -> str:
    return s.lower().replace("ё", "е")


def tokenize(s: str) -> list[str]:
    return TOKEN_RE.findall(norm(s))


@lru_cache(maxsize=200_000)
def lemma(word: str) -> str:
    w = norm(word)
    if not re.search("[а-я]", w):
        return w
    if "-" in w:  # «дрель-шуруповерт» → леммы частей через дефис
        return "-".join(lemma(p) for p in w.split("-") if p)
    return norm(_MORPH.parse(w)[0].normal_form)


@lru_cache(maxsize=200_000)
def is_known_word(word: str) -> bool:
    return _MORPH.word_is_known(norm(word))


def content_lemmas(s: str) -> list[str]:
    """Леммы значимых слов строки (без чисел и стоп-слов), в порядке появления."""
    out = []
    for t in tokenize(s):
        if t[0].isdigit():
            continue
        lem = lemma(t)
        if lem in STOPWORDS or len(lem) < 2:
            continue
        out.append(lem)
    return out


def head_lemma(name: str) -> str | None:
    """Главное слово наименования позиции: первое значимое существительное.

    Для «Стул на металлическом каркасе» → «стул», «Одежда специальная …» → «одежда».
    """
    for t in tokenize(name):
        if t[0].isdigit():
            continue
        p = _MORPH.parse(t)[0]
        lem = norm(p.normal_form)
        if lem in STOPWORDS:
            continue
        if "NOUN" in p.tag:
            return lemma(t)
    lems = content_lemmas(name)
    return lems[0] if lems else None


def damerau_levenshtein(a: str, b: str, limit: int = 3) -> int:
    """Расстояние Дамерау–Левенштейна (оптимальное выравнивание строк)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


def fuzzy_equal(a: str, b: str) -> bool:
    """Совпадение лемм с допуском 1 правки для длинных слов (сиденье/сидение)."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 6:
        return damerau_levenshtein(a, b, 1) <= 1
    return False
