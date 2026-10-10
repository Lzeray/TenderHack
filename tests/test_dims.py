"""Геометрические размеры: общие оси товара (docs/DIMENSIONS_PLAN.md)."""
from ktru_assist.dims import axis_of, context_of
from ktru_assist.text import content_lemmas


def ctx(name):
    return context_of(content_lemmas(name))


def test_overall_axis_vs_part():
    assert axis_of("Высота", ctx("Шкаф для одежды")) == axis_of("Высота шкафа", ctx("Шкаф для одежды"))
    assert axis_of("Глубина стеллажа", ctx("Стеллаж офисный")) is not None
    assert axis_of("Глубина секции стеллажа", ctx("Стеллаж офисный")) is None      # размер части
    assert axis_of("Длина полки", ctx("Шкаф для документов")) is None
    assert axis_of("Толщина материала каркаса", ctx("Стол письменный")) is None    # не ось
    assert axis_of("Высота до столешницы", ctx("Стол обеденный")) is not None
    assert axis_of("Высота (без учета регулировки)", ctx("Стол обеденный")) is not None
    assert axis_of("Длина разводного ключа", ctx("Ключ разводной")) is not None    # слова наименования
