"""Read XLSX exports and label parsing/quality; never invent KTRU ground truth."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import posixpath
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile

from ..units import lookup

VERSION = "1.0"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADERS = ["ID СТЕ", "Наименование СТЕ", "Модель", "Производитель", "Страна происхождения", "Характеристики"]
REFERENCE_HEADERS = ["Конечная категория ПП", "Код КПГЗ", "Наименование кода КПГЗ", "Название характеристики",
                     "Тип (базовая/эталонная/категореобразующая)", "Тип характеристики", "Значения характеристики",
                     "Единица измерения", "ID связанной эталонной характеристики СПГЗ",
                     "Наименование связанной эталонной характеристики СПГЗ", "Значения связанной эталонной характеристики СПГЗ"]
MISSING = {"", "-", "не задано", "(не задано)", "неизвестен", "неизвестно"}
NUMBER = r"[-+]?\d+(?:[.,]\d+)?"
VALUE_START = re.compile(r"\s+(?=(?:\(не задано\)|не задано|(?:до|от|не менее|не более)\s+\d|[<>≤≥]|[-+]?\d))", re.I)
QUANTITY = re.compile(rf"^(?P<op>не менее|не более|до|от|>=|<=|[<>≤≥])?\s*(?P<a>{NUMBER})(?:\s*[-–]\s*(?P<b>{NUMBER}))?\s*(?P<unit>[^\d]*)$")
DIMENSIONS = re.compile(rf"^({NUMBER})\s*[xх×]\s*({NUMBER})(?:\s*[xх×]\s*({NUMBER}))?\s*([^\d]*)$", re.I)
SEED_NAMES = {
    "Тип", "Тип инструмента", "Тип питания", "Тип патрона", "Тип замка", "Тип застежки",
    "Тип сумки", "Тип переноски", "Тип сейфа", "Цвет", "Материал", "Бренд", "Комплектация",
    "Особенности", "Функциональные особенности", "Конструктивные особенности", "Дополнительные функции",
    "Режим работы", "Режимы работы", "Половая принадлежность", "Специальные отделения", "Упаковка",
    "Назначение", "Назначение рюкзака", "Кострукция", "Конструкция", "Кассовое отделение",
}


def key(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split())


def xlsx_rows(path: Path):
    """Stream every sheet, retaining actual Excel row numbers and text cells."""
    with zipfile.ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            with z.open("xl/sharedStrings.xml") as stream:
                for event, el in ET.iterparse(stream, events=("end",)):
                    if el.tag == f"{{{NS['s']}}}si":
                        strings.append("".join(t.text or "" for t in el.findall(".//s:t", NS)))
                        el.clear()
        relationships = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in relationships}
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            rel = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = targets[rel]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            with z.open(member) as stream:
                parser = ET.iterparse(stream, events=("start", "end"))
                _, root = next(parser)
                sheet_data = None
                for event, el in parser:
                    if event == "start" and el.tag == f"{{{NS['s']}}}sheetData":
                        sheet_data = el
                    if event != "end" or el.tag != f"{{{NS['s']}}}row":
                        continue
                    cells = {}
                    for c in el.findall("s:c", NS):
                        col = re.match(r"[A-Z]+", c.get("r", "")).group()
                        v = c.find("s:v", NS)
                        value = v.text or "" if v is not None else ""
                        if c.get("t") == "s":
                            value = strings[int(value)]
                        elif c.get("t") == "inlineStr":
                            value = "".join(t.text or "" for t in c.findall(".//s:t", NS))
                        cells[col] = value
                    yield sheet.get("name"), int(el.get("r")), cells
                    if sheet_data is not None:
                        sheet_data.remove(el)
                    else:
                        el.clear()


def split_feature(raw: str, names: dict[str, str]):
    raw = raw.strip()
    if ":" in raw:
        name, value = raw.split(":", 1)
        if name.strip() and value.strip():
            return name.strip(), value.strip(), "explicit_separator"
    # Longest known prefix. Unresolved segments remain intact for human review.
    parts = raw.split()
    for i in range(len(parts) - 1, 0, -1):
        prefix = " ".join(parts[:i])
        if key(prefix) in names:
            return prefix, " ".join(parts[i:]), "dictionary_prefix"
    m = VALUE_START.search(raw)
    if m:
        return raw[:m.start()].strip(), raw[m.end():].strip(), "numeric_boundary"
    return None, raw, "unresolved"


def annotate(raw: str, names: dict[str, str]):
    name, value, method = split_feature(raw, names)
    result = {"name": name, "value": value, "method": method, "kind": "text",
              "numbers": [], "unit_raw": None, "unit_key": None, "dimension": None,
              "base_numbers": [], "operator": None, "issues": []}
    if name is None:
        result["issues"].append("unresolved_property")
    if key(value) in MISSING or key(value).startswith("(не задано)"):
        result["kind"] = "missing"
        result["issues"].append("missing_value")
        return result
    dims = DIMENSIONS.fullmatch(value)
    m = QUANTITY.fullmatch(value)
    if dims:
        result["kind"] = "dimensions"
        nums = [dims.group(i) for i in (1, 2, 3) if dims.group(i) is not None]
        unit_text = dims.group(4).strip()
        result["issues"].append("dimension_axes_unassigned")
    elif m:
        result["kind"] = "range" if m.group("b") else "number"
        nums = [m.group("a")] + ([m.group("b")] if m.group("b") else [])
        unit_text = m.group("unit").strip()
        result["operator"] = m.group("op") or ("between" if m.group("b") else "eq")
    else:
        return result
    numbers = [Decimal(n.replace(",", ".")) for n in nums]
    result["numbers"] = [str(n) for n in numbers]
    result["unit_raw"] = unit_text or None
    unit = lookup(unit_text) if unit_text else None
    if unit:
        result.update(unit_key=unit.key, dimension=unit.dimension,
                      base_numbers=[str(n * unit.factor) for n in numbers])
    elif unit_text:
        result["issues"].append("unrecognized_unit")
    else:
        result["issues"].append("unit_not_specified")
    if any(n == 0 for n in numbers):
        result["issues"].append("zero_value_review")
    if len(numbers) == 2 and result["kind"] == "range" and numbers[0] > numbers[1]:
        result["issues"].append("reversed_range")
    return result


SCHEMA = """
CREATE TABLE sources(id INTEGER PRIMARY KEY, filename TEXT, sha256 TEXT, category TEXT);
CREATE TABLE products(id INTEGER PRIMARY KEY, source_id INTEGER, sheet TEXT, row_number INTEGER,
 ste_id TEXT, name TEXT, model TEXT, manufacturer TEXT, country TEXT, raw_characteristics TEXT,
 raw_cells TEXT, quality_status TEXT, ktru_code TEXT, annotation_status TEXT DEFAULT 'unreviewed');
CREATE TABLE features(id INTEGER PRIMARY KEY, product_id INTEGER, ordinal INTEGER, raw TEXT,
 name TEXT, name_key TEXT, value TEXT, method TEXT, kind TEXT, numbers TEXT, operator TEXT,
 unit_raw TEXT, unit_key TEXT, dimension TEXT, base_numbers TEXT);
CREATE TABLE issues(id INTEGER PRIMARY KEY, product_id INTEGER, feature_id INTEGER,
 code TEXT, severity TEXT, detail TEXT);
CREATE TABLE category_properties(id INTEGER PRIMARY KEY, source_id INTEGER, sheet TEXT, row_number INTEGER,
 category_name TEXT, kpgz_code TEXT, kpgz_name TEXT, property_name TEXT, property_role TEXT,
 property_type TEXT, allowed_values_raw TEXT, unit_raw TEXT, spgz_id TEXT, spgz_name TEXT,
 spgz_values_raw TEXT, raw_cells TEXT, quality_labels TEXT, annotation_status TEXT DEFAULT 'unreviewed');
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX features_product ON features(product_id);
CREATE INDEX features_name ON features(name_key);
CREATE INDEX products_ste_id ON products(ste_id);
CREATE INDEX issues_product ON issues(product_id);
"""


def export_review(con: sqlite3.Connection, review: Path):
    """Deterministic sample per source and issue, with full context for review."""
    review.parent.mkdir(parents=True, exist_ok=True)
    with review.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["record_type", "record_id", "issue", "file", "sheet", "row", "ste_id", "name",
                         "fragment", "full_context", "review_decision", "corrected_property", "corrected_value",
                         "verified_ktru_code", "reviewer"])
        sources = con.execute("SELECT id,filename FROM sources ORDER BY id").fetchall()
        codes = [r[0] for r in con.execute("SELECT DISTINCT code FROM issues ORDER BY code")]
        for sid, filename in sources:
            for code in codes:
                for r in con.execute("SELECT p.id,i.code,p.sheet,p.row_number,p.ste_id,p.name,i.detail,p.raw_characteristics FROM issues i JOIN products p ON p.id=i.product_id WHERE i.code=? AND p.source_id=? ORDER BY i.id LIMIT 30", (code, sid)):
                    writer.writerow(["product", r[0], r[1], filename, *r[2:], "", "", "", "", ""])
            for code in ("missing_property_name", "missing_allowed_values", "unrecognized_unit"):
                for r in con.execute("SELECT id,sheet,row_number,property_name,raw_cells FROM category_properties WHERE source_id=? AND quality_labels LIKE ? ORDER BY id LIMIT 30", (sid, '%"' + code + '"%')):
                    writer.writerow(["category_property", r[0], code, filename, r[1], r[2], "", r[3], "", r[4], "", "", "", "", ""])


def run(src: Path, out: Path, report: Path, review: Path, catalog: Path | None = None):
    paths = sorted(src.glob("*.xlsx")) if src.is_dir() else [src]
    paths = [p for p in paths if not p.name.startswith("~$")]
    if not paths:
        raise ValueError("No XLSX sources found")
    names = {key(n): n for n in SEED_NAMES}
    if catalog and catalog.exists():
        with sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True) as cat:
            for (name,) in cat.execute("SELECT DISTINCT name FROM characteristics"):
                names[key(name)] = name
    # Discover numeric property boundaries first, for later categorical values.
    for path in paths:
        sheet_types = {}
        for sheet, row, cells in xlsx_rows(path):
            if not any(cells.values()):
                continue
            if sheet not in sheet_types:
                sheet_types[sheet] = "reference" if cells.get("A") == REFERENCE_HEADERS[0] else "products"
                continue
            if sheet_types[sheet] == "reference":
                for col in ("D", "J"):
                    name = cells.get(col, "").strip()
                    if name:
                        names[key(name)] = name
                continue
            for raw in cells.get("F", "").split("|"):
                m = VALUE_START.search(raw.strip())
                if m:
                    name = raw.strip()[:m.start()].strip()
                    if name:
                        names[key(name)] = name
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    if tmp.exists():
        raise FileExistsError(f"Previous temporary import exists: {tmp}")
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    counts = Counter()
    per_file = {}
    seen_ids = set()
    try:
        for path in paths:
            with path.open("rb") as f:
                sha = hashlib.file_digest(f, "sha256").hexdigest()
            sid = con.execute("INSERT INTO sources(filename,sha256,category) VALUES(?,?,?)",
                              (path.name, sha, path.stem)).lastrowid
            local = Counter()
            sheet_types = {}
            for sheet, row, cells in xlsx_rows(path):
                if not any(cells.values()):
                    local["blank_rows"] += 1
                    continue
                if sheet not in sheet_types:
                    headers = [cells.get(c, "").strip() for c in "ABCDEFGHIJK"]
                    if headers[:6] == HEADERS and not any(headers[6:]):
                        sheet_types[sheet] = "products"
                    elif headers == REFERENCE_HEADERS:
                        sheet_types[sheet] = "reference"
                    else:
                        raise ValueError(f"Unexpected headers in {path.name}/{sheet}: {headers}")
                    continue
                if sheet_types[sheet] == "reference":
                    vals = [cells.get(c, "") for c in "ABCDEFGHIJK"]
                    labels = []
                    if not vals[3].strip():
                        labels.append("missing_property_name")
                    if key(vals[6]) in MISSING:
                        labels.append("missing_allowed_values")
                    if vals[7].strip() and not lookup(vals[7]):
                        labels.append("unrecognized_unit")
                    con.execute("INSERT INTO category_properties(source_id,sheet,row_number,category_name,kpgz_code,kpgz_name,property_name,property_role,property_type,allowed_values_raw,unit_raw,spgz_id,spgz_name,spgz_values_raw,raw_cells,quality_labels) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (sid, sheet, row, *vals, json.dumps(cells, ensure_ascii=False), json.dumps(labels)))
                    local["category_properties"] += 1
                    if labels:
                        local["category_properties_needs_review"] += 1
                    continue
                values = [cells.get(c, "") for c in "ABCDEF"]
                pid = con.execute("INSERT INTO products(source_id,sheet,row_number,ste_id,name,model,manufacturer,country,raw_characteristics,raw_cells,quality_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                  (sid, sheet, row, *values, json.dumps(cells, ensure_ascii=False), "parsed")).lastrowid
                product_codes = set()

                def issue(code, detail, fid=None, severity="review"):
                    con.execute("INSERT INTO issues(product_id,feature_id,code,severity,detail) VALUES(?,?,?,?,?)",
                                (pid, fid, code, severity, detail))
                    counts[code] += 1
                    product_codes.add(code)

                for col, label in zip("ABCDEF", HEADERS):
                    if key(cells.get(col, "")) in MISSING:
                        issue("missing_field", label)
                if values[0]:
                    if values[0] in seen_ids:
                        issue("duplicate_ste_id", values[0])
                    seen_ids.add(values[0])
                if any(c not in "ABCDEF" and v for c, v in cells.items()):
                    issue("extra_columns", "Preserved in raw_cells")
                seen_features = {}
                for ordinal, segment in enumerate(values[5].split("|"), 1):
                    if not segment.strip():
                        continue
                    f = annotate(segment, names)
                    fid = con.execute("INSERT INTO features(product_id,ordinal,raw,name,name_key,value,method,kind,numbers,operator,unit_raw,unit_key,dimension,base_numbers) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                      (pid, ordinal, segment, f["name"], key(f["name"]) if f["name"] else None,
                                       f["value"], f["method"], f["kind"], json.dumps(f["numbers"]), f["operator"],
                                       f["unit_raw"], f["unit_key"], f["dimension"], json.dumps(f["base_numbers"]))).lastrowid
                    for code in f["issues"]:
                        issue(code, segment, fid)
                    if f["name"]:
                        nk = key(f["name"])
                        signature = (f["kind"], f["operator"], f["dimension"] or f["unit_raw"],
                                     tuple(Decimal(n) for n in (f["base_numbers"] or f["numbers"])) or key(f["value"]))
                        if nk in seen_features:
                            issue("duplicate_feature" if signature == seen_features[nk] else "conflicting_feature_values",
                                  segment, fid)
                        seen_features[nk] = signature
                    local["features"] += 1
                    local[f["method"]] += 1
                if product_codes:
                    con.execute("UPDATE products SET quality_status='needs_review' WHERE id=?", (pid,))
                    local["needs_review"] += 1
                local["products"] += 1
                if local["products"] % 5000 == 0:
                    con.commit()
            per_file[path.name] = dict(local)
            con.commit()
            print(path.name, dict(local), flush=True)
        summary = {"parser_version": VERSION, "files": per_file, "issue_counts": dict(counts),
                   "products": sum(v.get("products", 0) for v in per_file.values()),
                   "features": sum(v.get("features", 0) for v in per_file.values()),
                   "category_properties": sum(v.get("category_properties", 0) for v in per_file.values()),
                   "annotation": "automatic quality labels only; no verified KTRU codes",
                   "dictionary_size": len(names)}
        con.execute("INSERT INTO meta VALUES('summary',?)", (json.dumps(summary, ensure_ascii=False),))
        con.commit()
        export_review(con, review)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        con.close()
    tmp.replace(out)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/ste.sqlite"))
    ap.add_argument("--report", type=Path, default=Path("reports/ste_quality.json"))
    ap.add_argument("--review", type=Path, default=Path("reports/ste_review.csv"))
    ap.add_argument("--catalog", type=Path, default=Path("data/ktru.sqlite"))
    args = ap.parse_args()
    print(json.dumps(run(args.src, args.out, args.report, args.review, args.catalog), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
