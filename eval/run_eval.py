"""Оценка на вручную размеченных кейсах (eval/cases.jsonl) по реальной базе.

Метрики:
  * status_ok — фактический статус входит в допустимые для кейса;
  * correct_final — matched и код совпал с эталоном;
  * false_unique — matched, но код не совпал (или эталона нет) — ошибочное однозначное решение;
  * expected_in_compatible — эталонный код есть среди совместимых конечных кандидатов;
  * must_explain — нужное пояснение присутствует в ответе;
  * resolved_after_questions — СИМУЛЯЦИЯ: на каждый вопрос «пользователь» выбирает вариант,
    совместимый с эталонной позицией; считаем, за сколько вопросов получен верный код (макс. 6);
  * задержки: время engine.search (p50/p95) по всем кейсам × повторы, и полное время через HTTP API.
Повторяемость: ответы на одинаковые запросы сравниваются побайтно (без elapsed_ms и timings).

python -m eval.run_eval [--repeat 20]
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import app, get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402


def pct(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


def simulate(eng, case) -> tuple[bool, int, str]:
    """Отвечать на вопросы вариантом, совместимым с эталонной позицией."""
    exp = case["expected_code"]
    answers, qhash = [], None
    for step in range(7):
        r = eng.search(SearchRequest(text=case["text"], answers=answers, answers_query_hash=qhash))
        if r.status == "matched":
            return r.final_code == exp, step, r.final_code
        if r.question is None or step == 6:
            return False, step, r.status
        chosen = None
        for opt in r.question.options:
            trial = [a for a in answers if a.property != opt.answer.property] + [opt.answer]
            rr = eng.search(SearchRequest(text=case["text"], answers=trial, answers_query_hash=r.query_hash))
            if any(c.code == exp and c.compatible for c in rr.candidates):
                chosen = opt.answer
                break
        if chosen is None:
            return False, step, "эталон несовместим ни с одним вариантом"
        answers = [a for a in answers if a.property != chosen.property] + [chosen]
        qhash = r.query_hash
    return False, 6, "лимит вопросов"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "reports" / "eval_results.json"))
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases.jsonl"))
    args = ap.parse_args()
    cases = [json.loads(l) for l in Path(args.cases).read_text(encoding="utf-8").splitlines() if l.strip()]
    t0 = time.perf_counter()
    eng = get_engine()
    init_s = time.perf_counter() - t0

    rows, lat = [], []
    for c in cases:
        r = eng.search(SearchRequest(text=c["text"]))
        dump = json.dumps(r.model_dump(mode="json") | {"elapsed_ms": 0, "timings": {}}, ensure_ascii=False, sort_keys=True)
        same = True
        for _ in range(args.repeat):
            t = time.perf_counter()
            r2 = eng.search(SearchRequest(text=c["text"]))
            lat.append((time.perf_counter() - t) * 1000)
            d2 = json.dumps(r2.model_dump(mode="json") | {"elapsed_ms": 0, "timings": {}}, ensure_ascii=False, sort_keys=True)
            same &= d2 == dump
        exp = c["expected_code"]
        finals = [x.code for x in r.candidates if x.compatible and not x.is_template]
        text_all = json.dumps(r.model_dump(mode="json"), ensure_ascii=False).lower()
        row = {
            "id": c["id"], "category": c["category"], "text": c["text"], "expected_code": exp,
            "expected_status": c["expected_status"], "status": r.status, "final_code": r.final_code,
            "status_ok": r.status in c["expected_status"],
            "correct_final": r.status == "matched" and r.final_code == exp,
            "false_unique": r.status == "matched" and r.final_code != exp,
            "expected_in_compatible": (exp in finals) if exp else None,
            "expected_rank": (finals.index(exp) + 1) if exp in finals else None,
            "compatible_finals": len(finals),
            "must_explain_ok": (c["must_explain"].lower() in text_all) if c.get("must_explain") else None,
            "repeatable": same,
            "question": r.question.text if r.question else None,
        }
        if exp and r.status != "matched":
            ok, steps, info = simulate(eng, c)
            row.update(resolved_after_questions=steps if ok else None, simulation=info)
        rows.append(row)

    from fastapi.testclient import TestClient
    client = TestClient(app)
    api_lat = []
    for c in cases:
        for _ in range(5):
            t = time.perf_counter()
            resp = client.post("/api/search", json={"text": c["text"]})
            api_lat.append((time.perf_counter() - t) * 1000)
            assert resp.status_code == 200

    n = len(rows)
    with_code = [r for r in rows if r["expected_code"]]
    summary = {
        "cases": n,
        "status_ok": sum(r["status_ok"] for r in rows),
        "matched": sum(r["status"] == "matched" for r in rows),
        "correct_final": sum(r["correct_final"] for r in rows),
        "false_unique": sum(r["false_unique"] for r in rows),
        "cases_with_expected_code": len(with_code),
        "expected_in_compatible": sum(bool(r["expected_in_compatible"]) for r in with_code),
        "expected_rank1": sum(r["expected_rank"] == 1 for r in with_code),
        "must_explain_ok": f"{sum(bool(r['must_explain_ok']) for r in rows if r['must_explain_ok'] is not None)}/"
                           f"{sum(r['must_explain_ok'] is not None for r in rows)}",
        "simulated_resolved": f"{sum(r.get('resolved_after_questions') is not None for r in rows)}/"
                              f"{sum('resolved_after_questions' in r for r in rows)}",
        "repeatable": sum(r["repeatable"] for r in rows),
        "engine_latency_ms": {"n": len(lat), "p50": round(pct(lat, 50), 2), "p95": round(pct(lat, 95), 2),
                              "max": round(max(lat), 2), "mean": round(statistics.mean(lat), 2)},
        "api_latency_ms": {"n": len(api_lat), "p50": round(pct(api_lat, 50), 2), "p95": round(pct(api_lat, 95), 2),
                           "max": round(max(api_lat), 2)},
        "engine_init_s": round(init_s, 2),
        "backend": eng.backend.name,
        "catalog_snapshot": eng.catalog.meta.get("snapshot"),
        "machine": {"platform": platform.platform(), "python": platform.python_version(),
                    "processor": platform.processor()},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in rows:
        mark = "OK " if r["status_ok"] and not r["false_unique"] else "BAD"
        print(f"{mark} {r['id']} {r['status']:<21} final={r['final_code']} exp={r['expected_code']} "
              f"rank={r['expected_rank']} sim={r.get('resolved_after_questions', '-')} {r.get('simulation', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
