import pytest

from ktru_assist.models import Canonical, SearchRequest
from ktru_assist.registry import product_subjects


@pytest.mark.parametrize("text", [
    "стол и отвертка", "стол и стул", "стол, отвертка", "стол стул",
    "стол и отвертака", "стул и молоток", "стол; стул",
])
def test_different_products_are_detected(engine, text):
    assert len(product_subjects(text, engine.catalog)) > 1


@pytest.mark.parametrize("text", [
    "стол", "отвертка", "стол деревянный", "шкаф для одежды",
    "стол с ящиками и полками", "молоток с деревянной ручкой",
    "стол, материал каркаса: дерево", "стол, количество полок: 3",
    "Стул (банкетка) для клавишных инструментов", "стол и стол",
])
def test_parts_properties_and_variants_are_not_another_product(engine, text):
    assert len(product_subjects(text, engine.catalog)) <= 1


@pytest.mark.parametrize("canonical", [None, Canonical()])
@pytest.mark.parametrize("warmed", [False, True])
def test_api_multiple_products_has_no_results_or_model_call(engine, fixture_db, monkeypatch, canonical, warmed):
    from dataclasses import replace
    from ktru_assist import api
    from ktru_assist.engine import Engine
    from ktru_assist.api import make_backend
    from ktru_assist.llm.provider import FakeProvider
    from ktru_assist.orchestrator import Orchestrator, OrchestratorConfig
    settings = replace(engine.settings, recognition_mode="hybrid")
    core = Engine(engine.catalog, make_backend(settings, engine.catalog), settings)
    provider = FakeProvider({})
    o = Orchestrator(core, OrchestratorConfig(b_mode="always"), llm=provider)
    monkeypatch.setattr(api, "get_engine", lambda: core)
    monkeypatch.setattr(api, "get_orchestrator", lambda: o)
    if warmed:
        api.api_search(SearchRequest(text="стол", session_id="warmup", revision=1, stage="draft"))
    req = SearchRequest(text="стол и отвертка", session_id="multiple", revision=1,
                        stage="submitted", canonical=canonical)
    response = api.api_search(req)
    assert response.status == "not_found"
    assert not response.candidates and not response.compatible_codes
    assert not response.features and not response.additional and response.question is None
    assert response.final_code is None and not provider.calls
    assert (response.session_id, response.revision, response.stage) == ("multiple", 1, "submitted")
