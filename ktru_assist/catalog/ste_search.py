"""Offline FTS index and structured lookup over the supplied STE exports."""
from __future__ import annotations

import argparse
from collections import OrderedDict
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import threading

from ..text import content_lemmas, norm
from ..units import lookup


def build(src: Path, dst: Path):
    source = sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = dst.with_suffix(".tmp")
    if temporary.exists():
        raise FileExistsError(temporary)
    out = sqlite3.connect(temporary)
    out.executescript("""
        CREATE TABLE products(id INTEGER PRIMARY KEY,ste_id TEXT,name TEXT,model TEXT,manufacturer TEXT,
                              country TEXT,characteristics TEXT,quality_status TEXT);
        CREATE VIRTUAL TABLE names USING fts5(terms,content='');
        CREATE TABLE attributes(product_id INTEGER,name_key TEXT,dimension TEXT,number TEXT,value TEXT);
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    """)
    n = 0
    for r in source.execute("SELECT id,ste_id,name,model,manufacturer,country,raw_characteristics,quality_status FROM products ORDER BY id"):
        out.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?)", r)
        out.execute("INSERT INTO names(rowid,terms) VALUES(?,?)", (r[0], " ".join(content_lemmas(r[2]))))
        n += 1
        if n % 10000 == 0:
            out.commit()
    for pid, name, dim, numbers, value in source.execute("SELECT product_id,name_key,dimension,base_numbers,value FROM features"):
        ns = json.loads(numbers)
        number = format(Decimal(ns[0]).normalize(), "f") if len(ns) == 1 else None
        out.execute("INSERT INTO attributes VALUES(?,?,?,?,?)", (pid, name, dim, number, norm(value) + " " + " ".join(content_lemmas(value))))
    out.executescript("""
        CREATE INDEX attributes_product ON attributes(product_id);
        CREATE INDEX attributes_quantity ON attributes(dimension,number,product_id);
        CREATE INDEX attributes_name ON attributes(name_key,product_id);
    """)
    out.execute("INSERT INTO meta VALUES('source_summary',?)", source.execute("SELECT value FROM meta WHERE key='summary'").fetchone())
    out.execute("INSERT INTO meta VALUES('version','1.0')")
    out.commit()
    out.close()
    source.close()
    temporary.replace(dst)
    print(json.dumps({"products": n, "index": str(dst)}, ensure_ascii=False))


class SteSearch:
    def __init__(self, path):
        self.con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.cache = OrderedDict()

    def color_terms(self):
        with self.lock:
            rows = self.con.execute("SELECT value,count(*) AS n FROM attributes WHERE name_key='цвет' GROUP BY value ORDER BY n DESC LIMIT 500").fetchall()
        terms = set()
        for r in rows:
            words = set(content_lemmas(r["value"]))
            if len(words) == 1:
                terms.update(words)
        return terms

    def search(self, item_terms, attributes, offset=0, limit=25):
        terms = [t for t in item_terms if t and len(t) >= 2]
        if not terms:
            return {"total": 0, "items": [], "offset": offset, "limit": limit}
        fts = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
        where, params = ["p.id IN (SELECT rowid FROM names WHERE names MATCH ?)"], [fts]
        applied = []
        for a in attributes:
            u = lookup(a.get("raw_unit") or a.get("unit") or "")
            val = a.get("raw_value") or a.get("value")
            if u and val is not None:
                if a.get("op", "eq") != "eq":
                    continue
                try:
                    number = Decimal(str(val).replace(",", "."))
                except Exception:
                    continue
                if not number.is_finite():
                    continue
                # Exact decimal equality; no float comparisons or guessing numeric ranges.
                base = format((number * u.factor).normalize(), "f")
                where.append("EXISTS(SELECT 1 FROM attributes a WHERE a.product_id=p.id AND a.dimension=? AND a.number=?)")
                params.extend([u.dimension, base])
                applied.append(a)
            elif val and a.get("op", "eq") == "eq" and any(t in norm(a.get("name", "")) for t in ("цвет", "тип", "вид", "питани", "материал")):
                tokens = content_lemmas(str(val))
                stems = [t[:-2] if len(t) > 5 else t for t in tokens]
                if not stems:
                    continue
                checks = " AND ".join("a.value LIKE ?" for _ in stems)
                family = next(t for t in ("цвет", "тип", "вид", "питани", "материал") if t in norm(a["name"]))
                where.append("EXISTS(SELECT 1 FROM attributes a WHERE a.product_id=p.id AND a.name_key LIKE ? AND " + checks + ")")
                params.append("%" + family + "%")
                params.extend("%" + t + "%" for t in stems)
                applied.append(a)
            elif val in ("Да", "Нет") and "наличие" in norm(a.get("name", "")):
                terms = [t for t in content_lemmas(a["name"]) if t != "наличие"]
                if not terms:
                    continue
                noun = terms[-1][:3]
                yes = val == "Да"
                if len(terms) > 1:
                    qualifier = terms[0][:4]
                    if yes:
                        where.append("EXISTS(SELECT 1 FROM attributes a WHERE a.product_id=p.id AND a.name_key LIKE ? AND ((a.name_key LIKE ? AND a.value LIKE '%да%') OR a.value LIKE ?))")
                        params.extend(["%"+noun+"%", "%"+qualifier+"%", "%"+qualifier+"%"])
                    else:
                        where.append("EXISTS(SELECT 1 FROM attributes a WHERE a.product_id=p.id AND a.name_key LIKE ? AND a.name_key LIKE ? AND a.value LIKE '%нет%')")
                        params.extend(["%"+noun+"%", "%"+qualifier+"%"])
                else:
                    where.append("EXISTS(SELECT 1 FROM attributes a WHERE a.product_id=p.id AND a.name_key LIKE ? AND a.value LIKE ?)")
                    params.extend(["%"+noun+"%", "%да%" if yes else "%нет%"])
                applied.append(a)
        clause = " AND ".join(where)
        cache_key = (clause, tuple(params), offset, limit)
        with self.lock:
            hit = self.cache.get(cache_key)
            if hit:
                self.cache.move_to_end(cache_key)
                total, items = hit
            else:
                total = self.con.execute("SELECT count(*) FROM products p WHERE " + clause, params).fetchone()[0]
                rows = self.con.execute("SELECT p.* FROM products p WHERE " + clause + " ORDER BY p.id LIMIT ? OFFSET ?",
                                        [*params, limit, offset]).fetchall()
                items = [dict(r) for r in rows]
                self.cache[cache_key] = (total, items)
                if len(self.cache) > 128:
                    self.cache.popitem(last=False)
        return {"total": total, "items": items, "offset": offset, "limit": limit,
                "applied": applied, "note": "Фактические данные выгрузок СТЕ; не подтверждённое соответствие КТРУ"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path("data/ste.sqlite"))
    ap.add_argument("--out", type=Path, default=Path("data/ste_search.sqlite"))
    args = ap.parse_args()
    build(args.src, args.out)


if __name__ == "__main__":
    main()
