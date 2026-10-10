"""Real live flow: automatic filtering, complete results, independent model branch."""
from dataclasses import replace
import json
import sqlite3

import pytest

from ktru_assist.api import make_backend
from ktru_assist.catalog.repository import Catalog
from ktru_assist.catalog.ste_search import build, SteSearch
from ktru_assist.engine import Engine
from ktru_assist.llm.description import validate
from ktru_assist.llm.provider import FakeProvider
from ktru_assist.models import Constraint, SearchRequest
from ktru_assist.orchestrator import Orchestrator, OrchestratorConfig


@pytest.fixture
def live(engine, fixture_db):
    settings = replace(engine.settings, db_path=fixture_db[0], recognition_mode="hybrid")
    cat = Catalog(settings.db_path)
    core = Engine(cat, make_backend(settings, cat), settings)
    return Orchestrator(core, OrchestratorConfig(b_mode="off"))


def request(text, revision=1, stage="draft"):
    return SearchRequest(text=text, session_id="live", revision=revision, stage=stage)


def test_typing_filters_without_type_confirmation(live):
    first = live.run(request("пассатижи"))
    second = live.run(request("пассатижи слесарные 190 мм", 2))
    assert first.results_total > second.results_total == 1
    assert second.final_code == "25.73.30.163-90000001"
    assert not second.preview_candidates and second.features
    assert all(c.compatible and not c.is_template for c in first.candidates)


def test_every_compatible_position_is_returned(live):
    r = live.run(request("стул"))
    assert len(r.candidates) == len(r.compatible_codes) == r.results_total
    assert {c.name for c in r.candidates} == {"Стул на металлическом каркасе"}


def test_qwen_runs_without_user_selecting_type(live):
    live.cfg.b_mode = "always"
    live.llm = FakeProvider({"item": "дрель", "item_quote": "дрель", "catalogue_type": None,
                            "attributes": [], "unresolved": []})
    r = live.run(request("дрель ручная электрическая", stage="submitted"))
    assert live.llm.calls and r.results_total > 0
    assert any(p.name == "qwen" and p.used for p in r.providers)


def test_quantity_from_model_cannot_be_changed():
    reply = {"item": "молоток", "item_quote": "молоток", "attributes": [
        {"name": "масса", "value": "50", "unit": "г", "quote": "500 г"}]}
    parsed, accepted, rejected = validate("молоток 500 г", json.dumps(reply))
    assert not accepted and rejected


@pytest.mark.parametrize("quote,attribute", [
    ("не менее 500 г", {"value": "500", "unit": "г", "op": "eq"}),
    ("от 500 до 600 г", {"value": "500", "value_to": "650", "unit": "г", "op": "between"}),
    ("не красный", {"value": "красный", "op": "eq"}),
])
def test_model_cannot_change_comparison_range_or_negation(quote, attribute):
    reply = {"item": "молоток", "item_quote": "молоток", "attributes": [{"name": "Признак", "quote": quote, **attribute}]}
    _, accepted, rejected = validate("молоток " + quote, json.dumps(reply))
    assert not accepted and rejected


@pytest.mark.parametrize("quote,attribute", [
    ("не менее 500 г", {"value": "500", "unit": "г", "op": "ge"}),
    ("от 500 до 600 г", {"value": "500", "value_to": "600", "unit": "г", "op": "between"}),
    ("не красный", {"value": "красный", "op": "ne"}),
])
def test_model_preserving_original_conditions_is_accepted(quote, attribute):
    reply = {"item": "молоток", "item_quote": "молоток", "attributes": [{"name": "Признак", "quote": quote, **attribute}]}
    _, accepted, rejected = validate("молоток " + quote, json.dumps(reply))
    assert len(accepted) == 1 and not rejected


def test_model_proposal_requires_confirmation_and_does_not_filter(live):
    text = "пассатижи слесарные 190 мм, заточка есть"
    live.cfg.b_mode = "always"
    live.llm = FakeProvider({"item": "пассатижи", "item_quote": "пассатижи", "attributes": [
        {"name": "Режущие кромки", "value": "есть", "canonical_value": "Да", "quote": "заточка есть"}]})
    fast = live.run(request(text))
    full = live.run(request(text, stage="submitted"))
    assert full.compatible_codes == fast.compatible_codes
    assert full.final_code is None and full.code_resolution.status != "resolved"
    f = next(f for f in full.features if f.origin == "llm")
    assert f.confirmation == "tentative" and f.status == "proposed"
    assert full.question.kind == "confirm"
    confirmed = live.run(SearchRequest(text=text, session_id="live", revision=2, stage="submitted",
        answers=full.question.options[0].answers, answers_query_hash=full.query_hash))
    assert confirmed.status == "matched"
    assert not any(f.confirmation == "tentative" for f in confirmed.features)
    assert len(live.llm.calls) == 1  # confirmation reuses the validated extraction
    removed = live.run(SearchRequest(text=text, session_id="live", revision=3, stage="submitted",
        overrides=[Constraint(property=f.characteristic_ref, remove=True)]))
    assert removed.status == "matched" and not any(f.origin == "llm" for f in removed.features)


def test_hybrid_manual_override_replaces_rule_constraint(live):
    r = live.run(SearchRequest(text="пассатижи слесарные 150 мм", session_id="live", revision=1,
                              overrides=[Constraint(property="p-len", value="190", unit="мм")]))
    assert r.status == "matched"
    assert next(f for f in r.features if f.source == "text" and f.property_code == "p-len").status == "overridden"


def test_product_filters_use_exact_decimal_units_and_pagination(tmp_path):
    src, dst = tmp_path / "source.sqlite", tmp_path / "search.sqlite"
    with sqlite3.connect(src) as c:
        c.executescript("CREATE TABLE products(id INTEGER PRIMARY KEY,ste_id,name,model,manufacturer,country,raw_characteristics,quality_status); CREATE TABLE features(product_id,name_key,dimension,base_numbers,value); CREATE TABLE meta(key,value);")
        c.executemany("INSERT INTO products VALUES(?,?,?,?,?,?,?,?)", [
            (1,"001","Молоток красный","","Завод","Россия","Масса 500 г","parsed"),
            (2,"002","Молоток синий","","Завод","Россия","Масса 1 кг","parsed"),
            (3,"003","Стул красный","","Завод","Россия","","parsed")])
        c.executemany("INSERT INTO features VALUES(?,?,?,?,?)", [
            (1,"масса","mass",'["0.50000"]',"500 г"),
            (1,"цвет",None,'[]',"красный"), (2,"масса","mass",'["1.0"]',"1 кг"),
            (2,"цвет",None,'[]',"синий")])
        c.execute("INSERT INTO meta VALUES('summary','{}')")
    build(src, dst)
    search = SteSearch(dst)
    all_items = search.search(["молоток"], [], limit=1)
    assert all_items["total"] == 2 and len(all_items["items"]) == 1
    assert search.search(["молоток"], [], offset=1, limit=1)["items"][0]["ste_id"] == "002"
    filtered = search.search(["молоток"], [{"name":"Масса", "raw_value":"500", "raw_unit":"г", "value":"0.5", "unit":"кг"}])
    assert filtered["total"] == 1 and filtered["items"][0]["ste_id"] == "001"
    red = search.search(["молоток"], [{"name":"Цвет", "value":"красный"}])
    assert red["total"] == 1
