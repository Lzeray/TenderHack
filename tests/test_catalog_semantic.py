"""Catalogue-native integration. FakeProvider tests contracts, not model quality."""
from dataclasses import replace
import json

import pytest

from ktru_assist.api import make_backend
from ktru_assist.catalog.repository import Catalog
from ktru_assist.catalog.scope import identity_groups
from ktru_assist.engine import Engine
from ktru_assist.llm import catalog_extractor as parser
from ktru_assist.llm.provider import FakeProvider
from ktru_assist.models import Constraint, Feature, SearchRequest
from ktru_assist.orchestrator import Orchestrator, OrchestratorConfig


@pytest.fixture
def native(engine, fixture_db):
    settings = replace(engine.settings, db_path=fixture_db[0], recognition_mode="semantic")
    cat = Catalog(settings.db_path)
    return Engine(cat, make_backend(settings, cat), settings)


def type_ref(native, name="Пассатижи"):
    return next(t.ref for t in native.catalog_scope.types.values() if t.name == name)


def request(native, text="для слесаря 190 мм", stage="submitted", **kwargs):
    return SearchRequest(text=text, session_id="native-test", revision=kwargs.pop("revision", 1), stage=stage,
        overrides=[Constraint(property="__type__", value=type_ref(native))], **kwargs)


def reply(messages):
    context = json.loads(messages[1]["content"])["context"]
    length = next(p for p in context["properties"] if p["name"] == "Длина")
    kind = next(p for p in context["properties"] if p["name"] == "Вид пассатижей")
    v = next(v for v in kind["values"] if v["label"] == "Слесарные")
    return {"facts": [
        {"characteristic_id": length["characteristic_id"], "value_raw": "190", "unit_raw": "мм",
         "operation": "eq", "evidence_quote": "190 мм", "proposed_value_id": None},
        {"characteristic_id": kind["characteristic_id"], "value_raw": "для слесаря", "unit_raw": None,
         "operation": "eq", "evidence_quote": "для слесаря", "proposed_value_id": v["value_id"]}],
        "unresolved_fragments": [], "ambiguities": []}


def test_native_has_no_lexical_dependencies(engine, fixture_db, monkeypatch):
    import ktru_assist.text as text
    import ktru_assist.registry as registry
    def forbidden(*a, **kw):
        raise AssertionError("Lexical recognition must not run")
    monkeypatch.setattr(text, "_morph", forbidden)
    monkeypatch.setattr(registry, "load_aliases", forbidden)
    settings = replace(engine.settings, db_path=fixture_db[0], recognition_mode="semantic")
    cat = Catalog(settings.db_path)
    n = Engine(cat, make_backend(settings, cat), settings)
    r = n.search(SearchRequest(text="сидушка сетевая 190 мм"))
    assert not r.completeness.type_confirmed and r.final_code is None
    assert r.completeness.type_domain_total == len(n.catalog_scope.codes)


def test_native_hypotheses_do_not_exclude(native):
    raw = request(native)
    baseline = native.search(raw)
    g = next(g for g in identity_groups(native.catalog_scope.positions(type_ref(native))).values() if g.name == "Длина")
    hypothesis = Feature(id="hypothesis", source="model", origin="llm", status="proposed",
                         property_code=g.codes[0], property_name=g.name, value="9999", unit="мм")
    r = native.search(raw, model_features=[hypothesis])
    assert {c.code for c in r.candidates if c.compatible} == {c.code for c in baseline.candidates if c.compatible}
    assert any(k.status == "unknown" for c in r.candidates for k in c.checks if k.feature_id == "hypothesis")
    assert r.final_code is None


def test_native_confirmation_reuses_extraction_and_resolves(native):
    provider = FakeProvider(reply)
    o = Orchestrator(native, OrchestratorConfig(b_mode="always"), llm=provider)
    r = o.run(request(native))
    assert r.status == "clarification_needed" and r.final_code is None
    assert len(provider.calls) == 1
    opts = r.question.options[0].answers
    r2 = o.run(request(native, revision=2, action="confirm", answers=opts, answers_query_hash=r.query_hash,
                       confirmed=r.question.options[0].confirm))
    assert r2.final_code == "25.73.30.163-90000001" and r2.status == "matched"
    assert len(provider.calls) == 1


def test_native_draft_never_calls_llm(native):
    p = FakeProvider(reply)
    r = Orchestrator(native, OrchestratorConfig(b_mode="always"), llm=p).run(request(native, stage="draft"))
    assert not p.calls and not r.final_code and r.preliminary


def test_repeated_quotes_and_unknown_ids_are_not_facts(native):
    ctx = parser.build_context(native.catalog_scope, type_ref(native), "190 мм 190 мм")
    ref = next(r for r, g in ctx.groups.items() if g.name == "Длина")
    data = {"facts": [{"characteristic_id": ref, "value_raw": "190", "unit_raw": "мм",
                      "operation": "eq", "evidence_quote": "190 мм", "proposed_value_id": None}],
            "unresolved_fragments": [], "ambiguities": []}
    r = parser.parse_and_validate("190 мм 190 мм", json.dumps(data), ctx)
    assert not r.features and r.rejected
    data["facts"][0]["characteristic_id"] = "invented"
    r = parser.parse_and_validate("190 мм", json.dumps(data), ctx)
    assert not r.features and r.rejected


def test_null_characteristic_is_preserved(native):
    ctx = parser.build_context(native.catalog_scope, type_ref(native), "с запахом мяты")
    data = {"facts": [{"characteristic_id": None, "value_raw": "мяты", "unit_raw": None,
                      "operation": "eq", "evidence_quote": "с запахом мяты", "proposed_value_id": None}],
            "unresolved_fragments": [], "ambiguities": []}
    r = parser.parse_and_validate("с запахом мяты", json.dumps(data), ctx)
    assert r.features[0].status == "unknown_property" and r.features[0].evidence == "с запахом мяты"


def test_full_json_schema_is_validated(native):
    ctx = parser.build_context(native.catalog_scope, type_ref(native), "товар")
    assert not parser.parse_and_validate("товар", '{"facts":[]}', ctx).valid
    assert not parser.parse_and_validate("товар", '{"facts":[],"unresolved_fragments":[],"ambiguities":[],"origin":"manual"}', ctx).valid


def test_native_manual_override_wins_over_answer(native):
    r = native.search(request(native, answers=[Constraint(property="Длина", value="180", unit="мм")]))
    qhash = r.query_hash
    req = request(native, answers=[Constraint(property="Длина", value="180", unit="мм")], answers_query_hash=qhash)
    req.overrides += [Constraint(property="Длина", value="190", unit="мм")]
    r = native.search(req)
    assert [f.value for f in r.features if f.status == "bound" and f.property_name == "Длина"] == ["190"]


def test_native_nan_is_a_validation_result(native):
    req = request(native)
    req.overrides += [Constraint(property="Длина", value="NaN", unit="мм")]
    r = native.search(req)
    assert r.status != "matched"


def test_native_stale_response_not_applied(native):
    o = None
    def during(messages):
        o._register(request(native, revision=3))
        return reply(messages)
    o = Orchestrator(native, OrchestratorConfig(b_mode="always"), llm=FakeProvider(during))
    assert o.run(request(native, revision=2)).stale


def test_numeric_substring_is_not_a_source_number(native):
    ctx = parser.build_context(native.catalog_scope, type_ref(native), "1190 мм")
    length = next(r for r, g in ctx.groups.items() if g.name == "Длина")
    data = {"facts": [{"characteristic_id": length, "value_raw": "190", "unit_raw": "мм",
        "operation": "eq", "evidence_quote": "1190 мм", "proposed_value_id": None}],
        "unresolved_fragments": [], "ambiguities": []}
    result = parser.parse_and_validate("1190 мм", json.dumps(data), ctx)
    assert not result.features and result.rejected


def test_closed_set_policy_preserves_every_option_and_reports_ties():
    from ktru_assist.semantic.value_scorer import RecommendationPolicy
    opts = [{"value_id": str(i), "label": str(i)} for i in range(10)]
    result = RecommendationPolicy().apply(opts, {"scores_by_option_id": {str(i): 1.0 for i in range(10)}})
    assert len(result["options"]) == 10 and result["ambiguous"] and result["recommendations_truncated"]
    failure = RecommendationPolicy().apply(opts, {"error": "timeout"})
    assert failure["options"] == [dict(o, score=None, recommended=False) for o in opts]


def test_strict_characteristic_identity_does_not_match_by_name(native):
    from ktru_assist.validate import find_prop
    p = native.catalog_scope.positions(type_ref(native))[0]
    feature = Feature(id="f", source="model", status="proposed", property_name="Длина",
                      property_code="different-entity-with-same-name", strict_ref=True)
    assert find_prop(p, feature) is None


def test_numeric_set_is_preserved_for_confirmation(native):
    ctx = parser.build_context(native.catalog_scope, type_ref(native), "180 или 190 мм")
    length = next(r for r, g in ctx.groups.items() if g.name == "Длина")
    data = {"facts": [{"characteristic_id": length, "value_raw": "180 или 190", "values_raw": ["180", "190"],
        "unit_raw": "мм", "operation": "in", "evidence_quote": "180 или 190 мм", "proposed_value_id": None}],
        "unresolved_fragments": [], "ambiguities": []}
    result = parser.parse_and_validate("180 или 190 мм", json.dumps(data), ctx)
    assert result.features[0].op == "in" and result.proposals[0].answer.values == ["180", "190"]


def test_preference_is_not_a_confirmed_filter(native):
    req = request(native)
    baseline = native.search(req)
    req.overrides.append(Constraint(property="Длина", value="99999", unit="мм", intent="preference"))
    r = native.search(req)
    assert r.compatible_codes == baseline.compatible_codes


def test_native_api_requires_revision_and_exposes_complete_values(native, monkeypatch):
    from fastapi.testclient import TestClient
    import ktru_assist.api as api
    o = Orchestrator(native, OrchestratorConfig(b_mode="off"))
    monkeypatch.setattr(api, "get_engine", lambda: native)
    monkeypatch.setattr(api, "get_orchestrator", lambda: o)
    with TestClient(api.app) as client:
        assert client.post("/api/search", json={"text": "товар"}).status_code == 422
        groups = identity_groups(native.catalog_scope.positions(type_ref(native)))
        kind = next(r for r, g in groups.items() if g.name == "Вид пассатижей")
        r = client.get("/api/catalog/values", params={"type_ref": type_ref(native), "characteristic_ref": kind}).json()
        assert {v["label"] for v in r["options"]} >= {"Слесарные", "Рыбацкие"}
        assert all(v["answer"]["property"] == kind for v in r["options"])
        assert client.get("/api/catalog/types").status_code == 200


def test_empty_model_result_requires_explicit_review(native):
    provider = FakeProvider({"facts": [], "unresolved_fragments": [], "ambiguities": []})
    o = Orchestrator(native, OrchestratorConfig(b_mode="always"), llm=provider)
    r = o.run(request(native))
    assert r.question.kind == "confirm" and any(k.startswith("parse-review:") for k in r.question.options[0].confirm)


def test_manual_fallback_uses_core_and_never_calls_llm(native):
    provider = FakeProvider(error="offline")
    o = Orchestrator(native, OrchestratorConfig(b_mode="always"), llm=provider)
    req = request(native, manual_only=True)
    req.overrides += [Constraint(property="Длина", value="190", unit="мм"), Constraint(property="Вид пассатижей", value="Слесарные")]
    r = o.run(req)
    assert not provider.calls and r.status == "matched" and r.final_code == "25.73.30.163-90000001"


def test_rejected_binding_preserves_unresolved_source(native):
    o = Orchestrator(native, OrchestratorConfig(b_mode="always"), llm=FakeProvider(reply))
    r = o.run(request(native))
    key = next(p.key for p in r.proposals if p.kind == "value")
    r2 = o.run(request(native, revision=2, action="confirm", rejected=[key]))
    f = next(f for f in r2.features if f.proposal_key == key)
    assert f.status == "unknown_property" and f.evidence
    assert not r2.final_code


def test_unmapped_fact_stays_editable_in_real_core(native):
    ctx = parser.build_context(native.catalog_scope, type_ref(native), "аромат мяты")
    data = {"facts": [{"characteristic_id": None, "value_raw": "мяты", "unit_raw": None,
                      "operation": "eq", "evidence_quote": "аромат мяты", "proposed_value_id": None}],
            "unresolved_fragments": [], "ambiguities": []}
    result = parser.parse_and_validate("аромат мяты", json.dumps(data), ctx)
    r = native.search(request(native, text="аромат мяты"), model_features=result.features)
    assert r.features[0].status == "unknown_property" and r.features[0].evidence == "аромат мяты"


def test_search_preview_is_relevant_without_filtering_confirmed_domain(native):
    from ktru_assist.models import Proposal
    class Semantic:
        revision = "fake-retrieval"
        def propose(self, response, text, rejected):
            return [Proposal(key="type-suggestion", origin="semantic", kind="type", label="Пассатижи",
                             answer=Constraint(property="__type__", value=type_ref(native)))]
    o = Orchestrator(native, OrchestratorConfig(semantic=True), semantic=Semantic())
    req = SearchRequest(text="пассатижи", session_id="preview", revision=1)
    baseline = native.search(req)
    r = o.run(req)
    assert r.preview_candidates and {p.name for p in r.preview_candidates} == {"Пассатижи"}
    assert r.compatible_codes == baseline.compatible_codes and not r.final_code
    assert r.preview_total < len(r.compatible_codes)
