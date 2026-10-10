"""Conflicts belong to the request, not to the subset of candidates exposing a property."""
from dataclasses import replace
import datetime as dt

import pytest

from fixture_ktru import HEAD, TAIL, ch, pos, q
from ktru_assist.api import make_backend
from ktru_assist.catalog.importer import run_import
from ktru_assist.catalog.repository import Catalog
from ktru_assist.engine import Engine
from ktru_assist.llm.provider import FakeProvider
from ktru_assist.models import Feature, SearchRequest
from ktru_assist.orchestrator import Orchestrator, OrchestratorConfig
from ktru_assist.validate import conflicting_conditions


@pytest.fixture
def chairs(tmp_path, engine):
    source = tmp_path / "nsiKTRUNew_all_actual_fixture.xml"
    source.write_text(HEAD + pos("31.01.11.150-99000001", "Стул", "31.01.11.150", [
        ch("frame-type", "Тип каркаса", q("Деревянный", "Металлический"), kind=1)]) +
        pos("31.01.11.150-99000002", "Стул на металлическом каркасе", "31.01.11.150", [
            ch("soft", "Наличие мягкого сидения", q("Да", "Нет"), req=True)]) + TAIL, encoding="utf-8")
    db = tmp_path / "catalog.sqlite"
    run_import(source, db, dt.date(2026, 10, 9), log=lambda *_: None)
    settings = replace(engine.settings, db_path=db, recognition_mode="hybrid")
    catalog = Catalog(db)
    core = Engine(catalog, make_backend(settings, catalog), settings)
    return Orchestrator(core, OrchestratorConfig(b_mode="always"), llm=FakeProvider(error="should not run"))


@pytest.mark.parametrize("text", ["стул деревянный металлический", "стул деревянный метеллический"])
def test_clashing_frame_does_not_return_candidates_missing_frame_property(chairs, text):
    r = chairs.run(SearchRequest(text=text, session_id="conflict", revision=1, stage="submitted"))
    assert r.status == "conflict" and "Тип каркаса" in r.message
    assert "Деревянный" in r.message and "Металлический" in r.message
    assert not r.candidates and not r.compatible_codes and r.ste_results["total"] == 0
    assert r.question is None and r.final_code is None and not chairs.llm.calls
    if "метеллический" in text:
        assert any(c.corrected == "металлический" for c in r.corrections)


def test_single_material_still_searches(chairs):
    r = chairs.run(SearchRequest(text="стул деревянный", session_id="valid", revision=1))
    assert r.status != "conflict" and r.results_total > 0


def test_conflict_clears_after_edit(chairs):
    chairs.run(SearchRequest(text="стул деревянный металлический", session_id="edit", revision=1))
    r = chairs.run(SearchRequest(text="стул металлический", session_id="edit", revision=2))
    assert r.results_total > 0 and not r.query_profile.get("conflicts")


def fact(name, value, component=None, unit=None, span=None):
    return Feature(id=name+value, source="text", status="bound", property_name=name, value=value,
                   component=component, unit=unit, raw_span=span)


def test_different_components_and_explicit_alternatives_are_not_conflicts():
    assert not conflicting_conditions([fact("Материал каркаса", "Металл", "frame"),
                                       fact("Материал сиденья", "Дерево", "seat")], [])
    text = "деревянный или металлический"
    assert not conflicting_conditions([fact("Тип каркаса", "Деревянный", "frame", span=(0,10)),
                                       fact("Тип каркаса", "Металлический", "frame", span=(15,28))], [], text)


def test_equivalent_quantities_are_not_conflicts_but_disjoint_ones_are():
    a = fact("Масса", "500", unit="г")
    assert not conflicting_conditions([a, fact("Масса", "0.5", unit="кг")], [])
    assert conflicting_conditions([a, fact("Масса", "600", unit="г")], [])
