"""Нормализация запроса с сохранением истории преобразований.

Сохраняет числа, единицы, отрицания, коды и модели; ничего не удаляет из смысла.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Step
from ..text import NEGATIONS, STOPWORDS, is_known_word, lemma
from ..units import AMBIGUOUS_SHORT, lookup

_STEPS = [
    ("регистр и ё", lambda s: s.lower().replace("ё", "е"), "нижний регистр, ё → е"),
    ("пробелы", lambda s: re.sub(r"\s+", " ", s).strip(), "схлопнуты пробелы"),
    ("кв. и куб. единицы", lambda s: re.sub(r"\bкв\.?\s*(мм|см|м)\b", r"\g<1>2",
                                           re.sub(r"\bкуб\.?\s*(мм|см|м)\b", r"\g<1>3", s)),
     "«кв. м» → «м2», «куб. м» → «м3»"),
    ("разделитель размеров", lambda s: re.sub(r"(?<=\d)\s*[xх×*]\s*(?=\d)", " x ", s),
     "«120х60» → «120 x 60»"),
    ("число и единица", lambda s: re.sub(r"(?<=\d)(?=[a-zа-я°\"%])", " ", s), "«75см» → «75 см»"),
    ("сокращения", lambda s: re.sub(r"\b(мм|см|м|кг|гр|шт|вт|квт|мин)\.(?=\s|$|,)", r"\1", s),
     "точка после сокращения единицы"),
]

TOKEN_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)"
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

    def lemmas(self) -> list[str]:
        return [t.lemma for t in self.tokens if t.significant]


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
    s = original
    for name, fn, note in _STEPS:
        new = fn(s)
        if new != s:
            history.append(Step(step=name, before=s, after=new, note=note))
            s = new
    tokens = tokenize_query(s)
    lem = [f"{t.text}→{t.lemma}" for t in tokens if t.kind == "word" and t.lemma != t.text]
    if lem:
        history.append(Step(step="словоформы", before=s, after=" ".join(t.lemma for t in tokens),
                            note="леммы: " + ", ".join(lem[:30])))
    return NormalizedQuery(original, s, tokens, history)
