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


def test_real_generic_gloves_need_protection_clarification(real_engine):
    r = real_engine.search(SearchRequest(text="перчатки швейные для защиты от внешних воздействий"))
    assert r.final_code is None and r.question is not None
    assert len(r.compatible_codes) > 1
    assert not any(f.value == "От механических воздействий" for f in r.features)


def test_real_gloves_specific_protection_does_not_conflict(real_engine):
    r = real_engine.search(SearchRequest(text=
        "перчатки швейные для защиты от внешних воздействий, вид защиты: от пониженных температур"))
    assert r.status == "matched" and r.final_code == "14.12.30.150-00000006"


def test_real_long_property_name_preserves_quantity_binding(real_engine):
    r = real_engine.search(SearchRequest(text="ключ гаечный разводной, тип исполнения: b, "
        "длина разводного ключа 25,1 см, размер максимального разведения губок разводного ключа 1,4 см"))
    assert r.status == "matched" and r.final_code == "25.73.30.171-00000001"
