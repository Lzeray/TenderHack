"""Импорт выгрузки КТРУ (ЕИС, fcs_nsi/nsiKTRUNew) в SQLite.

Правила (docs/DATA.md):
1. Читаются только вложенные XML с «actual» в имени; файлы «not-actual»/«not_actual»
   пропускаются и учитываются в отчёте.
2. Для каждого кода позиции сначала выбирается запись с максимальным `version`
   (при равенстве — с более поздним updateDate, затем publishDate, затем по имени файла);
   отброшенные записи попадают в таблицу `dropped_records`.
3. Только после выбора версии проверяются статус и сроки применения на дату `as_of`.
4. Сохраняются: обязательность и вид характеристик, ОКЕИ, допустимые значения,
   диапазоны с включённостью границ, родительские связи, признак шаблона, запрет
   дополнительных характеристик, рубрики, источник записи.
5. Характеристики сохраняются для направлений MVP (или для всех при --all-characteristics).

Импорт идемпотентен: база собирается во временный файл и атомарно заменяет прежнюю.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import io
import json
import os
import sqlite3
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator
from xml.etree.ElementTree import Element, iterparse

from ..config import CATEGORIES, VERSIONS, category_for_okpd2
from ..text import MORPH_MODE, content_lemmas, head_lemma

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE source_files(
  outer_name TEXT, inner_name TEXT, kind TEXT, positions INTEGER, sha256 TEXT,
  PRIMARY KEY(outer_name, inner_name));
CREATE TABLE positions(
  code TEXT PRIMARY KEY, version INTEGER NOT NULL, version_code TEXT, name TEXT NOT NULL,
  okpd2_code TEXT, okpd2_name TEXT, status TEXT, is_template INTEGER NOT NULL,
  parent_code TEXT, parent_version INTEGER, no_new_features INTEGER,
  application_start TEXT, application_end TEXT, inclusion_date TEXT, publish_date TEXT,
  update_date TEXT, category TEXT, rubrics TEXT, okeis TEXT, has_characteristics INTEGER,
  active INTEGER NOT NULL, inactive_reason TEXT, head TEXT, name_lemmas TEXT,
  source_file TEXT NOT NULL);
CREATE INDEX positions_category ON positions(category, active);
CREATE INDEX positions_head ON positions(head);
CREATE INDEX positions_parent ON positions(parent_code);
CREATE TABLE characteristics(
  position_code TEXT NOT NULL, ord INTEGER NOT NULL, char_code TEXT NOT NULL, name TEXT NOT NULL,
  char_type INTEGER, kind INTEGER, is_required INTEGER, choice_type INTEGER, actual INTEGER,
  PRIMARY KEY(position_code, char_code));
CREATE TABLE char_values(
  position_code TEXT NOT NULL, char_code TEXT NOT NULL, ord INTEGER NOT NULL, value_code TEXT,
  value_kind TEXT NOT NULL,            -- quality | range | concrete | empty
  text TEXT, okei_code TEXT, okei_name TEXT, value_format TEXT,
  min_value TEXT, min_inclusive INTEGER, max_value TEXT, max_inclusive INTEGER,
  concrete_value TEXT,
  PRIMARY KEY(position_code, char_code, ord));
CREATE TABLE dropped_records(code TEXT, version INTEGER, status TEXT, source_file TEXT, reason TEXT);
CREATE TABLE import_issues(code TEXT, issue TEXT, detail TEXT);
"""

NS_LOCAL = lambda tag: tag.rsplit("}", 1)[-1]  # noqa: E731


def _ch(el: Element | None, name: str) -> Element | None:
    if el is None:
        return None
    for c in el:
        if NS_LOCAL(c.tag) == name:
            return c
    return None


def _chs(el: Element | None, name: str) -> list[Element]:
    if el is None:
        return []
    return [c for c in el if NS_LOCAL(c.tag) == name]


def _tx(el: Element | None, name: str) -> str | None:
    c = _ch(el, name)
    if c is None or c.text is None:
        return None
    return c.text.strip()


def _bool(v: str | None) -> int | None:
    if v is None:
        return None
    return 1 if v.lower() == "true" else 0


def _dec(v: str | None) -> str | None:
    """Число как строка Decimal без потери точности; некорректное → None."""
    if v is None:
        return None
    try:
        return str(Decimal(v))
    except InvalidOperation:
        return None


def classify_inner(name: str) -> str:
    low = name.lower().replace("-", "_")
    if "not_actual" in low:
        return "not_actual"
    if "actual" in low:
        return "actual"
    return "unknown"


@dataclass
class Record:
    code: str
    version: int
    data: dict
    characteristics: list
    source_file: str
    sort_key: tuple = field(default=())


def parse_position(pos: Element, source_file: str) -> Record:
    d = _ch(pos, "data")
    okpd = _ch(d, "OKPD2")
    parent = _ch(d, "parentPositionInfo")
    rub = [{"code": _tx(r, "code"), "name": _tx(r, "name")} for r in _chs(_ch(d, "rubricators"), "rubricatorInfo")]
    okeis = [{"code": _tx(o, "code"), "name": _tx(o, "name")} for o in _chs(_ch(d, "OKEIs"), "OKEI")]
    chars = []
    for i, c in enumerate(_chs(_ch(d, "characteristics"), "characteristic")):
        vals = []
        for j, v in enumerate(_chs(_ch(c, "values"), "value")):
            okei = _ch(v, "OKEI")
            base = {
                "ord": j, "value_code": _tx(v, "valueCode"), "text": None,
                "okei_code": _tx(okei, "code"), "okei_name": _tx(okei, "name"),
                "value_format": _tx(v, "valueFormat"), "min_value": None, "min_inclusive": None,
                "max_value": None, "max_inclusive": None, "concrete_value": None,
            }
            q = _tx(v, "qualityDescription")
            rs = _ch(v, "rangeSet")
            vs = _ch(v, "valueSet")
            if q is not None:
                base.update(value_kind="quality", text=q)
            elif rs is not None:
                r = _ch(rs, "valueRange")
                mn, mx = _tx(r, "minMathNotation"), _tx(r, "maxMathNotation")
                base.update(
                    value_kind="range",
                    min_value=_dec(_tx(r, "min")),
                    min_inclusive=None if mn is None else int(mn == "greaterOrEqual"),
                    max_value=_dec(_tx(r, "max")),
                    max_inclusive=None if mx is None else int(mx.replace(" ", "") == "lessOrEqual"),
                )
            elif vs is not None:
                base.update(value_kind="concrete", concrete_value=_dec(_tx(vs, "concreteValue")))
            else:
                base.update(value_kind="empty")
            vals.append(base)
        chars.append({
            "ord": i, "char_code": _tx(c, "code"), "name": _tx(c, "name") or "",
            "char_type": int(_tx(c, "type") or 0) or None, "kind": int(_tx(c, "kind") or 0) or None,
            "is_required": _bool(_tx(c, "isRequired")), "choice_type": int(_tx(c, "choiceType") or 0) or None,
            "actual": _bool(_tx(c, "actual")), "values": vals,
        })
    data = {
        "code": _tx(d, "code"), "version": int(_tx(d, "version") or 0), "version_code": _tx(d, "versionCode"),
        "name": (_tx(d, "name") or "").strip(), "okpd2_code": _tx(okpd, "code"), "okpd2_name": _tx(okpd, "name"),
        "status": _tx(d, "status"), "is_template": _bool(_tx(d, "isTemplate")) or 0,
        "parent_code": _tx(parent, "code"),
        "parent_version": int(_tx(parent, "version")) if _tx(parent, "version") else None,
        "no_new_features": _bool(_tx(d, "noNewFeatures")),
        "application_start": _tx(d, "applicationDateStart"), "application_end": _tx(d, "applicationDateEnd"),
        "inclusion_date": _tx(d, "inclusionDate"), "publish_date": _tx(d, "publishDate"),
        "update_date": _tx(d, "updateDate"), "rubrics": rub, "okeis": okeis,
    }
    rec = Record(data["code"], data["version"], data, chars, source_file)
    rec.sort_key = (data["version"], data["update_date"] or "", data["publish_date"] or "", source_file)
    return rec


def iter_xml_streams(src: Path) -> Iterator[tuple[str, str, str, bytes | None]]:
    """(outer, inner, kind, bytes|None) для каждого XML: каталог с zip, zip или XML."""
    paths: list[Path]
    if src.is_dir():
        paths = sorted(Path(p) for p in glob.glob(str(src / "**" / "*"), recursive=True)
                       if p.lower().endswith((".zip", ".xml")))
    else:
        paths = [src]
    for p in paths:
        if p.suffix.lower() == ".xml":
            kind = classify_inner(p.name)
            yield p.name, p.name, kind, (p.read_bytes() if kind == "actual" else None)
            continue
        yield from _iter_zip(p.name, zipfile.ZipFile(p))


def _iter_zip(outer: str, z: zipfile.ZipFile) -> Iterator[tuple[str, str, str, bytes | None]]:
    for name in sorted(z.namelist()):
        if name.lower().endswith(".zip"):  # вложенный архив
            yield from _iter_zip(f"{outer}/{name}", zipfile.ZipFile(io.BytesIO(z.read(name))))
        elif name.lower().endswith(".xml"):
            kind = classify_inner(name)
            yield outer, name, kind, (z.read(name) if kind == "actual" else None)


def parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    return dt.date.fromisoformat(s[:10])


def activity(data: dict, as_of: dt.date) -> tuple[int, str | None]:
    """Применимость выбранной версии на дату as_of."""
    if data["status"] != "ACTIVE":
        return 0, f"статус {data['status']}"
    start = parse_date(data["application_start"])
    end = parse_date(data["application_end"])
    if start and start > as_of:
        return 0, f"применяется с {start.isoformat()}"
    if end and end < as_of:
        return 0, f"применение окончено {end.isoformat()}"
    return 1, None


def run_import(src: Path, db_path: Path, as_of: dt.date, all_characteristics: bool = False,
               log=print) -> dict:
    best: dict[str, Record] = {}
    dropped: list[tuple] = []
    files: list[tuple] = []
    for outer, inner, kind, payload in iter_xml_streams(src):
        if kind != "actual":
            files.append((outer, inner, kind, 0, None))
            continue
        n = 0
        sha = hashlib.sha256(payload).hexdigest()
        for _ev, el in iterparse(io.BytesIO(payload)):
            if NS_LOCAL(el.tag) != "position":
                continue
            rec = parse_position(el, f"{outer}/{inner}")
            el.clear()
            rec.data["n_chars"] = len(rec.characteristics)
            if not all_characteristics and category_for_okpd2(rec.data["okpd2_code"]) is None:
                rec.characteristics = []  # экономия памяти: вне MVP храним только заголовок
            n += 1
            prev = best.get(rec.code)
            if prev is None or rec.sort_key > prev.sort_key:
                if prev is not None:
                    dropped.append((prev.code, prev.version, prev.data["status"], prev.source_file,
                                    f"есть более поздняя запись версии {rec.version}"))
                best[rec.code] = rec
            else:
                dropped.append((rec.code, rec.version, rec.data["status"], rec.source_file,
                                f"есть более поздняя запись версии {prev.version}"))
        files.append((outer, inner, kind, n, sha))
        log(f"  {outer}/{inner}: {n} позиций")

    tmp = db_path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    issues = []
    coverage = {k: {"title": v["title"], "okpd2_prefixes": v["okpd2_prefixes"], "positions": 0, "active": 0,
                    "active_final": 0, "active_templates": 0, "with_characteristics": 0}
                for k, v in CATEGORIES.items()}
    status_counts: dict[str, int] = {}
    for code in sorted(best):
        rec = best[code]
        d = rec.data
        cat = category_for_okpd2(d["okpd2_code"])
        act, reason = activity(d, as_of)
        status_counts[d["status"] or "?"] = status_counts.get(d["status"] or "?", 0) + 1
        keep_chars = all_characteristics or cat is not None
        con.execute(
            "INSERT INTO positions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (code, d["version"], d["version_code"], d["name"], d["okpd2_code"], d["okpd2_name"], d["status"],
             d["is_template"], d["parent_code"], d["parent_version"], d["no_new_features"],
             d["application_start"], d["application_end"], d["inclusion_date"], d["publish_date"],
             d["update_date"], cat, json.dumps(d["rubrics"], ensure_ascii=False),
             json.dumps(d["okeis"], ensure_ascii=False), int(d["n_chars"] > 0), act, reason,
             head_lemma(d["name"]) if cat else None,
             " ".join(content_lemmas(d["name"])) if cat else None, rec.source_file))
        if cat:
            c = coverage[cat]
            c["positions"] += 1
            c["active"] += act
            c["active_final"] += act and not d["is_template"]
            c["active_templates"] += act and d["is_template"]
            c["with_characteristics"] += act and d["n_chars"] > 0
        if keep_chars:
            seen = set()
            for ch in rec.characteristics:
                if ch["char_code"] in seen:
                    issues.append((code, "duplicate_characteristic", ch["char_code"]))
                    continue
                seen.add(ch["char_code"])
                con.execute("INSERT INTO characteristics VALUES(?,?,?,?,?,?,?,?,?)",
                            (code, ch["ord"], ch["char_code"], ch["name"], ch["char_type"], ch["kind"],
                             ch["is_required"], ch["choice_type"], ch["actual"]))
                for v in ch["values"]:
                    con.execute("INSERT INTO char_values VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (code, ch["char_code"], v["ord"], v["value_code"], v["value_kind"], v["text"],
                                 v["okei_code"], v["okei_name"], v["value_format"], v["min_value"],
                                 v["min_inclusive"], v["max_value"], v["max_inclusive"], v["concrete_value"]))
    # Проверка родительских связей (не додумываем: только фиксируем расхождения).
    for code, pcode, pver in con.execute(
            "SELECT code, parent_code, parent_version FROM positions WHERE parent_code IS NOT NULL").fetchall():
        row = con.execute("SELECT version, is_template FROM positions WHERE code=?", (pcode,)).fetchone()
        if row is None:
            issues.append((code, "parent_missing", pcode))
        elif pver is not None and row[0] != pver:
            issues.append((code, "parent_version_mismatch", f"{pcode}: ссылка v{pver}, в снимке v{row[0]}"))
        elif not row[1]:
            issues.append((code, "parent_not_template", pcode))
    con.executemany("INSERT INTO dropped_records VALUES(?,?,?,?,?)", dropped)
    con.executemany("INSERT INTO import_issues VALUES(?,?,?)", issues)
    con.executemany("INSERT INTO source_files VALUES(?,?,?,?,?)", files)
    actual_files = [f for f in files if f[2] == "actual"]
    snapshot = sorted({f[1].rsplit("_", 1)[0] for f in actual_files})
    meta = {
        "snapshot": ",".join(snapshot),
        "as_of": as_of.isoformat(),
        "imported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "importer_version": VERSIONS["importer"],
        "source": str(src),
        "files_actual": len(actual_files),
        "files_skipped": len(files) - len(actual_files),
        "records_read": sum(f[3] for f in files),
        "positions": len(best),
        "dropped_records": len(dropped),
        "status_counts": status_counts,
        "coverage": coverage,
        "issues": {k: sum(1 for i in issues if i[1] == k) for k in sorted({i[1] for i in issues})},
        "characteristics_scope": "all" if all_characteristics else "mvp",
        "morph": MORPH_MODE,   # нормализация словоформ, которой посчитаны леммы наименований
    }
    for k, v in meta.items():
        con.execute("INSERT INTO meta VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))
    con.commit()
    con.close()
    os.replace(tmp, db_path)
    return meta
