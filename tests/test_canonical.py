"""Скрытая строка запроса «тип; ключ: значение» (docs/PARSE_INPUT_PLAN.md, P4)."""
from ktru_assist.canonical import present, process
from ktru_assist.models import Canonical, Constraint, SearchRequest


def run(engine, text, prev=None, **kw):
    return process(SearchRequest(text=text, canonical=prev or Canonical(), **kw), engine, engine.search)


def bound(r):
    return {(f.property_name, f.value) for f in r.features if f.status == "bound"}


def test_present_is_whole_word():
    assert present("лдсп", "стол ЛДСП деревянный")
    assert not present("дер", "стол деревянный")            # обрывок слова при наборе — не фрагмент
    assert not present(None, "стол")


def test_same_result_as_text_and_key_value_form(engine):
    r_text = engine.search(SearchRequest(text="пассатижи слесарные 190 мм"))
    r = run(engine, "пассатижи слесарные 190 мм")
    assert r.canonical.text.startswith("пассатижи") and "Длина: 190 мм" in r.canonical.text
    assert set(r.compatible_codes) == set(r_text.compatible_codes) and bound(r) == bound(r_text)
    assert r.query["original"] == "пассатижи слесарные 190 мм"


def test_answer_survives_appended_text(engine):
    # «пассатижи» — две позиции, вопрос о виде; ответ живёт и после дописанного текста
    r = run(engine, "пассатижи")
    q = r.question
    opt = q.options[0]
    r = run(engine, "пассатижи", r.canonical, answers=opt.answers or [opt.answer])
    kept = [i for i in r.canonical.items if i.source == "answer"]
    assert kept and kept[0].evidence is None
    # дописанный текст не сбрасывает ответ на вопрос
    r2 = run(engine, "пассатижи, цвет: красный", r.canonical)
    assert any(i.source == "answer" for i in r2.canonical.items)
    assert set(r2.compatible_codes) <= set(r.compatible_codes)


def test_removed_fragment_drops_its_decision(engine):
    r = run(engine, "пассатижи слесарные 190 мм")
    r = run(engine, "пассатижи слесарные 190 мм", r.canonical,
            overrides=[Constraint(property="Длина", remove=True)])
    dec = next(i for i in r.canonical.items if i.source == "override")
    assert dec.evidence and "190" in dec.evidence
    assert not any(f.property_name == "Длина" and f.status == "bound" for f in r.features)
    # фрагмент «190 мм» стёрт — удаление тоже уходит
    r = run(engine, "пассатижи слесарные", r.canonical)
    assert not any(i.source == "override" for i in r.canonical.items)


def test_spelling_corrected_in_visible_text(engine):
    r = run(engine, "пасатижи слесарные")
    assert r.corrected_text == "пассатижи слесарные"
    assert r.canonical.text.startswith("пассатижи")


def test_choice_lives_with_its_fragment_real(real_engine):
    r = run(real_engine, "стол деревянный столешница лдсп")
    assert {"Тип каркаса: Деревянный", "Вид материала столешницы: ЛДСП"} <= {i.text for i in r.canonical.items}
    r = run(real_engine, "стол лдсп")
    amb = next(f for f in r.features if f.status == "ambiguous")
    o = next(o for o in amb.options if o["property_name"] == "Вид материала столешницы")
    r = run(real_engine, "стол лдсп", r.canonical, overrides=[Constraint(property=o["property_code"], value=o["value"])])
    assert not any(f.status == "ambiguous" for f in r.features)
    r = run(real_engine, "стол лдсп деревянный", r.canonical)          # дописали — выбор остался
    assert ("Вид материала столешницы", "ЛДСП") in bound(r) and not any(f.status == "ambiguous" for f in r.features)
    assert r.canonical.text == "стол; Тип каркаса: Деревянный; Вид материала столешницы: ЛДСП"   # без «лдсп» рядом
    r = run(real_engine, "стол деревянный", r.canonical)               # стёрли «лдсп» — выбора нет
    assert not any(i.source == "override" for i in r.canonical.items)
    assert ("Вид материала столешницы", "ЛДСП") not in bound(r)
