"""FIXTURE: синтетическая выгрузка КТРУ для модульных тестов.

Это НЕ реальные данные. Структура XML повторяет реальную выгрузку nsiKTRUNew (проверено
по КТРУ xml.zip), коды начинаются с 9 и не существуют в реальном каталоге.
"""
from __future__ import annotations

import io
import zipfile

HEAD = ('<export xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://zakupki.gov.ru/oos/export/1" '
        'xmlns:oos="http://zakupki.gov.ru/oos/types/1"><nsiKTRUs>')
TAIL = "</nsiKTRUs></export>"


def q(*texts):
    return "".join(f"<oos:value><oos:valueCode>q{i}</oos:valueCode><oos:qualityDescription>{t}"
                   f"</oos:qualityDescription></oos:value>" for i, t in enumerate(texts))


def rng(*ranges, okei=("003", "Миллиметр")):
    out = []
    for i, (mn_op, mn, mx_op, mx) in enumerate(ranges):
        parts = []
        if mn is not None:
            parts.append(f"<oos:minMathNotation>{mn_op}</oos:minMathNotation><oos:min>{mn}</oos:min>")
        if mx is not None:
            parts.append(f"<oos:maxMathNotation>{mx_op}</oos:maxMathNotation><oos:max>{mx}</oos:max>")
        ok = f"<oos:OKEI><oos:code>{okei[0]}</oos:code><oos:name>{okei[1]}</oos:name></oos:OKEI>" if okei else ""
        out.append(f"<oos:value><oos:valueCode>r{i}</oos:valueCode>{ok}<oos:valueFormat>N</oos:valueFormat>"
                   f"<oos:rangeSet><oos:valueRange>{''.join(parts)}</oos:valueRange></oos:rangeSet></oos:value>")
    return "".join(out)


def ch(code, name, values, ctype=1, kind=2, req=False):
    return (f"<oos:characteristic><oos:code>{code}</oos:code><oos:name>{name}</oos:name><oos:type>{ctype}</oos:type>"
            f"<oos:kind>{kind}</oos:kind><oos:actual>true</oos:actual><oos:isRequired>{'true' if req else 'false'}"
            f"</oos:isRequired><oos:choiceType>{1 if kind == 1 else 2}</oos:choiceType><oos:values>{values}"
            f"</oos:values></oos:characteristic>")


def pos(code, name, okpd, chars, version=1, status="ACTIVE", template=False, parent=None, start="2021-04-01",
        end=None, nnf=False, update="2025-01-01"):
    par = (f"<oos:parentPositionInfo><oos:code>{parent[0]}</oos:code><oos:version>{parent[1]}</oos:version>"
           f"</oos:parentPositionInfo>") if parent else ""
    end_x = f"<oos:applicationDateEnd>{end}T00:00:00+03:00</oos:applicationDateEnd>" if end else ""
    return (f"<oos:position><oos:data><oos:code>{code}</oos:code><oos:version>{version}</oos:version>"
            f"<oos:inclusionDate>2020-01-01T00:00:00+03:00</oos:inclusionDate>"
            f"<oos:publishDate>2020-01-01T00:00:00+03:00</oos:publishDate>"
            f"<oos:updateDate>{update}T00:00:00+03:00</oos:updateDate><oos:name>{name}</oos:name>"
            f"<oos:OKPD2><oos:code>{okpd}</oos:code><oos:name>ОКПД2 {okpd}</oos:name></oos:OKPD2>"
            f"<oos:status>{status}</oos:status>"
            f"<oos:applicationDateStart>{start}T00:00:00+03:00</oos:applicationDateStart>{end_x}"
            f"<oos:OKEIs><oos:OKEI><oos:code>796</oos:code><oos:name>Штука</oos:name></oos:OKEI></oos:OKEIs>"
            f"<oos:characteristics>{''.join(chars)}</oos:characteristics>"
            f"<oos:isTemplate>{'true' if template else 'false'}</oos:isTemplate>{par}"
            f"<oos:noNewFeatures>{'true' if nnf else 'false'}</oos:noNewFeatures></oos:data></oos:position>")


PLIERS_LEN = rng(("", None, "less", "160"), ("greaterOrEqual", "160", "less", "180"),
                 ("greaterOrEqual", "180", "lessOrEqual", "200"), ("greater", "200", "", None))


def pliers(code, kind_value, **kw):
    return pos(code, "Пассатижи", "25.73.30.163", [
        ch("p-len", "Длина", PLIERS_LEN, ctype=2, req=True),
        ch("p-edge", "Режущие кромки", q("Да", "Нет")),
        ch("p-kind", "Вид пассатижей", q(*kind_value), kind=1, req=True),
    ], **kw)


def build_files() -> dict[str, bytes]:
    tpl = ("25.73.30.163-90000010", 1)
    part1 = [
        pliers("25.73.30.163-90000010", ["Слесарные", "Рыбацкие", "Зажимные", "Переставные"], template=True),
        pliers("25.73.30.163-90000001", ["Слесарные"], parent=tpl),
        pliers("25.73.30.163-90000002", ["Рыбацкие"], parent=tpl),
        pliers("25.73.30.163-90000003", ["Зажимные"], parent=tpl, version=1),
        pliers("25.73.30.163-90000004", ["Переставные"], parent=tpl, start="2030-01-01"),
        pos("31.01.11.150-91000001", "Стул на металлическом каркасе", "31.01.11.150", [
            ch("s-soft", "Наличие мягкого сидения", q("Да"), kind=1, req=True),
            ch("s-arm", "Наличие подлокотников", q("Да", "Нет")),
            ch("s-w", "Ширина сиденья", rng(("greaterOrEqual", "40", "less", "45"), ("greaterOrEqual", "45", "", None),
                                            okei=("004", "Сантиметр")), ctype=2),
        ], parent=("31.01.11.150-91000009", 1)),
        pos("31.01.11.150-91000002", "Стул на металлическом каркасе", "31.01.11.150", [
            ch("s-soft", "Наличие мягкого сидения", q("Нет"), kind=1, req=True),
            ch("s-arm", "Наличие подлокотников", q("Нет")),
        ], parent=("31.01.11.150-91000009", 1), nnf=True),
        pos("31.01.11.150-91000009", "Стул на металлическом каркасе", "31.01.11.150", [
            ch("s-soft", "Наличие мягкого сидения", q("Да", "Нет"), kind=1, req=True),
        ], template=True),
    ]
    part2 = [
        # вторая (более поздняя) версия позиции 90000003 — аннулирована
        pliers("25.73.30.163-90000003", ["Зажимные"], parent=tpl, version=2, status="TERMINATED", update="2026-01-01"),
        pos("28.24.11.000-92000001", "Дрель ручная электрическая", "28.24.11.000", [
            ch("d-pow", "Тип питания", q("От сети"), kind=1, req=True),
            ch("d-w", "Мощность", rng(("greaterOrEqual", "500", "less", "750"), ("greaterOrEqual", "750", "", None),
                                      okei=("212", "Ватт")), ctype=2, req=True),
        ]),
        pos("28.24.11.000-92000002", "Дрель ручная электрическая", "28.24.11.000", [
            ch("d-pow", "Тип питания", q("От аккумулятора"), kind=1, req=True),
            ch("d-v", "Напряжение аккумулятора", rng(("greaterOrEqual", "12", "lessOrEqual", "18"),
                                                     okei=("222", "Вольт")), ctype=2, req=True),
        ]),
        pos("32.50.13.110-93000001", "Позиция вне MVP", "32.50.13.110", []),
        # части товара: цвет каркаса ≠ цвет сиденья (добавлено для плана улучшений, S3)
        *[pos(f"31.01.12.160-9400000{i}", "Кресло офисное", "31.01.12.160", [
            ch("k-arm", "Наличие подлокотников", q(arm), kind=1, req=True),
            ch("k-fc", "Цвет каркаса", q("Черный", "Серый")),
            ch("k-sc", "Цвет сиденья", q("Черный", "Красный", "Синий")),
            ch("k-sh", "Высота сиденья", rng(("greaterOrEqual", "400", "", None)), ctype=2),
            ch("k-um", "Материал обивки сиденья", q("Ткань", "Кожа")),
            ch("k-base", "Тип напольной опоры", q("Ножки", "Колесные опоры")),
            ch("k-uph", "Тип обивки", q("Без обивки", "Ткань", "Экокожа")),
        ]) for i, arm in ((1, "Да"), (2, "Нет"))],
        *[pos(f"31.01.12.170-9500000{i}", "Табурет", "31.01.12.170", [
            ch("t-mat", "Материал", q(mat), kind=1, req=True),
            ch("t-col", "Цвет", q("Черный", "Белый")),
            ch("t-h", "Высота сиденья", rng(("greaterOrEqual", "300", "", None)), ctype=2),
        ]) for i, mat in ((1, "Дерево"), (2, "Металл"))],
    ]
    not_actual = [pliers("25.73.30.163-90000001", ["Удалённые"], version=99)]
    return {
        "a_actual_001.xml": (HEAD + "".join(part1) + TAIL).encode("utf-8"),
        "a_actual_002.xml": (HEAD + "".join(part2) + TAIL).encode("utf-8"),
        "a_not-actual_001.xml": (HEAD + "".join(not_actual) + TAIL).encode("utf-8"),
    }


def write_fixture_dir(path) -> None:
    """Каталог как в реальной выгрузке: внешние zip, внутри по одному XML; один zip вложен в zip."""
    path.mkdir(parents=True, exist_ok=True)
    files = build_files()
    names = sorted(files)
    with zipfile.ZipFile(path / "001_fixture.zip", "w") as z:
        z.writestr("nsiKTRUNew_all_" + names[0].replace("a_", ""), files[names[0]])
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("nsiKTRUNew_all_" + names[1].replace("a_", ""), files[names[1]])
    with zipfile.ZipFile(path / "002_fixture_nested.zip", "w") as z:
        z.writestr("inner.zip", inner.getvalue())
    with zipfile.ZipFile(path / "003_fixture.zip", "w") as z:
        z.writestr("nsiKTRUNew_all_" + names[2].replace("a_", ""), files[names[2]])
