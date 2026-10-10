"""SMOKE-тесты на реальной базе (data/ktru.sqlite). Это проверка работоспособности на каталоге,
а не независимая оценка точности (она — в eval/). Пропускаются, если база не импортирована."""
import json
import sqlite3

import pytest

from conftest import REAL_DB, ROOT
from ktru_assist.models import SearchRequest

pytestmark = pytest.mark.skipif(not REAL_DB.exists(), reason="нет data/ktru.sqlite")


def test_aliases_point_to_existing_heads():
    aliases = json.loads((ROOT / "data" / "aliases.json").read_text(encoding="utf-8"))["aliases"]
    con = sqlite3.connect(REAL_DB)
    for alias, head in aliases.items():
        n = con.execute("SELECT count(*) FROM positions WHERE category IS NOT NULL AND active=1 AND head=?",
                        (head,)).fetchone()[0]
        assert n > 0, f"алиас {alias} → {head}: нет активных позиций"


def test_real_snapshot_meta():
    con = sqlite3.connect(REAL_DB)
    meta = {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM meta")}
    assert meta["files_skipped"] >= 0 and meta["positions"] > 1000
    for cat in ("clothes", "furniture", "tools"):
        assert meta["coverage"][cat]["active_final"] > 0


def test_real_pliers_end_to_end(real_engine):
    r = real_engine.search(SearchRequest(text="пассатижи слесарные 180 мм"))
    assert r.status == "matched" and r.final_code == "25.73.30.163-00000005"


def test_real_terminated_not_offered(real_engine):
    # 31.01.11.121-00000002 в снимке TERMINATED
    r = real_engine.search(SearchRequest(text="шкаф для одежды металлический"))
    assert "31.01.11.121-00000002" not in {c.code for c in r.candidates}


def test_value_aliases_exist():
    """Цель каждого алиаса значения (свойство + значение) есть у активных позиций направлений MVP."""
    aliases = json.loads((ROOT / "data" / "value_aliases.json").read_text(encoding="utf-8"))["aliases"]
    con = sqlite3.connect(REAL_DB)
    for a in aliases:
        n = con.execute(
            "SELECT count(*) FROM char_values v JOIN characteristics c ON c.position_code=v.position_code "
            "AND c.char_code=v.char_code JOIN positions p ON p.code=v.position_code "
            "WHERE p.category IS NOT NULL AND p.active=1 AND c.name=? AND v.text=?",
            (a["property"], a["value"])).fetchone()[0]
        assert n > 0, f"алиас значения «{a['phrase']}» → {a['property']} = {a['value']}: в каталоге нет"


def test_explicit_property_beats_name_word(real_engine):
    # «вид товара: секция стола» задано явно — «стол» из наименования не даёт второе значение
    r = real_engine.search(SearchRequest(text="стол администратора, тип каркаса: металлический, вид товара: секция стола"))
    assert not any(i.code == "contradictory_values" for i in r.issues)
    assert r.status != "conflict"


def test_axis_with_other_name_is_checked(real_engine):
    # «высота шкафа» проверяется и у позиций, где свойство называется «Высота»
    from ktru_assist.dims import axis_of, context_of
    r = real_engine.search(SearchRequest(text="шкаф для одежды высота 1,8 м"))
    for c in r.candidates:
        p = real_engine.catalog.get(c.code)
        ctx = context_of(p.name_lemmas, [p.head])
        has_height = any(axis_of(pr.name, ctx) == axis_of("Высота", ctx) for pr in p.props.values() if pr.is_numeric)
        absent = [k for k in c.checks if k.feature_id and k.unknown_reason == "property_absent"]
        assert not (has_height and absent), c.code


def test_overall_axis_preferred_over_part(real_engine):
    r = real_engine.search(SearchRequest(text="стеллаж высота 2 м ширина 1 м глубина 40 см"))
    f = next(f for f in r.features if f.evidence and "глубина" in f.evidence)
    assert f.status == "bound" and f.property_name == "Глубина стеллажа"


def test_dims_question_and_answer(real_engine):
    t = "стол обеденный 120 на 80 на 75 см"
    r = real_engine.search(SearchRequest(text=t))
    # «стол обеденный» подходит и «Стол обеденный школьный» (docs/KTRU_SEARCH_PLAN.md, K5): сначала тип
    assert r.question is not None and r.question.kind == "type"
    typ = next(o for o in r.question.options if o.label.startswith("Стол обеденный") and "школьн" not in o.label)
    type_answers = typ.answers or [typ.answer]
    r = real_engine.search(SearchRequest(text=t, answers=type_answers, answers_query_hash=r.query_hash))
    assert r.question is not None and r.question.kind == "dims"
    assert r.question.options[0].label == "длина 120 см, ширина 80 см, высота 75 см"
    # пока раскладка не выбрана, габариты не участвуют в подборе
    assert not any(f.status == "bound" and f.property_name and "столешниц" in f.property_name for f in r.features)
    r2 = real_engine.search(SearchRequest(text=t, answers=type_answers + r.question.options[0].answers,
                                          answers_query_hash=r.query_hash))
    bound = {f.property_name: f.value for f in r2.features if f.status == "bound" and f.source == "answer"}
    assert bound == {"Длина столешницы": "120", "Ширина столешницы": "80", "Высота до столешницы": "75"}


def test_dims_packaging_and_missing_axes(real_engine):
    r = real_engine.search(SearchRequest(text="стол письменный в упаковке 120х60х10 см"))
    assert any((f.named_property or "").lower() == "размеры упаковки" for f in r.features)
    r = real_engine.search(SearchRequest(text="сверло по металлу 6х100"))
    assert any((f.named_property or "").lower() == "габариты" and f.status == "unknown_property" for f in r.features)


def test_discrete_range_values(real_engine):
    r = real_engine.search(SearchRequest(text="куртка зимняя из текстильных материалов женская размер 48-50"))
    f = next(f for f in r.features if f.property_name == "Российский размер")
    c = next(c for c in r.candidates if c.compatible)
    k = next(k for k in c.checks if k.feature_id == f.id)
    assert k.status == "valid" and "48" in k.reason and "50" in k.reason


def test_bare_number_inferred_by_distributions(real_engine):
    f = next(f for f in real_engine.search(SearchRequest(text="кувалда 5")).features if f.value == "5")
    assert (f.status, f.property_name, f.unit, f.property_inferred) == ("bound", "Вес кувалды", "кг", True)
    # «шуруповерт 18» — скорее напряжение 18 В (в КТРУ нет), а не крутящий момент 18 Н·м
    f = next(f for f in real_engine.search(SearchRequest(text="шуруповерт аккумуляторный 18")).features if f.value == "18")
    assert f.status == "unknown_property" and "напряжение" in f.note
    # артикул с ведущими нулями не становится «ростом 0–6 м»
    r = real_engine.search(SearchRequest(text="Футболка (оверсайз) АРГУС черная 52/176 000-006"))
    assert not any(f.value == "0" for f in r.features)


def test_unit_inferred_by_distributions(real_engine):
    cases = {"молоток слесарный длина от 120": "мм", "шкаф для одежды высота 1,8": "м",
             "дрель ручная электрическая от сети мощность 0,6": "кВт", "шуруповерт аккумуляторный крутящий момент 40": "Н·м"}
    for text, unit in cases.items():
        f = next(f for f in real_engine.search(SearchRequest(text=text)).features if f.unit_inferred)
        assert f.unit == unit, text


def test_relation_warning_between_named_values(real_engine):
    r = real_engine.search(SearchRequest(text="шкаф для одежды высота шкафа 60 см глубина шкафа 180 см"))
    feats = {f.property_name: f.value for f in r.features if f.status == "bound" and f.unit}
    assert feats == {"Высота шкафа": "60", "Глубина шкафа": "180"}          # название — с одной стороны числа
    assert any(s.rule == "relation" for s in r.suggestions)
    r = real_engine.search(SearchRequest(text="шкаф для одежды высота шкафа 180 см глубина шкафа 60 см"))
    assert not any(s.rule == "relation" for s in r.suggestions)


def test_unknown_rival_blocks_auto_choice(real_engine):
    # у «Массы бойка» нет данных в выгрузках — выбрать между ней и «Массой молотка» нельзя: вопрос
    r = real_engine.search(SearchRequest(text="молоток слесарный 500 г"))
    assert r.question is not None and "500 г" in r.question.text


def test_long_property_name_in_segment(real_engine):
    t = "пила ручная, вид пилы: обушковая, длина режущей части полотна (без учета предельного отклонения) 56,2 см"
    f = next(f for f in real_engine.search(SearchRequest(text=t)).features if f.unit == "см")
    assert f.status == "bound" and f.property_name.startswith("Длина режущей части полотна")


def test_length_misspelling_binds_length_with_unit(real_engine):
    f = next(f for f in real_engine.search(SearchRequest(text="молоток длинной от 200")).features if f.value == "200")
    assert (f.status, f.property_name, f.op, f.unit, f.unit_inferred) == ("bound", "Длина рукоятки", "ge", "мм", True)


def test_type_scope_is_complete(real_engine):
    # docs/KTRU_SEARCH_PLAN.md: по типу находятся все позиции; секция — другое изделие, если её не назвали
    names = lambda r: {c.name for c in r.candidates if c.code in set(r.compatible_codes)}  # noqa: E731
    kind = lambda r: {k.reason for c in r.candidates for k in c.checks if k.property_name == "Вид товара"}  # noqa: E731
    r = real_engine.search(SearchRequest(text="стол"))
    assert len(r.compatible_codes) >= 30 and r.final_code is None
    assert {"Журнальный стол", "Стол письменный", "Стол для переговоров"} <= names(r)
    kinds = [[v.text for pr in p.props.values() if pr.name == "Вид товара" for v in pr.values]
             for p in real_engine.catalog.get_many(r.compatible_codes).values()]
    assert kinds and not any(k and all(v.startswith("Секция") for v in k) for k in kinds)
    r = real_engine.search(SearchRequest(text="шкаф, вид товара секция шкафа"))
    assert any("Секция шкафа" in x for x in kind(r) if "есть среди" in x)
    r = real_engine.search(SearchRequest(text="джинсы"))
    assert {"Джинсы", "Джинсы детские"} <= names(r)


def test_part_word_goes_to_its_value_and_choice_resolves_ambiguity(real_engine):
    from ktru_assist.models import Constraint
    bound = lambda r: {(f.property_name, f.value) for f in r.features if f.status == "bound"}  # noqa: E731
    r = real_engine.search(SearchRequest(text="стол деревянный столешница лдсп"))
    assert {("Тип каркаса", "Деревянный"), ("Вид материала столешницы", "ЛДСП")} <= bound(r)
    assert not any(f.status == "ambiguous" for f in r.features)
    # выбор варианта неоднозначного значения снимает неоднозначность (плашка выбора не остаётся)
    r = real_engine.search(SearchRequest(text="стол лдсп"))
    amb = next(f for f in r.features if f.status == "ambiguous")
    o = next(o for o in amb.options if o["property_name"] == "Вид материала столешницы")
    r = real_engine.search(SearchRequest(text="стол лдсп", overrides=[Constraint(property=o["property_code"], value=o["value"])]))
    assert not any(f.status == "ambiguous" for f in r.features)
    assert ("Вид материала столешницы", "ЛДСП") in bound(r)


def test_lone_no_value_is_not_negation(real_engine):
    # «наличие мягкого сидения: нет» — значение «Нет», а не «не Нет»
    r = real_engine.search(SearchRequest(text="стул; наличие мягкого сидения: нет"))
    f = next(f for f in r.features if f.property_name == "Наличие мягкого сидения")
    assert f.op == "eq" and f.value == "Нет"
    r = real_engine.search(SearchRequest(text="стол; вид материала столешницы: не лдсп"))
    f = next(f for f in r.features if f.property_name == "Вид материала столешницы")
    assert f.op == "ne" and f.value == "ЛДСП"


def test_value_without_property_is_checked_by_other_characteristic(real_engine):
    # «стол угловой»: у позиции нет «Тип конструкции стола», но есть «Конфигурация стола: Угловой» — проверка
    # засчитывается по ней; позиции, где «угловой» нет ни в одной характеристике, не подходят
    r = real_engine.search(SearchRequest(text="стол угловой"))
    f = next(f for f in r.features if f.status == "bound" and f.value and "углов" in f.value.lower())
    finals = [c for c in r.candidates if c.compatible and not c.is_template]
    assert finals
    for c in finals:
        k = next(k for k in c.checks if k.feature_id == f.id)
        assert k.status == "valid", (c.code, k.reason)
    assert any(not c.compatible and "ни в одной характеристике" in (c.excluded_reason or "") for c in r.candidates)


def test_negation_does_not_jump_over_repeated_word(real_engine):
    # «не» относится к «натуральный» (мех), а не к следующей «натуральная кожа»
    r = real_engine.search(SearchRequest(text="мужское пальто нагольное (дубленка), размер 52, мех не натуральный натуральная кожа"))
    feats = {f.property_name: f.value for f in r.features if f.status == "bound"}
    assert feats.get("Натуральный мех") == "Нет" and feats.get("Натуральная кожа") == "Да"
