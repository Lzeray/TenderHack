"""Prepare 180 unlabelled XLSX cases for experts; not an accuracy benchmark."""
import argparse
import json
from pathlib import Path
import sqlite3


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path("data/ste.sqlite"))
    ap.add_argument("--out", type=Path, default=Path("reports/manual_annotation_queue.jsonl"))
    ap.add_argument("--per-source", type=int, default=60)
    args = ap.parse_args()
    con = sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = []
    for source in con.execute("SELECT * FROM sources ORDER BY id").fetchall():
        candidates = con.execute("SELECT * FROM products WHERE source_id=? AND row_number % 997=2 AND length(name)+length(raw_characteristics)+2<=2000 ORDER BY row_number LIMIT ?",
                                 (source["id"], args.per_source)).fetchall()
        for p in candidates:
            rows.append({"id": f"XLSX-{p['id']}", "source_file": source["filename"], "source_sha256": source["sha256"],
                "sheet": p["sheet"], "row": p["row_number"], "ste_id": p["ste_id"], "source_category": source["category"],
                "text": p["name"] + "; " + p["raw_characteristics"], "annotation_status": "unreviewed",
                "acceptable_codes": [], "expected_features": [], "unknown": None,
                "rewritten_natural_description": None, "reviewer": None, "verified": None,
                "note": "Unlabelled source sample, not ground truth. Do not score until expert review."})
    con.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "out": str(args.out), "verified_cases": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
