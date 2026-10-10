"""Оценка уровня 2 и правила scale по выгрузкам на отложенных производителях (без утечки).

Статистика собирается без блока производителей (`ste_stats --holdout 0/5 --holdout-out …`), а реальные числовые
значения моделей этого блока проверяются:
* чистые значения — доли typical / rare / unseen (unseen и rare на чистых — ложные тревоги);
* испорченные (та же цифра в соседней единице, ×10, ÷10) — доля пойманных (unseen; unseen или rare) и точность
  исправления: вариант той же величины, что исходное значение, если он единственный «обычный».
Выборка: не больше --per-prop значений на пару (тип, свойство), чтобы частые свойства не задавили остальные.

python -m experiments.l2_holdout --stats data/exp_ste_stats_h0.sqlite --holdout reports/exp/ste_holdout0.jsonl --out reports/exp/l2.json
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.catalog.repository import Catalog  # noqa: E402
from ktru_assist.empirical import SteStats, assess  # noqa: E402
from ktru_assist.models import Feature  # noqa: E402
from ktru_assist.suspicious import _quantity, _variants  # noqa: E402
from ktru_assist.units import UNITS, fmt, lookup  # noqa: E402

LADDER = {"mm": ["cm", "m"], "cm": ["mm", "m"], "m": ["cm", "mm"], "g": ["kg"], "kg": ["g"], "w": ["kw"],
          "kw": ["w"], "mah": ["ah"], "ah": ["mah"], "ml": ["l"], "l": ["ml"]}
TITLE = {u.key: u.title for u in UNITS}


def corruptions(f: Feature):
    u = lookup(f.unit) if f.unit else None
    v = Decimal(f.value)
    if u is not None:
        for k in LADDER.get(u.key, []):
            yield "unit", f.model_copy(update={"unit": TITLE[k]})
    for kind, m in (("x10", Decimal(10)), ("d10", Decimal("0.1"))):
        yield kind, f.model_copy(update={"value": fmt(v * m)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", required=True)
    ap.add_argument("--holdout", required=True)
    ap.add_argument("--db", default=str(ROOT / "data" / "ktru.sqlite"))
    ap.add_argument("--per-prop", type=int, default=20)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    stats = SteStats(args.stats, Catalog(args.db).meta.get("snapshot"))
    assert stats.available, stats.reason
    rows = [json.loads(l) for l in Path(args.holdout).read_text(encoding="utf-8").splitlines()]
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["type"], r["property"].casefold())].append(r)
    rnd = random.Random(0)
    sample = []
    for k in sorted(by):
        grp = by[k]
        rnd.shuffle(grp)
        sample += grp[: args.per_prop]
    clean = collections.Counter()
    cor = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    for r in sample:
        try:
            v = Decimal(r["value"])
        except Exception:
            continue
        if v <= 0:
            continue
        f = Feature(id="h", source="text", status="bound", property_name=r["property"], value=fmt(v),
                    unit=r["unit"] or None)
        heads = r["type"].split("|")
        e = assess(f, heads, stats)
        if e is None or e.status == "not_assessed":
            clean["na:" + (e.reason if e else "none")] += 1
            continue
        clean[e.status] += 1
        if e.status == "unseen" and len(examples["clean_unseen"]) < 20:
            examples["clean_unseen"].append({**r, "reason": e.reason})
        if e.status != "typical":
            continue                     # портим только значения, которые сами типичны (иначе неясно, что «чисто»)
        for kind, g in corruptions(f):
            ge = assess(g, heads, stats)
            c = cor[kind]
            c["n"] += 1
            if ge is None or ge.status == "not_assessed":
                c["na"] += 1
                continue
            c[ge.status] += 1
            if ge.status != "unseen":
                continue
            fits = {}
            for _, h, _ in _variants(g):
                he = assess(h, heads, stats)
                if he is not None and he.status == "typical":
                    fits.setdefault(_quantity(h), h)
            if len(fits) == 1:
                c["fix"] += 1
                ok = next(iter(fits)) == _quantity(f)
                c["fix_ok"] += ok
                if not ok and len(examples["wrong_fix"]) < 20:
                    h = next(iter(fits.values()))
                    examples["wrong_fix"].append({"name": r["name"], "property": r["property"], "orig": f"{f.value} {f.unit}",
                                                  "bad": f"{g.value} {g.unit}", "fix": f"{h.value} {h.unit}"})
            elif fits:
                c["fix_ambiguous"] += 1
    assessed = sum(v for k, v in clean.items() if not k.startswith("na:"))
    summary = {"sample": len(sample), "clean": dict(clean),
               "clean_assessed_share": round(assessed / max(1, sum(clean.values())), 3),
               "clean_unseen_rate": round(clean["unseen"] / max(1, assessed), 4),
               "clean_rare_rate": round(clean["rare"] / max(1, assessed), 4)}
    for kind, c in cor.items():
        a = c["n"] - c["na"]
        summary[kind] = {**c, "detected_unseen": round(c["unseen"] / max(1, a), 3),
                         "detected_unseen_or_rare": round((c["unseen"] + c["rare"]) / max(1, a), 3),
                         "fix_precision": round(c["fix_ok"] / c["fix"], 3) if c["fix"] else None,
                         "fixed_share": round(c["fix_ok"] / max(1, a), 3)}
    Path(args.out).write_text(json.dumps({"summary": summary, "examples": examples}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
