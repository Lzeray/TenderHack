"""Импорт: версии, статусы, сроки, not-actual, вложенные zip, диапазоны, шаблоны, идемпотентность."""
import hashlib
import sqlite3

from conftest import AS_OF
from ktru_assist.catalog.importer import run_import


def rows(db, sql, *args):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def test_not_actual_skipped_and_nested_zip_read(fixture_db):
    db, meta = fixture_db
    assert meta["files_actual"] == 2           # второй файл лежит во вложенном zip
    assert meta["files_skipped"] == 1          # not-actual пропущен
    kinds = dict(((r[1], r[2]) for r in rows(db, "SELECT outer_name, inner_name, kind FROM source_files")))
    assert any("not-actual" in k for k in kinds) and "not_actual" in kinds.values()
    # запись из not-actual (version 99, «Удалённые») не попала в базу
    assert rows(db, "SELECT count(*) FROM char_values WHERE text='Удалённые'")[0][0] == 0


def test_latest_version_selected_before_status(fixture_db):
    db, _ = fixture_db
    (ver, status, active, reason), = rows(
        db, "SELECT version, status, active, inactive_reason FROM positions WHERE code='25.73.30.163-90000003'")
    assert (ver, status, active) == (2, "TERMINATED", 0)   # v2 новее v1 → позиция неактивна
    assert "TERMINATED" in reason
    dropped = rows(db, "SELECT version FROM dropped_records WHERE code='25.73.30.163-90000003'")
    assert dropped == [(1,)]


def test_future_start_date_inactive(fixture_db):
    db, _ = fixture_db
    (active, reason), = rows(db, "SELECT active, inactive_reason FROM positions WHERE code='25.73.30.163-90000004'")
    assert active == 0 and "2030-01-01" in reason


def test_ranges_and_inclusivity_preserved(fixture_db):
    db, _ = fixture_db
    got = rows(db, "SELECT min_value, min_inclusive, max_value, max_inclusive, okei_code FROM char_values "
                   "WHERE position_code='25.73.30.163-90000001' AND char_code='p-len' ORDER BY ord")
    assert got == [(None, None, "160", 0, "003"), ("160", 1, "180", 0, "003"),
                   ("180", 1, "200", 1, "003"), ("200", 0, None, None, "003")]


def test_template_parent_required_and_nnf(fixture_db):
    db, _ = fixture_db
    assert rows(db, "SELECT is_template FROM positions WHERE code='25.73.30.163-90000010'") == [(1,)]
    assert rows(db, "SELECT parent_code, parent_version FROM positions WHERE code='25.73.30.163-90000001'") == \
        [("25.73.30.163-90000010", 1)]
    assert rows(db, "SELECT is_required, kind FROM characteristics WHERE position_code='25.73.30.163-90000001' "
                    "AND char_code='p-kind'") == [(1, 1)]
    assert rows(db, "SELECT no_new_features FROM positions WHERE code='31.01.11.150-91000002'") == [(1,)]


def test_category_coverage_and_snapshot(fixture_db):
    db, meta = fixture_db
    assert meta["coverage"]["tools"]["active_final"] == 4       # 3 пассатижей + 2 дрели − 90000003 − 90000004 … см. ниже
    assert meta["coverage"]["furniture"]["active_templates"] == 1
    assert rows(db, "SELECT category FROM positions WHERE code='32.50.13.110-93000001'") == [(None,)]
    assert meta["snapshot"]
    assert meta["as_of"] == AS_OF.isoformat()


def _digest(db):
    con = sqlite3.connect(db)
    h = hashlib.sha256()
    for t in ("positions", "characteristics", "char_values", "dropped_records", "source_files"):
        for r in con.execute(f"SELECT * FROM {t} ORDER BY 1,2"):
            h.update(repr(r).encode())
    con.close()
    return h.hexdigest()


def test_import_idempotent(fixture_src, tmp_path):
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    run_import(fixture_src, a, AS_OF, log=lambda *_: None)
    run_import(fixture_src, b, AS_OF, log=lambda *_: None)
    run_import(fixture_src, b, AS_OF, log=lambda *_: None)   # повторный импорт поверх
    assert _digest(a) == _digest(b)


def test_packed_db_unpacked_on_open(fixture_src, tmp_path):
    """База из git лежит как data/ktru.sqlite.gz: Catalog распаковывает её сам, если .sqlite нет."""
    import gzip
    import shutil

    from ktru_assist.catalog.repository import Catalog
    src = tmp_path / "src.sqlite"
    run_import(fixture_src, src, AS_OF, log=lambda *_: None)
    db = tmp_path / "ktru.sqlite"
    with open(src, "rb") as f, gzip.open(tmp_path / "ktru.sqlite.gz", "wb") as g:
        shutil.copyfileobj(f, g)
    assert not db.exists()
    assert Catalog(db).meta["positions"] > 0
    assert _digest(db) == _digest(src)
