"""Метрики ранжирования и диалога (benchmark/ranking.py) на подставных решениях — без системы и без базы."""
from __future__ import annotations

import math

from benchmark import ranking as rk
from benchmark.adapters.base import Adapter
from benchmark.independent import metrics as mt
from benchmark.run import run_suite


def test_rank_stats_top_k_mrr_ndcg_type():
    pred = {"status": "clarification", "final_code": None,
            "ranked_codes": ["31.01.10.000-1", "14.12.30.190-2", "14.12.30.190-3", "14.12.30.190-4"]}
    s = rk.rank_stats(pred, {"14.12.30.190-2", "14.12.30.190-4"})
    assert s["rank"] == 2 and s["rr"] == 0.5
    assert (s["hit@1"], s["hit@3"], s["hit@5"]) == (False, True, True)
    assert s["type_hit@1"] is False                       # первым показан другой предмет (31.01 вместо 14.12)
    ideal = 1 + 1 / math.log2(3)
    assert s["ndcg@3"] == round((1 / math.log2(3)) / ideal, 4)
    assert s["list_size"] == 4 and s["list_precision"] == 0.5
    assert rk.rank_stats(pred, set()) is None              # пустой эталон — ранжирование не оценивается


def test_ranked_list_fallbacks():
    assert rk.ranked_list({"status": "matched", "final_code": "B", "compatible_codes": ["A", "B"]}) == ["B", "A"]
    assert rk.ranked_list({"status": "clarification", "final_code": None, "compatible_codes": ["A", "B"]}) == ["A", "B"]
    assert rk.ranked_list({"status": "matched", "final_code": "B", "compatible_codes": None}) == ["B"]
    assert rk.ranked_list({"status": "not_found", "final_code": None, "compatible_codes": None}) is None


def test_trace_stats_distance_by_step():
    trace = [{"ranked": list("XYZWG" + "QRST")}, {"ranked": list("YGZ")}, {"ranked": ["G"]}]
    t = rk.trace_stats(trace, {"G"}, resolved=True, max_steps=3)
    assert t["ranks"] == [5, 2, 1, 1]                      # после конца диалога — первая строка
    assert t["questions_to_top1"] == 2 and t["questions"] == 2
    assert t["bits"] == [round(math.log2(9 / 3), 4), round(math.log2(3), 4)] and t["useless"] == 0
    stuck = rk.trace_stats([{"ranked": list("AB")}, {"ranked": list("AB")}], {"B"}, False, 3, "no_option")
    assert stuck["ranks"] == [2, 2, 2, 2] and stuck["useless"] == 1 and stuck["dead_end"]
    assert stuck["questions_to_top1"] is None


def test_summarize_by_step():
    rows = [{"ranking": rk.rank_stats({"ranked_codes": ["G", "A"]}, {"G"}),
             "trace": rk.trace_stats([{"ranked": ["G", "A"]}], {"G"}, True, 2)},
            {"ranking": rk.rank_stats({"ranked_codes": ["A", "B", "G"]}, {"G"}),
             "trace": rk.trace_stats([{"ranked": ["A", "B", "G"]}, {"ranked": ["G"]}], {"G"}, True, 2)},
            {"ranking": rk.rank_stats({"ranked_codes": ["A"]}, {"G"}), "trace": None}]
    s = rk.summarize(rows, 2)
    assert s["hit@1"] == round(1 / 3, 3) and s["hit@3"] == round(2 / 3, 3) and s["gold_not_listed"] == round(1 / 3, 3)
    assert s["mrr"] == round((1 + 1 / 3 + 0) / 3, 3)
    assert s["hit1_by_step"] == [0.5, 1.0, 1.0] and s["rank_by_step"] == [2.0, 1.0, 1.0]
    assert s["questions_to_top1_mean"] == 0.5 and s["top1_reached"] == 1.0


class Ranked(Adapter):
    """Показывает эталон третьим, после одного вопроса — первым, после второго выдаёт код."""
    name = "ranked"

    def predict(self, text):
        return {"status": "clarification", "final_code": None, "compatible_codes": ["A", "B", "G", "H"],
                "ranked_codes": ["A", "B", "G", "H"], "features": [], "warnings": []}

    def dialog(self, text, acceptable_codes, max_steps=6):
        return {"resolved": True, "steps": 2, "final_code": "G", "reason": "matched",
                "trace": [{"ranked": ["A", "B", "G", "H"]}, {"ranked": ["G", "H"]}, {"ranked": ["G"]}]}


CASE = {"id": "1", "text": "x", "acceptable_codes": ["G"], "gold_codes": ["G"], "auto": "forbidden",
        "expect": "code_after_questions", "expected_status": ["clarification"]}


def test_common_runner_ranking_and_dialog_for_forbidden_auto():
    s, rows = run_suite(Ranked(), [CASE], dialog=True, repeat=1)
    r = s["ranking"]
    assert (r["hit@1"], r["hit@3"], r["mrr"]) == (0.0, 1.0, 0.333)
    assert r["rank_by_step"][:3] == [3.0, 1.0, 1.0] and r["questions_to_top1_mean"] == 1
    assert r["bits_per_question"] == round((1 + 1) / 2, 3)    # 4 → 2 → 1: по одному биту на вопрос
    assert s["dialog_resolved"] == 1.0                        # диалог запускается и при auto=forbidden
    assert "trace" not in rows[0]["dialog"]                   # трасса в отчёт не пишется — только её метрики


def test_v2_runner_ranking_and_ci():
    rows = mt.run_suite(Ranked(), [CASE], ks=(1, 2, 3))
    s = mt.summarize(rows, (1, 2, 3), 1000)
    assert s["ranking"]["hit@3"] == 1.0 and s["ranking"]["hit1_by_step"] == [0.0, 1.0, 1.0, 1.0]
    assert s["ci95"]["hit@1"]["value"] == 0.0 and s["over_asking"] is None
