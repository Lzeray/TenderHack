"""FIXTURE: инструменты оценки — независимая перепроверка гарантий matched (eval/guarantees.py)."""
from eval.guarantees import check_matched
from ktru_assist.models import SearchRequest


def test_guarantees_hold_for_matched(engine):
    r = engine.search(SearchRequest(text="пассатижи слесарные 190 мм"))
    assert r.status == "matched" and check_matched(engine, r) == []


def test_guarantees_detect_non_unique(engine):
    r = engine.search(SearchRequest(text="пассатижи слесарные 190 мм"))
    # подделка: убрать признак, различающий позиции, — в области станет несколько совместимых
    r.features = [f for f in r.features if f.property_name != "Вид пассатижей"]
    assert any("совместимы" in v for v in check_matched(engine, r))


def test_guarantees_detect_template(engine):
    r = engine.search(SearchRequest(text="пассатижи слесарные 190 мм"))
    r.final_code = "25.73.30.163-90000010"
    assert any("шаблон" in v for v in check_matched(engine, r))
