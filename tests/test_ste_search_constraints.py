"""Real SQLite queries: physical dimensions are insufficient to identify a property."""
import sqlite3

import pytest

from ktru_assist.catalog.ste_search import SteSearch


@pytest.fixture
def products(tmp_path):
    path = tmp_path / "ste_search.sqlite"
    with sqlite3.connect(path) as c:
        c.executescript("CREATE TABLE products(id INTEGER PRIMARY KEY,name); CREATE VIRTUAL TABLE names USING fts5(terms); "
                       "CREATE TABLE attributes(product_id,name_key,dimension,number,value);")
        for i in range(1, 5):
            c.execute("INSERT INTO products VALUES(?, 'Молоток')", (i,))
            c.execute("INSERT INTO names(rowid,terms) VALUES(?, 'молоток')", (i,))
        c.executemany("INSERT INTO attributes VALUES(?,?,?,?,?)", [
            (1, "масса", "mass", "0.5", "500 г"),
            (2, "вес", "mass", "1", "1 кг"),
            (3, "масса упаковки", "mass", "0.5", "500 г"),
            (4, "масса", "mass", "0.500000000000000000001", "0.500000000000000000001 кг"),
            (1, "длина рукоятки", "length", "0.2", "20 см"),
            (2, "длина молотка", "length", "0.2", "20 см"),
            (1, "цвет", None, None, "красный"),
            (2, "цвет", None, None, "синий"),
        ])
    return SteSearch(path)


def query(products, **kwargs):
    return products.search(["молоток"], [{"name": "Масса молотка", "raw_value": "500", "raw_unit": "г", **kwargs}])


def ids(result):
    return {p["id"] for p in result["items"]}


def test_mass_of_packaging_does_not_match_item_mass(products):
    assert ids(query(products)) == {1}


def test_numeric_comparisons_use_decimal_and_preserve_boundaries(products):
    assert ids(query(products, op="gt")) == {2, 4}
    assert ids(query(products, op="le")) == {1}
    assert ids(query(products, op="between", value_to="1000", max_inclusive=False)) == {1, 4}


def test_component_quantity_does_not_match_bare_item_quantity(products):
    r = products.search(["молоток"], [{"name": "Длина молотка", "value": "20", "unit": "см"}])
    assert ids(r) == {2}


def test_negation_requires_known_property_and_ignores_unconfirmed_filters(products):
    r = products.search(["молоток"], [{"name": "Цвет", "value": "красный", "op": "ne"}])
    assert ids(r) == {2}
    tentative = query(products, confirmation="tentative")
    assert ids(tentative) == {1, 2, 3, 4} and tentative["ignored"] and not tentative["fully_checked"]
    unsupported = products.search(["молоток"], [{"name": "Покрытие", "value": "хром"}])
    assert unsupported["ignored"] and not unsupported["applied"]
