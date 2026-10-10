"""Общий набор тестов подбора КТРУ: прогон любого решения и метрики по каждому набору.

  python -m benchmark.run --adapter ktru:core --suites all --dialog --out reports/bench/core.json
  python -m benchmark.compare reports/bench/core.json reports/bench/core_sem_b.json

Наборы (benchmark/suites/*.jsonl), формат кейса — benchmark/README.md. Для каждого набора считаются:
pass_rate, status_accuracy, auto_coverage, auto_correct, auto_incorrect, auto_precision,
required_auto_hit, forbidden_auto_violations, forbidden_code_hits, compatible_recall, checks_pass,
dialog_resolved, dialog_steps_mean, latency p50/p95/max, errors, determinism (при --repeat ≥ 2),
error_upper95 («правило трёх» при 0 ошибочных автоматических решений).
"""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SUITES_DIR = Path(__file__).resolve().parent / "suites"
SHORTCUTS = {"ktru": ("benchmark.adapters.ktru", "KtruInProcess"),
             "ktru_http": ("benchmark.adapters.ktru", "KtruHttp"),
             "ktru_draft_http": ("benchmark.adapters.ktru", "KtruDraftHttp")}


def load_adapter(spec: str):
    head, _, arg = spec.partition(":")
    if head in SHORTCUTS:
        mod, cls = SHORTCUTS[head]
        return getattr(importlib.import_module(mod), cls)(*([arg] if arg else []))
    cls, _, carg = arg.partition("=")
    return getattr(importlib.import_module(head), cls)(*([carg] if carg else []))


def load_suites(names: list[str], split: str | None) -> dict[str, list[dict]]:
    files = sorted(SUITES_DIR.glob("*.jsonl")) if names == ["all"] else [SUITES_DIR / f"{n}.jsonl" for n in names]
    out = {}
    for f in files:
        cases = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        if split:
            cases = [c for c in cases if c.get("split") == split]
        out[f.stem] = cases
    return out


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))], 2)


def _num(v):
    return str(v or "").replace(",", ".").strip().lower()


def run_check(chk: dict, pred: dict, predict_cached) -> str:
    """pass | fail | not_supported"""
    t = chk["type"]
    if t == "same_as":
        other = predict_cached(chk["text"])
        return "pass" if (pred["status"], pred["final_code"]) == (other["status"], other["final_code"]) else "fail"
    if t == "subset_of":
        other = predict_cached(chk["text"])
        if pred.get("compatible_codes") is None or other.get("compatible_codes") is None:
            return "not_supported"
        return "pass" if set(pred["compatible_codes"]) <= set(other["compatible_codes"]) else "fail"
    if t == "warning":
        if pred.get("warnings") is None:
            return "not_supported"
        return "pass" if pred["warnings"] else "fail"
    if t in ("feature", "no_feature"):
        if pred.get("features") is None:
            return "not_supported"
        hit = any(chk["property"].lower() in (f.get("property") or "").lower()
                  and ("value" not in chk or _num(f.get("value")) == _num(chk["value"]))
                  and ("unit" not in chk or (f.get("unit") or "").lower() == chk["unit"].lower())
                  for f in pred["features"])
        return "pass" if hit == (t == "feature") else "fail"
    raise ValueError(f"неизвестный тип проверки {t}")


def evaluate_case(case: dict, pred: dict, predict_cached) -> dict:
    acc = set(case.get("acceptable_codes") or [])
    matched = pred["status"] == "matched"
    auto = case.get("auto", "allowed")
    incorrect = matched and pred["final_code"] not in acc
    if auto == "required":
        auto_ok = matched and not incorrect
    elif auto == "forbidden":
        auto_ok = not matched
    else:
        auto_ok = not incorrect
    status_ok = pred["status"] in case["expected_status"] if case.get("expected_status") else None
    forbidden_hit = bool(pred["final_code"]) and pred["final_code"] in set(case.get("forbidden_codes") or [])
    comp = pred.get("compatible_codes")
    recall = (bool(set(comp) & acc) if comp is not None else None) if acc else None
    checks = {f"{i}:{c['type']}": run_check(c, pred, predict_cached) for i, c in enumerate(case.get("checks", []))}
    passed = auto_ok and status_ok is not False and not forbidden_hit and "fail" not in checks.values()
    return {"id": case["id"], "text": case["text"], "split": case.get("split"), "auto": auto,
            "acceptable": sorted(acc), "status": pred["status"], "final_code": pred["final_code"],
            "pass": passed, "status_ok": status_ok, "auto_ok": auto_ok, "auto_incorrect": incorrect,
            "forbidden_code_hit": forbidden_hit, "compatible_recall": recall, "checks": checks}


def summarize(rows: list[dict], lat: list[float], errors: int, determinism) -> dict:
    n = len(rows)
    m = [r for r in rows if r["status"] == "matched"]
    inc = sum(r["auto_incorrect"] for r in rows)
    req = [r for r in rows if r["auto"] == "required"]
    forb = [r for r in rows if r["auto"] == "forbidden"]
    st = [r for r in rows if r["status_ok"] is not None]
    rec = [r for r in rows if r["compatible_recall"] is not None]
    chk = [v for r in rows for v in r["checks"].values()]
    by_type: dict[str, dict[str, int]] = {}
    for r in rows:
        for k, v in r["checks"].items():
            t = k.split(":", 1)[1]
            by_type.setdefault(t, {"pass": 0, "fail": 0, "not_supported": 0})[v] += 1
    dl = [r for r in rows if "dialog" in r]
    dls = [r for r in dl if r["dialog"] is not None]
    ratio = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {
        "cases": n, "errors": errors,
        "pass_rate": ratio(sum(r["pass"] for r in rows), n),
        "status_accuracy": ratio(sum(r["status_ok"] for r in st), len(st)),
        "auto_coverage": ratio(len(m), n),
        "auto_correct": len(m) - inc, "auto_incorrect": inc,
        "auto_precision": ratio(len(m) - inc, len(m)),
        "error_upper95": ratio(3, len(m)) if m and not inc else None,
        "required_auto_hit": ratio(sum(r["auto_ok"] for r in req), len(req)),
        "forbidden_auto_violations": sum(not r["auto_ok"] for r in forb),
        "forbidden_code_hits": sum(r["forbidden_code_hit"] for r in rows),
        "compatible_recall": ratio(sum(r["compatible_recall"] for r in rec), len(rec)),
        "checks_pass": ratio(chk.count("pass"), chk.count("pass") + chk.count("fail")),
        "checks_not_supported": chk.count("not_supported"),
        "checks_by_type": by_type,
        "dialog_resolved": ratio(sum(r["dialog"]["resolved"] for r in dls), len(dls)) if dls else None,
        "dialog_cases": len(dls), "dialog_not_supported": len(dl) - len(dls),
        "dialog_steps_mean": round(statistics.mean(r["dialog"]["steps"] for r in dls if r["dialog"]["resolved"]), 2)
        if any(r["dialog"]["resolved"] for r in dls) else None,
        "latency_ms": {"p50": pct(lat, 50), "p95": pct(lat, 95), "max": round(max(lat), 2) if lat else None,
                       "mean": round(statistics.mean(lat), 2) if lat else None},
        "determinism": determinism,
    }


def run_suite(adapter, cases: list[dict], dialog: bool, repeat: int):
    cache: dict[str, dict] = {}

    def predict_cached(text):
        if text not in cache:
            cache[text] = adapter.predict(text)
        return cache[text]

    rows, lat, errors, same, rep_n = [], [], 0, 0, 0
    for c in cases:
        t0 = time.perf_counter()
        try:
            pred = adapter.predict(c["text"])
        except Exception as e:  # noqa: BLE001 — сбой решения считается ошибкой кейса, прогон продолжается
            errors += 1
            pred = {"status": "error", "final_code": None, "compatible_codes": None, "features": None,
                    "warnings": [f"исключение: {e}"]}
        lat.append((time.perf_counter() - t0) * 1000)
        cache.setdefault(c["text"], pred)
        row = evaluate_case(c, pred, predict_cached)
        for _ in range(max(0, repeat - 1)):
            p2 = adapter.predict(c["text"])
            rep_n += 1
            same += (p2["status"], p2["final_code"], sorted(p2.get("compatible_codes") or [])) == \
                (pred["status"], pred["final_code"], sorted(pred.get("compatible_codes") or []))
        if dialog and pred["status"] != "matched" and c.get("acceptable_codes") and c.get("auto") != "forbidden":
            row["dialog"] = adapter.dialog(c["text"], set(c["acceptable_codes"]))
        rows.append(row)
    det = round(same / rep_n, 3) if rep_n else None
    return summarize(rows, lat, errors, det), rows


def to_markdown(report: dict) -> str:
    keys = ["cases", "pass_rate", "status_accuracy", "auto_coverage", "auto_correct", "auto_incorrect",
            "auto_precision", "error_upper95", "required_auto_hit", "forbidden_auto_violations", "forbidden_code_hits",
            "compatible_recall", "checks_pass", "dialog_resolved", "dialog_steps_mean", "determinism", "errors"]
    suites = list(report["suites"])
    lines = [f"# Отчёт: {report['adapter']}", "", f"Дата: {report['date']}; машина: {report['machine']['platform']}", "",
             "| метрика | " + " | ".join(suites) + " |", "| --- |" + " --- |" * len(suites)]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(str(report["suites"][s]["summary"].get(k)) for s in suites) + " |")
    lines.append("| latency p50 / p95, мс | " + " | ".join(
        f"{report['suites'][s]['summary']['latency_ms']['p50']} / {report['suites'][s]['summary']['latency_ms']['p95']}"
        for s in suites) + " |")
    lines += ["", "Непройденные кейсы:", ""]
    for s in suites:
        for r in report["suites"][s]["cases"]:
            if not r["pass"]:
                lines.append(f"- `{s}/{r['id']}` {r['status']} {r['final_code'] or ''} — «{r['text']}» "
                             f"(ожидалось: auto={r['auto']}, коды {', '.join(r['acceptable'][:3]) or '—'}; "
                             f"проверки: {r['checks']})")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True, help="ktru:core | ktru_http:URL | модуль:Класс[=аргумент]")
    ap.add_argument("--suites", nargs="+", default=["all"])
    ap.add_argument("--split", default=None, help="только кейсы dev или test")
    ap.add_argument("--dialog", action="store_true", help="симулировать уточнения (если адаптер умеет)")
    ap.add_argument("--repeat", type=int, default=1, help="повторы для проверки детерминизма")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    adapter = load_adapter(args.adapter)
    report = {"adapter": args.adapter, "info": adapter.info(), "date": time.strftime("%Y-%m-%d %H:%M"),
              "machine": {"platform": platform.platform(), "python": platform.python_version()},
              "split": args.split, "suites": {}}
    for name, cases in load_suites(args.suites, args.split).items():
        summary, rows = run_suite(adapter, cases, args.dialog, args.repeat)
        report["suites"][name] = {"summary": summary, "cases": rows}
        print(f"[{name}] " + json.dumps({k: v for k, v in summary.items() if k != "checks_by_type"},
                                        ensure_ascii=False))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    out.with_suffix(".md").write_text(to_markdown(report), encoding="utf-8")
    print(f"отчёт: {out} и {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
