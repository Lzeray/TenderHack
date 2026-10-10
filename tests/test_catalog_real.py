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
    assert r.question is not None and r.question.kind == "dims"
    assert r.question.options[0].label == "длина 120 см, ширина 80 см, высота 75 см"
    # пока раскладка не выбрана, габариты не участвуют в подборе
    assert not any(f.status == "bound" and f.property_name and "столешниц" in f.property_name for f in r.features)
    r2 = real_engine.search(SearchRequest(text=t, answers=r.question.options[0].answers, answers_query_hash=r.query_hash))
    bound = {f.property_name: f.value for f in r2.features if f.status == "bound" and f.source == "answer"}
    assert bound == {"Длина столешницы": "120", "Ширина столешницы": "80", "Высота до столешницы": "75"}


def test_dims_packaging_and_missing_axes(real_engine):
    r = real_engine.search(SearchRequest(text="стол письменный в упаковке 120х60х10 см"))
    assert any(f.named_property == "размеры упаковки" for f in r.features)
    r = real_engine.search(SearchRequest(text="сверло по металлу 6х100"))
    assert any(f.named_property == "габариты" and f.status == "unknown_property" for f in r.features)


def test_discrete_range_values(real_engine):
    r = real_engine.search(SearchRequest(text="куртка зимняя из текстильных материалов женская размер 48-50"))
    f = next(f for f in r.features if f.property_name == "Российский размер")
    c = next(c for c in r.candidates if c.compatible)
    k = next(k for k in c.checks if k.feature_id == f.id)
    assert k.status == "valid" and "48" in k.reason and "50" in k.reason
