"""Focused integration with a REAL local Ollama model, not an accuracy benchmark.

RECOGNITION_MODE=hybrid SEMANTIC=0 LLM_MODE=always python -m eval.live_model_check
"""
import argparse
import json
from pathlib import Path
import platform
import time

from ktru_assist.api import get_orchestrator
from ktru_assist.models import SearchRequest


CASES = [
    "Молоток слесарный 500 г",
    "Стул на металлическом каркасе с мягким сиденьем и мягкой спинкой",
    "перчатки швейные для защиты от внешних воздействий, вид защиты: от пониженных температур",
    "Пассатижи слесарные 190 мм, заточка есть",
    "Стул, подлокотники имеются",
    "Молоток слесарный не менее 500 г",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("reports/live_qwen_improved.json"))
    args = ap.parse_args()
    o = get_orchestrator()
    if o.engine.settings.recognition_mode != "hybrid" or o.llm is None or not o.llm.available():
        raise RuntimeError("Нужны RECOGNITION_MODE=hybrid, LLM_MODE=always и доступная локальная Qwen")
    rows = []
    failures = []
    for i, text in enumerate(CASES):
        req = SearchRequest(text=text, session_id=f"real-qwen-{i}", revision=1, stage="draft")
        fast = o.run(req)
        start = time.perf_counter()
        full = o.run(req.model_copy(update={"stage": "submitted"}))
        provider = next((p for p in full.providers if p.name == "qwen"), None)
        tentative = [f for f in full.features if f.confirmation == "tentative"]
        if provider is None or not provider.used or provider.status not in ("ok", "cached"):
            failures.append({"text": text, "reason": "реальный разбор не завершён", "provider": provider.model_dump() if provider else None})
        if tentative and (full.final_code or full.code_resolution.status == "resolved"):
            failures.append({"text": text, "reason": "неподтверждённая трактовка привела к конечному коду"})
        if not set(fast.compatible_codes) <= set(full.compatible_codes):
            failures.append({"text": text, "reason": "неподтверждённый разбор исключил проверенных кандидатов"})
        confirmation = None
        if full.question and full.question.kind == "confirm":
            option = full.question.options[0]
            accepted = o.run(req.model_copy(update={"revision": 2, "stage": "submitted", "answers": option.answers,
                                                    "answers_query_hash": full.query_hash}))
            confirmation = {"status": accepted.status, "final_code": accepted.final_code,
                "providers": [p.model_dump() for p in accepted.providers], "message": accepted.message}
        rows.append({"text": text, "fast_status": fast.status, "status": full.status,
            "final_code": full.final_code, "fast_codes": fast.compatible_codes, "compatible_codes": full.compatible_codes,
            "wall_ms": round((time.perf_counter() - start) * 1000, 2),
            "provider": provider.model_dump() if provider else None,
            "features": [f.model_dump() for f in full.features], "issues": [i.model_dump() for i in full.issues],
            "model_description": full.query.get("model_description"), "confirmation": confirmation})
    report = {"kind": "real_model_integration_not_independent_accuracy", "machine": platform.platform(),
              "versions": o.versions(), "cases": rows, "contract_failures": failures}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "contract_failures": len(failures), "out": str(args.out),
                      "providers": [r["provider"] for r in rows]}, ensure_ascii=False, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
