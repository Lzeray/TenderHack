"""Real live flow: automatic filtering, complete results, independent model branch."""
from dataclasses import replace
import json
import sqlite3
from types import SimpleNamespace

import pytest

from ktru_assist.api import make_backend
from ktru_assist.catalog.repository import Catalog
from ktru_assist.catalog.ste_search import build, SteSearch
from ktru_assist.engine import Engine
from ktru_assist.llm.description import validate
from ktru_assist.llm.provider import FakeProvider
from ktru_assist.models import SearchRequest
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


def test_unknown_product_does_not_use_unrelated_semantic_neighbors(live):
    from ktru_assist.live_search import LiveSearch
    calls = []
    target = next(iter(live.engine.catalog_scope.types))
    def propose(*args):
        calls.append(args)
        return [SimpleNamespace(score=0.99, answer=SimpleNamespace(value=target))]
    live.semantic = SimpleNamespace(propose=propose)
    req = request("шмякозябра")
    positions, verified = LiveSearch(live)._fallback(req, None)
    assert not positions and not verified and not calls


def test_unknown_product_has_no_compatible_positions(live):
    r = live.run(request("шмякозябра"))
    assert r.status == "not_found"
    assert not r.candidates and not r.compatible_codes and r.final_code is None


def test_qwen_runs_without_user_selecting_type(live):
    live.cfg.b_mode = "always"
    live.llm = FakeProvider({"item": "дрель", "item_quote": "дрель", "catalogue_type": None,
                            "attributes": [], "unresolved": []})
    r = live.run(request("дрель ручная электрическая", stage="submitted"))
    assert live.llm.calls and r.results_total > 0
    assert any(p.name == "qwen" and p.used for p in r.providers)


def test_extra_only_mode_does_not_send_recognized_input_to_primary_qwen(live, monkeypatch):
    monkeypatch.setenv("EXTRAS_LLM", "on")
    live.cfg.b_mode = "always"
    live.llm = FakeProvider({"item": "дрель", "item_quote": "дрель", "attributes": []})
    r = live.run(request("дрель ручная электрическая мощность 600 Вт", stage="submitted"))
    assert not live.llm.calls
    assert any(p.name == "qwen" and p.status == "skipped" and not p.used for p in r.providers)
    assert any(f.value == "600" and f.origin == "rule" for f in r.features)


def test_quantity_from_model_cannot_be_changed():
    reply = {"item": "молоток", "item_quote": "молоток", "attributes": [
        {"name": "масса", "value": "50", "unit": "г", "quote": "500 г"}]}
    parsed, accepted, rejected = validate("молоток 500 г", json.dumps(reply))
    assert not accepted and rejected


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
