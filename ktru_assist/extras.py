"""Дополнительные характеристики: указаны пользователем, но их нет в позициях КТРУ области.

На выбор кода они не влияют. Порядок проверки:
1. характеристика должна нести категориальный смысл: есть название свойства и конкретное значение
   (число, материал, цвет …), а не оценка («красивое», «качественный», «удобный»);
2. есть в выгрузках СТЕ у этого типа товара → «из СТЕ»;
3. уже указывалась в этой сессии для этого типа → «запомнена в сессии»;
4. иначе — новая дополнительная характеристика: принимается и запоминается в сессии.
Память — только в процессе (базы не меняются), компактная: ключ «тип × свойство по леммам», не больше
MAX_VALUES значений на свойство, MAX_PROPS свойств на сессию и MAX_SESSIONS сессий (вытесняются самые старые).
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from .canon import display, value_supported
from .models import AdditionalCharacteristic, Feature
from .text import content_lemmas, lemma_set, norm

VERSION = "1.1"
MAX_SESSIONS = 1000
MAX_PROPS = 40
MAX_VALUES = 5
MAX_VALUE_WORDS = 6

# оценочные слова: мнение о товаре, а не его характеристика (словарная форма; приводятся к текущей нормализации)
SUBJECTIVE = lemma_set({
    "красивый", "симпатичный", "прекрасный", "отличный", "хороший", "плохой", "лучший", "худший", "классный",
    "крутой", "модный", "стильный", "элегантный", "удобный", "неудобный", "качественный", "некачественный",
    "надёжный", "надежный", "практичный", "замечательный", "шикарный", "нормальный", "обычный", "дешёвый",
    "дешевый", "дорогой", "недорогой", "бюджетный", "роскошный", "милый", "приятный", "уютный", "идеальный",
    "великолепный", "оригинальный", "интересный", "необычный", "супер", "клёвый", "клевый", "прикольный",
    "солидный", "престижный", "добротный", "нарядный", "любой", "какой-нибудь", "неважно", "красиво", "хорошо",
    "отлично", "удобно", "качественно", "стильно", "модно", "крепкий",
})
PLACEHOLDERS = {"-", "—", "нет данных", "не знаю", "неизвестно", "не важно", "неважно", "любой", "любая", "любое",
                "не задано", "?"}


class SessionMemory:
    """Компактная память дополнительных характеристик по сессиям (LRU)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, OrderedDict[tuple, dict]] = OrderedDict()

    def get(self, session_id: str | None, type_key: str, name: str) -> dict | None:
        if not session_id:
            return None
        with self._lock:
            mem = self._sessions.get(session_id)
            return dict(mem[(type_key, _key(name))]) if mem and (type_key, _key(name)) in mem else None

    def remember(self, session_id: str | None, type_key: str, name: str, value: str | None, unit: str | None):
        if not session_id or not _key(name):
            return
        with self._lock:
            mem = self._sessions.pop(session_id, None) or OrderedDict()
            self._sessions[session_id] = mem
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)
            k = (type_key, _key(name))
            item = mem.pop(k, None) or {"name": name, "values": [], "unit": unit}
            shown = f"{value} {unit}".strip() if value is not None else None
            if shown and norm(shown) not in {norm(v) for v in item["values"]}:
                item["values"] = (item["values"] + [shown])[-MAX_VALUES:]
            mem[k] = item
            while len(mem) > MAX_PROPS:
                mem.popitem(last=False)

    def items(self, session_id: str | None, type_key: str) -> list[dict]:
        if not session_id:
            return []
        with self._lock:
            mem = self._sessions.get(session_id) or {}
            return [dict(v) for (tk, _), v in mem.items() if tk == type_key]


MEMORY = SessionMemory()


def _key(name: str | None) -> tuple[str, ...]:
    return tuple(content_lemmas(name or ""))


def type_key(heads: list[str]) -> str:
    return "|".join(sorted(heads)) if heads else ""


def check_meaning(name: str | None, value: str | None, heads: list[str]) -> str | None:
    """Причина, по которой это не характеристика товара; None — категориальный смысл есть."""
    if not name or not _key(name):
        return "нет названия свойства — непонятно, к чему относится значение"
    name_lem = set(_key(name))
    if name_lem & SUBJECTIVE:
        return f"«{name}» — оценка, а не свойство товара"
    if name_lem <= set(heads):
        return f"«{name}» — это сам тип товара, а не его свойство"
    if value is None or norm(value).strip() in PLACEHOLDERS:
        return "значение не указано"
    has_digit = any(ch.isdigit() for ch in value)
    val_lem = _key(value)
    if not has_digit and not val_lem:
        return "значение не указано"
    if val_lem and set(val_lem) <= SUBJECTIVE:
        return f"«{value}» — оценочное слово: оно не описывает товар однозначно (укажите материал, цвет, размер …)"
    if len(value.split()) > MAX_VALUE_WORDS:
        return "значение похоже на описание, а не на конкретное значение — укажите его короче"
    return None


def _in_ste(stats, heads: list[str], name: str, numeric: bool) -> bool:
    if stats is None or not getattr(stats, "available", False):
        return False
    lem = _key(name)
    for tk in stats.type_keys(heads):
        for (lk, kind, _dim), ps in stats.by_lemmas(tk).items():
            if lk == lem and (kind == "number") == numeric:
                return True
    return False


def classify(features: list[Feature], extra_attrs: list[dict], heads: list[str], stats,
             session_id: str | None) -> list[AdditionalCharacteristic]:
    """Дополнительные характеристики запроса. Принятые запоминаются в сессии."""
    tk = type_key(heads)
    items: list[tuple[str, str | None, str | None, str | None, str]] = []   # name, value, unit, feature_id, origin
    for f in features:
        if f.status != "unknown_property":
            continue
        name = f.named_property or f.property_name
        if not name:
            continue
        value = f.value if f.op != "between" else f"{f.value}–{f.value_to}"
        if f.op == "ne" and value:
            value = "не " + value
        items.append((name, value, f.unit, f.id, f.origin))
    for a in extra_attrs:
        value = a.get("raw_value") or a.get("value")
        normalized = a.get("value")
        if a.get("source") == "llm" and value and normalized and not any(c.isdigit() for c in value) \
                and value_supported(normalized, value):
            value = normalized
        items.append((a.get("name") or "", value, a.get("raw_unit") or a.get("unit"),
                      None, a.get("source") or "llm"))
    out: list[AdditionalCharacteristic] = []
    seen: set[tuple] = set()
    for name, value, unit, fid, origin in items:
        name, value = display(name) or "", display(value) if value and not any(c.isdigit() for c in value) else value
        k = (_key(name), norm(value or ""))
        if k in seen:
            continue
        seen.add(k)
        why = check_meaning(name, value, heads)
        if why is not None:
            out.append(AdditionalCharacteristic(name=name, value=value, unit=unit, feature_id=fid, origin=origin,
                                                accepted=False, source="rejected", reason=why))
            continue
        numeric = bool(value) and any(c.isdigit() for c in value)
        if _in_ste(stats, heads, name, numeric):
            source, reason = "ste", "нет в КТРУ этого товара, но указывается у товаров этого типа в выгрузках СТЕ"
        elif MEMORY.get(session_id, tk, name) is not None:
            source, reason = "session", "нет в КТРУ и СТЕ; уже указывалась в этой сессии для такого товара"
        else:
            source, reason = "new", "нет в КТРУ и СТЕ; принята как дополнительная и запомнена в сессии"
        MEMORY.remember(session_id, tk, name, value, unit)
        out.append(AdditionalCharacteristic(name=name, value=value, unit=unit, feature_id=fid, origin=origin,
                                            accepted=True, source=source, reason=reason))
    return out


def subjective_words(words: list[str]) -> list[str]:
    """Нераспознанные слова описания, которые являются оценкой («красивое»)."""
    return [w for w in words if any(l in SUBJECTIVE for l in content_lemmas(w))]


__all__ = ["classify", "check_meaning", "subjective_words", "MEMORY", "SessionMemory", "VERSION"]
