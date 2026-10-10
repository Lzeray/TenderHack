"""Подбор только по КТРУ: единый формат значений, обязательные характеристики, общие вопросы, доп. характеристики."""
from types import SimpleNamespace

from ktru_assist import canon, extras
from ktru_assist.models import Feature, SearchRequest


def search(engine, text, **kw):
    return engine.search(SearchRequest(text=text, **kw))


def test_value_brought_to_ktru_spelling():
    allowed = {"угловой": "Угловой", "прямой": "Прямой"}
    assert canon.match_value("угловой", allowed) == "Угловой"
    assert canon.match_value("УГЛОВОЙ", allowed) == "Угловой"
    assert canon.match_value("угловая", allowed) == "Угловой"          # род не мешает: сравнение по леммам
    assert canon.match_value("круглый", allowed) is None
    assert canon.display("  угловой  стол ") == "Угловой стол"


def test_bind_by_value_when_name_fits_several_properties():
    groups = {"a": SimpleNamespace(name="Тип столешницы", numeric=False, quality={"прямая": "Прямая"}),
              "b": SimpleNamespace(name="Тип стола", numeric=False, quality={"угловой": "Угловой"})}
    assert canon.groups_with_value("угловой", groups) == [groups["b"]]


def test_canonicalize_bound_feature():
    g = SimpleNamespace(name="Вид пассатижей", quality={"слесарные": "Слесарные"})
    f = Feature(id="x", source="override", status="bound", property_name="вид пассатижей", value="слесарные")
    canon.canonicalize([f], {"вид пассатижей": g})
    assert f.property_name == "Вид пассатижей" and f.value == "Слесарные"


def test_meaning_check_rejects_evaluations():
    assert extras.check_meaning("Внешний вид", "красивый", ["платье"]) is not None
    assert extras.check_meaning("Красота", None, ["платье"]) is not None
    assert extras.check_meaning("Цвет", "красный", ["платье"]) is None
    assert extras.subjective_words(["красивое", "синее"]) == ["красивое"]


def test_session_memory_is_compact():
    mem = extras.SessionMemory()
    for i in range(extras.MAX_PROPS + 10):
        mem.remember("s", "стол", f"Свойство номер {i}", "1", None)
    for i in range(extras.MAX_VALUES + 3):
        mem.remember("s", "стол", "Покрытие", f"лак {i}", None)
    items = mem.items("s", "стол")
    assert len(items) <= extras.MAX_PROPS
    cover = next(x for x in items if x["name"] == "Покрытие")
    assert len(cover["values"]) == extras.MAX_VALUES


def test_additional_characteristic_remembered_in_session(engine):
    r1 = search(engine, "пассатижи слесарные 190 мм, покрытие рукояток: резина", session_id="t-extras", revision=1)
    a1 = next(a for a in r1.additional if a.name.startswith("Покрытие"))
    assert a1.accepted and a1.source == "new"
    r2 = search(engine, "пассатижи слесарные 195 мм, покрытие рукояток: пластик", session_id="t-extras", revision=2)
    a2 = next(a for a in r2.additional if a.name.startswith("Покрытие"))
    assert a2.accepted and a2.source == "session"


def test_required_rows_common_first(engine):
    r = search(engine, "дрель ручная электрическая")
    rows = r.required_characteristics
    assert rows and rows[0].common and rows[0].name == "Тип питания"
    assert all(not x.common for x in rows[1:])


def test_user_property_required_elsewhere_drops_positions_without_it(engine):
    # «Мощность» обязательна у сетевой дрели и отсутствует у аккумуляторной → аккумуляторная отбрасывается
    r = search(engine, "дрель ручная электрическая мощность 600 Вт")
    assert r.compatible_codes == ["28.24.11.000-92000001"]
    dropped = next(c for c in r.candidates if c.code == "28.24.11.000-92000002")
    assert not dropped.compatible and "обязательна в других позициях" in dropped.excluded_reason


def test_question_prefers_property_common_to_all(engine):
    r = search(engine, "дрель ручная электрическая")
    if r.question is not None and r.question.kind == "property":
        assert r.question.property_name == "Тип питания"
