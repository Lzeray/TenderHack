"""Метрики ранжирования и диалога — общие для benchmark.run и benchmark.independent.

Ранжированный список — то, что решение показывает пользователю первым делом, лучший кандидат первым
(`ranked_codes` в ответе адаптера; если поля нет — `final_code`, затем `compatible_codes` в их порядке).
Позиция эталона в списке — `rank` (1 = первая строка). Эталон может состоять из нескольких кодов: берётся лучший.

Метрика «—» в отчёте: решение не отдаёт ни списка, ни трассы (например, тривиальные базовые линии).

По одному ответу (до вопросов):
  hit@1, hit@3, hit@5 — эталон среди первых k строк; mrr — 1/rank (0, если эталона в списке нет);
  ndcg@3 — насколько все допустимые коды собраны наверху (важно при |gold| > 1);
  type_hit@1 — первая строка того же ОКПД2 (часть кода до «-»), что эталон: верный ли предмет, даже если не та
               позиция (приближение «типа товара»);
  list_size — сколько строк пользователю пришлось бы просмотреть; list_precision — доля верных строк в списке.
По диалогу (трасса adapter.dialog: что видел пользователь после каждого ответа):
  rank_by_step[k] — средняя строка эталона после k вопросов (среди кейсов, где он в списке);
  mrr_by_step[k], hit1_by_step[k] — то же через 1/rank и долю «эталон первым» (эталона нет в списке — 0);
  questions_to_top1 — сколько вопросов нужно, чтобы эталон стал первой строкой;
  bits_per_question — log2(сужение списка) за один вопрос; useless_question_rate — вопросы, после которых список
                     не сузился; dead_end_rate — диалог остановился, потому что ни один вариант ответа не сохранял
                     эталон (вопрос без правильного варианта).
"""
from __future__ import annotations

import math
import statistics

KS = (1, 3, 5)


def ranked_list(pred: dict) -> list[str] | None:
    """Ранжированный список ответа; None — решение не отдаёт ни списка, ни кода."""
    if pred.get("ranked_codes") is not None:
        return list(pred["ranked_codes"])
    comp = pred.get("compatible_codes")
    code = pred.get("final_code") if pred.get("status") == "matched" else None
    if comp is None:
        return [code] if code else None
    return ([code] if code else []) + [c for c in comp if c != code]


def okpd2(code: str | None) -> str | None:
    return code.split("-", 1)[0] if code else None


def gold_rank(ranked: list[str] | None, gold: set[str]) -> int | None:
    if not ranked:
        return None
    return next((i for i, c in enumerate(ranked, 1) if c in gold), None)


def rank_stats(pred: dict, gold) -> dict | None:
    """Метрики одного ответа; None — эталон пуст или решение не отдаёт список."""
    gold = set(gold or [])
    ranked = ranked_list(pred)
    if not gold or ranked is None:
        return None
    r = gold_rank(ranked, gold)
    dcg = sum(1 / math.log2(i + 1) for i, c in enumerate(ranked[:3], 1) if c in gold)
    idcg = sum(1 / math.log2(i + 1) for i in range(1, min(len(gold), 3) + 1))
    out = {"rank": r, "rr": round(1 / r, 4) if r else 0.0, "ndcg@3": round(dcg / idcg, 4),
           "type_hit@1": bool(ranked) and okpd2(ranked[0]) in {okpd2(g) for g in gold},
           "list_size": len(ranked),
           "list_precision": round(len(set(ranked) & gold) / len(ranked), 4) if ranked else None}
    for k in KS:
        out[f"hit@{k}"] = r is not None and r <= k
    return out


def trace_stats(trace: list[dict] | None, gold, resolved: bool, max_steps: int, reason: str | None = None) -> dict | None:
    """Траектория эталона по шагам диалога. trace[i] = {"ranked": [...], "status": ...}; шаг 0 — исходный ответ."""
    gold = set(gold or [])
    if not trace or not gold:
        return None
    ranks = [gold_rank(t.get("ranked"), gold) for t in trace]
    sizes = [len(t.get("ranked") or []) for t in trace]
    # после конца диалога состояние не меняется: верный код — первая строка, иначе — последнее состояние
    last = 1 if resolved else ranks[-1]
    full = (ranks + [last] * (max_steps + 1))[:max_steps + 1]
    q_top1 = next((k for k, r in enumerate(full) if r == 1), None)
    trans = [(a, b) for a, b in zip(sizes, sizes[1:]) if a > 0 and b > 0]
    return {"ranks": full, "questions_to_top1": q_top1,
            "bits": [round(math.log2(a / b), 4) for a, b in trans],
            "useless": sum(b >= a for a, b in trans), "questions": len(trace) - 1,
            "dead_end": reason == "no_option"}


def _ratio(a, b):
    return round(a / b, 3) if b else None


def summarize(rows: list[dict], max_steps: int = 3) -> dict:
    """rows: [{"ranking": rank_stats|None, "trace": trace_stats|None}, ...]"""
    rk = [r["ranking"] for r in rows if r.get("ranking")]
    out: dict = {"ranked_cases": len(rk)}
    if rk:
        for k in KS:
            out[f"hit@{k}"] = _ratio(sum(x[f"hit@{k}"] for x in rk), len(rk))
        out["mrr"] = round(statistics.mean(x["rr"] for x in rk), 3)
        out["ndcg@3"] = round(statistics.mean(x["ndcg@3"] for x in rk), 3)
        out["type_hit@1"] = _ratio(sum(x["type_hit@1"] for x in rk), len(rk))
        found = [x["rank"] for x in rk if x["rank"]]
        out["gold_rank_median"] = statistics.median(found) if found else None
        out["gold_not_listed"] = _ratio(sum(x["rank"] is None for x in rk), len(rk))
        out["list_size_median"] = statistics.median(x["list_size"] for x in rk)
        lp = [x["list_precision"] for x in rk if x["list_precision"] is not None]
        out["list_precision_mean"] = round(statistics.mean(lp), 3) if lp else None
    tr = [r["trace"] for r in rows if r.get("trace")]
    out["dialog_traced"] = len(tr)
    if tr:
        steps = range(max_steps + 1)
        out["mrr_by_step"] = [round(statistics.mean((1 / t["ranks"][k]) if t["ranks"][k] else 0 for t in tr), 3)
                              for k in steps]
        out["hit1_by_step"] = [_ratio(sum(t["ranks"][k] == 1 for t in tr), len(tr)) for k in steps]
        out["rank_by_step"] = [round(statistics.mean(xs), 2) if (xs := [t["ranks"][k] for t in tr if t["ranks"][k]])
                               else None for k in steps]
        q = [t["questions_to_top1"] for t in tr if t["questions_to_top1"] is not None]
        out["top1_reached"] = _ratio(len(q), len(tr))
        out["questions_to_top1_mean"] = round(statistics.mean(q), 2) if q else None
        bits = [b for t in tr for b in t["bits"]]
        nq = sum(len(t["bits"]) for t in tr)
        out["bits_per_question"] = round(statistics.mean(bits), 3) if bits else None
        out["useless_question_rate"] = _ratio(sum(t["useless"] for t in tr), nq)
        out["dead_end_rate"] = _ratio(sum(t["dead_end"] for t in tr), len(tr))
    return out


def markdown_rows(summaries: dict[str, dict]) -> list[str]:
    """Строки таблицы «метрика | набор…» для отчётов."""
    keys = ["hit@1", "hit@3", "hit@5", "mrr", "ndcg@3", "type_hit@1", "gold_rank_median", "gold_not_listed",
            "list_size_median", "list_precision_mean", "top1_reached", "questions_to_top1_mean", "rank_by_step",
            "hit1_by_step", "mrr_by_step", "bits_per_question", "useless_question_rate", "dead_end_rate"]
    names = list(summaries)
    lines = ["| метрика | " + " | ".join(names) + " |", "| --- |" + " --- |" * len(names)]
    for k in keys:
        vals = [summaries[n].get(k) for n in names]
        if all(v is None for v in vals):
            continue
        lines.append(f"| {k} | " + " | ".join("—" if v is None else str(v) for v in vals) + " |")
    return lines
