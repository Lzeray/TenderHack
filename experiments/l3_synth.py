"""Синтетическая оценка уровня 3 (сомнительные значения): внесение ошибок в числа кейсов бенчмарка.

Для каждого кейса берутся числовые признаки из текста с распознанной единицей. Каждый портится:
* unit — та же цифра в соседней единице той же размерности (мм↔см↔м, г↔кг, Вт↔кВт, мА·ч↔А·ч, мл↔л);
* x10 / d10 — лишний или пропущенный ноль.
Меряется:
* ceiling — доля порч, которые КТРУ вообще может заметить: испорченное значение не подходит ни одной позиции
  области со свойством (иначе по КТРУ ошибки нет — это задача уровня 2);
* flagged — доля обнаружимых порч, на которые есть предложение по этому свойству;
* fixed — доля предложений с исправлением, совпавшим с исходным значением (точность исправления);
* wrong_fix — предложено исправление, но не исходное;
* false_alarm — предложения на неиспорченных текстах (на признак).
Плюс безопасность уровня 1: автоматические коды на испорченных текстах, не совпавшие с эталоном.

python -m experiments.l3_synth --suites synthetic,stress --out reports/exp/l3.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402
from ktru_assist.suspicious import _label, _num, _quantity, _replacement, _status_counts  # noqa: E402
from ktru_assist.units import UNITS, fmt, lookup  # noqa: E402

LADDER = {"mm": ["cm", "m"], "cm": ["mm", "m"], "m": ["cm", "mm"], "g": ["kg"], "kg": ["g"], "w": ["kw"],
          "kw": ["w"], "mah": ["ah"], "ah": ["mah"], "ml": ["l"], "l": ["ml"]}
TITLE = {u.key: u.title for u in UNITS}

SUITES = {"synthetic": ROOT / "benchmark" / "suites" / "synthetic.jsonl",
          "stress": ROOT / "experiments" / "suites" / "stress.jsonl",
          "manual_dev": ROOT / "benchmark" / "suites" / "manual_dev.jsonl"}


def _same(proposed: str, f) -> bool:
    """Предложение равно исходному значению как физическая величина («170 см» = «1700 мм»)."""
    parts = proposed.split(" ", 1)
    nums = parts[0].split("–")
    g = f.model_copy(update={"value": nums[0], "value_to": nums[1] if len(nums) > 1 else None,
                             "unit": parts[1] if len(parts) > 1 else None})
    return _quantity(g) == _quantity(f)


def corruptions(f):
    u = lookup(f.unit) if f.unit else None
    v = _num(f.value)
    if u is None or v is None or v == 0:
        return
    for k in LADDER.get(u.key, []):
        yield "unit", f.value, f.value_to, TITLE[k]
    v2 = _num(f.value_to) if f.value_to else None
    for kind, m in (("x10", Decimal(10)), ("d10", Decimal("0.1"))):
        yield kind, fmt(v * m), fmt(v2 * m) if v2 is not None else None, f.unit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suites", default="synthetic,stress")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    eng = get_engine()
    st = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    base_feats = base_alarms = 0
    emp_status = collections.Counter()
    for suite in args.suites.split(","):
        rows = [json.loads(l) for l in SUITES[suite].read_text(encoding="utf-8").splitlines() if l.strip()]
        if args.limit:
            rows = rows[: args.limit]
        for row in rows:
            text = row["text"]
            r = eng.search(SearchRequest(text=text))
            nums = [f for f in r.features if f.status == "bound" and f.source == "text" and f.unit and _num(f.value)]
            base_feats += len(nums)
            base_alarms += sum(1 for s in r.suggestions if s.rule in ("scale", "unit_missing"))
            for e in r.empirical:
                emp_status[e.status if e.status != "not_assessed" else "na:" + e.reason] += 1
            if len(examples["clean_alarm"]) < 15:
                examples["clean_alarm"] += [{"text": text, "msg": s.message} for s in r.suggestions
                                            if s.rule == "scale"][:1]
            positions = None
            for f in nums:
                for kind, nv, nv2, nu in corruptions(f):
                    rep = _replacement(text, f, nv, nv2, nu)
                    if rep is None:
                        st[kind]["no_replace"] += 1
                        continue
                    (a, b), new = rep
                    bad_text = text[:a] + new + text[b:]
                    rb = eng.search(SearchRequest(text=bad_text))
                    g = next((x for x in rb.features if x.property_name == f.property_name and x.status == "bound"), None)
                    c = st[kind]
                    c["n"] += 1
                    if g is None:
                        c["not_bound"] += 1
                        continue
                    if positions is None:
                        domain = eng.catalog.get_many(rb.compatible_codes or [x.code for x in rb.candidates])
                        positions = list(domain.values())
                    have, ok, bad = _status_counts(g, list(eng.catalog.get_many([x.code for x in rb.candidates]).values()))
                    detectable = have > 0 and ok == 0 and bad == have
                    c["detectable"] += detectable
                    sg = next((s for s in rb.suggestions if s.property_name == f.property_name and s.rule == "scale"), None)
                    if sg is not None:
                        c["flagged"] += 1
                        c["src_" + sg.evidence.get("source", "?")] += 1
                        c["flagged_detectable"] += detectable
                        orig = _label(f.value, f.value_to, f.unit)
                        if sg.proposed is None:
                            c["no_fix"] += 1
                        elif _same(sg.proposed, f):
                            c["fixed"] += 1
                        else:
                            c["wrong_fix"] += 1
                            if len(examples["wrong_fix"]) < 15:
                                examples["wrong_fix"].append({"text": bad_text, "orig": orig, "proposed": sg.proposed})
                    elif detectable and len(examples["missed"]) < 15:
                        examples["missed"].append({"text": bad_text, "orig": _label(f.value, f.value_to, f.unit)})
                    if rb.status == "matched" and rb.final_code not in row.get("acceptable_codes", []):
                        c["auto_wrong"] += 1
                    if rb.status == "matched":
                        c["auto"] += 1
    summary = {}
    for kind, c in st.items():
        n, d = c["n"], c["detectable"]
        summary[kind] = {**c,
                         "ceiling": round(d / n, 3) if n else None,
                         "recall_vs_ceiling": round(c["flagged_detectable"] / d, 3) if d else None,
                         "flagged_share": round(c["flagged"] / n, 3) if n else None,
                         "fixed_share": round(c["fixed"] / n, 3) if n else None,
                         "fix_precision": round(c["fixed"] / (c["fixed"] + c["wrong_fix"]), 3)
                         if c["fixed"] + c["wrong_fix"] else None}
    summary["_clean"] = {"numeric_features": base_feats, "alarms": base_alarms, "empirical": dict(emp_status),
                         "false_alarm_rate": round(base_alarms / base_feats, 4) if base_feats else None}
    Path(args.out).write_text(json.dumps({"summary": summary, "examples": examples}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
