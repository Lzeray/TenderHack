"""Независимый эталон: чтение каталога КТРУ из SQLite и проверка совместимости фактов.

Этот модуль НЕ использует код системы (ktru_assist): логика интервалов, единиц и сравнения
значений написана заново, числа — только Decimal. Используется только схема таблиц
positions / characteristics / char_values, которую создаёт импортёр.

Факт — то, что заявлено в тексте кейса:
  {"property": <точное имя характеристики КТРУ>, "kind": "text" | "number",
   "value": <строка>, "unit": <как написано в тексте или None>, "unit_key": <ключ единицы или None>,
   "op": "=" | ">=" | "<="}

Правила совместимости (см. README):
  * текстовый факт совместим с характеристикой, если среди её допустимых значений есть
    качественное значение с тем же текстом (без учёта регистра, ё=е, лишних пробелов);
  * числовой факт совместим, если хотя бы одно допустимое значение (конкретное число или диапазон
    с учётом включённости границ) совместимо с ним после точного перевода единиц;
    единицы разных величин (В и Вт, кг и Вт, мм и кг) несовместимы никогда;
  * числовой факт без единицы сравнивается с числом каталога в единице каталога;
  * числовой факт с единицей несовместим со значением каталога без ОКЕИ (единицу проверить нельзя).
Позиция входит в эталон, если для КАЖДОГО факта у неё есть характеристика с таким именем
и факт с ней совместим.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "ktru.sqlite"

# ---------------------------------------------------------------- единицы
# ключ -> (величина, множитель к базовой единице величины)
UNITS: dict[str, tuple[str, Decimal]] = {
    "mm": ("length", Decimal("0.001")),
    "cm": ("length", Decimal("0.01")),
    "m": ("length", Decimal("1")),
    "km": ("length", Decimal("1000")),
    "inch": ("length", Decimal("0.0254")),
    "g": ("mass", Decimal("0.001")),
    "kg": ("mass", Decimal("1")),
    "W": ("power", Decimal("1")),
    "kW": ("power", Decimal("1000")),
    "V": ("voltage", Decimal("1")),
    "Ah": ("charge", Decimal("1")),
    "C": ("temperature", Decimal("1")),
    "rpm": ("rotation", Decimal("1")),
    "mm2": ("area", Decimal("1")),
    "m3h": ("flow", Decimal("1")),
    "deg": ("angle", Decimal("1")),
    "min": ("time", Decimal("60")),
    "s": ("time", Decimal("1")),
    "pcs": ("count", Decimal("1")),
}
# код ОКЕИ -> ключ единицы
OKEI: dict[str, str] = {
    "003": "mm", "004": "cm", "006": "m", "008": "km", "039": "inch",
    "163": "g", "166": "kg", "212": "W", "214": "kW", "222": "V", "263": "Ah",
    "280": "C", "331": "rpm", "050": "mm2", "598": "m3h", "2355": "deg", "355": "min",
    "796": "pcs",
}


def unit_dimension(key: str | None) -> str | None:
    return UNITS[key][0] if key in UNITS else None


def convert(value: Decimal, src: str, dst: str) -> Decimal | None:
    """Точный перевод внутри одной величины; None — величины разные (перевод невозможен)."""
    if src not in UNITS or dst not in UNITS:
        return None
    (d1, f1), (d2, f2) = UNITS[src], UNITS[dst]
    if d1 != d2:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return value * f1 / f2


# ---------------------------------------------------------------- значения
@dataclass(frozen=True)
class Interval:
    """Множество чисел: нижняя/верхняя граница (None — нет границы) и их включённость."""
    lo: Decimal | None
    lo_inc: bool
    hi: Decimal | None
    hi_inc: bool

    @staticmethod
    def point(x: Decimal) -> "Interval":
        return Interval(x, True, x, True)

    def contains(self, x: Decimal) -> bool:
        if self.lo is not None and (x < self.lo or (x == self.lo and not self.lo_inc)):
            return False
        if self.hi is not None and (x > self.hi or (x == self.hi and not self.hi_inc)):
            return False
        return True

    def intersects(self, other: "Interval") -> bool:
        # нижняя граница пересечения = max(lo), верхняя = min(hi); проверяем непустоту
        lo, lo_inc = _max_lo((self.lo, self.lo_inc), (other.lo, other.lo_inc))
        hi, hi_inc = _min_hi((self.hi, self.hi_inc), (other.hi, other.hi_inc))
        if lo is None or hi is None:
            return True
        if lo < hi:
            return True
        return lo == hi and lo_inc and hi_inc

    def scaled(self, factor: Decimal) -> "Interval":
        with localcontext() as ctx:
            ctx.prec = 60
            return Interval(None if self.lo is None else self.lo * factor, self.lo_inc,
                            None if self.hi is None else self.hi * factor, self.hi_inc)


def _max_lo(a, b):
    if a[0] is None:
        return b
    if b[0] is None:
        return a
    if a[0] != b[0]:
        return a if a[0] > b[0] else b
    return a[0], a[1] and b[1]


def _min_hi(a, b):
    if a[0] is None:
        return b
    if b[0] is None:
        return a
    if a[0] != b[0]:
        return a if a[0] < b[0] else b
    return a[0], a[1] and b[1]


def dec(s) -> Decimal | None:
    if s is None:
        return None
    try:
        return Decimal(str(s).strip().replace(",", "."))
    except InvalidOperation:
        return None


def norm_text(s: str | None) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" .;,")


@dataclass
class Value:
    kind: str                      # quality | range | concrete
    text: str | None = None
    unit_key: str | None = None
    okei_name: str | None = None
    has_okei: bool = False
    interval: Interval | None = None   # для range / concrete


@dataclass
class Char:
    name: str
    kind: int | None
    required: bool
    char_type: int | None
    values: list[Value] = field(default_factory=list)


@dataclass
class Position:
    code: str
    name: str
    category: str
    okpd2: str | None
    chars: dict[str, Char] = field(default_factory=dict)    # norm_text(имя) -> Char

    def must_state(self) -> set[str]:
        """Характеристики, которые должны быть заявлены для code_required: kind=1 и обязательные."""
        return {k for k, c in self.chars.items() if c.kind == 1 or c.required}


def fact_interval(fact: dict) -> Interval:
    x = dec(fact["value"])
    op = fact.get("op", "=")
    if op == ">=":
        return Interval(x, True, None, False)
    if op == "<=":
        return Interval(None, False, x, True)
    if op == ">":
        return Interval(x, False, None, False)
    if op == "<":
        return Interval(None, False, x, False)
    return Interval.point(x)


def value_compatible(fact: dict, v: Value) -> bool:
    if fact["kind"] == "text":
        return v.kind == "quality" and norm_text(v.text) == norm_text(fact["value"])
    # числовой факт
    if dec(fact["value"]) is None:
        return False
    fi = fact_interval(fact)
    if v.kind == "quality":
        # число, записанное текстом («48»): только равенство и только без единицы в факте
        x = dec(v.text)
        return x is not None and fact.get("unit_key") is None and fi.contains(x)
    if v.interval is None:
        return False
    fu = fact.get("unit_key")
    if fu is None:
        return fi.intersects(v.interval)
    if v.unit_key is None:
        return False          # у значения каталога нет единицы — проверить нельзя
    if unit_dimension(fu) != unit_dimension(v.unit_key):
        return False          # разные величины: В ≠ Вт, кг ≠ Вт
    # переводим интервал факта в единицу каталога
    with localcontext() as ctx:
        ctx.prec = 60
        factor = UNITS[fu][1] / UNITS[v.unit_key][1]
    return fi.scaled(factor).intersects(v.interval)


def char_compatible(fact: dict, ch: Char) -> bool:
    return any(value_compatible(fact, v) for v in ch.values)


def position_compatible(facts: list[dict], p: Position) -> bool:
    for f in facts:
        ch = p.chars.get(norm_text(f["property"]))
        if ch is None or not char_compatible(f, ch):
            return False
    return True


# ---------------------------------------------------------------- каталог
class Catalog:
    """Активные конечные позиции трёх направлений с характеристиками (только чтение)."""

    def __init__(self, db: Path | str = DEFAULT_DB, include_templates: bool = False):
        self.db = Path(db)
        con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            self.positions: dict[str, Position] = {}
            q = ("SELECT code, name, category, okpd2_code FROM positions "
                 "WHERE active = 1 AND category IS NOT NULL" + ("" if include_templates else " AND is_template = 0"))
            for code, name, cat, okpd2 in con.execute(q):
                self.positions[code] = Position(code, name, cat, okpd2)
            cc_key: dict[tuple[str, str], str] = {}
            for pc, cc, name, ctype, kind, req in con.execute(
                    "SELECT position_code, char_code, name, char_type, kind, is_required FROM characteristics "
                    "ORDER BY position_code, ord"):
                p = self.positions.get(pc)
                if p is None:
                    continue
                key = norm_text(name)
                if key not in p.chars:
                    p.chars[key] = Char(name, kind, bool(req), ctype)
                ch = p.chars[key]
                ch.kind = kind if ch.kind is None else min(ch.kind, kind or ch.kind)
                ch.required = ch.required or bool(req)
                cc_key[(pc, cc)] = key
            for pc, cc, vk, text, okei, okei_name, mn, mn_inc, mx, mx_inc, conc in con.execute(
                    "SELECT position_code, char_code, value_kind, text, okei_code, okei_name, min_value, "
                    "min_inclusive, max_value, max_inclusive, concrete_value FROM char_values "
                    "ORDER BY position_code, char_code, ord"):
                key = cc_key.get((pc, cc))
                if key is None or vk == "empty":
                    continue
                ch = self.positions[pc].chars[key]
                v = Value(vk, text=text, unit_key=OKEI.get(okei) if okei else None, okei_name=okei_name,
                          has_okei=bool(okei))
                if vk == "range":
                    v.interval = Interval(dec(mn), bool(mn_inc), dec(mx), bool(mx_inc))
                elif vk == "concrete":
                    x = dec(conc)
                    v.interval = Interval.point(x) if x is not None else None
                ch.values.append(v)
        finally:
            con.close()
        self.by_name: dict[str, list[Position]] = {}
        for p in sorted(self.positions.values(), key=lambda p: p.code):
            self.by_name.setdefault(p.name, []).append(p)

    def gold(self, name: str, facts: list[dict]) -> list[str]:
        return [p.code for p in self.by_name.get(name, []) if position_compatible(facts, p)]

    def expect(self, name: str | None, facts: list[dict]) -> tuple[list[str], str]:
        """(gold_codes, expect) по правилам эталона."""
        if name is None:
            return [], "no_code"
        g = self.gold(name, facts)
        if not g:
            return [], "no_code"
        if len(g) == 1:
            stated = {norm_text(f["property"]) for f in facts}
            if self.positions[g[0]].must_state() <= stated:
                return g, "code_required"
        return g, "code_after_questions"
