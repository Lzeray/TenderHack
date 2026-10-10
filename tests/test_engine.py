"""Сквозной конвейер на FIXTURE-каталоге: статусы, проверки свойств, шаблоны, правки, вопросы."""
from conftest import make_engine
from ktru_assist.models import Constraint, SearchRequest


def search(engine, text, **kw):
    return engine.search(SearchRequest(text=text, **kw))


def check_of(res, code, prop):
    c = next(c for c in res.candidates if c.code == code)
    return next(k for k in c.checks if k.property_name == prop)


def test_matched_single_final_with_range_boundary(engine):
    r = search(engine, "пассатижи слесарные 200 мм")          # 200 входит в [180, 200] (lessOrEqual)
    assert r.status == "matched" and r.final_code == "25.73.30.163-90000001"
    assert check_of(r, "25.73.30.163-90000001", "Длина").status == "valid"
    assert r.completeness.type_domain_complete and r.completeness.type_confirmed


def test_template_never_final(engine):
    r = search(engine, "пассатижи слесарные 170 мм")
    tpl = next(c for c in r.candidates if c.code == "25.73.30.163-90000010")
    assert tpl.is_template and tpl.compatible and tpl.rank is None
    assert r.final_code != "25.73.30.163-90000010"


def test_inactive_versions_excluded_from_domain(engine):
    r = search(engine, "пассатижи зажимные 170 мм")             # 90000003 v2 TERMINATED
    codes = {c.code for c in r.candidates}
    assert "25.73.30.163-90000003" not in codes and "25.73.30.163-90000004" not in codes
    assert r.status in ("conflict", "not_found")


def test_unit_conversion_cm_to_mm(engine):
    r = search(engine, "пассатижи рыбацкие длина 17,5 см")
    k = check_of(r, "25.73.30.163-90000002", "Длина")
    assert k.status == "valid" and "17,5 см" in k.user_value
    assert r.final_code == "25.73.30.163-90000002"


def test_open_boundary_strict_greater(engine):
    r = search(engine, "пассатижи рыбацкие длина 160 мм")      # [160,180) включает 160
    assert check_of(r, "25.73.30.163-90000002", "Длина").status == "valid"


def test_incompatible_units_volt_vs_watt(engine):
    r = search(engine, "дрель ручная электрическая от сети мощность 600 в")
    k = check_of(r, "28.24.11.000-92000001", "Мощность")
    assert k.status == "invalid" and "несовместимая размерность" in k.reason
    assert r.status != "matched"


def test_kw_to_w(engine):
    r = search(engine, "дрель ручная электрическая от сети мощность 0,6 квт")
    assert check_of(r, "28.24.11.000-92000001", "Мощность").status == "valid"
    assert r.status == "matched" and r.final_code == "28.24.11.000-92000001"


def test_negation_boolean(engine):
    r = search(engine, "стул на металлическом каркасе без мягкого сиденья")
    f = next(f for f in r.features if f.property_name == "Наличие мягкого сидения")
    assert f.value == "Нет" and f.negated
    assert r.final_code == "31.01.11.150-91000002"


def test_incomplete_data_asks_question(engine):
    r = search(engine, "пассатижи")
    assert r.status == "clarification_needed" and r.question is not None
    assert r.question.kind == "property"
    assert r.question.worst_case_remaining < r.question.current_remaining


def test_required_property_question_when_single_candidate(engine):
    r = search(engine, "пассатижи слесарные")                   # длина обязательна и не указана
    assert r.status == "clarification_needed" and r.final_code is None
    assert r.question.property_name == "Длина" and r.question.required


def test_unknown_property_reported(engine):
    r = search(engine, "пассатижи слесарные 190 мм, цвет: красный")
    f = next(f for f in r.features if f.evidence and "цвет" in f.evidence)
    assert f.status == "unknown_property"
    assert any(i.code == "unknown_property" for i in r.issues)


def test_unrecognized_fragment_returned(engine):
    r = search(engine, "пассатижи слесарные 190 мм хромированные")
    assert "хромированные" in r.unrecognized


def test_manual_override_has_priority(engine):
    r = search(engine, "пассатижи слесарные 150 мм",
               overrides=[Constraint(property="Длина", op="eq", value="190", unit="мм")])
    text_f = next(f for f in r.features if f.source == "text" and f.property_name == "Длина")
    assert text_f.status == "overridden"
    assert check_of(r, "25.73.30.163-90000001", "Длина").user_value == "190 мм"


def test_remove_extracted_value(engine):
    r = search(engine, "пассатижи слесарные 150 мм", overrides=[Constraint(property="Длина", remove=True)])
    assert next(f for f in r.features if f.property_name == "Длина").status == "removed"
    assert r.final_code is None                                # длина обязательна


def test_conflicting_values_conflict(engine):
    r = search(engine, "пассатижи слесарные рыбацкие 170 мм")
    assert r.status == "conflict" and r.final_code is None


def test_no_new_features_rule(engine):
    r = search(engine, "стул на металлическом каркасе без мягкого сиденья ширина сиденья 42 см")
    k = check_of(r, "31.01.11.150-91000002", "Ширина сиденья")
    assert k.status == "unknown" and "запрещены" in k.reason


def test_answer_and_stale_answer(engine):
    r1 = search(engine, "пассатижи слесарные")
    opt = next(o for o in r1.question.options if o.label.startswith("≥ 160"))
    r2 = search(engine, "пассатижи слесарные", answers=[opt.answer], answers_query_hash=r1.query_hash)
    assert r2.status == "matched"
    r3 = search(engine, "пассатижи рыбацкие", answers=[opt.answer], answers_query_hash=r1.query_hash)
    assert any(i.code == "stale_answers" for i in r3.issues)


def test_type_choice_and_not_found(engine):
    assert search(engine, "утюг паровой").status == "not_found"


def test_limited_search_does_not_prove_uniqueness(fixture_db):
    eng = make_engine(fixture_db[0], top_k=1, type_fetch_limit=2)
    r = eng.search(SearchRequest(text="пассатижи слесарные 190 мм"))
    assert not r.completeness.type_domain_complete
    assert r.status != "matched"
    assert any(i.code == "domain_truncated" for i in r.issues)


def test_top_k_one_still_complete_domain(fixture_db):
    eng = make_engine(fixture_db[0], top_k=1)
    r = eng.search(SearchRequest(text="пассатижи слесарные 190 мм"))
    assert r.completeness.retrieval_returned == 1
    assert r.completeness.type_domain_complete and r.status == "matched"


def test_repeatability(engine):
    a = search(engine, "стул на металлическом каркасе с мягким сиденьем").model_dump(mode="json")
    b = search(engine, "стул на металлическом каркасе с мягким сиденьем").model_dump(mode="json")
    for k in ("elapsed_ms", "timings"):
        a.pop(k), b.pop(k)
    assert a == b


def test_ambiguous_number_binding(engine):
    r = search(engine, "дрель ручная электрическая 15")
    assert r.final_code is None


def test_single_name_needs_support_from_text(engine):
    # в области одно наименование «Дрель ручная электрическая», но в описании только главное слово:
    # тип не подтверждается автоматически, первым идёт вопрос-подтверждение
    r = search(engine, "дрель от сети мощность 600 вт")
    assert r.status != "matched" and r.final_code is None
    assert r.question is not None and r.question.kind == "type"
    r2 = search(engine, "дрель электрическая от сети мощность 600 вт")
    assert r2.status == "matched" and r2.final_code == "28.24.11.000-92000001"


def test_word_after_preposition_is_not_type(engine):
    # «подставка для дрели»: дрель — назначение, а не тип товара
    r = search(engine, "подставка для дрели ручной электрической")
    assert r.status == "not_found" and r.final_code is None


def test_contradictory_values_block_code(engine):
    # переизбыток данных: одно свойство указано двумя несовместимыми значениями
    r = search(engine, "пассатижи слесарные длина 170 мм, длина 210 мм")
    assert r.status == "conflict" and r.final_code is None
    assert any(i.code == "contradictory_values" for i in r.issues)
    assert r.question is not None and len(r.question.options) == 2
    # одно и то же значение в разных единицах — не противоречие
    r2 = search(engine, "пассатижи слесарные длина 17 см, 170 мм")
    assert not any(i.code == "contradictory_values" for i in r2.issues)


def test_repeated_boolean_mentions_are_all_checked(engine):
    r = search(engine, "стул на металлическом каркасе с мягким сиденьем, без мягкого сиденья")
    assert r.final_code is None
    assert any(i.code == "contradictory_values" for i in r.issues)


def test_unknown_reason_separates_not_specified(engine):
    # «не указано» и «не удалось проверить» — разные причины unknown
    r = search(engine, "шкаф для документов металлический ширина 0,8 км")
    for c in r.candidates:
        for k in c.checks:
            assert (k.status == "unknown") == (k.unknown_reason is not None)
            if k.feature_id is None and k.status == "unknown":
                assert k.unknown_reason in ("not_specified", "ambiguous")


def test_level3_scale_suggestion_and_keep(engine):
    # 140 В не подходит ни одной позиции (12–18 В); ровно одно объяснение — пропущенная запятая: 14 В
    text = "дрель ручная электрическая аккумуляторная напряжение аккумулятора 140 В"
    r = search(engine, text)
    s = next(s for s in r.suggestions if s.rule == "scale")
    assert s.proposed == "14 В"
    a, b = s.replace_span
    fixed = text[:a] + s.replacement_text + text[b:]
    assert fixed.endswith("напряжение аккумулятора 14 В")
    assert not search(engine, fixed).suggestions
    # «Оставить»: ключ в confirmed — предложение больше не показывается, проверка по КТРУ не меняется
    r2 = engine.search(SearchRequest(text=text, confirmed=[s.id]))
    assert not r2.suggestions and r2.status == r.status


def test_level3_other_unit(engine):
    r = search(engine, "дрель ручная электрическая от сети мощность 0,6 Вт")
    s = next(s for s in r.suggestions if s.rule == "scale")
    assert s.proposed == "0,6 кВт"


def test_level3_does_not_change_level1(engine):
    # уровень 3 не влияет на кандидатов и код
    text = "дрель ручная электрическая аккумуляторная напряжение аккумулятора 140 В"
    r = search(engine, text)
    r_keep = engine.search(SearchRequest(text=text, confirmed=[s.id for s in r.suggestions]))
    assert [c.code for c in r.candidates] == [c.code for c in r_keep.candidates]
    assert r.final_code == r_keep.final_code


def _check(r, code, name):
    c = next(c for c in r.candidates if c.code == code)
    return next(k for k in c.checks if k.property_name == name)


def test_range_covering_steps_is_compatible(engine):
    # «от 160 до 200»: обе ступени [160;180) и [180;200] целиком внутри — подходят, пометки нет
    k = _check(search(engine, "пассатижи слесарные длина от 160 до 200 мм"), "25.73.30.163-90000001", "Длина")
    assert k.status == "valid" and not k.wider


def test_range_partially_inside_step_is_wider(engine):
    # «от 170 до 190»: ни одна ступень не внутри целиком — совместимо, но значение КТРУ шире запроса
    k = _check(search(engine, "пассатижи слесарные длина от 170 до 190 мм"), "25.73.30.163-90000001", "Длина")
    assert k.status == "valid" and k.wider


def test_range_boundary_point_is_not_neighbour_step(engine):
    # «от 160 до 180»: ступень [160;180); [180;200] касается одной точкой 180 и не считается
    k = _check(search(engine, "пассатижи слесарные длина от 160 до 180 мм"), "25.73.30.163-90000001", "Длина")
    assert k.status == "valid" and not k.wider and "180 и" not in k.reason.split("подходит")[1]


def test_approx_is_five_percent_for_measures_only(engine):
    f = next(f for f in search(engine, "пассатижи слесарные длина около 180 мм").features if f.property_name == "Длина")
    assert (f.op, f.value, f.value_to) == ("between", "171", "189")
