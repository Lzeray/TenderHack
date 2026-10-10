"""Уровень 2 на чистых кейсах бенчмарка: какие признаки получают unseen/rare и почему (разбор ложных тревог).

python -m experiments.l2_clean --suites synthetic,stress,manual_dev --out reports/exp/l2_clean.txt
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402
from experiments.l3_synth import SUITES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", default="synthetic,stress,manual_dev")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eng = get_engine()
    by_prop = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    total = collections.Counter()
    for suite in args.suites.split(","):
        for line in SUITES[suite].read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            r = eng.search(SearchRequest(text=row["text"]))
            feats = {f.id: f for f in r.features}
            for e in r.empirical:
                f = feats[e.feature_id]
                kind = "num" if f.unit or (f.value or "").replace(",", "").isdigit() else "text"
                st = e.status if e.status != "not_assessed" else "na:" + e.reason
                total[(kind, st)] += 1
                by_prop[(kind, e.type_key or "-", e.property_name)][st] += 1
                k = (e.type_key, e.property_name)
                if e.status in ("unseen", "rare") and len(ex[k]) < 3:
                    ex[k].append(f"{f.value} {f.unit or ''} | {e.reason[:160]}")
    with open(args.out, "w", encoding="utf-8") as out:
        out.write("ИТОГО: " + json.dumps({f"{a}/{b}": n for (a, b), n in sorted(total.items())}, ensure_ascii=False) + "\n\n")
        rows = sorted(by_prop.items(), key=lambda kv: -(kv[1]["unseen"] + kv[1]["rare"]))
        for (kind, t, p), c in rows[:60]:
            if not (c["unseen"] + c["rare"]):
                break
            out.write(f"[{kind}] {t} / {p}: {dict(c)}\n")
            for s in ex[(t, p)]:
                out.write(f"     {s}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
