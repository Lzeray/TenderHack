import pytest
"""Нормализация, опечатки, извлечение: числа, единицы, отрицания, конструкции «свойство: значение»."""
from ktru_assist.nlp.normalize import normalize
from ktru_assist.nlp.typos import TypoCorrector
from ktru_assist.text import MORPH_MODE, lemma


def test_normalization_keeps_numbers_units_codes_and_history():
    nq = normalize("Дрель  BOSCH PSR-14.4 мощностью 0,5кВт, 120х60 СМ")
    kinds = [(t.text, t.kind) for t in nq.tokens]
    assert ("0,5", "number") in kinds and ("квт", "unit") in kinds
    assert ("120", "number") in kinds and ("см", "unit") in kinds
    assert any(k == "code" for _, k in kinds)            # модель не лемматизируется
    assert nq.original.startswith("Дрель  BOSCH")         # исходный текст сохранён
    assert [s.step for s in nq.history][:2] == ["регистр и ё", "пробелы"]


def test_short_unit_words_only_after_number():
    nq = normalize("стул в офис 220 в")
    units = [t for t in nq.tokens if t.kind == "unit"]
    assert len(units) == 1 and units[0].unit_key == "v" and nq.tokens[units[0].i - 1].text == "220"


def test_typo_unique_correction():
    tc = TypoCorrector(["Пассатижи", "Шуруповерт"])
    nq = normalize("пасатижи")
    res = tc.correct(nq.tokens, {})
    assert res[0].status == "corrected" and res[0].corrected == "пассатижи"


def test_typo_ambiguous_offers_choice():
    tc = TypoCorrector(["шкаф", "шарф"])
    nq = normalize("шкрф")
    res = tc.correct(nq.tokens, {})
    assert res[0].status == "ambiguous" and set(res[0].options) == {"шкаф", "шарф"}
    assert nq.tokens[0].text == "шкрф"                    # не исправлено автоматически
    res2 = tc.correct(normalize("шкрф").tokens, {"шкрф": "шарф"})
    assert res2[0].status == "user_choice"


def test_numbers_and_units_not_fuzzy_corrected():
    tc = TypoCorrector(["мм", "миллиметр", "шуруповерт"])
    nq = normalize("шуруповерт 18 мн 12в")
    tc.correct(nq.tokens, {})
    assert [t.text for t in nq.tokens if t.kind == "number"] == ["18", "12"]
    assert any(t.text == "мн" for t in nq.tokens)          # короткое слово не «исправлено» в «мм»


@pytest.mark.skipif(MORPH_MODE != "pymorphy", reason="без словаря нельзя отличить настоящее слово от опечатки")
def test_known_word_not_corrected():
    tc = TypoCorrector(["стул"])
    res = tc.correct(normalize("стол").tokens, {})
    assert res == []                                       # реальное слово русского языка


def test_typo_tie_broken_by_type_head():
    # «куркта» одинаково близка к «курка» и «куртка»; тип товара — только «куртка»
    tc = TypoCorrector(["курка", "куртка"])
    res = tc.correct(normalize("куркта").tokens, {}, type_heads={lemma("куртка")})
    assert res[0].status == "corrected" and res[0].corrected == "куртка"
    assert TypoCorrector(["курка", "куртка"]).correct(normalize("куркта").tokens, {})[0].status == "ambiguous"


def test_snowball_stemmer_merges_word_forms():
    from ktru_assist.morph import stem
    assert stem("металлический") == stem("металлическом") == stem("металлическая")
    assert stem("сиденьем") == stem("сиденья")
    assert stem("менее") == "менее" and stem("без") == "без"      # служебные слова не меняются


def test_catalog_refuses_other_morph_mode(fixture_db, monkeypatch):
    import ktru_assist.catalog.repository as repo
    monkeypatch.setattr(repo, "MORPH_MODE", "snowball" if MORPH_MODE == "pymorphy" else "pymorphy")
    with pytest.raises(RuntimeError):
        repo.Catalog(fixture_db[0])


def test_clothing_size_notation():
    assert "размер 66" in normalize("Футболка женская р.66").text
    assert "размер 48 рост 170-176 см" in normalize("Брюки р-р 48/170-176").text
    # обхват груди (от 76) и детский рост (трёхзначный) размером не считаются
    assert "размер" not in normalize("Жакет р. 104-108/170-176").text
    assert "размер" not in normalize("Жакет р.88").text
    assert "размер" not in normalize("пила 50 р. за штуку").text


def test_dimension_notation_normalization():
    assert "1200-1400 мм" in normalize("длина 1200–1400 мм").text
    assert "1200 мм" in normalize("длина 1 200 мм").text
    assert "98 104 см" in normalize("рост 98 104 см").text            # не разряды
    assert "от 135 до 145 см" in normalize("длина 140±5 см").text
    assert "от 540 до 660 вт" in normalize("мощность 600 ± 10 % Вт").text
    assert "около 140" in normalize("~140 см").text


def test_dimensions_separator_normalization():
    assert "120 x 60 x 75 см" in normalize("стол 120 на 60 на 75 см").text
    assert "120 см x 60 см" in normalize("стол 120 см на 60 см").text
    assert "на 4 ножках" in normalize("стол на 4 ножках").text


def test_quotes_and_size_height_notation():
    assert "«cs 23-355»" in normalize('Пила Metabo "CS 23-355"').text          # парные кавычки — не дюймы
    assert '24 "' in normalize('монитор 24"').text                             # непарная — дюйм
    assert "размер 48-50 рост 182-188 см" in normalize("Куртка 48-50/182-188").text
    assert "размер 54-56 рост 158-164 см" in normalize("Брюки р. 54-56/158-164см").text
    assert "12/24" in normalize("напряжение 12/24 В").text                     # не размер/рост


def test_common_length_misspelling():
    assert "длиной от 200" in normalize("молоток длинной от 200").text
    assert "длина 300" in normalize("молоток длинна 300").text
    assert "длинный молоток" in normalize("длинный молоток").text        # прилагательное не трогаем


def test_homoglyphs_and_layout():
    assert normalize("шкaф для одежды").text == "шкаф для одежды"          # латинская a
    assert normalize("стул мужcкой").text == "стул мужской"
    assert normalize("куртка ххl").text == "куртка xxl"                    # размер — в латиницу
    assert normalize("автоdело").text == "автоdело"                        # латиница без двойника — не трогаем
    assert normalize("irfa lkz jlt;ls").text == "шкаф для одежды"          # раскладка
    assert normalize("dtnhjdrf ltncrfz, hjcn 74").text == "ветровка детская, рост 74"   # запятая — знак
    assert normalize("Bosch GSR 18-2-LI").text == "bosch gsr 18-2-li"       # бренд и код — не раскладка


def test_typo_stem_fallback_and_ending():
    # формы «офисное» нет в словаре каталога, но есть лемма «офисный»: находится через основу
    tc = TypoCorrector(["кресло офисный", "стол круглый", "круг", "дуга"])
    res = tc.correct(normalize("кресло офиссное").tokens, {})
    assert res[0].corrected == "офисное"
    # «кругой»: окончание «-ой» есть только у «круглой» (а не у «круг», «дуга»)
    res = tc.correct(normalize("стол кругой").tokens, {})
    assert res[0].status == "corrected" and res[0].corrected == "круглой"


def test_merged_and_split_words():
    tc = TypoCorrector(["шкаф для одежды", "шуруповерт аккумуляторный", "кресло с подлокотниками"])
    nq = normalize("шкафдля одежды")
    res = tc.correct(nq.tokens, {})
    assert res[0].corrected == "шкаф для" and [t.text for t in nq.tokens] == ["шкаф", "для", "одежды"]
    assert [t.i for t in nq.tokens] == [0, 1, 2]                          # перенумерованы
    assert nq.tokens[0].start == 0 and nq.tokens[1].end == 7              # координаты внутри исходного токена
    nq = normalize("шуруп оверт аккумуляторный 18 в")
    res = tc.correct(nq.tokens, {})
    assert res[0].corrected == "шуруповерт" and nq.tokens[0].text == "шуруповерт" and nq.tokens[1].text == "аккумуляторный"
    assert [t.i for t in nq.tokens] == list(range(len(nq.tokens)))
    # пользователь оставил раздельно — не склеиваем
    nq = normalize("шуруп оверт")
    assert tc.correct(nq.tokens, {"шуруп оверт": "шуруп оверт"}) == []
    # два настоящих слова не склеиваются, даже если вместе — слово каталога
    tc2 = TypoCorrector(["подставка"])
    nq = normalize("под ставка")
    assert tc2.correct(nq.tokens, {}) == [] and len(nq.tokens) == 2
    # выбор пользователя с пробелом разбивает токен
    nq = normalize("креслосподлокотниками")
    tc.correct(nq.tokens, {"креслосподлокотниками": "кресло с подлокотниками"})
    assert [t.text for t in nq.tokens] == ["кресло", "с", "подлокотниками"]


@pytest.mark.skipif(MORPH_MODE != "pymorphy", reason="согласование проверяется по словарю")
def test_adjective_agrees_with_part():
    from ktru_assist.nlp.extract import _agrees
    assert _agrees("деревянная", "столешница") and _agrees("металлическом", "каркасе")
    assert not _agrees("деревянный", "столешница")       # «стол деревянный столешница лдсп»: дерево — про стол
    assert _agrees("лдсп", "столешница")                  # не прилагательное — не проверяется


def test_property_key_merges_spelling_only():
    from ktru_assist.text import property_key
    assert property_key("Наличие мягкого сидения") == property_key("Наличие мягкого сиденья")
    assert property_key("Наличие полки") == property_key("Наличие полок")
    assert property_key("Натуральная мех") == property_key("Натуральный мех")
    assert property_key("Количество закрытых секций") != property_key("Количество открытых секций")
    assert property_key("Длина") != property_key("Ширина")
