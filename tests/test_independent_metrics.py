"""Тесты независимых метрик v2 (benchmark/independent) на фейковых адаптерах.

Систему (ktru_assist) эти тесты не запускают: проверяются только формулы метрик, интервалы,
базовые линии и собственный эталон (интервалы, единицы).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from benchmark.independent import metrics as mt
from benchmark.independent.reference import (Char, Interval, Value, char_compatible, convert, norm_text,
                                             value_compatible)

ROOT = Path(__file__).resolve().parent.parent


class FakeAdapter:
    """predict по таблице; dialog — шаг, на котором «пользователь» получает код (или None — не получает)."""
    name = "fake"

    def __init__(self, answers: dict, dialogs: dict | None = None, with_dialog: bool = True):
        self.answers = answers
        self.dialogs = dialogs or {}
        self.with_dialog = with_dialog
        self.dialog_calls: list[tuple[str, frozenset, int]] = []

    def info(self):
        return {"adapter": self.name}

    def predict(self, text):
        a = self.answers[text]
        if a == "boom":
            raise RuntimeError("сбой")
        status, code = a
        return {"status": status, "final_code": code}

    def dialog(self, text, acceptable_codes, max_steps=6):
        if not self.with_dialog:
            return None
        self.dialog_calls.append((text, frozenset(acceptable_codes), max_steps))
        d = self.dialogs.get(text)
        if d is None:
            return {"resolved": False, "steps": max_steps, "final_code": None}
        steps, code = d
        if steps > max_steps:
            return {"resolved": False, "steps": max_steps, "final_code": None}
        return {"resolved": code in acceptable_codes, "steps": steps, "final_code": code}


def case(cid, expect, gold, split="dev"):
    return {"id": cid, "text": cid, "expect": expect, "gold_codes": gold, "split": split}


CASES = [
    case("c1", "code_required", ["A"]),
    case("c2", "code_required", ["B"]),
    case("c3", "code_after_questions", ["A", "B"]),
    case("c4", "code_after_questions", ["D"], split="test"),
    case("c5", "code_after_questions", ["E", "F"]),
    case("c6", "no_code", []),
    case("c7", "no_code", [], split="test"),
    case("c8", "code_after_questions", ["A", "B"]),
]
ANSWERS = {
    "c1": ("matched", "A"),          # верный автокод
    "c2": ("matched", "C"),          # неверный автокод
    "c3": ("clarification", None),   # код после 1 вопроса
    "c4": ("clarification", None),   # код после 3 вопросов
    "c5": ("clarification", None),   # диалог не доводит до кода
    "c6": ("matched", "X"),          # код при пустом эталоне — ошибка
    "c7": ("not_found", None),
    "c8": ("matched", "A"),          # догадка при |gold| > 1, но код из эталона
}
DIALOGS = {"c3": (1, "A"), "c4": (3, "D"), "c5": (2, "Z")}


def summary(adapter, cases=CASES, ks=(1, 2, 3)):
    rows = mt.run_suite(adapter, cases, ks)
    return rows, mt.summarize(rows, ks, n_boot=1000)


def test_wrong_auto_precision_coverage():
    _, s = summary(FakeAdapter(ANSWERS, DIALOGS))
    assert s["auto"] == 4
    assert s["wrong_auto"] == 2                     # c2 (код не из эталона) и c6 (эталон пуст)
    assert s["wrong_auto_rate"] == 0.5
    assert s["auto_precision"] == 0.5
    assert s["auto_coverage"] == 0.5


def test_code_reached_at_k_and_questions():
    rows, s = summary(FakeAdapter(ANSWERS, DIALOGS))
    assert s["gold_nonempty"] == 6
    assert s["code_reached@0"] == round(2 / 6, 4)  # c1, c8
    assert s["code_reached@1"] == round(3 / 6, 4)  # + c3
    assert s["code_reached@2"] == round(3 / 6, 4)
    assert s["code_reached@3"] == round(4 / 6, 4)  # + c4
    assert s["questions_mean"] == 1.0              # (0 + 0 + 1 + 3) / 4
    assert s["dialog_support"] == "supported"
    assert s["dialog_wrong_final"] == 1            # c5: диалог закончился кодом не из эталона
    by_id = {r["id"]: r for r in rows}
    assert by_id["c3"]["reached_at"] == 1 and by_id["c5"]["reached_at"] is None


def test_dialog_called_once_with_gold_and_max_k():
    ad = FakeAdapter(ANSWERS, DIALOGS)
    summary(ad, ks=(1, 2, 3))
    called = {t: (g, k) for t, g, k in ad.dialog_calls}
    # диалог не вызывается, если код уже выдан верно, и для пустого эталона
    assert set(called) == {"c2", "c3", "c4", "c5"}
    assert called["c3"] == (frozenset({"A", "B"}), 3)


def test_required_hit_no_code_premature():
    _, s = summary(FakeAdapter(ANSWERS, DIALOGS))
    assert s["required_cases"] == 2 and s["required_hit"] == 0.5
    assert s["no_code_cases"] == 2 and s["no_code_respected"] == 0.5
    assert s["premature_auto"] == round(1 / 3, 4)  # c3, c5, c8 — автокод только в c8


def test_dialog_not_supported_means_at_k_equals_at_0():
    _, s = summary(FakeAdapter(ANSWERS, DIALOGS, with_dialog=False))
    assert s["dialog_support"] == "not_supported"
    for k in (1, 2, 3):
        assert s[f"code_reached@{k}"] == s["code_reached@0"]


def test_trivial_baselines_show_floor():
    for cls in mt.BASELINES:
        _, s = summary(cls())
        assert s["auto"] == 0 and s["wrong_auto"] == 0
        assert s["auto_precision"] is None and s["auto_coverage"] == 0
        assert s["code_reached@0"] == 0 and s["code_reached@3"] == 0
        assert s["required_hit"] == 0
        assert s["no_code_respected"] == 1.0       # «всегда уточнение» тривиально соблюдает no_code
        assert s["dialog_support"] == "not_supported"


def test_predict_error_is_not_a_code():
    ans = dict(ANSWERS, c7="boom")
    rows, s = summary(FakeAdapter(ans, DIALOGS))
    r = next(r for r in rows if r["id"] == "c7")
    assert r["status"] == "error" and not r["matched"] and r["error"].startswith("RuntimeError")
    assert s["errors"] == 1


def test_proportion_ci_rule_of_three_and_bootstrap():
    ci = mt.proportion_ci([True] * 100)
    assert ci["value"] == 1.0 and ci["lo"] == 0.97 and ci["hi"] == 1.0 and ci["method"] == "rule_of_three"
    ci = mt.proportion_ci([False] * 60)
    assert ci["value"] == 0.0 and ci["hi"] == 0.05 and ci["lo"] == 0.0
    assert mt.proportion_ci([]) is None
    xs = [True] * 100 + [False] * 100
    a, b = mt.proportion_ci(xs, 1000, 1), mt.proportion_ci(xs, 1000, 1)
    assert a == b                                  # фиксированный seed — воспроизводимо
    assert a["method"] == "bootstrap" and a["lo"] < 0.5 < a["hi"]
    assert 0.41 <= a["lo"] <= 0.46 and 0.54 <= a["hi"] <= 0.59   # ≈ 0.5 ± 1.96·√(0.25/200)


def test_summary_ci_blocks():
    _, s = summary(FakeAdapter(ANSWERS, DIALOGS))
    assert set(s["ci95"]) == {"code_reached@2", "auto_precision", "no_code_respected"}
    assert s["ci95"]["auto_precision"]["n"] == 4
    # 0 ошибочных автокодов из 10 → нижняя граница точности 1 − 3/10
    cases = [case(f"k{i}", "code_required", ["A"]) for i in range(10)]
    ad = FakeAdapter({f"k{i}": ("matched", "A") for i in range(10)})
    _, s = summary(ad, cases)
    assert s["auto_precision"] == 1.0 and s["ci95"]["auto_precision"]["lo"] == 0.7
    assert s["wrong_auto_rate_upper95"] == 0.3


def test_runner_report_and_markdown(tmp_path):
    from benchmark.independent import run
    rep = run.evaluate([FakeAdapter(ANSWERS, DIALOGS), mt.AlwaysClarify()], {"toy": CASES}, (1, 2, 3), True, 1000,
                       hide_test=True)
    toy = rep["fake"]["suites"]["toy"]
    assert {r["id"] for r in toy["cases"]} == {"c1", "c2", "c3", "c5", "c6", "c8"}   # test-строки скрыты
    assert toy["by_split"]["test"]["cases"] == 2                                     # агрегаты по test есть
    md = run.to_markdown({"meta": {"generated_at": "t", "split": "all", "ks": [1, 2, 3], "bootstrap": 1000,
                                   "frozen": {}}, "adapters": rep})
    assert "| fake |" in md and "baseline:always_clarify" in md


# ---------------------------------------------------------------- собственный эталон
def test_interval_bounds():
    iv = Interval(Decimal("160"), True, Decimal("180"), False)
    assert iv.contains(Decimal("160")) and iv.contains(Decimal("179.9"))
    assert not iv.contains(Decimal("180")) and not iv.contains(Decimal("159.99"))
    assert Interval(Decimal("180"), True, None, False).intersects(Interval(None, False, Decimal("180"), True))
    assert not Interval(Decimal("180"), False, None, False).intersects(Interval(None, False, Decimal("180"), True))


def _num(value, unit_key, op="="):
    return {"property": "x", "kind": "number", "value": value, "unit": None, "unit_key": unit_key, "op": op}


def test_units_and_dimensions():
    mm = Value("range", unit_key="mm", has_okei=True, interval=Interval(Decimal("160"), True, Decimal("180"), False))
    assert value_compatible(_num("17", "cm"), mm)
    assert value_compatible(_num("0.16", "m"), mm)              # граница включена
    assert not value_compatible(_num("18", "cm"), mm)           # граница исключена
    assert not value_compatible(_num("170", "kg"), mm)          # другая величина
    w = Value("range", unit_key="W", has_okei=True, interval=Interval(Decimal("500"), True, Decimal("600"), False))
    assert value_compatible(_num("0.55", "kW"), w)
    assert not value_compatible(_num("550", "V"), w)            # В ≠ Вт
    assert value_compatible(_num("550", None), w)               # без единицы — в единице каталога
    assert value_compatible(_num("600", "W", ">="), Value("range", unit_key="W", has_okei=True,
                                                          interval=Interval(Decimal("599"), True, None, False)))
    assert convert(Decimal("1"), "kW", "W") == Decimal("1000") and convert(Decimal("1"), "V", "W") is None


def test_text_values():
    ch = Char("Вид", 1, True, 1, [Value("quality", text="Рыбацкие"), Value("quality", text="Зелёный")])
    t = lambda v: {"property": "Вид", "kind": "text", "value": v, "unit": None, "unit_key": None, "op": "="}  # noqa: E731
    assert char_compatible(t("рыбацкие"), ch) and char_compatible(t("зеленый "), ch)
    assert not char_compatible(t("угловые"), ch)
    assert norm_text("  Да. ") == "да"


@pytest.mark.skipif(not (ROOT / "data" / "ktru.sqlite").exists(), reason="нет data/ktru.sqlite")
def test_suites_gold_matches_catalog_and_manifest():
    """Эталон в файлах наборов совпадает с пересчётом по базе; test-часть совпадает с манифестом."""
    from benchmark.independent.generate import MANIFEST, SUITES, test_hash
    from benchmark.independent.reference import Catalog
    cat = Catalog()
    frozen = {l.split()[1]: l.split()[0] for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()}
    for f in sorted(SUITES.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            gold, expect = cat.expect(c.get("name"), c["facts"])
            assert (gold, expect) == (c["gold_codes"], c["expect"]), c["id"]
            assert c["acceptable_codes"] == c["gold_codes"]
        assert frozen.get(f.name) == test_hash(f)[0], f.name
