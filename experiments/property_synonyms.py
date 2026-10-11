"""Свойства-синонимы внутри типа (docs/PROPERTY_VARIANTS.md): разные названия, одно понятие.

Кандидат — пара характеристик области типа, которые ни разу не встречаются в одной позиции, а их качественные
значения пересекаются по леммам (Жаккар ≥ 0,5): «Пол» / «Половая принадлежность» / «Половозрастная группа».
Это кандидаты для решения команды, а не автоматическая склейка.

python -m experiments.property_synonyms --out reports/exp/property_synonyms.json
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.text import content_lemmas, norm  # noqa: E402


def vkey(text: str) -> tuple:
    return tuple(content_lemmas(text)) or (norm(text),)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jaccard", type=float, default=0.5)
    args = ap.parse_args()
    eng = get_engine()
    docs = [d for d in eng.catalog.search_documents() if d["active"] and not d["is_template"]]
    by_type = collections.defaultdict(list)
    for d in docs:
        for h in d["head_parts"]:
            by_type[h].append(d["code"])
    pos = eng.catalog.get_many([d["code"] for d in docs])
    found = {}
    for h, codes in sorted(by_type.items()):
        props = collections.defaultdict(lambda: {"name": None, "positions": set(), "values": set(), "required": 0})
        for c in codes:
            for pr in pos[c].props.values():
                e = props[pr.norm_name]
                e["name"] = e["name"] or pr.name
                e["positions"].add(c)
                e["required"] += pr.required
                e["values"] |= {vkey(v.text) for v in pr.values if v.kind == "quality" and v.text}
        for a, b in itertools.combinations(sorted(props), 2):
            ea, eb = props[a], props[b]
            if ea["positions"] & eb["positions"] or not ea["values"] or not eb["values"]:
                continue
            j = len(ea["values"] & eb["values"]) / len(ea["values"] | eb["values"])
            if j < args.jaccard or ea["values"] <= {("да",), ("нет",)}:
                continue
            pair = tuple(sorted((ea["name"], eb["name"])))
            rec = found.setdefault(pair, {"names": list(pair), "jaccard": round(j, 2), "types": [],
                                          "shared": sorted(" ".join(v) for v in ea["values"] & eb["values"])[:8]})
            rec["types"].append(f'{h} ({len(ea["positions"])}/{len(eb["positions"])})')
    rows = sorted(found.values(), key=lambda r: (-len(r["types"]), -r["jaccard"]))
    Path(args.out).write_text(json.dumps({"pairs": len(rows), "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"pairs": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
