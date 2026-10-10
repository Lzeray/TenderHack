"""Геометрические размеры: общие оси товара (docs/DIMENSIONS_PLAN.md, шаги D3–D4).

Свойство КТРУ — «общий размер» по оси, если его название — слово-ось (длина, ширина, глубина, высота, диаметр),
после которого идут только название самого товара («Высота шкафа»), «столешница» («Длина столешницы»,
«Высота до столешницы») или пояснение в скобках («Высота (без учета регулировки)»). Размеры частей
(«Глубина секции стеллажа», «Длина полки», «Высота антресоли») и толщины общими не считаются.

Нужно, чтобы одна ось с разными названиями у позиций одного типа («Высота» / «Высота шкафа») проверялась
одинаково, и чтобы габариты «80х50х180» раскладывались только по общим осям.
"""
from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache

from .text import content_lemmas, lemma_of_literal

AXES = tuple(lemma_of_literal(w) for w in ("длина", "ширина", "глубина", "высота", "диаметр"))
OVERALL_QUALIFIERS = frozenset(lemma_of_literal(w) for w in ("столешница", "изделие", "товар", "габаритный",
                                                              "общий"))


@lru_cache(maxsize=20_000)
def axis_of(prop_name: str, context: frozenset[str] = frozenset()) -> str | None:
    """Ось общего размера или None (размер части, толщина, не размер).

    context — леммы наименования позиции или главные слова типа: «Длина разводного ключа» у «Ключ разводной»."""
    base = re.sub(r"\([^)]*\)", " ", prop_name or "")
    lem = content_lemmas(base)
    if not lem or lem[0] not in AXES:
        return None
    rest = set(lem[1:]) - context - OVERALL_QUALIFIERS
    return lem[0] if not rest else None


def context_of(name_lemmas, heads=()) -> frozenset[str]:
    out = set(name_lemmas or ())
    for h in heads:
        out |= set(h.split("-")) | {h}
    return frozenset(out)


__all__ = ["AXES", "axis_of"]


# --- габариты: раскладка по осям (D4) -------------------------------------------------------------------------
UNIT_GUESSES = ("мм", "см", "м")
MAX_OPTIONS = 4


def _axis_props(positions) -> dict[str, list[str]]:
    """Ось → названия свойств общих размеров в области (самое частое название первым)."""
    from collections import Counter
    names: dict[str, Counter] = {}
    for p in positions:
        ctx = context_of(p.name_lemmas, [p.head] if p.head else [])
        for pr in p.props.values():
            if not pr.is_numeric or not any(u.dimension == "length" for u in pr.units):
                continue
            ax = axis_of(pr.name, ctx)
            if ax is not None:
                names.setdefault(ax, Counter())[pr.name] += 1
    return {ax: [n for n, _ in c.most_common()] for ax, c in names.items()}


def _layout_label(layout) -> str:
    return ", ".join(f"{ax} {v} {u}" for ax, _, v, u in layout)


DENSITY_WINDOW = (Decimal("0.9"), Decimal("1.1"))   # «рядом» с числом — ±10 %
DENSITY_FLOOR = 0.002                               # нижняя граница доли, чтобы ноль не обнулял произведение
SINGLE_RATIO = 5.0                                  # лучшая раскладка правдоподобнее второй в 5 раз — одна


def _label_axes(letters: list[str], axes: dict) -> list[str] | None:
    """«ДхШхВ» → оси типа. Если у типа нет «длины», Д — ширина, Ш — глубина (стеллаж, шкаф: длина × ширина
    фасада… в описаниях мебели «Д» часто значит ширину фасада, «Ш» — глубину)."""
    if all(a in axes for a in letters):
        return letters
    alt = {"длина": "ширина", "ширина": "глубина"} if "длина" not in axes else {"глубина": "ширина"}
    mapped = [alt.get(a, a) if a not in axes else a for a in letters]
    return mapped if all(a in axes for a in mapped) and len(set(mapped)) == len(mapped) else None


CONVENTION_BOOST = 3.0     # общепринятый порядок записи габаритов (Д×Ш×В, Ш×Г×В): высота последней


def _conventional(order) -> bool:
    L, W, D, H = (lemma_of_literal(w) for w in ("длина", "ширина", "глубина", "высота"))
    if len(order) == 3:
        return order[2] == H and order[0] in (L, W) and order[1] in (W, D) and order[0] != order[1]
    return len(order) == 2 and order in ((L, W), (W, D))


def _prop_stats(stats, heads, name: str, axis: str, dimension: str):
    """Статистика свойства по названию; иначе по общей оси или слову-оси того же типа («Длина рукоятки» → «Длина»)."""
    ps = stats.find(heads, name, "number", dimension) or stats.find(heads, axis.capitalize(), "number", dimension)
    if ps is None:
        first = (content_lemmas(name) or [""])[0]
        if first in AXES:
            ps = stats.find(heads, first.capitalize(), "number", dimension)
    return ps if ps is not None and ps.n_models >= 30 else None


def share_satisfying(stats, heads, name: str, axis: str, interval, unit: str | None) -> float | None:
    """Доля моделей выгрузок, удовлетворяющих условию (интервал в единицах пользователя); точка — ±10 %."""
    if stats is None or not getattr(stats, "available", False) or unit is None:
        return None
    from .units import lookup
    u = lookup(unit)
    if u is None:
        return None
    ps = _prop_stats(stats, heads, name, axis, u.dimension)
    if ps is None:
        return None
    I = interval.scaled(u.factor)
    if I.lo is not None and I.lo == I.hi:
        lo, hi = I.lo * DENSITY_WINDOW[0], I.lo * DENSITY_WINDOW[1]
        near = sum(n for x, n in stats.values(ps.prop_id) if lo <= x <= hi)
    else:
        near = sum(n for x, n in stats.values(ps.prop_id) if I.contains_point(x))
        # «до 40»: условию «≤ 40 см» и «≤ 40 м» удовлетворяют все модели, но граница 40 м далеко от реальных
        # значений. Граница одностороннего условия должна лежать рядом с ними: от p01/3 до p99·3.
        bound = I.hi if I.lo is None else I.lo if I.hi is None else None
        q = ps.quantiles
        if bound is not None and q.get("p01") and q.get("p99"):
            if not (Decimal(q["p01"]) / 3 <= bound <= Decimal(q["p99"]) * 3):
                return DENSITY_FLOOR
    return max(near / ps.n_models, DENSITY_FLOOR)


def _density(stats, heads, name: str, axis: str, value: str, unit: str | None) -> float | None:
    """Доля моделей выгрузок со значением в пределах ±10 % (None — статистики нет)."""
    if stats is None or not getattr(stats, "available", False) or unit is None:
        return None
    from .units import lookup
    u = lookup(unit)
    if u is None:
        return None
    ps = stats.find(heads, name, "number", u.dimension) or stats.find(heads, axis.capitalize(), "number", u.dimension)
    if ps is None:
        # нет статистики по точному названию («Длина рукоятки») — по слову-оси того же типа («Длина»)
        first = (content_lemmas(name) or [""])[0]
        if first in AXES:
            ps = stats.find(heads, first.capitalize(), "number", u.dimension)
    if ps is None or ps.n_models < 30:
        return None
    v = Decimal(value.replace(",", ".")) * u.factor
    lo, hi = v * DENSITY_WINDOW[0], v * DENSITY_WINDOW[1]
    near = sum(n for x, n in stats.values(ps.prop_id) if lo <= x <= hi)
    return max(near / ps.n_models, DENSITY_FLOOR)


def resolve(features, positions, heads, stats=None):
    """Габаритные признаки → вопрос о раскладке осей (или пометка, что размеров в КТРУ нет).

    Раскладка — назначение каждого числа своей общей оси типа (и единицы, если её нет в тексте). Она правдоподобна,
    если каждое число подходит хотя бы одной позиции по КТРУ и (если есть статистика выгрузок) не «редко» и
    не «не встречается». Пока пользователь не выбрал раскладку, признак остаётся неоднозначным и не участвует
    в подборе (решение команды: подтверждение обязательно, docs/DIMENSIONS_PLAN.md).
    Возвращает вопрос по первому неразрешённому габариту или None."""
    from itertools import permutations

    from .empirical import assess
    from .models import Constraint, Feature, Question, QuestionOption
    from .validate import check_feature

    question = None
    answered = {f.proposal_key for f in features if f.source in ("answer", "override") and f.proposal_key}
    for f in features:
        if not f.dims or f.status != "ambiguous":
            continue
        key = "dims:" + "×".join(d["value"] for d in f.dims) + ":" + ",".join(d["unit"] or "" for d in f.dims)
        if key in answered:
            f.status = "overridden"
            f.note += "; раскладка подтверждена пользователем"
            continue
        axes = _axis_props(positions)
        k = len(f.dims)
        if len(axes) < k:
            f.status = "unknown_property"
            f.named_property = "габариты"
            f.note = ("в КТРУ у позиций этого типа нет стольких общих размеров (длина, ширина, глубина, высота, "
                      "диаметр) — габариты на выбор кода не влияют")
            continue
        labelled = _label_axes(f.dims_axes, axes) if f.dims_axes else None
        dia, height = lemma_of_literal("диаметр"), lemma_of_literal("высота")
        orders = [tuple(labelled)] if labelled else [
            o for o in permutations(sorted(axes), k)
            # диаметр не сочетается с длиной, шириной и глубиной (у круглого стола их нет)
            if not (dia in o and set(o) - {dia, height})]
        unit_sets = [tuple(d["unit"] for d in f.dims)] if all(d["unit"] for d in f.dims) else \
            [tuple(u for _ in f.dims) for u in UNIT_GUESSES]
        scored = []
        for units in unit_sets:
            for order in orders:
                layout, ok, like, known = [], True, 1.0, 0
                for d, ax, u in zip(f.dims, order, units):
                    name = axes[ax][0]
                    probe = Feature(id=f.id, source="text", status="bound", property_name=name, value=d["value"],
                                    unit=u)
                    ok &= any(check_feature(p, probe)[0] == "valid" for p in positions)
                    dens = _density(stats, heads, name, ax, d["value"], u)
                    if dens is not None:
                        like *= dens
                        known += 1
                    layout.append((ax, name, d["value"], u))
                if ok:
                    if not labelled and _conventional(order):
                        like *= CONVENTION_BOOST
                    scored.append((known, like, layout))
        # правдоподобие раскладки — произведение долей моделей «рядом» с числом по каждой оси (выгрузки СТЕ);
        # сравниваются раскладки с одинаковым числом оценённых осей
        top_known = max((x[0] for x in scored), default=0)
        pool = sorted((x for x in scored if x[0] == top_known), key=lambda x: (-x[1], _layout_label(x[2])))
        plausible = pool if top_known == 0 else [x for x in pool if x[1] * SINGLE_RATIO >= pool[0][1]]
        if not pool:
            f.note = "габариты: ни одна раскладка не подходит позициям КТРУ этого типа — проверьте числа и единицы"
            continue
        opts = []
        for _, _, layout in pool[:MAX_OPTIONS]:
            answers = [Constraint(property=name, op="eq", value=v, unit=u, evidence_key=key)
                       for _, name, v, u in layout]
            opts.append(QuestionOption(label=_layout_label(layout), remaining=len(positions), answers=answers,
                                       answer=answers[0]))
        single = len(plausible) == 1
        f.note = ("габариты: по выгрузкам правдоподобна одна раскладка — подтвердите" if single else
                  f"габариты: близких по правдоподобию раскладок {len(plausible)} — выберите")
        if question is None:
            question = Question(
                kind="dims", text=(f"Габариты «{f.value}»: верно ли, что это {_layout_label(pool[0][2])}?" if single
                                   else f"Габариты «{f.value}»: что есть что?"),
                required=True, worst_case_remaining=len(positions), current_remaining=len(positions),
                options=opts, reason=f.note)
    return question
