"""Единицы измерения: распознавание, размерность и точный перевод (Decimal).

Перевод выполняется только между единицами одной размерности. Коэффициенты точные
(степени 10 и 25,4 мм для дюйма). Разные величины (В и Вт, кг и мм) не сравниваются.
Единицы без коэффициента (°C, градусы угла, об/мин) сравниваются только сами с собой.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .text import norm


@dataclass(frozen=True)
class Unit:
    key: str
    title: str
    dimension: str
    factor: Decimal  # множитель к базовой единице размерности
    okei: tuple[str, ...]
    aliases: tuple[str, ...]


D = Decimal
UNITS: list[Unit] = [
    Unit("mm", "мм", "length", D("0.001"), ("003",), ("мм", "миллиметр", "mm")),
    Unit("cm", "см", "length", D("0.01"), ("004",), ("см", "сантиметр", "cm")),
    Unit("dm", "дм", "length", D("0.1"), ("005",), ("дм", "дециметр")),
    Unit("m", "м", "length", D("1"), ("006",), ("м", "метр", "m")),
    Unit("km", "км", "length", D("1000"), ("008",), ("км", "километр")),
    Unit("inch", "дюйм", "length", D("0.0254"), ("039",), ("дюйм", "\"", "inch")),
    Unit("mm2", "мм²", "area", D("0.000001"), ("050",), ("мм2", "мм²", "кв мм", "квадратный миллиметр")),
    Unit("cm2", "см²", "area", D("0.0001"), ("051",), ("см2", "см²", "квадратный сантиметр")),
    Unit("m2", "м²", "area", D("1"), ("055",), ("м2", "м²", "кв м", "квадратный метр")),
    Unit("mg", "мг", "mass", D("0.000001"), ("161",), ("мг", "миллиграмм")),
    Unit("g", "г", "mass", D("0.001"), ("163",), ("г", "гр", "грамм")),
    Unit("kg", "кг", "mass", D("1"), ("166",), ("кг", "килограмм")),
    Unit("t", "т", "mass", D("1000"), ("168",), ("т", "тонна")),
    Unit("ml", "мл", "volume", D("0.001"), ("111",), ("мл", "миллилитр")),
    Unit("l", "л", "volume", D("1"), ("112",), ("л", "литр")),
    Unit("m3", "м³", "volume", D("1000"), ("113",), ("м3", "м³", "кубический метр")),
    Unit("w", "Вт", "power", D("1"), ("212",), ("вт", "ватт", "w")),
    Unit("kw", "кВт", "power", D("1000"), ("214",), ("квт", "киловатт", "kw")),
    Unit("v", "В", "voltage", D("1"), ("222",), ("в", "вольт", "v")),
    Unit("kv", "кВ", "voltage", D("1000"), ("223",), ("кв", "киловольт")),
    Unit("a", "А", "current", D("1"), ("260",), ("а", "ампер")),
    Unit("ah", "А·ч", "charge", D("1"), ("263",), ("ач", "а·ч", "а*ч", "ампер-час", "ah")),
    Unit("mah", "мА·ч", "charge", D("0.001"), ("2621",), ("мач", "ма·ч", "ма*ч", "миллиампер-час", "mah")),
    Unit("hz", "Гц", "frequency", D("1"), ("290",), ("гц", "герц")),
    Unit("rpm", "об/мин", "rotation", D("1"), ("331",), ("об/мин", "оборот в минуту", "rpm")),
    Unit("celsius", "°C", "temperature_c", D("1"), ("280",), ("°c", "°с", "градус цельсия")),
    Unit("deg", "°", "angle", D("1"), ("2355",), ("градус", "°")),
    Unit("min", "мин", "time", D("60"), ("355",), ("мин", "минута")),
    Unit("h", "ч", "time", D("3600"), ("356",), ("ч", "час")),
    Unit("m3h", "м³/ч", "flow", D("1"), ("598",), ("м3/ч", "м³/ч", "кубический метр в час")),
    Unit("nm", "Н·м", "torque", D("1"), (), ("нм", "н·м", "н*м", "ньютон-метр")),
    Unit("pcs", "шт", "count", D("1"), ("796",), ("шт", "штука")),
    Unit("pct", "%", "percent", D("1"), ("744",), ("%", "процент")),
    Unit("gm2", "г/м²", "surface_density", D("1"), (), ("г/м2", "г/м²")),
    Unit("lmin", "л/мин", "flow_l", D("1"), (), ("л/мин",)),
    Unit("mmin", "м/мин", "speed_m", D("1"), (), ("м/мин",)),
    Unit("gmin", "г/мин", "rate_g", D("1"), (), ("г/мин",)),
]

BY_KEY = {u.key: u for u in UNITS}
BY_OKEI = {code: u for u in UNITS for code in u.okei}
_ALIASES: dict[str, Unit] = {}
for _u in UNITS:
    for _a in _u.aliases:
        _ALIASES[norm(_a)] = _u
# Формы, которые пишут в тексте (словоформы и сокращения с точкой обрабатываются в нормализаторе).
_WORD_FORMS = {
    "миллиметра": "мм", "миллиметров": "мм", "сантиметра": "см", "сантиметров": "см", "метра": "м",
    "метров": "м", "килограмма": "кг", "килограммов": "кг", "грамма": "г", "граммов": "г",
    "ватта": "вт", "ватт": "вт", "вольта": "в", "вольт": "в", "литра": "л", "литров": "л",
    "дюйма": "дюйм", "дюймов": "дюйм", "ампер": "а", "оборотов": "об/мин", "градусов": "градус",
}

# Единицы, которые слишком легко спутать с предлогами/словами — распознаются только сразу после числа.
AMBIGUOUS_SHORT = {"в", "а", "т", "г", "м", "ч", "л"}


def lookup(token: str) -> Unit | None:
    t = norm(token).strip(".")
    t = _WORD_FORMS.get(t, t)
    return _ALIASES.get(t)


def from_okei(code: str | None, name: str | None) -> Unit | None:
    if code and code in BY_OKEI:
        return BY_OKEI[code]
    if name:
        return lookup(name)
    return None


_NAME_UNIT_RE = re.compile(r"(?:\(([^()]+)\)\s*$|,\s*([^,]+)$)")


def unit_from_char_name(name: str) -> Unit | None:
    """Единица, записанная в наименовании характеристики: «Момент (Нм)», «Плотность, г/м2»."""
    m = _NAME_UNIT_RE.search(name.strip())
    if not m:
        return None
    return lookup((m.group(1) or m.group(2) or "").strip())


def convert(value: Decimal, src: Unit, dst: Unit) -> Decimal | None:
    """Точный перевод; None, если размерности несовместимы."""
    if src.dimension != dst.dimension:
        return None
    if src.key == dst.key:
        return value
    return value * src.factor / dst.factor


def fmt(value: Decimal) -> str:
    """Decimal без экспоненты и лишних нулей: 750.000 → 750, 0.50 → 0,5."""
    s = format(value.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")
