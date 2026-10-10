"""FIXTURE: синтетический каталог для набора ленивых чисел (lazy_numbers_fixture). Это НЕ реальные данные.

Коды начинаются с 9 и не существуют в реальном каталоге. XML строится теми же помощниками, что tests/fixture_ktru.py,
и импортируется штатным импортёром — так набор и система видят одну и ту же базу без data/ktru.sqlite.
Семейства подобраны так, чтобы числа различали позиции: смежные диапазоны, открытые и закрытые границы,
разрыв между диапазонами (рост халата), открытый верх (мощность шуруповерта), две числовые характеристики (пила).
"""
from __future__ import annotations

import datetime as dt
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AS_OF = dt.date(2026, 10, 9)


def _helpers():
    sys.path.insert(0, str(ROOT / "tests"))
    import fixture_ktru as fx
    return fx


def build_xml() -> bytes:
    fx = _helpers()
    q, rng, ch, pos = fx.q, fx.rng, fx.ch, fx.pos
    mm, cm, w = ("003", "Миллиметр"), ("004", "Сантиметр"), ("212", "Ватт")
    ge, gt, lt, le = "greaterOrEqual", "greater", "less", "lessOrEqual"

    def desk(code, frame, length, template=False):
        return pos(f"31.01.10.000-{code}", "Стол письменный бенчмарка", "31.01.10.000", [
            ch("t-frame", "Тип каркаса", q(*frame), kind=1, req=True),
            ch("t-len", "Длина столешницы", rng(*length, okei=mm), ctype=2, req=True),
        ], template=template)

    def saw(code, kind, length, pitch):
        return pos(f"25.73.30.110-{code}", "Пила ручная бенчмарка", "25.73.30.110", [
            ch("s-kind", "Тип пилы", q(kind), kind=1, req=True),
            ch("s-len", "Длина полотна", rng(*length, okei=mm), ctype=2, req=True),
            ch("s-pitch", "Шаг зубьев", rng(*pitch, okei=mm), ctype=2),
        ])

    def driver(code, power, watts):
        return pos(f"28.24.11.000-{code}", "Шуруповерт бенчмарка", "28.24.11.000", [
            ch("d-pow", "Тип питания", q(power), kind=1, req=True),
            ch("d-w", "Мощность", rng(*watts, okei=w), ctype=2, req=True),
        ])

    def robe(code, sex, height):
        return pos(f"14.12.30.190-{code}", "Халат медицинский бенчмарка", "14.12.30.190", [
            ch("r-sex", "Пол", q(sex), kind=1, req=True),
            ch("r-h", "Рост", rng(*height, okei=cm), ctype=2, req=True),
        ])

    items = [
        desk("95000009", ["Металлический", "Деревянный"], [(ge, "600", lt, "1800")], template=True),
        desk("95000001", ["Металлический"], [(ge, "600", lt, "1000")]),
        desk("95000002", ["Металлический"], [(ge, "1000", lt, "1400")]),
        desk("95000003", ["Металлический"], [(ge, "1400", le, "1800")]),
        desk("95000004", ["Деревянный"], [(ge, "600", lt, "1000")]),
        desk("95000005", ["Деревянный"], [(ge, "1000", le, "1800")]),
        saw("95000011", "Ножовка", [("", None, lt, "300")], [(ge, "2", le, "3")]),
        saw("95000012", "Ножовка", [(ge, "300", lt, "450")], [(ge, "3", le, "5")]),
        saw("95000013", "Ножовка", [(ge, "450", le, "600")], [(gt, "5", le, "8")]),
        saw("95000014", "Лучковая", [(ge, "450", le, "600")], [(ge, "3", le, "5")]),
        driver("95000021", "От сети", [(ge, "300", lt, "500")]),
        driver("95000022", "От сети", [(ge, "500", lt, "800")]),
        driver("95000023", "От сети", [(ge, "800", "", None)]),
        driver("95000024", "От аккумулятора", [(ge, "300", lt, "500")]),
        robe("95000031", "Женский", [(ge, "158", le, "164")]),
        robe("95000032", "Женский", [(ge, "170", le, "176")]),
        robe("95000033", "Женский", [(ge, "182", le, "188")]),
        robe("95000034", "Мужской", [(ge, "170", le, "176")]),
    ]
    return (fx.HEAD + "".join(items) + fx.TAIL).encode("utf-8")


def build_db(workdir: Path) -> Path:
    """Импорт синтетического каталога штатным импортёром; возвращает путь к SQLite."""
    from ktru_assist.catalog.importer import run_import
    workdir = Path(workdir)
    src = workdir / "src"
    src.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src / "001_bench.zip", "w") as z:
        z.writestr("nsiKTRUNew_all_actual_bench_001.xml", build_xml())
    db = workdir / "bench_fixture.sqlite"
    if db.exists():
        db.unlink()
    run_import(src, db, AS_OF, log=lambda *_: None)
    return db


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/bench_fixture")
    print(build_db(out))
