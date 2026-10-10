"""Оценка подстановки единиц (docs/UNITS_PLAN.md, U5).

1. bench: у чисел с единицей в кейсах бенчмарка единица убирается из текста; проверяется, что подставлено:
   та же единица (верно), другая (ошибка), вопрос, ничего.
2. holdout: реальные значения отложенных производителей (статистика собрана без них): гипотезы единиц той же
   размерности оцениваются только выгрузками (свидетельство 4) — доля подстановок, точность, доля вопросов.

python -m experiments.u5_units --mode bench --out reports/exp/u5_bench.json
python -m experiments.u5_units --mode holdout --stats data/exp_ste_stats_h0.sqlite --holdout reports/exp/ste_holdout0.jsonl --out reports/exp/u5_holdout.json
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.units import UNITS, lookup  # noqa: E402


def bench(out: Path) -> dict:
    from experiments.l3_synth import SUITES
    from ktru_assist.api import get_engine
    from ktru_assist.models import SearchRequest
    eng = get_engine()
    c = collections.Counter()
    ex = collections.defaultdict(list)
    for suite in ("synthetic", "stress", "manual_dev"):
        for line in SUITES[suite].read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            text = row["text"]
            r = eng.search(SearchRequest(text=text))
            for f in r.features:
                u = lookup(f.unit) if f.unit else None
                if f.status != "bound" or f.source != "text" or u is None or not f.raw_span or u.dimension == "count":
                    continue
                a, b = f.raw_span
                seg = text[a:b]
                aliases = sorted(set(u.aliases + (u.title,)), key=len, reverse=True)
                m = re.search(r"(\d)(\s*)(?:" + "|".join(re.escape(x) for x in aliases) + r")\.?(?![а-яa-z])", seg, re.I)
                if not m:
                    continue
                bare = text[:a] + seg[:m.start() + 1] + seg[m.end():] + text[b:]
                r2 = eng.search(SearchRequest(text=bare))
                g = next((x for x in r2.features if x.property_name == f.property_name and x.value == f.value), None)
                c["n"] += 1
                if g is None:
                    c["lost"] += 1
                elif g.unit_inferred:
                    gu = lookup(g.unit)
                    if gu and gu.key == u.key:
                        c["correct"] += 1
                    else:
                        c["wrong"] += 1
                        if len(ex["wrong"]) < 20:
                            ex["wrong"].append({"text": bare, "orig": f.unit, "inferred": g.unit, "note": g.note})
                elif r2.question and "В каких единицах" in (r2.question.text or ""):
                    c["asked"] += 1
                else:
                    c["no_unit"] += 1
    n = c["n"] or 1
    res = {**c, "auto_share": round((c["correct"] + c["wrong"]) / n, 3),
           "precision": round(c["correct"] / max(1, c["correct"] + c["wrong"]), 4), "examples": ex}
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def holdout(stats_path: str, holdout_path: str, out: Path, per_prop: int = 20) -> dict:
    from ktru_assist.catalog.repository import Catalog, Interval
    from ktru_assist.dims import share_satisfying
    from ktru_assist.empirical import SteStats
    from ktru_assist.unit_infer import CANDIDATES, RATIO, strongly_overlap
    stats = SteStats(stats_path, Catalog(ROOT / "data" / "ktru.sqlite").meta.get("snapshot"))
    rows = [json.loads(l) for l in Path(holdout_path).read_text(encoding="utf-8").splitlines()]
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["type"], r["property"].casefold())].append(r)
    rnd = random.Random(0)
    c = collections.Counter()
    ex = collections.defaultdict(list)
    for k in sorted(by):
        grp = by[k]
        rnd.shuffle(grp)
        for r in grp[:per_prop]:
            u0 = lookup(r["unit"]) if r["unit"] else None
            if u0 is None or u0.dimension == "count":
                continue
            try:
                v = Decimal(str(r["value"]).replace(",", "."))
            except Exception:
                continue
            if v <= 0:
                continue
            heads = r["type"].split("|")
            hyp = []
            for u in UNITS:
                if u.dimension != u0.dimension or (u.key not in CANDIDATES and u.key != u0.key):
                    continue
                sh = share_satisfying(stats, heads, r["property"], r["property"], Interval(v, True, v, True), u.title)
                if sh is not None:
                    hyp.append((sh, u.key))
            if not hyp:
                c["not_assessed"] += 1
                continue
            c["n"] += 1
            hyp.sort(reverse=True)
            best, second = hyp[0], (hyp[1][0] if len(hyp) > 1 else 0.0)
            overlap = len(hyp) > 1 and strongly_overlap(best[0], hyp[1][0])
            if not overlap and (second == 0 or best[0] >= RATIO * second):
                ok = best[1] == u0.key
                c["correct" if ok else "wrong"] += 1
                if not ok:
                    ex["wrong"].append({**r, "inferred": best[1], "scores": hyp[:3]})
            else:
                c["asked"] += 1
    n = c["n"] or 1
    res = {**c, "auto_share": round((c["correct"] + c["wrong"]) / n, 3),
           "precision": round(c["correct"] / max(1, c["correct"] + c["wrong"]), 4), "examples": ex}
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bench", "holdout"], required=True)
    ap.add_argument("--stats", default=str(ROOT / "data" / "exp_ste_stats_h0.sqlite"))
    ap.add_argument("--holdout", default=str(ROOT / "reports" / "exp" / "ste_holdout0.jsonl"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = bench(Path(a.out)) if a.mode == "bench" else holdout(a.stats, a.holdout, Path(a.out))
    print(json.dumps({k: v for k, v in res.items() if k != "examples"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
