"""Сравнение конфигураций на одном наборе кейсов (план, п. 9.3–9.4).

Конфигурации:
  core          — усиленное ядро без моделей;
  core_b_always — ядро + разбор B на каждом Enter;
  core_sem_b    — ядро + SemanticProposer + B по эскалации;
  core_b_nodraft— как core_sem_b, но B без черновика A в контексте (проверка привязки к ошибкам A).

Каждый кейс: черновик (draft) → Enter (submitted) → симуляция диалога ответами, совместимыми с эталоном
(не больше 6 шагов). Метрики — eval/SCHEMA.md. Числа печатаются только из реального прогона.

python -m eval.run_benchmark --cases eval/cases.jsonl eval/holdout.jsonl --configs core core_sem_b \
    --out reports/benchmark.json
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.guarantees import check_matched  # noqa: E402
from ktru_assist.api import build_orchestrator, get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402
from ktru_assist.orchestrator import OrchestratorConfig  # noqa: E402

CONFIGS = {
    "core": dict(b_mode="off", semantic=False),
    "core_b_always": dict(b_mode="always", semantic=False),
    "core_sem_b": dict(b_mode="escalate", semantic=True),
    "core_b_nodraft": dict(b_mode="escalate", semantic=True, b_include_draft=False),
}
MAX_STEPS = 6


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))], 2)


class VramSampler:
    """Пиковая занятость видеопамяти всеми процессами (nvidia-smi), МиБ. None — если GPU нет."""

    def __init__(self, every=0.5):
        self.every, self.peak, self.base, self._stop = every, None, None, threading.Event()

    @staticmethod
    def used():
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5).stdout
            return sum(int(x) for x in out.split())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    def __enter__(self):
        self.base = self.used()
        self.peak = self.base

        def loop():
            while not self._stop.wait(self.every):
                u = self.used()
                if u is not None:
                    self.peak = max(self.peak or 0, u)
        self.t = threading.Thread(target=loop, daemon=True)
        self.t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self.t.join(timeout=2)


def acceptable(case) -> set[str]:
    if case.get("acceptable_codes"):
        return set(case["acceptable_codes"])
    return {case["expected_code"]} if case.get("expected_code") else set()


def compatible_finals(r) -> set[str]:
    return {c.code for c in r.candidates if c.compatible and not c.is_template}


def simulate(o, case, first, codes, rev0) -> tuple[bool, int, str]:
    """Отвечать на вопросы вариантом, сохраняющим совместимость эталона; подтверждения — только если
    эталон после них остаётся совместимым, иначе отклонять гипотезы."""
    r, answers, rejected, confirmed, rev = first, [], [], [], rev0
    for step in range(MAX_STEPS + 1):
        if r.status == "matched":
            return r.final_code in codes, step, r.final_code
        if r.question is None or step == MAX_STEPS or not codes:
            return False, step, r.status
        chosen = None
        for opt in r.question.options:
            many = opt.answers or ([opt.answer] if opt.answer else [])
            trial_a = [a for a in answers if a.property not in {m.property for m in many}] + many
            trial_rej = rejected + list(opt.reject)
            trial_conf = confirmed + list(opt.confirm)
            rev += 1
            rr = o.run(SearchRequest(text=case["text"], stage="submitted", session_id="bench-" + case["id"], revision=rev,
                                     answers=trial_a, answers_query_hash=r.query_hash, rejected=trial_rej,
                                     confirmed=trial_conf))
            if compatible_finals(rr) & codes:
                chosen = (trial_a, trial_rej, trial_conf, rr)
                break
        if chosen is None:
            return False, step, "эталон несовместим ни с одним вариантом"
        answers, rejected, confirmed, r = chosen
    return False, MAX_STEPS, "лимит вопросов"


def run_config(name, cases, repeat_latency=3):
    cfg = OrchestratorConfig(**{"cache_size": 512, **CONFIGS[name]})
    eng = get_engine()
    t0 = time.perf_counter()
    o = build_orchestrator(eng, cfg)
    init_s = time.perf_counter() - t0
    rows, lat_a, lat_sub, lat_b = [], [], [], []
    with VramSampler() as vram:
        for c in cases:
            codes = acceptable(c)
            sid = "bench-" + c["id"]       # свой сеанс на кейс: версии разных кейсов не пересекаются
            draft = o.run(SearchRequest(text=c["text"], stage="draft", session_id=sid, revision=1))
            for _ in range(repeat_latency):
                t = time.perf_counter()
                o.engine.search(SearchRequest(text=c["text"]))
                lat_a.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            sub = o.run(SearchRequest(text=c["text"], stage="submitted", session_id=sid, revision=2))
            lat_sub.append((time.perf_counter() - t) * 1000)
            llm = next((p for p in sub.providers if p.name == "llm"), None)
            if llm is not None and llm.used and llm.elapsed_ms is not None and llm.status == "ok":
                lat_b.append(llm.elapsed_ms)
            unsafe = check_matched(o.engine, sub)
            row = {
                "id": c["id"], "split": c.get("split"), "category": c.get("category"), "text": c["text"],
                "acceptable": sorted(codes), "expected_status": c.get("expected_status"),
                "draft_status": draft.status, "status": sub.status, "final_code": sub.final_code,
                "status_ok": sub.status in c.get("expected_status", [sub.status]),
                "correct_matched": sub.status == "matched" and sub.final_code in codes,
                "incorrect_matched": sub.status == "matched" and sub.final_code not in codes,
                "unsafe_matched": bool(unsafe), "unsafe_reasons": unsafe,
                "must_not_auto_violated": bool(c.get("must_not_auto")) and sub.status == "matched",
                "expected_in_draft": bool(compatible_finals(draft) & codes) if codes else None,
                "expected_in_final": bool(compatible_finals(sub) & codes) if codes else None,
                "escalated": bool(llm and llm.used),
                "llm_status": llm.status if llm else None,
                "issues_expected_ok": all(any(i.code == e for i in sub.issues) for e in c.get("expected_issues", [])),
                "question": sub.question.kind if sub.question else None,
                "code_resolution": sub.code_resolution.status if sub.code_resolution else None,
            }
            if codes and sub.status != "matched":
                ok, steps, info = simulate(o, c, sub, codes, 100)
                row.update(resolved_dialog=ok, dialog_steps=steps if ok else None, dialog_info=info)
            rows.append(row)
    n = len(rows)
    matched = [r for r in rows if r["status"] == "matched"]
    nm = len(matched)
    esc = [r for r in rows if r["escalated"]]
    with_codes = [r for r in rows if r["acceptable"]]
    summary = {
        "config": name, "cases": n, "init_s": round(init_s, 2),
        "status_ok": sum(r["status_ok"] for r in rows),
        "matched": nm, "coverage": round(nm / n, 3) if n else None,
        "correct_matched": sum(r["correct_matched"] for r in rows),
        "incorrect_matched": sum(r["incorrect_matched"] for r in rows),
        "unsafe_matched": sum(r["unsafe_matched"] for r in rows),
        "must_not_auto_violated": sum(r["must_not_auto_violated"] for r in rows),
        "error_upper95_rule_of_three": round(3 / nm, 3) if nm and not any(
            r["incorrect_matched"] for r in rows) else None,
        "manual_choice": sum(r["status"] == "manual_choice" for r in rows),
        "clarification": sum(r["status"] == "clarification_needed" for r in rows),
        "resolved_dialog": f"{sum(bool(r.get('resolved_dialog')) for r in rows)}/{sum('resolved_dialog' in r for r in rows)}",
        "dialog_steps_mean": round(statistics.mean([r["dialog_steps"] for r in rows if r.get("dialog_steps")]), 2)
        if any(r.get("dialog_steps") for r in rows) else None,
        "expected_in_compatible_final": f"{sum(bool(r['expected_in_final']) for r in with_codes)}/{len(with_codes)}",
        "escalations": len(esc),
        "b_fixed": sum(1 for r in rows if r["acceptable"] and not r["expected_in_draft"] and r["expected_in_final"]),
        "b_lost_expected": sum(1 for r in rows if r["acceptable"] and r["expected_in_draft"] and not r["expected_in_final"]),
        "llm_status": {s: sum(r["llm_status"] == s for r in rows) for s in sorted({r["llm_status"] for r in rows if r["llm_status"]})},
        "latency_ms": {"core_p50": pct(lat_a, 50), "core_p95": pct(lat_a, 95),
                       "submitted_p50": pct(lat_sub, 50), "submitted_p95": pct(lat_sub, 95),
                       "llm_p50": pct(lat_b, 50), "llm_p95": pct(lat_b, 95), "llm_n": len(lat_b)},
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "vram_mib": {"before": vram.base, "peak": vram.peak},
        "versions": o.versions(),
    }
    return summary, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=[str(ROOT / "eval" / "cases.jsonl")])
    ap.add_argument("--configs", nargs="+", default=["core"])
    ap.add_argument("--split", default=None, help="только кейсы с этим split")
    ap.add_argument("--out", default=str(ROOT / "reports" / "benchmark.json"))
    args = ap.parse_args()
    cases = []
    for f in args.cases:
        cases += [json.loads(l) for l in Path(f).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.split:
        cases = [c for c in cases if c.get("split") == args.split]
    result = {"machine": {"platform": platform.platform(), "python": platform.python_version()},
              "cases_files": args.cases, "split": args.split, "configs": {}}
    for name in args.configs:
        s, rows = run_config(name, cases)
        result["configs"][name] = {"summary": s, "cases": rows}
        print(json.dumps(s, ensure_ascii=False, indent=1))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(args.configs) > 1:
        base = {r["id"]: r for r in result["configs"][args.configs[0]]["cases"]}
        for name in args.configs[1:]:
            print(f"\n=== {args.configs[0]} → {name}: изменения по кейсам ===")
            for r in result["configs"][name]["cases"]:
                b = base[r["id"]]
                if (b["status"], b["final_code"]) != (r["status"], r["final_code"]):
                    tag = "ИСПРАВЛЕНИЕ" if r["correct_matched"] and not b["correct_matched"] else \
                        "РЕГРЕССИЯ" if b["correct_matched"] and not r["correct_matched"] else "изменение"
                    print(f"{tag:12} {r['id']} {b['status']}/{b['final_code']} → {r['status']}/{r['final_code']}  {r['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
