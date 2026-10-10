"""Выбор уточняющих вопросов при бюджете в два вопроса (docs/QUESTIONS_PLAN.md, Q2)."""
from ktru_assist.qplan import Planner, Q, branches


def q(key, values, required=False):
    """values: код → набор ответов позиции (пусто — характеристики у позиции нет)."""
    answers = {a for v in values.values() for a in v}
    members = {a: frozenset(c for c, v in values.items() if not v or a in v) for a in answers}
    return Q(key=key, members=members, own={c: frozenset(v) for c, v in values.items() if v},
             required=required, tie=(0, len(answers), key))


S = frozenset("abcd")


def test_one_question_identifies_all():
    full = q("full", {"a": {1}, "b": {2}, "c": {3}, "d": {4}})
    half = q("half", {"a": {1}, "b": {1}, "c": {2}, "d": {2}})
    best, value, _ = Planner([half, full], S).choose(S, budget=1)
    assert best.key == "full" and value == (1.0, 0.0)


def test_two_questions_chosen_together():
    # по отдельности ни один вопрос не определяет позицию, вместе — всегда
    x = q("x", {"a": {1}, "b": {1}, "c": {2}, "d": {2}})
    y = q("y", {"a": {1}, "b": {2}, "c": {1}, "d": {2}})
    skew = q("skew", {"a": {1}, "b": {2}, "c": {2}, "d": {2}})
    p = Planner([skew, x, y], S)
    best, value, scored = p.choose(S, budget=2)
    assert best.key in ("x", "y") and value[0] == 1.0
    assert scored["skew"][0] < 1.0          # после «skew» три позиции различает только один вопрос из двух
    best1, value1, _ = p.choose(S, budget=1)
    assert best1.key == "skew" and value1[0] == 0.25    # один вопрос: лучше всего — отделить хотя бы одну


def test_position_without_property_stays_in_every_branch():
    partial = q("partial", {"a": {1}, "b": {2}, "c": set(), "d": set()})
    br = {a: b for a, _, b in branches(partial, S)}
    assert br[1] == frozenset("acd") and br[2] == frozenset("bcd")
    useless = q("useless", {"a": {1}, "b": {1}, "c": {1}, "d": {1}})
    best, _, scored = Planner([useless], S).choose(S)
    assert best is None and not scored        # вопрос, который ничего не делит, не задаётся


def test_multi_valued_position_and_tie_prefers_required():
    multi = q("multi", {"a": {1, 2}, "b": {1}, "c": {2}, "d": {2}})
    br = {a: b for a, _, b in branches(multi, S)}
    assert "a" in br[1] and "a" in br[2]
    x = q("x", {"a": {1}, "b": {1}, "c": {2}, "d": {2}})
    y = q("y", {"a": {1}, "b": {1}, "c": {2}, "d": {2}}, required=True)
    best, _, _ = Planner([x, y], S).choose(S, budget=1)
    assert best.key == "y"                      # равная ценность — обязательная характеристика


def test_engine_asks_at_most_two_questions(engine):
    from ktru_assist.models import SearchRequest
    r = engine.search(SearchRequest(text="пассатижи"))
    assert r.question is not None and "вероятностью" in r.question.reason
    answers = []
    for _ in range(2):
        if r.question is None or r.status == "matched":
            break
        o = r.question.options[-1]
        answers += o.answers or [o.answer]
        r = engine.search(SearchRequest(text="пассатижи", answers=answers))
    if r.status != "matched" and len({a.property for a in answers}) >= 2:
        assert r.question is None and "Осталось ввести" in r.message
