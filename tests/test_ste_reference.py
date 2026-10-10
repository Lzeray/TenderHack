"""Proof boundaries for the offline procurement-reference hypothesis."""
from decimal import Decimal

from experiments.ste_reference import ReferenceCategory, bridge, classify, product_check, property_key
from ktru_assist.catalog.repository import AllowedValue, Interval, Position, Prop
from ktru_assist.units import lookup


def position(name="Молоток", okpd2="25.73.30.141", props=None):
    return Position("99.00.00.000-00000001", name, 1, okpd2, None, "actual", False,
                    None, None, None, None, None, "tools", True, None, "молоток", [], [], [], props or {})


def feature(value, *, kind="text", name="Тип", numbers="[]", unit=None, op=None, fid=1):
    return {"id": fid, "name": name, "value": value, "kind": kind, "numbers": numbers,
            "unit_raw": unit, "operator": op}


def test_category_binding_requires_explicit_terminal_fact():
    root, leaf = property_key("Вид продукции"), property_key("Виды инструмента")
    idx = {(root, "товары"): {1}, (leaf, "молотки"): {1}}
    assert classify([], {1}, idx, {root, leaf}, {1: "Молотки"}) == ("no_category_facts", set())
    assert classify([("Вид продукции", "Товары")], {1}, idx, {root, leaf}, {1: "Молотки"}) == ("partial_facts", {1})
    assert classify([("Виды инструмента", "Молотки")], {1}, idx, {root, leaf}, {1: "Молотки"}) == ("unique", {1})


def test_unknown_or_conflicting_category_values_are_not_guessed():
    prop = property_key("Виды стульев")
    idx = {(prop, "металл"): {1}, (prop, "дерево"): {2}}
    names = {1: "Металл", 2: "Дерево"}
    assert classify([("Виды стульев", "Пластик")], {1, 2}, idx, {prop}, names)[0] == "unknown_value"
    assert classify([("Виды стульев", "Металл"), ("Виды стульев", "Дерево")], {1, 2}, idx, {prop}, names)[0] == "conflicting_facts"


def test_bridge_requires_name_and_complete_okpd2_not_prefix_or_id_equality():
    cat = {(1, "01.11.02.02.03.15", "Молотки"): ReferenceCategory(1, "01.11.02.02.03.15", "Молотки")}
    record = {"global_id": 123, "spgz_name": "Молоток", "okpd2_code": "25.73.30.141", "kpgz_code": "01.11.02.02.03.15"}
    targets, evidence = bridge([position()], cat, [record])
    assert targets == set(cat) and evidence[0]["basis"].startswith("third_party_")
    assert not bridge([position()], cat, [{**record, "okpd2_code": "25.73"}])[0]
    assert not bridge([position()], cat, [{**record, "spgz_name": "Молоток хирургический"}])[0]


def test_missing_required_property_stays_unknown():
    prop = Prop("kind", "Тип", 1, 1, True, [AllowedValue("quality", "Слесарный", None, None, None, None)])
    p = position(props={prop.code: prop})
    assert product_check([], p, [])['state'] == "unknown"
    assert product_check([feature("Слесарный")], p, [])['state'] == "checked"
    assert product_check([feature("Столярный")], p, [])['state'] == "contradicted"


def test_spgz_link_alias_is_contextual_not_a_product_code():
    prop = Prop("kind", "Тип", 1, 1, True, [AllowedValue("quality", "Слесарный", None, None, None, None)])
    cat = ReferenceCategory(1, "01.11.02.02.03.15", "Молотки")
    cat.aliases[property_key("Тип инструмента")].add("Тип")
    assert product_check([feature("Слесарный", name="Тип инструмента")], position(props={prop.code: prop}), [cat])["state"] == "checked"
    assert product_check([feature("Слесарный", name="Тип инструмента")], position(props={prop.code: prop}), [])["state"] == "unknown"


def test_numeric_boundary_and_component_ownership():
    prop = Prop("mass", "Масса молотка", 2, 2, True, [AllowedValue("range", None,
        Interval(Decimal("0.4"), True, Decimal("0.6"), False), lookup("кг"), None, None)])
    p = position(props={prop.code: prop})
    good = feature("500 г", kind="number", name=prop.name, numbers='["500"]', unit="г")
    assert product_check([good], p, [])["state"] == "checked"
    assert product_check([{**good, "numbers": '["600"]', "value": "600 г"}], p, [])["state"] == "contradicted"
    assert product_check([{**good, "name": "Масса упаковки"}], p, [])["state"] == "unknown"


def test_conflicting_duplicate_facts_cannot_be_fully_checked():
    prop = Prop("kind", "Тип", 1, 1, True, [AllowedValue("quality", v, None, None, None, None)
                                            for v in ("Слесарный", "Столярный")])
    result = product_check([feature("Слесарный"), feature("Столярный", fid=2)], position(props={prop.code: prop}), [])
    assert result["state"] == "unknown"
