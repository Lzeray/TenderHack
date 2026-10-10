"""Извлечение характеристик из текста и привязка к свойствам КТРУ.

Привязка выполняется только к свойствам позиций текущей области поиска (domain) и только
при однозначном соответствии. Иначе признак возвращается как «ambiguous» с вариантами
или как «unknown_property». Значимые слова, которые ничем не объяснены, возвращаются
отдельным списком (unrecognized).

Распознаваемые конструкции:
  1. «характеристика: значение» (разделители — запятая/точка с запятой);
  2. число [единица] рядом с названием свойства («длина 75 см», «3 выдвижных ящика»);
     сравнения «не менее/от/до/не более/более/менее», диапазон «от N до M», «N-M»;
  3. число с единицей без названия — если в области ровно одно свойство такой размерности;
  4. логические свойства «Наличие X» / «Складная конструкция»: все ключевые слова названия
     рядом в тексте → «Да», с отрицанием («без», «не», «нет») → «Нет»;
  5. проверенные алиасы значений (data/value_aliases.json: «сетевой» → «Тип питания» = «От сети»);
  6. качественные значения справочника («слесарные», «аккумуляторный») с учётом отрицания.

Части товара: если рядом со значением названа часть («чёрный каркас»), значение привязывается
только к свойству этой части («Цвет каркаса»). Свойство другой части («Цвет сиденья») не подходит,
общее свойство без части («Цвет») — только через выбор пользователя.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache

from ..catalog.repository import Position, Prop
from ..components import canonical_key, component_of_lemma, property_component
from ..config import ROOT
from ..models import Feature
from ..text import NEGATIONS, STOPWORDS, content_lemmas, fuzzy_equal, head_lemma, lemma, lemma_set, norm, tokenize
from ..units import BY_KEY, fmt
from .normalize import NormalizedQuery, Token

GENERIC_NAME_WORDS = lemma_set({"наличие", "вид", "тип", "функция", "возможность", "количество", "показатель",
                                "конструкция", "значение", "характеристика", "исполнение"})
GE_WORDS = {("не", "менее"), ("не", "меньше"), ("не", "ниже"), ("от",), ("более",), ("больше",),
            ("свыше",), (">=",), ("≥",), (">",), ("минимум",)}
LE_WORDS = {("не", "более"), ("не", "больше"), ("не", "выше"), ("до",), ("менее",), ("меньше",),
            ("<=",), ("≤",), ("<",), ("максимум",)}
STRICT = {("более",), ("больше",), ("свыше",), (">",), ("менее",), ("меньше",), ("<",)}
BOUNDARY = {",", ";", ":", "(", ")"}


@dataclass
class PropGroup:
    key: str
    name: str
    codes: list[str]
    numeric: bool
    boolean: bool
    dims: set[str]
    unit_keys: set[str]
    quality: dict[str, str]           # норм. текст → исходный текст
    value_lemmas: dict[str, tuple]    # норм. текст → леммы значения
    terms: list[str]                  # ключевые леммы наименования
    required: bool
    positions: int = 0
    unit_in_name: str | None = None
    core: str | None = None           # главное существительное названия («Российский размер» → «размер»)
    component: str | None = None      # часть товара («Цвет каркаса» → frame)
    canonical: str | None = None      # внутренний ключ «компонент.свойство»


def _core_noun(name: str) -> str | None:
    words = [w for w in tokenize(name) if not w[0].isdigit() and lemma(w) not in GENERIC_NAME_WORDS]
    h = head_lemma(" ".join(words)) if words else None
    return h


def build_groups(positions: list[Position]) -> dict[str, PropGroup]:
    groups: dict[str, PropGroup] = {}
    for p in positions:
        for prop in p.props.values():
            key = prop.norm_name
            g = groups.get(key)
            if g is None:
                terms = [t for t in content_lemmas(prop.name) if t not in GENERIC_NAME_WORDS]
                if not terms:
                    terms = content_lemmas(prop.name)
                g = groups[key] = PropGroup(key, prop.name, [], False, True, set(), set(), {}, {}, terms, False)
                g.core = _core_noun(prop.name)
                g.component = property_component(prop.name)
                g.canonical = canonical_key(prop.name, g.core)
            if prop.code not in g.codes:
                g.codes.append(prop.code)
            g.positions += 1
            g.numeric |= prop.is_numeric
            g.boolean &= prop.is_boolean
            g.required |= prop.required
            for u in prop.units:
                g.dims.add(u.dimension)
                g.unit_keys.add(u.key)
            if prop.name_unit:
                g.unit_in_name = prop.name_unit.key
            for v in prop.values:
                if v.kind == "quality" and v.text:
                    g.quality.setdefault(norm(v.text), v.text)
                    g.value_lemmas.setdefault(norm(v.text), v.lemmas)
    for g in groups.values():
        g.codes.sort()
        if not g.quality:
            g.boolean = False
    return groups


@dataclass
class ExtractionResult:
    features: list[Feature] = field(default_factory=list)


def _lemma_at(tokens: list[Token], i: int) -> str:
    return tokens[i].lemma if 0 <= i < len(tokens) else ""


def _window(tokens: list[Token], i: int, back: int, fwd: int) -> list[int]:
    """Индексы соседних токенов без пересечения границ сегмента и других чисел."""
    out = []
    j = i - 1
    while j >= 0 and i - j <= back and tokens[j].lemma not in BOUNDARY and tokens[j].kind != "number":
        out.append(j)
        j -= 1
    j = i + 1
    while j < len(tokens) and j - i <= fwd and tokens[j].lemma not in BOUNDARY and tokens[j].kind != "number":
        out.append(j)
        j += 1
    return out


def _terms_present(terms: list[str], tokens: list[Token], idxs: list[int]) -> list[int] | None:
    """Все ключевые леммы присутствуют среди idxs → индексы найденных токенов.

    Если слово встречается несколько раз, выбирается сочетание вхождений с минимальным
    разбросом позиций («мягким сиденьем и мягкой спинкой» → второе «мягкой» для спинки).
    """
    if not terms:
        return None
    occ = []
    for t in terms:
        hits = [i for i in idxs if tokens[i].kind in ("word", "code")
                and fuzzy_equal(PROPERTY_SYNONYMS.get(tokens[i].lemma, tokens[i].lemma), t)]
        if not hits:
            return None
        occ.append(sorted(hits))
    best = None
    for combo in itertools.product(*occ):
        if len(set(combo)) < len(combo):
            continue
        span = max(combo) - min(combo)
        if best is None or (span, combo) < best:
            best = (span, combo)
    return list(best[1]) if best else None


# Синонимы слов в названиях свойств (проверенные вручную по каталогу).
PROPERTY_SYNONYMS = {lemma("вес"): lemma("масса")}


@dataclass(frozen=True)
class ValueAlias:
    phrase: tuple[str, ...]
    property: str
    value: str


@lru_cache(maxsize=1)
def value_aliases() -> tuple[ValueAlias, ...]:
    path = ROOT / "data" / "value_aliases.json"
    if not path.exists():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for a in raw["aliases"]:
        ph = tuple(content_lemmas(a["phrase"])) or (lemma(a["phrase"]),)
        out.append(ValueAlias(ph, a["property"], a["value"]))
    return tuple(sorted(out, key=lambda a: (-len(a.phrase), a.phrase, a.property)))


def value_aliases_version() -> str:
    path = ROOT / "data" / "value_aliases.json"
    return json.loads(path.read_text(encoding="utf-8"))["version"] if path.exists() else "-"


def _component_near(tokens: list[Token], idxs: list[int], dist: int = 2,
                    forward_only: bool = False, include_self: bool = False,
                    exclude: frozenset[int] = frozenset()) -> tuple[str, int] | None:
    """Часть товара, названная вплотную к значению (± dist слов, без пересечения границ и чисел).

    forward_only — для названий свойств: часть стоит после них в родительном падеже («высота каркаса»).
    include_self — часть может быть словом самого найденного названия свойства («высота сиденья»);
    для значений не используется: «ножки» — это значение «Тип опоры», а не часть товара.
    Слова, уже объяснённые другим признаком («масса головки», «металлическом каркасе»), не считаются.
    """
    if include_self:
        for j in idxs:
            c = component_of_lemma(tokens[j].lemma) if tokens[j].kind == "word" else None
            if c:
                return c, j
    lo, hi = min(idxs), max(idxs)
    order = []
    for d in range(1, dist + 1):
        order += [hi + d] if forward_only else [hi + d, lo - d]
    for j in order:
        if not (0 <= j < len(tokens)):
            continue
        between = range(min(j, lo) + 1, max(j, hi)) if j > hi or j < lo else []
        if any(tokens[k].lemma in BOUNDARY or tokens[k].kind == "number" for k in between):
            continue
        t = tokens[j]
        if t.kind != "word" or t.lemma in BOUNDARY or t.used_by is not None or j in exclude:
            continue
        c = component_of_lemma(t.lemma)
        if c:
            return c, j
    return None


def _core_present(g: "PropGroup", tokens: list[Token], idxs: list[int]) -> int | None:
    """Первое ключевое слово названия свойства («Длина режущей части» → «длина») среди idxs."""
    core = g.core or (g.terms[0] if g.terms else None)
    if not core:
        return None
    for i in idxs:
        lem = PROPERTY_SYNONYMS.get(tokens[i].lemma, tokens[i].lemma)
        if tokens[i].kind == "word" and fuzzy_equal(lem, core):
            return i
    return None


def _negated(tokens: list[Token], first: int) -> bool:
    for j in (first - 1, first - 2):
        if j >= 0 and tokens[j].lemma in NEGATIONS:
            # «не менее» — это сравнение, а не отрицание значения
            if tokens[j].lemma == "не" and _lemma_at(tokens, j + 1) in ("менее", "меньше", "более", "больше",
                                                                          "ниже", "выше"):
                continue
            return True
    return False


class Extractor:
    def __init__(self, groups: dict[str, PropGroup], known_terms: set[str] | None = None,
                 name_tokens: set[int] | None = None):
        self.groups = groups
        # индексы токенов, которыми в описании записано наименование типа
        self.name_tokens = frozenset(name_tokens or ())
        # ключевые слова названий свойств по всему каталогу MVP: чтобы отличать «нет такого
        # свойства у этого типа» от «непонятного слова»
        self.known_terms = known_terms or set()
        self.counter = itertools.count(1)

    def _fid(self) -> str:
        return f"f{next(self.counter)}"

    @staticmethod
    def _opt(g: PropGroup) -> dict:
        return {"property_code": g.codes[0], "property_name": g.name, "codes": g.codes}

    def _feature(self, g: PropGroup | None, tokens: list[Token], idxs: list[int], nq: NormalizedQuery,
                 status: str = "bound", **kw) -> Feature:
        idxs = sorted(set(idxs))
        span = (tokens[idxs[0]].start, tokens[idxs[-1]].end) if idxs else None
        fid = self._fid()
        for i in idxs:
            if tokens[i].used_by is None:
                tokens[i].used_by = fid
        raw = nq.raw_span(*span) if span else None
        kw.setdefault("component", g.component if g else None)
        return Feature(id=fid, source="text", status=status,
                       property_code=g.codes[0] if g else None, property_name=g.name if g else None,
                       evidence=nq.text[span[0]:span[1]] if span else None, span=span, raw_span=raw,
                       canonical_key=g.canonical if g else None, **kw)

    # ------------------------------------------------------------------
    def extract(self, nq: NormalizedQuery) -> list[Feature]:
        self._nq_text = nq.text
        feats: list[Feature] = []
        feats += self._explicit_pairs(nq)
        feats += self._numbers(nq)
        feats += self._booleans(nq)
        feats += self._value_aliases(nq)
        # свойства, уже заданные явно или найденные раньше, не получают значение только из слов наименования
        self._bound_keys = {" ".join(tokenize(f.property_name)) for f in feats
                            if f.status == "bound" and f.property_name}
        feats += self._qualities(nq)
        return feats

    # 5. алиасы значений --------------------------------------------------------
    def _value_aliases(self, nq: NormalizedQuery) -> list[Feature]:
        tokens = nq.tokens
        feats = []
        words = [t for t in tokens if t.kind == "word"]
        for a in value_aliases():
            g = self.groups.get(" ".join(tokenize(a.property)))
            if g is None or norm(a.value) not in g.quality:
                continue  # свойства или значения нет у позиций области — алиас не применяется
            n = len(a.phrase)
            for k in range(len(words) - n + 1):
                seq = words[k:k + n]
                if any(t.used_by for t in seq) or not all(t.lemma == p for t, p in zip(seq, a.phrase)):
                    continue
                idxs = [t.i for t in seq]
                # «от электросети»: предлог перед фразой тоже объяснён алиасом
                if idxs[0] > 0 and tokens[idxs[0] - 1].lemma == "от":
                    idxs.insert(0, idxs[0] - 1)
                neg = _negated(tokens, idxs[0])
                extra = [j for j in (idxs[0] - 1, idxs[0] - 2) if neg and j >= 0 and tokens[j].lemma in NEGATIONS]
                feats.append(self._feature(g, tokens, idxs + extra, nq, op="ne" if neg else "eq",
                                           value=g.quality[norm(a.value)], negated=neg,
                                           note=f"проверенный алиас значения «{' '.join(t.text for t in seq)}» → "
                                                f"«{a.value}» (data/value_aliases.json)"))
        return feats

    # 1. «характеристика: значение» ---------------------------------------
    def _match_name(self, lemmas: list[str]) -> list[PropGroup]:
        best, best_len = [], 0
        for g in self.groups.values():
            if not g.terms:
                continue
            if all(any(fuzzy_equal(l, t) for l in lemmas) for t in g.terms):
                if len(g.terms) > best_len:
                    best, best_len = [g], len(g.terms)
                elif len(g.terms) == best_len:
                    best.append(g)
        return sorted(best, key=lambda g: g.key)

    def _explicit_pairs(self, nq: NormalizedQuery) -> list[Feature]:
        tokens = nq.tokens
        feats = []
        seg: list[int] = []
        segments = []
        for t in tokens:
            if t.lemma in (",", ";"):
                segments.append(seg)
                seg = []
            else:
                seg.append(t.i)
        segments.append(seg)
        for seg in segments:
            colons = [i for i in seg if tokens[i].lemma == ":"]
            if not colons:
                continue
            colon = colons[-1]
            prev_colon = colons[-2] if len(colons) > 1 else -1
            left = [i for i in seg if prev_colon < i < colon and tokens[i].kind in ("word", "code")]
            right = [i for i in seg if i > colon]
            if not left or not right:
                continue
            left_lemmas = [tokens[i].lemma for i in left if tokens[i].lemma not in STOPWORDS]
            groups = [g for g in self._match_name(left_lemmas)
                      if all(l in GENERIC_NAME_WORDS or any(fuzzy_equal(l, n) for n in content_lemmas(g.name))
                             for l in left_lemmas)]
            raw_value = nq.text[tokens[right[0]].start:tokens[right[-1]].end]
            if not groups:
                feats.append(self._feature(None, tokens, left + [colon] + right, nq, status="unknown_property",
                                           value=raw_value, note="в области поиска нет свойства с таким названием: "
                                           + nq.text[tokens[left[0]].start:tokens[left[-1]].end]))
                continue
            if len(groups) > 1:
                feats.append(self._feature(None, tokens, left + [colon] + right, nq, status="ambiguous",
                                           value=raw_value, options=[self._opt(g) for g in groups],
                                           note="название подходит к нескольким свойствам"))
                continue
            g = groups[0]
            num = self._parse_number_expr(tokens, right[0], set(right))
            if num is not None and g.numeric:
                op, v1, v2, lo_inc, hi_inc, unit_key, used = num
                feats.append(self._feature(g, tokens, left + [colon] + used, nq, op=op, value=fmt(v1),
                                           value_to=fmt(v2) if v2 is not None else None, min_inclusive=lo_inc,
                                           max_inclusive=hi_inc, unit=BY_KEY[unit_key].title if unit_key else None,
                                           note="конструкция «характеристика: значение»"))
                continue
            neg = tokens[right[0]].lemma in NEGATIONS
            val_idx = right[1:] if neg else right
            text_value = nq.text[tokens[val_idx[0]].start:tokens[val_idx[-1]].end] if val_idx else raw_value
            matched = self._match_quality_text(g, text_value)
            feats.append(self._feature(g, tokens, left + [colon] + right, nq, op="ne" if neg else "eq",
                                       value=matched or text_value, negated=neg,
                                       note="конструкция «характеристика: значение»"
                                       + ("" if matched else "; значение не найдено среди допустимых")))
        return feats

    @staticmethod
    def _match_quality_text(g: PropGroup, text: str) -> str | None:
        n = norm(text).strip(" .")
        if n in g.quality:
            return g.quality[n]
        lem = tuple(content_lemmas(text))
        hits = [orig for k, orig in g.quality.items() if g.value_lemmas.get(k) == lem and lem]
        if len(hits) == 1:
            return hits[0]
        if g.boolean and lem:
            if lem[0] in ("да", "есть", "наличие", "с"):
                return g.quality.get("да")
            if lem[0] in ("нет", "отсутствовать", "без"):
                return g.quality.get("нет")
        return None

    # 2–3. числа ------------------------------------------------------------
    def _parse_number_expr(self, tokens: list[Token], i: int, allowed: set[int] | None = None):
        """Разбор числового выражения, начинающегося около токена i.

        Возвращает (op, v1, v2, lo_incl, hi_incl, unit_key, used_idxs) или None.
        """
        n = len(tokens)
        ok = (lambda k: allowed is None or k in allowed)
        # найти число начиная с i
        j = i
        prefix: list[int] = []
        while j < n and tokens[j].kind != "number" and ok(j) and j - i < 3:
            prefix.append(j)
            j += 1
        if j >= n or tokens[j].kind != "number" or not ok(j):
            return None
        pre = tuple(tokens[k].lemma for k in prefix)
        v1 = Decimal(tokens[j].lemma)
        used = prefix + [j]
        op, v2, lo_inc, hi_inc = "eq", None, True, True
        k = j + 1
        # диапазон «от N до M» / «N-M» / «N … M»
        if k + 1 < n and tokens[k].lemma == "до" and tokens[k + 1].kind == "number" and ok(k + 1):
            op, v2 = "between", Decimal(tokens[k + 1].lemma)
            used += [k, k + 1]
            k += 2
        elif k < n and tokens[k].kind == "number" and ok(k) and "-" in self._gap(tokens, j, k):
            op, v2 = "between", Decimal(tokens[k].lemma)
            used.append(k)
            k += 1
        unit_key = None
        if k < n and tokens[k].kind == "unit" and ok(k):
            unit_key = tokens[k].unit_key
            used.append(k)
        if op == "eq":
            # самое длинное совпадение: «не менее» (≥), а не «менее» (<)
            hits = [(len(w), w, "ge") for w in GE_WORDS if pre[-len(w):] == w] + \
                   [(len(w), w, "le") for w in LE_WORDS if pre[-len(w):] == w]
            if hits:
                _, words, kind = max(hits, key=lambda h: h[0])
                op = {"ge": "gt", "le": "lt"}[kind] if words in STRICT else kind
            if op == "eq":
                used = [j] + used[used.index(j) + 1:]
        return op, v1, v2, lo_inc, hi_inc, unit_key, used

    _nq_text: str = ""

    def _gap(self, tokens: list[Token], a: int, b: int) -> str:
        return self._nq_text[tokens[a].end:tokens[b].start]

    def _numbers(self, nq: NormalizedQuery) -> list[Feature]:
        self._nq_text = nq.text
        tokens = nq.tokens
        feats = []
        numeric_groups = [g for g in self.groups.values() if g.numeric]
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.kind != "number" or t.used_by is not None:
                i += 1
                continue
            start = i
            # отступить назад к словам сравнения
            while start > 0 and tokens[start - 1].lemma in ("не", "от", "до", "менее", "более", "меньше", "больше",
                                                             "свыше", "ниже", "выше", ">=", "<=", "≥", "≤", ">", "<",
                                                             "минимум", "максимум") and i - start < 2:
                start -= 1
            parsed = self._parse_number_expr(tokens, start)
            if parsed is None:
                i += 1
                continue
            op, v1, v2, lo_inc, hi_inc, unit_key, used = parsed
            unit = BY_KEY.get(unit_key) if unit_key else None
            dims_part = (i + 1 < len(tokens) and tokens[i + 1].text in ("x", "х")) or \
                        (i > 0 and tokens[i - 1].text in ("x", "х"))
            anchor = max(used)
            back_w = _window(tokens, min(used), 1 if dims_part else 4, 0)
            fwd_all = [] if dims_part else _window(tokens, anchor, 0, 3)
            # слово после числа, за которым сразу идёт другое число, у измеряемых свойств относится к
            # следующему числу: «92-96 рост 158-164» — «рост» описывает 158-164. У счётных — к предыдущему:
            # «4 ящика 40×60» — число стоит перед существительным
            fwd_strict = [k for k in fwd_all if not (k + 1 < len(tokens) and tokens[k + 1].kind == "number")]
            # слова, уже объяснённые другим признаком («4 ящика»), не называют свойство следующего числа
            free = lambda ks: [k for k in ks if tokens[k].used_by is None]  # noqa: E731
            win_count, win = free(back_w + fwd_all), free(back_w + fwd_strict)
            # кандидаты по размерности
            if unit is not None:
                cand = [g for g in numeric_groups if unit.dimension in g.dims]
            else:
                cand = numeric_groups
            # Явно названное свойство ищется среди всех числовых свойств области (не только той же
            # размерности): если пользователь написал «мощность 500 В», привязываем к «Мощность»,
            # а несовпадение В/Вт покажет валидатор, вместо того чтобы молча искать другое свойство.
            def named(groups, use_core: bool):
                out = []
                for g in groups:
                    w = win_count if g.dims == {"count"} else win
                    if use_core:
                        h = _core_present(g, tokens, w)
                        hit = [h] if h is not None else None
                    else:
                        hit = _terms_present(g.terms, tokens, w)
                    if hit is not None:
                        out.append((1 if use_core else len(g.terms), g, hit))
                return out
            explicit = named(cand, False) or named(numeric_groups, False) or \
                named(cand, True) or named(numeric_groups, True)
            if not explicit and unit is None and op == "eq":
                # качественное свойство с числовыми значениями («Российский размер»: 44, 46 …)
                textual = [g for g in self.groups.values() if not g.numeric and fmt(v1) in g.quality]
                explicit = named(textual, False) or named(textual, True)
            kw = dict(op=op, value=fmt(v1), value_to=fmt(v2) if v2 is not None else None,
                      min_inclusive=lo_inc, max_inclusive=hi_inc, unit=unit.title if unit else None)
            named_unknown = None
            part = None   # часть товара рядом с названием свойства не совпала со схемой
            if explicit:
                near = _component_near(tokens, sorted({h for e in explicit for h in e[2]}), forward_only=True, include_self=True)
                if near is not None:
                    same = [e for e in explicit if e[1].component == near[0]]
                    if same:
                        explicit = same
                    else:
                        part = (near, [e[1] for e in explicit if e[1].component is None])
            if part is not None:
                (comp, j), generic = part
                if generic:
                    feats.append(self._feature(None, tokens, used + [j], nq, status="ambiguous", component=comp,
                                               options=[self._opt(g) for g in sorted(generic, key=lambda g: g.key)],
                                               note=f"значение указано для части «{tokens[j].text}», а у позиций "
                                                    "свойство без указания части — подтвердите привязку", **kw))
                else:
                    feats.append(self._feature(None, tokens, used + [j], nq, status="unknown_property", component=comp,
                                               note=f"у позиций нет такого свойства для части «{tokens[j].text}»; "
                                                    "свойства других частей не подходят", **kw))
                i = anchor + 1
                continue
            if not explicit:
                back = [k for k in win if k < min(used) and min(used) - k <= 2]
                named_unknown = next((tokens[k] for k in sorted(back, reverse=True) if tokens[k].kind == "word"
                                      and PROPERTY_SYNONYMS.get(tokens[k].lemma, tokens[k].lemma) in self.known_terms),
                                     None)
            if named_unknown is not None:
                feats.append(self._feature(None, tokens, used + [named_unknown.i], nq, status="unknown_property",
                                           note=f"у позиций этого типа нет свойства «{named_unknown.text}» "
                                                "подходящей размерности", **kw))
            elif explicit:
                top = max(e[0] for e in explicit)
                best = [e for e in explicit if e[0] == top]
                if len({e[1].key for e in best}) == 1:
                    g, hit = best[0][1], best[0][2]
                    feats.append(self._feature(g, tokens, used + hit, nq, note="число рядом с названием свойства",
                                               **kw))
                else:
                    feats.append(self._feature(None, tokens, used, nq, status="ambiguous",
                                               options=[self._opt(e[1]) for e in sorted(best, key=lambda e: e[1].key)],
                                               note="рядом названия нескольких свойств", **kw))
            elif unit is not None and not dims_part:
                same_dim = sorted(cand, key=lambda g: g.key)
                if len(same_dim) == 1:
                    feats.append(self._feature(same_dim[0], tokens, used, nq,
                                               note=f"единственное свойство размерности «{unit.dimension}» в области",
                                               **kw))
                elif same_dim:
                    feats.append(self._feature(None, tokens, used, nq, status="ambiguous",
                                               options=[self._opt(g) for g in same_dim],
                                               note="несколько свойств такой размерности — укажите свойство", **kw))
                else:
                    other = [g for g in numeric_groups if g.dims]
                    feats.append(self._feature(None, tokens, used, nq, status="unknown_property",
                                               note=f"в области нет свойств с единицей размерности «{unit.dimension}»"
                                               + (f" (есть: {', '.join(sorted({d for g in other for d in g.dims}))})"
                                                  if other else ""), **kw))
            elif unit is not None and dims_part:
                same_dim = sorted(cand, key=lambda g: g.key)
                feats.append(self._feature(None, tokens, used, nq, status="ambiguous",
                                           options=[self._opt(g) for g in same_dim],
                                           note="габаритный размер без названия измерения", **kw))
            i = anchor + 1
        return feats

    # 4. логические свойства ----------------------------------------------------
    def _booleans(self, nq: NormalizedQuery) -> list[Feature]:
        tokens = nq.tokens
        feats = []
        word_idx = [t.i for t in tokens if t.kind in ("word", "code")]
        matches = []
        for g in sorted(self.groups.values(), key=lambda g: g.key):
            if not g.boolean or not g.terms:
                continue
            # каждое упоминание отдельно: «с мягким сиденьем …, без мягкого сиденья» — два признака,
            # противоречие между ними обнаруживает движок
            free = list(word_idx)
            while True:
                hit = _terms_present(g.terms, tokens, free)
                if hit is None or max(hit) - min(hit) > 3:
                    break
                matches.append((g, hit))
                free = [i for i in free if i not in hit]
        # если одно совпадение строго содержит другое (по токенам), оставить более полное
        kept = []
        for g, hit in matches:
            if any(set(hit) < set(h2) for _, h2 in matches):
                continue
            kept.append((g, hit))
        for g, hit in kept:
            if any(tokens[i].used_by for i in hit):
                continue
            neg = _negated(tokens, min(hit))
            val = g.quality.get("нет" if neg else "да")
            if val is None:
                continue
            idxs = list(hit)
            if neg:
                idxs += [j for j in (min(hit) - 1, min(hit) - 2) if j >= 0 and tokens[j].lemma in NEGATIONS]
            feats.append(self._feature(g, tokens, idxs, nq, value=val, negated=neg,
                                       note="логическое свойство: слова названия" + (" с отрицанием" if neg else "")))
        return feats

    # 6. качественные значения ---------------------------------------------------
    def _qualities(self, nq: NormalizedQuery) -> list[Feature]:
        tokens = nq.tokens
        feats = []
        by_token: dict[int, list[tuple[PropGroup, str, list[int]]]] = {}
        name_tok = self.name_tokens
        cands: list[tuple[PropGroup, str, list[int], bool]] = []
        for g in sorted(self.groups.values(), key=lambda g: g.key):
            if g.boolean or not g.quality:
                continue
            for nval, lem in sorted(g.value_lemmas.items()):
                lem = tuple(x for x in lem if x not in STOPWORDS and len(x) >= 3)
                if not lem:
                    continue
                others = {x for k, l2 in g.value_lemmas.items() if k != nval for x in l2}
                occ = {x: [t.i for t in tokens if t.kind == "word" and t.used_by is None and fuzzy_equal(t.lemma, x)]
                       for x in lem}
                full = all(occ[x] for x in lem)
                if not full:
                    # Частичное совпадение не может опираться на слова наименования типа:
                    # «перчатки … для защиты от внешних воздействий» не доказывает «От механических воздействий».
                    occ = {x: [i for i in o if i not in name_tok] for x, o in occ.items()}
                present = [x for x in lem if occ[x]]
                if not present:
                    continue
                # ближайшие вхождения; при равенстве — не занятые наименованием
                best_combo = min(itertools.product(*(occ[x] for x in present)),
                                 key=lambda cmb: (sum(i in name_tok for i in cmb), max(cmb) - min(cmb), cmb))
                found = dict(zip(present, best_combo))
                unique = [x for x in found if x not in others]
                if not (full or unique):
                    continue
                # значение с отрицанием («Без обивки») по части слов не сопоставляется:
                # «обивка» в тексте означает скорее наличие обивки, чем её отсутствие
                if not full and set(lem) & NEGATIONS:
                    continue
                idxs = sorted(found.values())
                # длинные значения с перечислением («от нефти, нефтепродуктов, масел, жиров») шире окна в 3 слова
                if max(idxs) - min(idxs) > max(3, 2 * len(lem) - 1):
                    continue
                cands.append((g, g.quality[nval], idxs, full))
        # слова полностью найденных значений («трикотажное полотно») не указывают на часть товара
        full_tok = frozenset(i for _, _, ix, f in cands if f for i in ix)
        # Более полное значение того же свойства поглощает вложенное: «секция шкафа» ⊃ «шкаф».
        for g, val, idxs, full in cands:
            s = set(idxs)
            if any(g2.key == g.key and f2 and set(i2) > s for g2, _, i2, f2 in cands):
                continue
            # значение только из слов наименования («шкаф» → «Шкаф») уступает значению того же свойства,
            # найденному по другим словам («для уборочного инвентаря» → «Шкаф для хозяйственного инвентаря»)
            if s <= name_tok and any(g2.key == g.key and set(i2) - name_tok for g2, _, i2, _ in cands):
                continue
            # «стол администратора, вид товара: секция стола»: свойство задано явно — «стол» из наименования
            # не даёт второе значение
            if s <= name_tok and g.key in getattr(self, "_bound_keys", set()):
                continue
            by_token.setdefault(idxs[0], []).append((g, val, idxs))
        for first in sorted(by_token):
            opts = by_token[first]
            if any(tokens[i].used_by for _, _, idxs in opts for i in idxs):
                continue
            prop_keys = sorted({g.key for g, _, _ in opts})
            neg = _negated(tokens, first)
            comp_idx: list[int] = []
            own = {i for _, _, ix in opts for i in ix}
            near = _component_near(tokens, sorted(own), exclude=full_tok - own)
            if near is not None:
                comp, j = near
                same = [o for o in opts if o[0].component == comp]
                if same:
                    opts, comp_idx = same, [j]
                    prop_keys = sorted({g.key for g, _, _ in opts})
                else:
                    generic = [o for o in opts if o[0].component is None]
                    idxs = sorted({i for _, _, ix in opts for i in ix} | {j})
                    value = nq.text[tokens[min(i for _, _, ix in opts for i in ix)].start:
                                    tokens[max(i for _, _, ix in opts for i in ix)].end]
                    if generic:
                        feats.append(self._feature(
                            None, tokens, idxs, nq, status="ambiguous", negated=neg, value=value, component=comp,
                            options=[{**self._opt(g), "value": v} for g, v, _ in
                                     sorted(generic, key=lambda o: (o[0].key, o[1]))],
                            note=f"значение указано для части «{tokens[j].text}», а у позиций свойство без "
                                 "указания части — подтвердите привязку"))
                    else:
                        feats.append(self._feature(
                            None, tokens, idxs, nq, status="unknown_property", negated=neg, value=value, component=comp,
                            note=f"у позиций нет такого свойства для части «{tokens[j].text}»; свойства других "
                                 f"частей ({', '.join(sorted({o[0].name for o in opts}))}) не подходят"))
                    continue
            if len(prop_keys) > 1:
                # уточнить по названию свойства рядом
                win = _window(tokens, first, 4, 4)
                named = [o for o in opts if o[0].terms and _terms_present(o[0].terms, tokens, win) is not None]
                if len({o[0].key for o in named}) == 1:
                    opts = named
                    prop_keys = [named[0][0].key]
            values = sorted({v for _, v, _ in opts})
            if len(prop_keys) == 1 and len(values) == 1:
                g, val, idxs = opts[0]
                win = _window(tokens, min(idxs), 4, 4)
                name_hit = _terms_present(g.terms, tokens, win) or []
                extra = [j for j in (first - 1, first - 2) if neg and j >= 0 and tokens[j].lemma in NEGATIONS]
                note = "значение из справочника допустимых значений"
                if g.component and not comp_idx and not name_hit:
                    note += "; часть товара в описании не названа — значение отнесено к единственному свойству " \
                            f"«{g.name}»"
                feats.append(self._feature(g, tokens, idxs + comp_idx + [h for h in name_hit if tokens[h].used_by is None]
                                           + extra, nq, op="ne" if neg else "eq", value=val, negated=neg, note=note))
            else:
                idxs = sorted({i for _, _, ix in opts for i in ix})
                feats.append(self._feature(None, tokens, idxs, nq, status="ambiguous", negated=neg,
                                           value=nq.text[tokens[idxs[0]].start:tokens[idxs[-1]].end],
                                           options=[{**self._opt(g), "value": v} for g, v, _ in
                                                    sorted(opts, key=lambda o: (o[0].key, o[1]))],
                                           note="слово совпадает со значениями нескольких свойств"))
        return feats
