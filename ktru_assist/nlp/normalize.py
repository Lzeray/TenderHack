"""Нормализация запроса с сохранением истории преобразований и карты координат.

Сохраняет числа, единицы, отрицания, коды и модели; ничего не удаляет из смысла.
Для каждого символа нормализованного текста хранится интервал исходного текста
(Unicode code points), из которого он получен: `NormalizedQuery.raw_span` переводит
координаты нормализованного текста в координаты исходного.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Step
from ..text import NEGATIONS, STOPWORDS, is_known_word, lemma
from ..units import AMBIGUOUS_SHORT, lookup

def _tolerance(m: re.Match) -> str:
    """«140±5» → «от 135 до 145»; «600±10%» → «от 540 до 660». Decimal, без округления."""
    from decimal import Decimal
    from ..units import fmt
    a, d = Decimal(m.group(1).replace(",", ".")), Decimal(m.group(2).replace(",", "."))
    if m.group(3):
        d = a * d / 100
    return f"от {fmt(a - d)} до {fmt(a + d)}"


# Преобразования: (название, [(шаблон, замена)], пояснение). Регистр обрабатывается отдельно.
_STEPS = [
    ("пробелы", [(r"\s+", " "), (r"^ | $", "")], "схлопнуты пробелы"),
    ("кв. и куб. единицы", [(r"\bкуб\.?\s*(мм|см|м)\b", r"\g<1>3"), (r"\bкв\.?\s*(мм|см|м)\b", r"\g<1>2")],
     "«кв. м» → «м2», «куб. м» → «м3»"),
    ("тире в диапазоне", [(r"(?<=\d)\s*[–—]\s*(?=\d)", "-")], "«1200–1400» → «1200-1400»"),
    # пробел-разделитель разрядов: только «1 200 мм» (одна цифра, пробел, три цифры, единица), чтобы не склеить
    # «рост 98 104 см» или «размер 52 176»
    ("разряды", [(r"(?<![\d.,])([1-9]) (\d{3})(?!\d)(?=\s*(?:мм|см|м|кг|г|гр|вт|квт|л|мл)(?![а-я]))", r"\1\2")],
     "«1 200 мм» → «1200 мм»"),
    ("допуск", [(r"(\d+(?:[.,]\d+)?)\s*(?:±|\+/-|\+-)\s*(\d+(?:[.,]\d+)?)(\s*%)?", _tolerance)],
     "«140±5» → «от 135 до 145», «600 ± 10 %» → «от 540 до 660»"),
    ("приблизительно", [(r"~\s*(?=\d)", "около ")], "«~140» → «около 140»"),
    ("разделитель размеров", [(r"(?<=\d)\s*[xх×*]\s*(?=\d)", " x "),
                               # «120 на 60 на 75», «120 см на 60 см» (габариты); «стол на 4 ножках» не трогаем
                               (r"(?<=\d)\s+на\s+(?=\d)", " x "),
                               (r"(\d\s*(?:мм|см|м))\s+на\s+(?=\d)", r"\1 x "),
                               (r"(\d\s*(?:мм|см|м))\s*[xх×*]\s*(?=\d)", r"\1 x ")],
     "«120х60», «120 на 60» → «120 x 60»"),
    ("число и единица", [(r"(?<=\d)(?=[a-zа-я°\"%])", " ")], "«75см» → «75 см»"),
    ("сокращения", [(r"\b(мм|см|м|кг|гр|шт|вт|квт|мин)\.(?=\s|$|,)", r"\1")], "точка после сокращения единицы"),
    # одежда: «р.66», «р-р 44», «разм. 48» → «размер»; «размер 48/170-176» (размер/рост) → «размер 48 рост 170-176»
    # Российский размер — не больше 74; обхват груди в нотации спецодежды («р. 88», «р. 104-108») — от 76,
    # детский рост («р.146») — трёхзначный: их в «размер» не превращаем. Рост в нотации «размер/рост» — в см.
    ("обозначение размера", [(r"(?<![а-я0-9])(?:р-р|разм\.?|р\.)\s*(?=([1-6]\d|7[0-4])(?!\d))", "размер "),
                              (r"(размер\s*[-:]?\s*\d{2}(?:-\d{2})?)\s*/\s*(\d{3}(?:-\d{3})?)(?!\d)(?!\s*см)",
                               r"\1 рост \2 см"),
                              (r"(размер\s*[-:]?\s*\d{2}(?:-\d{2})?)\s*/\s*(?=\d{3})", r"\1 рост ")],
     "«р.66» → «размер 66», «размер 48/170» → «размер 48 рост 170 см»"),
]


class Tracked:
    """Строка с картой: для каждого символа — (начало, конец) в исходном тексте."""

    def __init__(self, text: str):
        self.text = text
        self.map: list[tuple[int, int]] = [(i, i + 1) for i in range(len(text))]

    def lower(self) -> None:
        chars, mp = [], []
        for ch, m in zip(self.text, self.map):
            low = ch.lower().replace("ё", "е")
            chars.append(low)
            mp.extend([m] * len(low))
        self.text, self.map = "".join(chars), mp

    def sub(self, pattern: str, repl) -> None:
        """repl — шаблон re или функция от совпадения (для вычисляемых замен, например «140±5»)."""
        out, mp, pos = [], [], 0
        for m in re.finditer(pattern, self.text):
            out.append(self.text[pos:m.start()])
            mp.extend(self.map[pos:m.start()])
            new = repl(m) if callable(repl) else m.expand(repl)
            if m.end() > m.start():
                lo, hi = self.map[m.start()][0], self.map[m.end() - 1][1]
            else:  # вставка: привязка к соседнему символу нулевой ширины
                at = self.map[m.start()][0] if m.start() < len(self.map) else (self.map[-1][1] if self.map else 0)
                lo = hi = at
            out.append(new)
            mp.extend([(lo, hi)] * len(new))
            pos = m.end()
        out.append(self.text[pos:])
        mp.extend(self.map[pos:])
        self.text, self.map = "".join(out), mp

TOKEN_RE = re.compile(
    r"(?P<num>(?:(?<![\w.,])-)?\d+(?:[.,]\d+)?)"   # знак минуса — только не внутри «10-20»
    r"|(?P<unit>об/мин|г/м2|м3/ч|л/мин|м/мин|г/мин|а\*ч|а·ч|ма\*ч|ма·ч|н\*м|н·м|°c|°с|%|\")"
    r"|(?P<cmp>>=|<=|≥|≤|>|<)"
    r"|(?P<word>[a-zа-я0-9]+(?:[-/][a-zа-я0-9]+)*)"
    r"|(?P<punct>[:;,()=])",
)


@dataclass
class Token:
    i: int
    text: str
    start: int
    end: int
    kind: str           # number | unit | word | code | cmp | punct
    lemma: str = ""
    unit_key: str | None = None
    used_by: str | None = None   # кем «объяснён» токен: type / feature id

    @property
    def significant(self) -> bool:
        return self.kind in ("word", "code") and self.lemma not in STOPWORDS and self.lemma not in NEGATIONS \
            and len(self.text) > 1


@dataclass
class NormalizedQuery:
    original: str
    text: str
    tokens: list[Token]
    history: list[Step] = field(default_factory=list)
    offsets: list[tuple[int, int]] = field(default_factory=list)

    def lemmas(self) -> list[str]:
        return [t.lemma for t in self.tokens if t.significant]

    def raw_span(self, start: int, end: int) -> tuple[int, int] | None:
        """Координаты [start, end) нормализованного текста → координаты исходного текста."""
        if not self.offsets or start >= end or end > len(self.offsets):
            return None
        part = self.offsets[start:end]
        return min(a for a, _ in part), max(b for _, b in part)

    def raw_quote(self, start: int, end: int) -> str | None:
        rs = self.raw_span(start, end)
        return self.original[rs[0]:rs[1]] if rs else None


def _classify_word(w: str) -> str:
    has_digit = any(c.isdigit() for c in w)
    has_latin = bool(re.search("[a-z]", w))
    if has_digit or (has_latin and len(w) <= 3) or (has_latin and not is_known_word(w)):
        return "code"  # модели, артикулы, коды: не лемматизируются и не исправляются
    return "word"


def tokenize_query(text: str) -> list[Token]:
    toks: list[Token] = []
    for m in TOKEN_RE.finditer(text):
        kind = m.lastgroup
        s = m.group()
        t = Token(len(toks), s, m.start(), m.end(), kind)
        if kind == "num":
            t.kind = "number"
            t.lemma = s.replace(",", ".")
        elif kind == "unit":
            u = lookup(s)
            t.kind, t.lemma, t.unit_key = "unit", s, (u.key if u else None)
        elif kind == "cmp":
            t.lemma = s
        elif kind == "punct":
            t.lemma = s
        else:
            t.kind = _classify_word(s)
            t.lemma = s if t.kind == "code" else lemma(s)
        toks.append(t)
    # единицы-слова: только сразу после числа (иначе «в», «м», «а» — предлоги/буквы)
    for j, t in enumerate(toks):
        if t.kind not in ("word", "code"):
            continue
        u = lookup(t.text)
        if u is None:
            continue
        prev = toks[j - 1] if j else None
        after_number = prev is not None and prev.kind == "number"
        if t.text in AMBIGUOUS_SHORT and not after_number:
            continue
        if after_number or t.text not in AMBIGUOUS_SHORT and len(t.text) <= 4:
            t.kind, t.unit_key = "unit", u.key
    for j, t in enumerate(toks):
        t.i = j
    return toks


def normalize(original: str) -> NormalizedQuery:
    history: list[Step] = []
    tr = Tracked(original)
    tr.lower()
    if tr.text != original:
        history.append(Step(step="регистр и ё", before=original, after=tr.text, note="нижний регистр, ё → е"))
    for name, rules, note in _STEPS:
        before = tr.text
        for pattern, repl in rules:
            tr.sub(pattern, repl)
        if tr.text != before:
            history.append(Step(step=name, before=before, after=tr.text, note=note))
    s = tr.text
    tokens = tokenize_query(s)
    lem = [f"{t.text}→{t.lemma}" for t in tokens if t.kind == "word" and t.lemma != t.text]
    if lem:
        history.append(Step(step="словоформы", before=s, after=" ".join(t.lemma for t in tokens),
                            note="леммы: " + ", ".join(lem[:30])))
    return NormalizedQuery(original, s, tokens, history, tr.map)
