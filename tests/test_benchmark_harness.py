"""Проверка самих метрик общего набора (benchmark/run.py) на подставном решении."""
from benchmark.adapters.base import Adapter
from benchmark.run import run_suite


class Fixed(Adapter):
    def __init__(self, answers):
        self.answers = answers

    def predict(self, text):
        status, code = self.answers[text]
        return {"status": status, "final_code": code, "compatible_codes": [code] if code else [],
                "features": [], "warnings": ["w"] if status == "conflict" else []}


CASES = [
    {"id": "1", "text": "a", "acceptable_codes": ["X"], "auto": "required", "expected_status": ["matched"]},
    {"id": "2", "text": "b", "acceptable_codes": ["Y"], "auto": "allowed", "expected_status": []},
    {"id": "3", "text": "c", "acceptable_codes": [], "auto": "forbidden", "expected_status": ["conflict"],
     "checks": [{"type": "warning"}]},
    {"id": "4", "text": "d", "acceptable_codes": ["Z"], "auto": "allowed", "forbidden_codes": ["Q"],
     "checks": [{"type": "same_as", "text": "a"}]},
]


def test_metrics_on_known_answers():
    ad = Fixed({"a": ("matched", "X"), "b": ("matched", "W"), "c": ("conflict", None), "d": ("matched", "Q")})
    s, rows = run_suite(ad, CASES, dialog=False, repeat=2)
    assert s["auto_correct"] == 1 and s["auto_incorrect"] == 2           # b → W и d → Q вне допустимых
    assert s["forbidden_code_hits"] == 1 and s["forbidden_auto_violations"] == 0
    assert s["required_auto_hit"] == 1.0 and s["pass_rate"] == 0.5
    assert s["auto_precision"] == round(1 / 3, 3) and s["error_upper95"] is None
    assert s["determinism"] == 1.0 and s["checks_by_type"]["warning"]["pass"] == 1
    assert [r["pass"] for r in rows] == [True, False, True, False]
