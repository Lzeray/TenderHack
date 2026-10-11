"""Нормализованное значение модели не должно терять связь с исходным текстом."""
import json
import pytest

from ktru_assist.canon import value_supported
from ktru_assist.extras import classify
from ktru_assist.llm.extra_characteristics import enrich
from ktru_assist.llm.provider import FakeProvider
from ktru_assist.models import Feature, SearchRequest


@pytest.mark.parametrize("raw,normalized", [
    ("деревянной", "Дерево"),
    ("металлической", "Металл"),
    ("резиновой", "Резина"),
    ("рещиновой", "Резина"),
])
def test_extra_pass_preserves_quote_and_returns_normalized_material(engine, raw, normalized):
    text = f"молоток с {raw} ручкой"
    req = SearchRequest(text=text, stage="submitted")
    response = engine.search(req)
    response.detected_types = ["молоток"]
    response.properties = []
    response.features = []
    response.additional = []
    response.unrecognized = [raw]
    provider = FakeProvider({"attributes": [{
        "name": "Материал ручки", "value": normalized, "unit": None,
        "evidence": f"с {raw} ручкой", "value_quote": raw,
    }]})
    result = enrich(req, response, engine, provider, lambda _: False)
    assert provider.calls and result.providers[-1].status == "ok"
    assert [(a.name, a.value, a.accepted) for a in result.additional] == [
        ("Материал ручки", normalized, True)]
    assert not result.unrecognized
    assert f"с {raw} ручкой" in result.additional[0].reason


@pytest.mark.parametrize("raw,normalized,expected", [
    ("деревянной", "Дерево", "Дерево"),
    ("металлической", "Металл", "Металл"),
    ("деревянной", "Сталь", "Деревянной"),
    ("не деревянной", "Дерево", "Не деревянной"),
    ("500", "0.5", "500"),
])
def test_primary_model_uses_only_supported_normalization(raw, normalized, expected):
    result = classify([], [{"name": "Материал ручки", "raw_value": raw,
                           "value": normalized, "source": "llm"}], ["молоток"], None, None)
    assert len(result) == 1 and result[0].value == expected


@pytest.mark.parametrize("value,quote", [
    ("Сталь", "деревянной"),
    ("Дерево", "не деревянной"),
    ("не Дерево", "деревянной"),
    ("50", "500"),
    ("500", "не менее 500"),
])
def test_normalization_cannot_invent_material_or_change_constraints(value, quote):
    assert not value_supported(value, quote)


def _response(engine, text, unknown, features=()):
    req = SearchRequest(text=text, stage="submitted")
    response = engine.search(req)
    response.detected_types = ["молоток"]
    response.properties = []
    response.features = list(features)
    response.additional = []
    response.unrecognized = list(unknown)
    response.query_profile = {"item_terms": ["молоток"]}
    return req, response


def _wood_provider(evidence="с деревянной ручкой", quote="деревянной"):
    return FakeProvider({"attributes": [{"name": "Материал ручки", "value": "Дерево",
        "unit": None, "evidence": evidence, "value_quote": quote}]})


def test_only_unused_fragments_reach_model_and_lemma_warning_is_removed(engine):
    mass = Feature(id="mass", source="text", status="bound", property_name="Масса молотка",
                   value="500", unit="г", evidence="500 г")
    req, response = _response(engine, "молоток 500 г с деревянной ручкой",
                              ["500", "деревянный", "ручкой"], [mass])
    provider = _wood_provider()
    result = enrich(req, response, engine, provider, lambda _: False)
    payload = json.loads(provider.calls[0][1]["content"])
    assert payload == {"product": "молоток", "text": "с деревянной ручкой",
                       "unresolved": ["деревянной", "ручкой"]}
    assert result.additional[0].value == "Дерево"
    assert not result.unrecognized and not result.query_profile["unrecognized"]
    assert result.features[0].value == "500"


def test_type_name_property_is_not_reextracted_as_material(engine):
    frame = Feature(id="frame", source="text", status="bound", property_name="Тип каркаса",
                    value="Деревянный", evidence="деревянный", from_type_name=True)
    req, response = _response(engine, "стул деревянный", ["деревянный"], [frame])
    response.detected_types = ["Стул на деревянном каркасе"]
    response.query_profile["item_terms"] = ["стул"]
    provider = _wood_provider("деревянный", "деревянный")
    result = enrich(req, response, engine, provider, lambda _: False)
    assert not provider.calls and not result.additional and not result.unrecognized


def test_same_material_for_another_component_is_still_unprocessed(engine):
    frame = Feature(id="frame", source="text", status="bound", property_name="Тип каркаса",
                    value="Деревянный", evidence="деревянный", from_type_name=True)
    req, response = _response(engine, "стул деревянный с деревянной ручкой",
                              ["деревянной", "ручкой"], [frame])
    response.detected_types = ["Стул на деревянном каркасе"]
    response.query_profile["item_terms"] = ["стул"]
    provider = _wood_provider()
    result = enrich(req, response, engine, provider, lambda _: False)
    payload = json.loads(provider.calls[0][1]["content"])
    assert payload["text"] == "с деревянной ручкой"
    assert result.additional[0].value == "Дерево"


def test_model_cannot_turn_product_context_into_an_additional_property(engine):
    req, response = _response(engine, "молоток с деревянной ручкой", ["деревянной", "ручкой"])
    provider = FakeProvider({"attributes": [{"name": "Назначение", "value": "Молоток",
        "unit": None, "evidence": req.text, "value_quote": "молоток"}]})
    result = enrich(req, response, engine, provider, lambda _: False)
    assert provider.calls and not result.additional
    assert result.unrecognized == ["деревянной", "ручкой"]
