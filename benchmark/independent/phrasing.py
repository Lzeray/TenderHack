"""Естественные русские формулировки фактов для генератора независимых наборов.

Согласование делается через pymorphy3 только там, где разбор надёжен (слово есть в словаре
и нашлась форма нужной части речи и падежа). Если надёжного разбора нет, значение пишется как есть
или используется нейтральная формулировка — ошибка морфологии не должна менять смысл факта.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pymorphy3

M = pymorphy3.MorphAnalyzer()
PREPS = {"для", "из", "с", "со", "на", "в", "во", "от", "по", "без", "до", "под", "над", "при", "к", "о",
         "об", "и", "или", "а", "у", "за", "через"}
CYR = re.compile(r"^[а-яё]+$", re.I)


def known(word: str) -> bool:
    return bool(CYR.match(word)) and M.word_is_known(word.lower())


def parse(word: str, pos: set[str], case: str | None = None):
    if not known(word):
        return None
    for p in M.parse(word.lower()):
        if p.tag.POS in pos and (case is None or case in p.tag):
            return p
    return None


def lower_first(s: str) -> str:
    if not s:
        return s
    w = s.split(" ", 1)[0]
    if len(w) > 1 and (w.isupper() or re.search(r"[A-Za-z0-9]", w)):
        return s
    return s[0].lower() + s[1:]


ADJ_NOMN_TAIL = re.compile(r"(ая|яя|ое|ее|ый|ий|ые|ие)$")


def _grams(head, case: str) -> set[str]:
    if "plur" in head.tag or "Pltm" in head.tag:
        return {"plur", case}
    return {g for g in (head.tag.gender, "sing", case) if g}


def inflect_np(phrase: str, case: str, src: str = "nomn") -> tuple[str, object] | None:
    """Склоняет именную группу: вершина-существительное и согласованные с ней прилагательные
    до первого предлога / знака / несогласованного слова. Возвращает (текст, разбор вершины)
    или None, если надёжно просклонять нельзя (тогда генератор берёт другую формулировку).
    """
    tokens = phrase.split()
    bare = [t.strip(",.;()") for t in tokens]
    roles: list[tuple[int, object, str]] = []   # (индекс, разбор, роль adj|noun)
    head = None
    i = 0
    while i < len(tokens):
        b = bare[i]
        if b.lower() in PREPS or not CYR.match(b):
            break
        if head is None:
            p = parse(b, {"NOUN"}, src)
            if p is not None and parse(b, {"ADJF", "PRTF"}, src) is None:
                head = p
                roles.append((i, p, "noun"))
                i += 1
                if tokens[i - 1].endswith(","):
                    break
                continue
            p = parse(b, {"ADJF", "PRTF"}, src)
            if p is None:
                return None
            roles.append((i, p, "adj"))
            i += 1
            continue
        # после вершины: серия прилагательных, если за ней не идёт существительное
        j = i
        run = []
        while j < len(tokens):
            p = parse(bare[j], {"ADJF", "PRTF"}, src)
            if p is None:
                break
            run.append((j, p, "adj"))
            if tokens[j].endswith(","):
                j += 1
                break
            j += 1
        nxt = bare[j] if j < len(tokens) else None
        if run and (nxt is None or tokens[j - 1].endswith(",") or parse(nxt, {"NOUN"}, src) is None):
            roles.extend(run)
            i = j
        break
    if head is None:
        return None
    last = roles[-1][0] if roles else -1
    # хвост после остановки не должен содержать согласованных прилагательных в именительном
    if src == "nomn" and case != "nomn":
        for b in bare[last + 1:]:
            if ADJ_NOMN_TAIL.search(b.lower()) and parse(b, {"NOUN"}) is None:
                return None
    out = list(tokens)
    gr = _grams(head, case)
    for idx, p, role in roles:
        infl = p.inflect({case}) if role == "noun" else p.inflect(gr)
        if infl is None:
            return None
        word = infl.word.replace("ё", "е")
        out[idx] = tokens[idx].replace(bare[idx], word)
    return " ".join(out), head


def agree_adj(word: str, head, case: str) -> str | None:
    """Прилагательное-значение («Рыбацкие») в форме, согласованной с вершиной наименования."""
    p = parse(word, {"ADJF", "PRTF"}, "nomn")
    if p is None or head is None:
        return None
    if "plur" in head.tag or "Pltm" in head.tag:
        gr = {"plur", case}
    else:
        if head.tag.gender is None:
            return None
        gr = {head.tag.gender, "sing", case}
    infl = p.inflect(gr)
    return infl.word.replace("ё", "е") if infl else None


def need_word(head) -> str | None:
    """«нужен / нужна / нужно / нужны» в согласовании с вершиной."""
    if head is None:
        return None
    if "plur" in head.tag or "Pltm" in head.tag:
        return "нужны"
    return {"masc": "нужен", "femn": "нужна", "neut": "нужно"}.get(head.tag.gender)


def with_prep(np: str) -> str:
    """«с» или «со» перед именной группой в творительном падеже."""
    w = np.split(" ", 1)[0].lower()
    if re.match(r"[сзжшщ][бвгджзклмнпрстфхцчшщ]", w) or re.match(r"(в[сзт]|мн)", w):
        return "со " + np
    return "с " + np


# ---------------------------------------------------------------- числа и единицы
UNIT_FORMS: dict[str, list[tuple[str, str, str]]] = {
    "mm": [("мм", "мм", "мм"), ("миллиметр", "миллиметра", "миллиметров")],
    "cm": [("см", "см", "см"), ("сантиметр", "сантиметра", "сантиметров")],
    "m": [("м", "м", "м"), ("метр", "метра", "метров")],
    "km": [("км", "км", "км")],
    "inch": [("дюйм", "дюйма", "дюймов")],
    "g": [("г", "г", "г"), ("грамм", "грамма", "граммов")],
    "kg": [("кг", "кг", "кг"), ("килограмм", "килограмма", "килограммов")],
    "W": [("Вт", "Вт", "Вт"), ("ватт", "ватта", "ватт")],
    "kW": [("кВт", "кВт", "кВт"), ("киловатт", "киловатта", "киловатт")],
    "V": [("В", "В", "В"), ("вольт", "вольта", "вольт")],
    "Ah": [("А·ч", "А·ч", "А·ч"), ("Ач", "Ач", "Ач")],
    "C": [("°C", "°C", "°C"), ("градус Цельсия", "градуса Цельсия", "градусов Цельсия")],
    "rpm": [("об/мин", "об/мин", "об/мин")],
    "mm2": [("мм²", "мм²", "мм²"), ("кв. мм", "кв. мм", "кв. мм")],
    "m3h": [("м³/ч", "м³/ч", "м³/ч")],
    "deg": [("градус", "градуса", "градусов")],
    "min": [("мин", "мин", "мин"), ("минута", "минуты", "минут")],
    "pcs": [("шт", "шт", "шт"), ("штука", "штуки", "штук")],
}
# в какие единицы можно переписать значение каталога (та же величина)
UNIT_ALTERNATIVES = {"mm": ["mm", "cm", "m"], "cm": ["cm", "mm", "m"], "m": ["m", "cm", "mm"],
                     "g": ["g", "kg"], "kg": ["kg", "g"], "W": ["W", "kW"], "kW": ["kW", "W"]}


def fmt_dec(d: Decimal, comma: bool) -> str:
    s = format(d.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",") if comma else s


def decimals(d: Decimal) -> int:
    s = format(d.normalize(), "f")
    return len(s.split(".", 1)[1]) if "." in s else 0


def plural(num: str, forms: tuple[str, str, str]) -> str:
    if "," in num or "." in num:
        return forms[1]
    n = int(num.lstrip("-") or 0)
    if 11 <= n % 100 <= 14:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if 2 <= n % 10 <= 4:
        return forms[1]
    return forms[2]


def unit_text(key: str, num: str, variant: int) -> str:
    forms = UNIT_FORMS[key]
    return plural(num, forms[variant % len(forms)])
