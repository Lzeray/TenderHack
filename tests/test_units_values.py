"""Единицы, интервалы с открытыми/закрытыми границами, Decimal."""
from decimal import Decimal

from ktru_assist.catalog.repository import Interval, merge_intervals
from ktru_assist.units import convert, lookup, unit_from_char_name

D = Decimal


def test_exact_conversion_cm_mm():
    assert convert(D("75"), lookup("см"), lookup("мм")) == D("750")
    assert convert(D("0.5"), lookup("кВт"), lookup("Вт")) == D("500")
    assert convert(D("1"), lookup("дюйм"), lookup("мм")) == D("25.4")
    assert convert(D("500"), lookup("г"), lookup("кг")) == D("0.5")


def test_incompatible_dimensions_not_converted():
    assert convert(D("500"), lookup("В"), lookup("Вт")) is None   # В ≠ Вт
    assert convert(D("1"), lookup("кг"), lookup("мм")) is None


def test_unit_from_characteristic_name():
    assert unit_from_char_name("Максимальный крутящий момент (Нм)").key == "nm"
    assert unit_from_char_name("Плотность материала, г/м2").key == "gm2"
    assert unit_from_char_name("Длина") is None


def iv(lo, li, hi, hi_i):
    return Interval(None if lo is None else D(lo), li, None if hi is None else D(hi), hi_i)


def test_open_and_closed_boundaries():
    half_open = iv("160", True, "180", False)          # ≥160 и <180
    assert half_open.contains_point(D("160"))
    assert not half_open.contains_point(D("180"))
    closed = iv("180", True, "200", True)
    assert closed.contains_point(D("200"))
    open_left = iv("200", False, None, False)           # >200
    assert not open_left.contains_point(D("200"))
    assert open_left.contains_point(D("200.0001"))
    below = iv(None, False, "160", False)               # <160
    assert below.contains_point(D("-5")) and not below.contains_point(D("160"))


def test_subset_and_intersection():
    a = iv("10", True, "20", True)
    assert iv("12", True, "15", True).subset_of(a)
    assert not iv("15", True, "25", True).subset_of(a)
    assert iv("15", True, "25", True).intersects(a)
    assert not iv("20", False, "30", True).intersects(a)   # (20,30] ∩ [10,20] = ∅
    assert iv("20", True, "30", True).intersects(a)        # [20,30] ∩ [10,20] = {20}


def test_merge_adjacent_ranges():
    m = merge_intervals([iv("160", True, "180", False), iv("180", True, "200", False), iv("250", True, None, False)])
    assert m == [iv("160", True, "200", False), iv("250", True, None, False)]
    # смежность без общей точки ([..180) и (180..]) не склеивается
    m2 = merge_intervals([iv("160", True, "180", False), iv("180", False, "200", True)])
    assert len(m2) == 2
