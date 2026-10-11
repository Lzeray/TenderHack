"""Единый формат характеристик: название свойства и значение в написании КТРУ.

Любой источник (правила, модель, ручной ввод, ответ на вопрос) приводится к одному виду:
* название свойства — точное название характеристики КТРУ области поиска;
* качественное значение — допустимое значение КТРУ этой характеристики («угловой», «УГЛОВАЯ» → «Угловой»).
  Сравнение без учёта регистра, «ё» и словоформы (леммы, поэтому род и падеж не мешают);
* значение, которого нет в КТРУ, — в едином виде отображения: без лишних пробелов, с прописной первой буквой,
  как значения КТРУ. Само слово не исправляется и не подменяется.
Числа и единицы не трогаются (их приводит units.py без округления).
"""
from __future__ import annotations

import re

from .models import Feature
from .text import content_lemmas, damerau_levenshtein, is_known_word, norm, property_key, tokenize

VERSION = "1.2"


def display(text: str | None) -> str | None:
    """Вид отображения значения вне КТРУ: пробелы схлопнуты, первая буква прописная."""
    if text is None:
        return None
    s = " ".join(text.split()).strip(" .,;:")
    if not s:
        return s
    return s[0].upper() + s[1:]


def _lemkey(text: str) -> tuple[str, ...]:
    return tuple(content_lemmas(text))


def value_supported(value: str, quote: str) -> bool:
    """Нормализация словоформ без новых фактов, чисел или изменения отрицания."""
    words = content_lemmas(value)
    cited = content_lemmas(quote)
    numbers = [t.replace(",", ".") for t in re.findall(r"-?\d+(?:[.,]\d+)?", value)]
    quoted_numbers = [t.replace(",", ".") for t in re.findall(r"-?\d+(?:[.,]\d+)?", quote)]
    modifiers = {"не", "без", "нет", "менее", "более", "от", "до"}
    if numbers != quoted_numbers or set(tokenize(value)) & modifiers != set(tokenize(quote)) & modifiers:
        return False
    return bool(words or numbers) and all(
        any(w == q or (len(w) >= 4 and len(q) >= 4 and (
            w[:4] == q[:4] or (not is_known_word(q) and damerau_levenshtein(w[:4], q[:4], 1) <= 1)))
            for q in cited)
        for w in words
    )


def match_value(text: str | None, allowed: dict[str, str]) -> str | None:
    """Допустимое значение КТРУ для текста пользователя. allowed: норм. текст → исходное написание КТРУ.
    Сначала точное совпадение без регистра и «ё», затем единственное совпадение по леммам."""
    if not text or not allowed:
        return None
    n = " ".join(norm(text).split()).strip(" .")
    if n in allowed:
        return allowed[n]
    lem = _lemkey(text)
    if not lem:
        return None
    hits = sorted({orig for k, orig in allowed.items() if _lemkey(k) == lem})
    return hits[0] if len(hits) == 1 else None


def match_group(name: str | None, groups: dict) -> object | None:
    """Группа свойства КТРУ по названию из текста: точное совпадение без регистра, затем по леммам."""
    if not name:
        return None
    key = property_key(name)
    exact = [g for g in groups.values() if property_key(g.name) == key]
    if len(exact) == 1:
        return exact[0]
    lem = _lemkey(name)
    if not lem:
        return None
    same = [g for g in groups.values() if _lemkey(g.name) == lem]
    return same[0] if len(same) == 1 else None


def groups_with_value(text: str | None, groups: dict, among=None) -> list:
    """Группы, у которых значение есть среди допустимых (для привязки «Тип: угловой» по значению)."""
    pool = among if among is not None else list(groups.values())
    return [g for g in pool if not getattr(g, "numeric", False) and match_value(text, g.quality)]


def canonicalize(features: list[Feature], groups: dict) -> list[Feature]:
    """Приводит признаки к единому формату на месте. Привязку и статус не меняет: только написание."""
    by_name = {g.name: g for g in groups.values()}
    for f in features:
        g = by_name.get(f.property_name or "")
        if g is None and f.property_name and f.status in ("bound", "proposed", "overridden"):
            g = match_group(f.property_name, groups)
            if g is not None:
                f.property_name = g.name
        if g is not None and g.quality:
            if f.value is not None and f.unit is None:
                v = match_value(f.value, g.quality)
                if v is not None:
                    f.value = v
            if f.values:
                f.values = [match_value(v, g.quality) or v for v in f.values]
        elif f.status == "ambiguous":
            for o in f.options:
                og = by_name.get(o.get("property_name") or "")
                if og is not None and o.get("value"):
                    o["value"] = match_value(o["value"], og.quality) or o["value"]
            shown = {o.get("value") for o in f.options if o.get("value")}
            if len(shown) == 1 and f.unit is None:
                f.value = shown.pop()
            elif f.unit is None and f.value and not any(ch.isdigit() for ch in f.value):
                f.value = display(f.value)
        # unknown_property не меняется: его исходный текст нужен проверкам по выгрузкам; вид отображения
        # дополнительных характеристик задаёт extras.classify
    return features


__all__ = ["display", "value_supported", "match_value", "match_group", "groups_with_value", "canonicalize", "VERSION"]
