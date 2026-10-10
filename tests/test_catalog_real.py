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
