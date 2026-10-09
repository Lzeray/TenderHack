"""Сравнение двух (и более) отчётов benchmark.run: метрики по наборам и изменения по кейсам.

  python -m benchmark.compare reports/bench/core.json reports/bench/core_sem_b.json [--out cmp.md]

Порядок важности при сравнении решений (рекомендация, не единый балл):
1) меньше auto_incorrect и forbidden_auto_violations / forbidden_code_hits (безопасность);
2) выше pass_rate и required_auto_hit / auto_coverage (полезность);
3) выше dialog_resolved и compatible_recall (можно ли дойти до кода уточнениями);
4) ниже latency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

KEYS = ["pass_rate", "status_accuracy", "auto_coverage", "auto_correct", "auto_incorrect", "auto_precision",
        "required_auto_hit", "forbidden_auto_violations", "forbidden_code_hits", "compatible_recall", "checks_pass",
        "dialog_resolved", "errors"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    reps = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
    names = [r["adapter"] for r in reps]
    suites = [s for s in reps[0]["suites"] if all(s in r["suites"] for r in reps)]
    lines = []
    for s in suites:
        lines += [f"## {s}", "", "| метрика | " + " | ".join(names) + " |", "| --- |" + " --- |" * len(names)]
        for k in KEYS:
            lines.append(f"| {k} | " + " | ".join(str(r["suites"][s]["summary"].get(k)) for r in reps) + " |")
        lines.append("| latency p50 / p95, мс | " + " | ".join(
            f"{r['suites'][s]['summary']['latency_ms']['p50']} / {r['suites'][s]['summary']['latency_ms']['p95']}"
            for r in reps) + " |")
        base = {c["id"]: c for c in reps[0]["suites"][s]["cases"]}
        for r in reps[1:]:
            ch = []
            for c in r["suites"][s]["cases"]:
                b = base.get(c["id"])
                if b and b["pass"] != c["pass"]:
                    ch.append(f"- {'ИСПРАВЛЕНО' if c['pass'] else 'РЕГРЕССИЯ'} `{c['id']}` «{c['text']}»: "
                              f"{b['status']}/{b['final_code']} → {c['status']}/{c['final_code']}")
            lines += ["", f"Изменения {names[0]} → {r['adapter']}: {len(ch)}", *ch, ""]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
