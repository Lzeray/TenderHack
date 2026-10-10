"""A shared fragment of an enum is not evidence for its distinguishing words."""
import pytest

from ktru_assist.nlp.extract import Extractor, PropGroup
from ktru_assist.nlp.normalize import normalize
from ktru_assist.text import content_lemmas, norm


def protection_group():
    values = ["От механических воздействий", "От пониженных температур", "От повышенных температур"]
    return PropGroup("вид защиты", "Вид защиты", ["protection"], False, False, set(), set(),
        {norm(v): v for v in values}, {norm(v): tuple(content_lemmas(v)) for v in values}, ["защита"], True)


def test_generic_exposure_does_not_invent_specific_protection():
    g = protection_group()
    fs = Extractor({g.key: g}).extract(normalize("перчатки для защиты от внешних воздействий"))
    assert not fs


def test_explicit_protection_is_not_overridden_by_product_name():
    g = protection_group()
    fs = Extractor({g.key: g}).extract(normalize(
        "перчатки для защиты от внешних воздействий, вид защиты: от пониженных температур"))
    assert [f.value for f in fs] == ["От пониженных температур"]


def test_full_inflected_value_still_extracts_and_preserves_negation():
    g = protection_group()
    fs = Extractor({g.key: g}).extract(normalize("перчатки не от механических воздействий"))
    assert len(fs) == 1 and fs[0].op == "ne" and fs[0].value == "От механических воздействий"


@pytest.mark.parametrize("name,values", [
    ("Стол для переговоров", ["Стол для переговоров", "Секция стола для переговоров"]),
    ("Стол администратора", ["Стол", "Секция стола"]),
])
def test_generic_product_designation_does_not_override_explicit_subtype(name, values):
    g = PropGroup("вид товара", "Вид товара", ["kind"], False, False, set(), set(),
        {norm(v): v for v in values}, {norm(v): tuple(content_lemmas(v)) for v in values}, ["товар"], True)
    fs = Extractor({g.key: g}, product_names=[name]).extract(normalize(
        name.lower() + ", вид товара: " + values[1].lower()))
    assert [f.value for f in fs] == [values[1]]
