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


def test_position_without_user_property_stays(engine):
    # «Мощность» обязательна у сетевой дрели, у аккумуляторной её нет: аккумуляторная не исключается
    # (unknown ≠ invalid, docs/KTRU_SEARCH_PLAN.md, K2), кода нет — выбор не доказан
    r = search(engine, "дрель ручная электрическая мощность 600 Вт")
    assert set(r.compatible_codes) == {"28.24.11.000-92000001", "28.24.11.000-92000002"}
    kept = next(c for c in r.candidates if c.code == "28.24.11.000-92000002")
    assert kept.compatible and r.final_code is None


def test_type_word_matches_by_head(engine):
    # «Вид товара» из слова типа сравнивается по главному слову (K1)
    from ktru_assist.validate import check_feature
    from ktru_assist.catalog.repository import AllowedValue, Position, Prop
    def pos(*vals):
        p = Position(code="9", name="Стол", version=1, okpd2_code=None, okpd2_name=None, status=None,
                     is_template=False, parent_code=None, parent_version=None, no_new_features=None,
                     application_start=None, application_end=None, category="furniture", active=True,
                     inactive_reason=None, head="стол", name_lemmas=["стол"], rubrics=[], okeis=[])
        p.props["1"] = Prop("1", "Вид товара", 1, 1, True,
                            [AllowedValue("quality", v, None, None, None, None) for v in vals])
        return p
    f = Feature(id="f", source="text", status="bound", property_code="1", property_name="Вид товара",
                value="Стол", from_type_name=True)
    assert check_feature(pos("Стол для переговоров"), f)[0] == "valid"
    assert check_feature(pos("Секция стола"), f)[0] == "invalid"
    # явно названное значение сравнивается целиком
    assert check_feature(pos("Стол для переговоров"), f.model_copy(update={"from_type_name": False}))[0] == "invalid"


def test_question_prefers_property_common_to_all(engine):
    r = search(engine, "дрель ручная электрическая")
    if r.question is not None and r.question.kind == "property":
        assert r.question.property_name == "Тип питания"


def test_feature_role_main_or_other(engine):
    # основная — обязательна хотя бы в одной позиции типа, неосновная — иначе или свойства нет в КТРУ (K4)
    r = search(engine, "пассатижи слесарные 190 мм, цвет: красный")
    roles = {(f.property_name or f.named_property or "").lower(): f.role for f in r.features}
    assert roles.get("длина") == "main"
    assert any(f.role == "other" and f.status == "unknown_property" for f in r.features)
