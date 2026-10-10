"""Тип по составу слова (без словаря синонимов): дефис, сложные слова в обе стороны."""
from ktru_assist.nlp.normalize import normalize
from ktru_assist.registry import TypeRegistry
from ktru_assist.text import content_lemmas, head_lemma, lemma


def doc(name):
    h = head_lemma(name)
    return {"code": name, "name": name, "head": h, "head_parts": sorted({h, *h.split("-")}),
            "category": "tools", "active": True, "is_template": False, "name_lemmas": content_lemmas(name)}


REG = TypeRegistry([doc("Электролобзик"), doc("Шуруповерт"), doc("Дрель ручная электрическая"),
                    doc("Вешалка металлическая"), doc("Стойка напольная"), doc("Пила ручная")], aliases=[])


def detect(text):
    return REG.detect(normalize(text).tokens)


def test_catalog_compound_from_two_words():
    d = detect("лобзик электрический 650 вт")
    assert d.heads == [lemma("электролобзик")] and d.type_token_idx


def test_hyphen_single_type():
    assert detect("стеллаж-пила ручная").heads == [lemma("пила")]


def test_hyphen_two_types_needs_confirmation():
    d = detect("дрель-шуруповерт аккумуляторная")
    assert d.heads == sorted([lemma("дрель"), lemma("шуруповерт")])
    assert d.ambiguous_aliases                      # тип подтверждает пользователь


def test_no_compound_without_supporting_word():
    # «электропила»: у позиций «Пила» нет слова на «электр…» — тип не угадывается
    assert detect("электропила цепная").heads == []
    # соседнее слово не начинается с «электр» — «лобзик» один не даёт «электролобзик»
    assert detect("лобзик ручной").heads == []
