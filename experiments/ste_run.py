"""Прогон ядра по реальным наименованиям СТЕ (data/exp_ste_sample.jsonl) без эталона кода.

Метрики по направлению: доля «тип не распознан» (not_found), доля с подтверждённым типом,
доля запросов с привязанными признаками, доля нераспознанных значимых слов, распределение статусов,
совместимые кандидаты не из того направления. Плюс файл для ручной проверки.

python -m experiments.ste_run --out reports/exp/ste_pymorphy [--stemmer snowball]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stemmer", default=None)
    args = ap.parse_args()
    if args.stemmer:
        from experiments.stemmers import install
        install(args.stemmer)
        os.environ["KTRU_DB"] = str(ROOT / "data" / f"exp_{args.stemmer}.sqlite")
    from ktru_assist.api import get_engine
    from ktru_assist.config import category_for_okpd2
    from ktru_assist.models import SearchRequest
    eng = get_engine()
    rows = [json.loads(l) for l in (ROOT / "data" / "exp_ste_sample.jsonl").read_text(encoding="utf-8").splitlines()]
    stats: dict[str, collections.Counter] = {}
    audit = []
    for r in rows:
        res = eng.search(SearchRequest(text=r["name"][:1900]))
        s = stats.setdefault(r["category"], collections.Counter())
        s["n"] += 1
        s[res.status] += 1
        bound = [f for f in res.features if f.status == "bound"]
        s["with_feature"] += bool(bound)
        s["type_confirmed"] += bool(res.completeness.type_confirmed)
        s["sig"] += len(res.query.get("terms", []))
        s["unrec"] += len(res.unrecognized)
        comp = [c for c in res.candidates if c.compatible and not c.is_template]
        s["cat_mismatch"] += bool(comp) and r["category"] not in {category_for_okpd2(c.okpd2) for c in comp}
        audit.append({"category": r["category"], "text": r["name"][:160], "status": res.status,
                      "types": res.detected_types, "final": res.final_code, "n": len(comp),
                      "features": [f"{f.property_name}={f.value}{' ' + f.unit if f.unit else ''}" for f in bound],
                      "unrec": res.unrecognized[:10], "top": [f"{c.code} {c.name}" for c in comp[:2]]})
    summary = {}
    for cat, s in stats.items():
        n = s["n"]
        summary[cat] = {"n": n, **{k: round(s[k] / n, 3) for k in
                                   ("not_found", "matched", "clarification_needed", "conflict", "manual_choice",
                                    "type_confirmed", "with_feature")},
                        "unrecognized_share": round(s["unrec"] / max(1, s["sig"]), 3),
                        "category_mismatch": s["cat_mismatch"]}
    Path(args.out + ".json").write_text(json.dumps({"summary": summary, "audit": audit}, ensure_ascii=False),
                                        encoding="utf-8")
    with open(args.out + "_audit.txt", "w", encoding="utf-8") as f:
        for a in audit:
            f.write(f"[{a['category']}] {a['status']} types={a['types']} n={a['n']} final={a['final']}\n"
                    f"   {a['text']}\n   F={a['features']} U={a['unrec']}\n   top={a['top']}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
