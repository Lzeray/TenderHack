"""Measure native retrieval and inference. Simulated type confirmations are explicitly labelled."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import time
import urllib.request

from ktru_assist.api import get_orchestrator
from ktru_assist.models import Constraint, SearchRequest


def percentile(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int((len(xs) - 1) * p))], 2) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--full", type=int, default=0, help="Number of real LLM calls (one per selected known-code case)")
    args = ap.parse_args()
    t0 = time.perf_counter()
    o = get_orchestrator()
    if not o.engine.native or o.semantic is None:
        raise RuntimeError("Run with RECOGNITION_MODE=semantic SEMANTIC=1")
    init_ms = (time.perf_counter() - t0) * 1000
    cases = []
    for file in (Path("benchmark/suites/manual_dev.jsonl"), Path("benchmark/suites/manual_holdout.jsonl")):
        cases.extend(json.loads(l) for l in file.read_text(encoding="utf-8").splitlines() if l.strip())
    rows, full_rows, latencies, recall = [], [], [], []
    full_categories = set()
    scope = o.engine.catalog_scope
    for i, case in enumerate(cases):
        start = time.perf_counter()
        draft = o.run(SearchRequest(text=case["text"], session_id=f"native-eval-{i}", revision=1))
        ms = (time.perf_counter() - start) * 1000
        latencies.append(ms)
        expected_types = {t.ref for t in scope.types.values() if set(t.codes) & set(case.get("acceptable_codes", []))}
        offered = [p.answer.value for p in draft.proposals if p.kind == "type"]
        hit = bool(set(offered) & expected_types) if expected_types else None
        if hit is not None:
            recall.append(hit)
        rows.append({"id": case["id"], "text": case["text"], "draft_ms": round(ms, 2), "expected_types": sorted(expected_types),
                     "type_recall_at_8": hit, "offered_types": offered, "matched": draft.status == "matched"})
        if expected_types and len(full_rows) < args.full and (args.full > 3 or case.get("category") not in full_categories):
            full_categories.add(case.get("category"))
            selected = sorted(expected_types)[0]  # oracle for testing extraction, NOT automatic type detection
            req = SearchRequest(text=case["text"], session_id=f"native-eval-{i}", revision=2, stage="submitted",
                                overrides=[Constraint(property="__type__", value=selected)])
            start = time.perf_counter()
            submitted = o.run(req)
            elapsed = (time.perf_counter() - start) * 1000
            entry = {"id": case["id"], "type_confirmation": "simulated from labelled acceptable codes",
                     "full_ms": round(elapsed, 2), "status": submitted.status, "final_code": submitted.final_code,
                     "features": [f.model_dump() for f in submitted.features],
                     "issues": [issue.model_dump() for issue in submitted.issues],
                     "providers": [p.model_dump() for p in submitted.providers]}
            # Accept the displayed model bindings in simulation; this is not expert verification.
            answers = [p.answer for p in submitted.proposals if p.kind == "value" and p.answer]
            if answers:
                final = o.run(req.model_copy(update={"revision": 3, "action": "confirm", "answers": answers,
                                                    "confirmed": submitted.question.options[0].confirm if submitted.question and submitted.question.kind == "confirm" else [],
                                                    "answers_query_hash": submitted.query_hash}))
                entry.update(simulated_confirmation_status=final.status, simulated_final_code=final.final_code,
                             simulated_code_correct=final.final_code in case.get("acceptable_codes", []) if final.final_code else None)
            full_rows.append(entry)
    vram = None
    try:
        with urllib.request.urlopen(o.llm.url + "/api/ps", timeout=2) as r:
            models = json.loads(r.read())
        vram = {"ollama_reported_gpu_bytes": sum(m.get("size_vram", 0) for m in models.get("models", [])),
                "encoder_device": "cpu", "note": "macOS unified memory; not a Linux CUDA peak VRAM measurement"}
    except Exception:
        pass
    report = {"machine": platform.platform(), "python": platform.python_version(), "versions": o.versions(),
              "initialization_ms": round(init_ms, 2), "draft_cases": len(rows),
              "draft_ms": {"p50": percentile(latencies, .5), "p95": percentile(latencies, .95), "cold_first": rows[0]["draft_ms"]},
              "type_recall_at_8": {"hits": sum(recall), "cases": len(recall)}, "draft_matched": sum(r["matched"] for r in rows),
              "full_cases": full_rows, "runtime_memory": vram, "cases": rows,
              "limitations": "Existing team labels, small sample; full type and feature confirmations simulated, not expert-reviewed. UI debounce/network/render not included."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("cases", "full_cases")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
