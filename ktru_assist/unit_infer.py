"""Подстановка единицы измерения к числу без единицы (docs/UNITS_PLAN.md, шаги U1–U2).

Число без единицы у числового свойства — несколько гипотез «число + единица той же размерности, что у свойства
в КТРУ». Свидетельства:
1. единственная единица размерности в справочнике или единица в названии свойства («Крутящий момент (Нм)»);
2. единица соседних признаков того же описания (той же размерности) — множитель SIBLING_BOOST;
3. допустимость по КТРУ (уровень 1): гипотеза, при которой значение не подходит ни одной позиции, отбрасывается;
4. типичность по выгрузкам (уровень 2): доля моделей со значением в пределах ±10 % (dims._density);
5. запись числа: дробное меньше 10 — скорее крупная единица (1,8 м), от 1000 — мелкая (1800 мм); слабый множитель;
6. без выгрузок — единица, в которой КТРУ хранит значения свойства (слабый множитель).
Подстановка — если лучшая гипотеза правдоподобнее следующей не меньше чем в RATIO раз; иначе вопрос.
Числа пользователя не меняются («1,8» остаётся «1,8 м»). Единицы другой размерности не рассматриваются.
"""
from __future__ import annotations

from decimal import Decimal

from .dims import axis_of, context_of, share_satisfying
from .units import UNITS, lookup

VERSION = "1.3"   # 1.3 сильное пересечение распределений → вопрос; подсказки: связи «A ≤ B»
RATIO = 10.0
SIBLING_BOOST = 10.0
NOTATION_BOOST = 2.0
STORAGE_BOOST = 3.0
# единицы, которые подставляем; редкие в описаниях (дюйм, км, дм, т, мг, м³, кВ) — нет
CANDIDATES = {u.key for u in UNITS} - {"inch", "km", "dm", "t", "mg", "m3", "kv", "pcs", "mm2", "cm2"}
SMALL = {"mm", "cm", "g", "w", "ml", "mah"}       # мелкие единицы своей размерности
LARGE = {"m", "kg", "kw", "l", "ah"}


def _num(s: str | None) -> Decimal | None:
    try:
        return Decimal((s or "").replace(",", "."))
    except Exception:
        return None


def _props(positions, f):
    from .validate import find_prop
    return [p for p in (find_prop(pos, f) for pos in positions) if p is not None]


SCALE_PENALTY = 0.1
RELATION_PENALTY = 0.1     # нарушает связь «A ≤ B» с другой характеристикой (≥ 99 % моделей выгрузок)
OVERLAP_MIN_SHARE = 0.02   # распределения «сильно пересекаются»: обе доли не меньше 2 % …
OVERLAP_RATIO = 3.0        # … и отличаются меньше чем в 3 раза — тогда вопрос, если подсказки не различают
SAME_AXIS_RATIO = 3        # одна ось («высота» и «максимальная высота») — не больше чем в 3 раза
OTHER_AXIS_RATIO = 20      # разные оси длины («ширина» и «длина» гладильной доски) — не больше чем в 20 раз


def _axis_word(name: str | None) -> str | None:
    """Слово-ось в названии свойства («Максимальная регулируемая высота» → «высота»)."""
    from .dims import AXES
    from .text import content_lemmas, lemma_of_literal
    thick = lemma_of_literal("толщина")
    return next((l for l in content_lemmas(name or "") if l in AXES or l == thick), None)


def _out_of_scale(f, u, values, sibling_values) -> bool:
    from .text import lemma_of_literal
    thick = lemma_of_literal("толщина")
    first = _axis_word(f.property_name)
    if first == thick:
        return False
    for name, dim, base in sibling_values:
        if dim != u.dimension or name == f.property_name:
            continue
        sfirst = _axis_word(name)
        if sfirst == thick:
            continue
        limit = SAME_AXIS_RATIO if sfirst is not None and sfirst == first else OTHER_AXIS_RATIO
        for v in values:
            x = v * u.factor
            if x > 0 and base > 0 and max(x, base) / min(x, base) > limit:
                return True
    return False


def _violates_relation(name: str | None, x, dim: str, heads, stats, sibling_values) -> bool:
    """Значение x (в базовой единице) нарушает связь «A ≤ B» с другой характеристикой описания."""
    from .catalog.ste_stats import prop_key
    if stats is None or not getattr(stats, "available", False) or not name:
        return False
    me = prop_key(name)
    for tk in stats.type_keys(heads):
        rules = stats.pair_rules(tk)
        for sname, sdim, base in sibling_values:
            if sdim != dim or not sname:
                continue
            other = prop_key(sname)
            for a, b, d, _, _ in rules:
                if d != dim:
                    continue
                if (a, b) == (me, other) and x > base or (a, b) == (other, me) and base > x:
                    return True
        if rules:
            break
    return False


def hypotheses(f, positions, heads, stats, sibling_units: dict[str, str], sibling_values=()):
    """[(score, unit_title, basis, share, hinted)] по убыванию: score — с учётом подсказок, share — доля моделей
    выгрузок (None — нет данных), hinted — сработала подсказка из других характеристик (единица, соразмерность,
    связь «A ≤ B»). Пустой список — подставлять нечего (не число, штуки, нет свойства)."""
    from .validate import check_feature, user_interval
    props = _props(positions, f)
    if not props or not all(p.is_numeric for p in props):
        return []
    dims = {u.dimension for p in props for u in p.units}
    if len(dims) != 1:
        return []
    dim = next(iter(dims))
    if dim == "count":
        return []
    name_units = {p.name_unit.key for p in props if p.name_unit}
    stored = {u.key for p in props for u in p.units}
    cands = [u for u in UNITS if u.dimension == dim and (u.key in CANDIDATES or u.key in stored)]
    if name_units:
        cands = [u for u in cands if u.key in name_units]
    values = [v for v in (_num(f.value), _num(f.value_to)) if v is not None]
    if not values or not cands:
        return []
    if len(cands) == 1:
        return [(1.0, cands[0].title, "единственная единица этой величины" if not name_units
                 else "единица указана в названии свойства КТРУ", None, True)]
    out = []
    for u in cands:
        probe = f.model_copy(update={"unit": u.title})
        if not any(check_feature(pos, probe)[0] == "valid" for pos in positions):
            continue
        score, basis = 1.0, []
        dens = None
        name = f.property_name or ""
        ax = None
        for pos in positions[:1]:
            ax = axis_of(name, context_of(pos.name_lemmas, [pos.head] if pos.head else []))
        U = user_interval(probe)
        dens = share_satisfying(stats, heads, name, ax or name, U, u.title) if U is not None else None
        if dens is not None:
            score *= dens
            basis.append("типичность по выгрузкам")
        elif u.key in stored:
            score *= STORAGE_BOOST
            basis.append("единица значений КТРУ")
        hinted = False
        if sibling_units.get(dim) == u.key:
            score *= SIBLING_BOOST
            basis.append("единица соседних характеристик")
            hinted = True
        # соразмерность с соседними характеристиками той же размерности: «высота 399 мм, максимальная
        # регулируемая высота 65» — 65 мм в 6 раз меньше, 65 см соразмерно
        if _out_of_scale(f, u, values, sibling_values):
            score *= SCALE_PENALTY
            basis.append("несоразмерно соседним характеристикам")
            hinted = True
        if any(_violates_relation(f.property_name, v * u.factor, dim, heads, stats, sibling_values) for v in values):
            score *= RELATION_PENALTY
            basis.append("нарушает связь с другой характеристикой")
            hinted = True
        v0 = values[0]
        if v0 != v0.to_integral_value() and v0 < 10 and u.key in LARGE:
            score *= NOTATION_BOOST
        if v0 >= 1000 and u.key in SMALL:
            score *= NOTATION_BOOST
        out.append((score, u.title, ", ".join(basis) or "допустимо по КТРУ", dens, hinted))
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def strongly_overlap(a_share, b_share) -> bool:
    """Распределения сильно пересекаются: обе гипотезы обычны и отличаются по доле меньше чем в 3 раза."""
    return a_share is not None and b_share is not None and b_share >= OVERLAP_MIN_SHARE and         a_share < OVERLAP_RATIO * b_share


def infer(features, positions, heads, stats):
    """Подставить единицы; вернуть вопрос по первому неоднозначному признаку или None."""
    from .models import Constraint, Question, QuestionOption
    sibling: dict[str, str] = {}
    sibling_values = []
    for f in features:
        u = lookup(f.unit) if f.unit else None
        if f.status == "bound" and u is not None and f.source == "text":
            sibling.setdefault(u.dimension, u.key)
            v = _num(f.value)
            if v is not None and f.value_to is None:
                sibling_values.append((f.property_name, u.dimension, v * u.factor))
    question = None
    for f in features:
        if f.status != "bound" or f.unit or f.source != "text" or f.op in ("ne", "in") or _num(f.value) is None:
            continue
        hyp = hypotheses(f, positions, heads, stats, sibling, sibling_values)
        if not hyp:
            continue
        best = hyp[0]
        second = hyp[1][0] if len(hyp) > 1 else 0.0
        # сильное пересечение распределений — вопрос, если подсказки других характеристик не различают варианты
        overlap = len(hyp) > 1 and strongly_overlap(best[3], hyp[1][3]) and not (best[4] or hyp[1][4])
        if not overlap and (second == 0.0 or best[0] >= RATIO * second):
            f.unit = best[1]
            f.unit_inferred = True
            f.note = (f.note + "; " if f.note else "") + f"единица подставлена: {best[1]} ({best[2]})"
            continue
        if question is None:
            shown = f.value + (f"–{f.value_to}" if f.value_to else "")
            opts = []
            for score, unit, basis, *_ in hyp[:4]:
                c = Constraint(property=f.property_code or f.property_name or "", op=f.op, value=f.value,
                               value_to=f.value_to, unit=unit, min_inclusive=f.min_inclusive,
                               max_inclusive=f.max_inclusive)
                opts.append(QuestionOption(label=f"{shown} {unit}", remaining=len(positions), answer=c, answers=[c]))
            question = Question(kind="property", property_code=f.property_code, property_name=f.property_name,
                                text=f"В каких единицах «{f.property_name}» = {shown}?", required=True,
                                worst_case_remaining=len(positions), current_remaining=len(positions),
                                options=opts, reason="число без единицы: подходят несколько единиц")
            f.note = (f.note + "; " if f.note else "") + ("единица не указана — значение обычно в нескольких единицах, "
                                                           "нужен выбор" if overlap else
                                                           "единица не указана — подходят несколько, нужен выбор")
    return question


__all__ = ["infer", "hypotheses", "VERSION"]


# --- U2: число без названия свойства («молоток 500»), выбор свойства при известной единице («500 г») -----------
BARE_RATIO = 20.0          # перевес лучшей пары над следующей для подстановки без вопроса
BARE_MIN_SHARE = 0.05      # и не меньше 5 % моделей рядом с числом (или удовлетворяют условию)
BARE_ASK_SHARE = 0.02      # меньше — вариант не предлагаем (не о чем спрашивать)


def _pair_scores(f, positions, heads, stats, names: list[str], fixed_unit: str | None):
    """[(доля, свойство, единица, код)] для пар «свойство + единица», допустимых по КТРУ и с данными выгрузок."""
    from .validate import check_feature, find_prop, user_interval
    out = []
    for name in names:
        probe0 = f.model_copy(update={"property_name": name, "property_code": None, "status": "bound", "bare": False})
        props = _props(positions, probe0)
        if not props or not all(p.is_numeric for p in props):
            continue
        dims = {u.dimension for p in props for u in p.units}
        if len(dims) != 1:
            continue
        dim = next(iter(dims))
        units = [lookup(fixed_unit)] if fixed_unit else \
            [u for u in UNITS if u.dimension == dim and (u.key in CANDIDATES or u.key in {x.key for p in props for x in p.units})]
        for u in units:
            if u is None or u.dimension != dim:
                continue
            probe = probe0.model_copy(update={"unit": u.title})
            if not any(check_feature(pos, probe)[0] == "valid" for pos in positions):
                continue
            U = user_interval(probe)
            ctx_pos = positions[0]
            ax = axis_of(name, context_of(ctx_pos.name_lemmas, [ctx_pos.head] if ctx_pos.head else []))
            share = share_satisfying(stats, heads, name, ax or name, U, u.title) if U is not None else None
            if share is None:
                # допустимо по КТРУ, но данных в выгрузках нет — вариант не выпадает молча: он блокирует
                # автоматический выбор среди вариантов той же размерности (доля неизвестна)
                code = next((find_prop(pos, probe).code for pos in positions if find_prop(pos, probe)), None)
                out.append((-1.0, name, u.title, code))
                continue
            code = next((find_prop(pos, probe).code for pos in positions if find_prop(pos, probe)), None)
            out.append((share, name, u.title, code))
    out.sort(key=lambda x: (-x[0], x[1], x[2]))
    return out


RIVAL_PREVALENCE = 0.2     # соперник из выгрузок — свойство, указанное хотя бы у 20 % моделей типа


def _ste_only_scores(f, heads, stats, ktru_names: set[str], exclude_dim: str | None = None):
    """Соперники из выгрузок: числовые свойства типа, которых нет в КТРУ («шуруповерт 18» — напряжение 18 В,
    а не крутящий момент 18 Н·м). [(доля, название, единица)]."""
    from .catalog.ste_stats import prop_key
    from .validate import user_interval
    if stats is None or not getattr(stats, "available", False):
        return []
    known = {prop_key(n) for n in ktru_names}
    tks = set(stats.type_keys(heads))
    out = []
    for (tk, pk, kind, dim), ps in stats.props.items():
        if tk not in tks or kind != "number" or pk in known or dim in (None, "count") or dim == exclude_dim:
            continue
        # нишевое свойство подтипа («длина кабеля» у отбойных молотков в типе «молоток») — не соперник
        total = stats.types.get(tk, {}).get("n_models", 0)
        if not total or ps.n_models < RIVAL_PREVALENCE * total:
            continue
        for u in UNITS:
            if u.dimension != dim or u.key not in CANDIDATES:
                continue
            probe = f.model_copy(update={"property_name": ps.display_name, "unit": u.title})
            U = user_interval(probe)
            share = share_satisfying(stats, heads, ps.display_name, ps.display_name, U, u.title) if U else None
            if share is not None:
                out.append((share, ps.display_name, u.title))
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def _unknown_rivals(raw, best) -> bool:
    """Есть допустимый по КТРУ вариант той же размерности без данных выгрузок — сравнить нельзя."""
    bu = lookup(best[2])
    return any(x[0] < 0 and bu is not None and lookup(x[2]) is not None and lookup(x[2]).dimension == bu.dimension
               and (x[1], x[2]) != (best[1], best[2]) for x in raw)


def infer_bare(features, positions, heads, stats):
    """Подобрать свойство (и единицу) для числа без названия; вернуть вопрос по первому неоднозначному или None.
    Без статистики выгрузок свойство не угадывается: признак помечается «уточните»."""
    from .models import Constraint, Question, QuestionOption
    numeric_names = sorted({pr.name for p in positions for pr in p.props.values() if pr.is_numeric})
    sibling_values = []
    for g in features:
        gu = lookup(g.unit) if g.unit else None
        gv = _num(g.value)
        if g.status == "bound" and gu is not None and gv is not None and g.value_to is None:
            sibling_values.append((g.property_name, gu.dimension, gv * gu.factor))
    question = None
    for f in features:
        if f.status != "ambiguous" or f.dims:
            continue
        if f.bare:
            names, fixed = numeric_names, None
        elif f.unit and f.options and _num(f.value) is not None:
            names, fixed = [o["property_name"] for o in f.options if o.get("property_name")], f.unit
        else:
            continue
        raw_all = _pair_scores(f, positions, heads, stats, names, fixed)
        raw = [x for x in raw_all if x[0] >= 0]
        # подсказки других характеристик: соразмерность и связи «A ≤ B» (как для единиц, U1)
        scores, hinted = [], set()
        for share, name, unit, code in raw:
            u = lookup(unit)
            vals = [v for v in (_num(f.value), _num(f.value_to)) if v is not None]
            adj = share
            probe = f.model_copy(update={"property_name": name})
            if u is not None and _out_of_scale(probe, u, vals, sibling_values):
                adj *= SCALE_PENALTY
                hinted.add((name, unit))
            if u is not None and any(_violates_relation(name, v * u.factor, u.dimension, heads, stats, sibling_values)
                                     for v in vals):
                adj *= RELATION_PENALTY
                hinted.add((name, unit))
            scores.append((adj, name, unit, code, share))
        scores.sort(key=lambda x: (-x[0], x[1], x[2]))
        shown = f.value + (f"–{f.value_to}" if f.value_to else "") + (f" {f.unit}" if f.unit else "")
        if not scores or scores[0][0] < BARE_ASK_SHARE:
            if f.bare:
                f.status = "unknown_property"
                f.note = f"число «{shown}» без названия свойства: по типичным значениям не понятно, что это — уточните"
            continue
        best = scores[0]
        second = next((x[0] for x in scores[1:] if (x[1], x[2]) != (best[1], best[2])), 0.0)
        # соперник той же размерности — скорее то же свойство под другим названием («вес» / «Вес кувалды»)
        best_dim = lookup(best[2]).dimension if lookup(best[2]) else None
        rival = _ste_only_scores(f, heads, stats, set(numeric_names), best_dim) if f.bare else []
        if rival and rival[0][0] >= BARE_MIN_SHARE and rival[0][0] * BARE_RATIO > best[0]:
            # число лучше (или сопоставимо) объясняется свойством, которого нет в КТРУ — не подставляем
            if rival[0][0] >= best[0]:
                f.status = "unknown_property"
                f.named_property = rival[0][1].lower()
                f.note = (f"«{shown}» похоже на «{rival[0][1].lower()} {f.value} {rival[0][2]}» (так у "
                          f"{round(rival[0][0] * 100)} % моделей в выгрузках), но в КТРУ этого свойства нет — "
                          "на выбор кода не влияет; если имелось в виду другое, уточните")
                continue
            second = max(second, rival[0][0])
        nxt = next((x for x in scores[1:] if (x[1], x[2]) != (best[1], best[2])), None)
        # распределения сильно пересекаются и подсказки их не различают — вопрос
        overlap = nxt is not None and strongly_overlap(best[4], nxt[4]) and             not ({(best[1], best[2]), (nxt[1], nxt[2])} & hinted)
        if _unknown_rivals(raw_all, best):
            overlap = True
        if not overlap and best[4] >= BARE_MIN_SHARE and best[0] >= BARE_RATIO * second:
            f.status, f.property_name, f.property_code = "bound", best[1], best[3]
            if not f.unit:
                f.unit, f.unit_inferred = best[2], True
            f.property_inferred = True
            f.options = []
            f.note = (f"«{shown}» — {best[1].lower()} {best[2]}: так у {round(best[0] * 100)} % моделей этого типа "
                      "в выгрузках (свойство подставлено)")
            continue
        if question is None:
            opts = []
            for share, name, unit, code, _ in [x for x in scores if x[4] >= BARE_ASK_SHARE][:4]:
                c = Constraint(property=name, op=f.op, value=f.value, value_to=f.value_to, unit=unit,
                               min_inclusive=f.min_inclusive, max_inclusive=f.max_inclusive)
                opts.append(QuestionOption(label=f"{name}: {f.value}{'–' + f.value_to if f.value_to else ''} {unit}",
                                           remaining=len(positions), answer=c, answers=[c]))
            question = Question(kind="property", text=f"Что означает «{shown}»?", required=True,
                                worst_case_remaining=len(positions), current_remaining=len(positions), options=opts,
                                reason="число без названия: подходят несколько свойств")
    return question
