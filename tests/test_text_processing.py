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
