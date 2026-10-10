"""Метрики v2 для независимых наборов.

Оценка одного кейса (evaluate_case) и сводка по набору (summarize). Определения — в README.md:

  wrong_auto          — status=matched и код ∉ gold (или gold пуст); число и доля среди автокодов;
  auto_precision      — 1 − wrong_auto / автокоды; auto_coverage — автокоды / все кейсы;
  code_reached@0      — среди кейсов с непустым gold: верный код выдан сразу (predict);
  code_reached@k      — верный код получен не более чем за k уточнений (adapter.dialog);
  required_hit        — среди code_required: верный код выдан сразу;
  no_code_respected   — среди no_code: код не выдан;
  premature_auto      — среди code_after_questions с |gold| > 1: код выдан сразу (догадка);
  questions_mean      — среднее число вопросов до верного кода (среди кейсов, где он получен за ≤ max k).
Интервалы — перцентильный бутстреп с фиксированным seed; при 0 ошибок (доля = 1) нижняя граница 1 − 3/n,
при 0 успехов (доля = 0) верхняя граница 3/n («правило трёх»).
"""
from __future__ import annotations

import random
import statistics
import time

from benchmark import ranking

KS = (1, 2, 3)
BOOT_N = 2000
BOOT_SEED = 20261010


# ---------------------------------------------------------------- тривиальные базовые линии
class AlwaysClarify:
    """«Всегда уточнение»: никогда не выдаёт код. Показывает пол метрик."""
    name = "baseline:always_clarify"

    def info(self):
        return {"adapter": self.name, "trivial": True}

    def predict(self, text):
        return {"status": "clarification", "final_code": None, "compatible_codes": None, "features": None,
                "warnings": None}

    def dialog(self, text, acceptable_codes, max_steps=6):
        return None


class AlwaysNotFound(AlwaysClarify):
    """«Всегда не найдено»."""
    name = "baseline:always_not_found"

    def predict(self, text):
        return {"status": "not_found", "final_code": None, "compatible_codes": None, "features": None,
                "warnings": None}


BASELINES = (AlwaysClarify, AlwaysNotFound)


# ---------------------------------------------------------------- один кейс
def evaluate_case(adapter, case: dict, ks=KS, use_dialog: bool = True) -> dict:
    gold = set(case.get("gold_codes") or [])
    t0 = time.perf_counter()
    try:
        pred = adapter.predict(case["text"])
        err = None
    except Exception as e:  # noqa: BLE001 — ошибка решения = кейс без кода
        pred, err = {"status": "error", "final_code": None}, f"{type(e).__name__}: {e}"
    latency = (time.perf_counter() - t0) * 1000
    status = pred.get("status")
    code = pred.get("final_code") if status == "matched" else None
    matched = status == "matched"
    row = {
        "id": case["id"], "split": case.get("split"), "expect": case["expect"], "gold_size": len(gold),
        "status": status, "final_code": code, "matched": matched,
        "wrong_auto": matched and code not in gold,
        "hit0": matched and code in gold,
        "latency_ms": round(latency, 2), "error": err,
        "dialog": None, "reached_at": 0 if (matched and code in gold) else None,
        "ranking": ranking.rank_stats(pred, gold), "trace": None,
    }
    if gold and use_dialog and ks:
        if row["hit0"]:
            row["dialog"] = {"skipped": "hit0"}     # код выдан сразу — диалог не нужен
            row["trace"] = ranking.trace_stats([{"ranked": ranking.ranked_list(pred)}], gold, True, max(ks))
        else:
            k = max(ks)
            try:
                d = adapter.dialog(case["text"], set(gold), max_steps=k) if hasattr(adapter, "dialog") else None
            except Exception as e:  # noqa: BLE001
                d = {"resolved": False, "steps": 0, "final_code": None, "error": f"{type(e).__name__}: {e}"}
            if d is None:
                row["dialog"] = {"supported": False}
            else:
                fc = d.get("final_code")
                ok = bool(d.get("resolved")) and fc in gold
                row["dialog"] = {"supported": True, "resolved": ok, "steps": d.get("steps"), "final_code": fc,
                                 "wrong_final": fc is not None and fc not in gold, "reason": d.get("reason")}
                row["trace"] = ranking.trace_stats(d.get("trace"), gold, ok, k, d.get("reason"))
                if ok and d.get("steps") is not None and d["steps"] <= k:
                    row["reached_at"] = int(d["steps"])
    return row


def run_suite(adapter, cases: list[dict], ks=KS, use_dialog: bool = True) -> list[dict]:
    return [evaluate_case(adapter, c, ks, use_dialog) for c in cases]


# ---------------------------------------------------------------- интервалы
def proportion_ci(xs: list[bool], n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> dict | None:
    """Доля и 95% интервал. Бутстреп (перцентили), при доле 0 или 1 — правило трёх."""
    n = len(xs)
    if n == 0:
        return None
    k = sum(bool(x) for x in xs)
    p = k / n
    if k == n:
        return {"value": round(p, 4), "lo": round(max(0.0, 1 - 3 / n), 4), "hi": 1.0, "n": n,
                "method": "rule_of_three"}
    if k == 0:
        return {"value": 0.0, "lo": 0.0, "hi": round(min(1.0, 3 / n), 4), "n": n, "method": "rule_of_three"}
    rng = random.Random(seed)
    vals = [1 if x else 0 for x in xs]
    stats = sorted(sum(rng.choices(vals, k=n)) / n for _ in range(n_boot))
    lo = stats[int(0.025 * (n_boot - 1))]
    hi = stats[int(round(0.975 * (n_boot - 1)))]
    return {"value": round(p, 4), "lo": round(lo, 4), "hi": round(hi, 4), "n": n, "method": "bootstrap"}


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))], 2)


def ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


# ---------------------------------------------------------------- сводка
def summarize(rows: list[dict], ks=KS, n_boot: int = BOOT_N, seed: int = BOOT_SEED) -> dict:
    n = len(rows)
    auto = [r for r in rows if r["matched"]]
    wrong = sum(r["wrong_auto"] for r in auto)
    gold_rows = [r for r in rows if r["gold_size"] > 0]
    req = [r for r in rows if r["expect"] == "code_required"]
    noc = [r for r in rows if r["expect"] == "no_code"]
    amb = [r for r in rows if r["expect"] == "code_after_questions" and r["gold_size"] > 1]
    dl = [r for r in gold_rows if r["dialog"] is not None and "skipped" not in r["dialog"]]
    supported = [r for r in dl if r["dialog"].get("supported")]
    if not dl:
        dialog_support = "not_run"
    elif not supported:
        dialog_support = "not_supported"
    elif len(supported) < len(dl):
        dialog_support = "partial"
    else:
        dialog_support = "supported"

    def reached(r, k):
        return r["reached_at"] is not None and r["reached_at"] <= k

    out = {
        "cases": n,
        "status_counts": dict(sorted(_count(r["status"] for r in rows).items())),
        "errors": sum(r["error"] is not None for r in rows),
        "auto": len(auto),
        "wrong_auto": wrong,
        "wrong_auto_rate": ratio(wrong, len(auto)),
        "auto_precision": ratio(len(auto) - wrong, len(auto)),
        "auto_coverage": ratio(len(auto), n),
        "gold_nonempty": len(gold_rows),
        "code_reached@0": ratio(sum(r["hit0"] for r in gold_rows), len(gold_rows)),
        "dialog_support": dialog_support,
    }
    for k in ks:
        out[f"code_reached@{k}"] = ratio(sum(reached(r, k) for r in gold_rows), len(gold_rows))
    out.update({
        "required_cases": len(req),
        "required_hit": ratio(sum(r["hit0"] for r in req), len(req)),
        "no_code_cases": len(noc),
        "no_code_respected": ratio(sum(not r["matched"] for r in noc), len(noc)),
        "premature_auto": ratio(sum(r["matched"] for r in amb), len(amb)),
        "dialog_wrong_final": sum(bool(r["dialog"] and r["dialog"].get("wrong_final")) for r in gold_rows),
    })
    kmax = max(ks) if ks else 0
    q = [r["reached_at"] for r in gold_rows if reached(r, kmax)]
    out["questions_mean"] = round(statistics.mean(q), 3) if q else None
    lat = [r["latency_ms"] for r in rows]
    out["latency_ms_p50"] = pct(lat, 50)
    out["latency_ms_p95"] = pct(lat, 95)
    k2 = 2 if 2 in ks else (max(ks) if ks else 0)
    out["ci95"] = {
        f"code_reached@{k2}": proportion_ci([reached(r, k2) for r in gold_rows], n_boot, seed),
        "auto_precision": proportion_ci([not r["wrong_auto"] for r in auto], n_boot, seed),
        "no_code_respected": proportion_ci([not r["matched"] for r in noc], n_boot, seed),
    }
    # верхняя граница доли ошибочных автокодов
    ap = out["ci95"]["auto_precision"]
    out["wrong_auto_rate_upper95"] = round(1 - ap["lo"], 4) if ap else None
    # ранжирование (что показано первым) и дальность эталона от вершины по шагам диалога
    out["ranking"] = ranking.summarize(rows, kmax)
    rk = [r["ranking"] for r in rows if r.get("ranking")]
    out["ci95"]["hit@1"] = proportion_ci([x["hit@1"] for x in rk], n_boot, seed)
    out["ci95"]["hit@3"] = proportion_ci([x["hit@3"] for x in rk], n_boot, seed)
    # лишние вопросы: среди code_required код был ясен из текста, а решение спросило
    out["over_asking"] = ratio(sum(not r["matched"] for r in req), len(req))
    # уверенная ошибка: автокод не из эталона, хотя эталон был в списке решения — ранжирование подвело
    out["wrong_auto_gold_listed"] = sum(r["wrong_auto"] and bool(r.get("ranking") and r["ranking"]["rank"])
                                        for r in rows)
    return out


def _count(xs):
    d: dict = {}
    for x in xs:
        d[x] = d.get(x, 0) + 1
    return d
