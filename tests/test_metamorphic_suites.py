"""Метаморфные и состязательные наборы (benchmark/metamorphic): целостность, эталон, заморозка, метрики.

Систему (ktru_assist) и базу эти тесты не используют: эталон проверяется против исходных кейсов
benchmark/independent/suites/natural.jsonl, метрики — на подставных решениях.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from benchmark.adapters.base import Adapter
from benchmark.independent import metrics as mt
from benchmark.independent.reference import convert
from benchmark.independent.run import frozen_status
from benchmark.metamorphic import generate as gen
from benchmark.run import run_suite

ROOT = Path(__file__).resolve().parent.parent
SUITES = {n: [json.loads(l) for l in (gen.SUITES / f"{n}.jsonl").read_text(encoding="utf-8").splitlines()
              if l.strip()] for n in gen.SUITE_NAMES}
NATURAL = {c["id"]: c for c in gen.load("natural")}
ALL = [c for cs in SUITES.values() for c in cs]
EXPECT = {"code_required": ("required", ["matched"])}


def test_files_match_generator_and_manifest():
    built = gen.build()
    for n in gen.SUITE_NAMES:
        assert [gen.dump_line(c) for c in built[n]] == [gen.dump_line(c) for c in SUITES[n]], n
    status = frozen_status([str(gen.SUITES / f"{n}.jsonl") for n in gen.SUITE_NAMES])
    assert all(s["ok"] for s in status.values()), status


def test_generation_independent_of_hash_seed(tmp_path):
    code = ("import json,sys; from benchmark.metamorphic.generate import build; "
            "json.dump(build(), open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)")
    outs = []
    for seed in ("1", "2"):
        out = tmp_path / f"b{seed}.json"
        subprocess.run([sys.executable, "-c", code, str(out)], cwd=ROOT, check=True,
                       env={**os.environ, "PYTHONHASHSEED": seed})
        outs.append(out.read_text(encoding="utf-8"))
    assert outs[0] == outs[1]


def test_case_format_and_gold_consistency():
    ids = [c["id"] for c in ALL]
    assert len(ids) == len(set(ids))
    for c in ALL:
        gold = set(c["gold_codes"])
        assert c["split"] in ("dev", "test") and isinstance(c["text"], str)
        assert set(c["acceptable_codes"]) == gold
        assert not gold & set(c["forbidden_codes"]), c["id"]
        assert (c["expect"] == "no_code") == (not gold), c["id"]
        if c["expect"] == "no_code":
            assert c["auto"] == "forbidden" and "matched" not in c["expected_status"]
        if c["expect"] == "code_required":
            assert (c["auto"], c["expected_status"]) == EXPECT["code_required"]


@pytest.mark.parametrize("suite", ["invariance", "injection", "procurement_noise", "monotonicity"])
def test_derived_cases_inherit_source_gold_and_split(suite):
    for c in SUITES[suite]:
        src = NATURAL[c["source_id"]]
        assert "typo" not in src["variant"]
        assert c["split"] == src["split"], c["id"]                  # test-тексты не попадают в dev
        assert c["gold_codes"] == src["gold_codes"] and c["expect"] == src["expect"]
        if suite != "monotonicity":
            assert c["checks"] == [{"type": "same_as", "text": src["text"]}]
            assert c["text"] != src["text"]


def test_invariance_unit_equiv_is_exact():
    cases = [c for c in SUITES["invariance"] if c["variant"] == "unit_equiv"]
    assert cases
    for c in cases:
        src = NATURAL[c["source_id"]]
        changed = [(a, b) for a, b in zip(src["facts"], c["facts"]) if a != b]
        assert len(changed) == 1 and len(src["facts"]) == len(c["facts"])
        a, b = changed[0]
        assert a["property"] == b["property"] and a["op"] == b["op"]
        assert convert(Decimal(a["value"]), a["unit_key"], b["unit_key"]) == Decimal(b["value"])


def test_invariance_upper_has_no_numeric_facts():
    for c in SUITES["invariance"]:
        if c["variant"] == "upper":
            assert not any(f["kind"] == "number" for f in c["facts"])


def test_injection_code_is_wrong_and_forbidden():
    for c in SUITES["injection"]:
        x = c["injected_code"]
        assert x in c["text"] and x in c["forbidden_codes"] and x not in c["gold_codes"]


def test_multi_item_pairs_same_split_different_items():
    for c in SUITES["multi_item"]:
        a, b = (NATURAL[i] for i in c["source_ids"])
        assert a["split"] == b["split"] == c["split"]
        assert a["name"] != b["name"]
        assert set(c["forbidden_codes"]) == set(a["gold_codes"]) | set(b["gold_codes"])


def test_monotonicity_reference_is_monotone():
    for c in SUITES["monotonicity"]:
        bare = NATURAL[c["bare_id"]]
        assert bare["facts"] == [] and bare["name"] == c["name"] and bare["split"] == c["split"]
        assert c["checks"] == [{"type": "subset_of", "text": bare["text"]}]
        assert set(c["gold_codes"]) <= set(bare["gold_codes"])


def test_edge_inputs_have_no_gold():
    for c in SUITES["edge_inputs"]:
        assert c["gold_codes"] == [] and c["expect"] == "no_code"
    assert {c["variant"] for c in SUITES["edge_inputs"]} >= {"empty", "too_broad", "code_only", "markup"}


# ---------------------------------------------------------------- метрики на подставных решениях
def _answers():
    """Ответ «оракула» по эталону: исходные тексты и производные тексты получают одинаковый ответ."""
    table = {}
    for c in list(NATURAL.values()) + ALL:
        gold = c["gold_codes"]
        if c["expect"] == "code_required":
            table[c["text"]] = ("matched", gold[0], gold)
        else:
            table[c["text"]] = ("clarification", None, gold)
    return table


class Oracle(Adapter):
    name = "oracle"

    def __init__(self, obey_injection: bool = False):
        self.table = _answers()
        self.obey = obey_injection
        self.inj = {c["text"]: c["injected_code"] for c in SUITES["injection"]}

    def predict(self, text):
        st, code, comp = self.table[text]
        if self.obey and text in self.inj:
            st, code = "matched", self.inj[text]
        return {"status": st, "final_code": code, "compatible_codes": list(comp), "features": [],
                "warnings": [] if st != "clarification" else ["нужно уточнение"]}


@pytest.mark.parametrize("suite", gen.SUITE_NAMES)
def test_oracle_passes_every_suite(suite):
    s, rows = run_suite(Oracle(), SUITES[suite], dialog=False, repeat=1)
    assert s["pass_rate"] == 1.0 and s["auto_incorrect"] == 0, [r for r in rows if not r["pass"]][:3]
    assert all(v["fail"] == 0 for v in s["checks_by_type"].values())


def test_obeying_injection_is_caught_by_both_metric_sets():
    cases = SUITES["injection"]
    s, _ = run_suite(Oracle(obey_injection=True), cases, dialog=False, repeat=1)
    assert s["pass_rate"] == 0.0 and s["forbidden_code_hits"] == len(cases)
    assert s["auto_incorrect"] == len(cases) and s["checks_by_type"]["same_as"]["fail"] == len(cases)
    v2 = mt.summarize(mt.run_suite(Oracle(obey_injection=True), cases, use_dialog=False), mt.KS, 1000)
    assert v2["wrong_auto"] == len(cases)


def test_trivial_baselines_floor_on_new_suites():
    """Пол метрик: «всегда уточнение» не ошибается, но и не получает код — по одной метрике решение не судят."""
    for suite in ("invariance", "multi_item", "edge_inputs"):
        s = mt.summarize(mt.run_suite(mt.AlwaysClarify(), SUITES[suite], use_dialog=False), mt.KS, 1000)
        assert s["wrong_auto"] == 0
        if suite == "invariance":
            assert s["required_hit"] == 0
        else:
            assert s["no_code_respected"] == 1.0


# ---------------------------------------------------------------- слитные слова и ленивый пользователь
def test_glued_words_only_remove_spaces():
    for c in SUITES["glued_words"]:
        src = NATURAL[c["source_id"]]["text"]
        k = int(c["variant"][-1])
        assert c["text"].replace(" ", "") == src.replace(" ", "")
        assert src.count(" ") - c["text"].count(" ") == k - 1
    assert {c["variant"] for c in SUITES["glued_words"]} == {"glue2", "glue3"}


def test_lazy_user_keeps_numbers_and_ops():
    by = {}
    for c in SUITES["lazy_user"]:
        by.setdefault(c["variant"], []).append(c)
        src = NATURAL[c["source_id"]]
        assert c["gold_codes"] == src["gold_codes"] and c["split"] == src["split"]
        assert [(f["property"], f["value"], f["op"]) for f in c["facts"]] == \
            [(f["property"], f["value"], f["op"]) for f in src["facts"]]
    assert set(by) == {"no_unit", "lower_no_punct", "ineq_symbol", "ineq_words", "ineq_no_unit", "telegraph"}
    for v in ("no_unit", "ineq_no_unit", "telegraph"):
        for c in by[v]:
            # число без единицы допустимо, только если исходный кейс писал его в единице каталога
            assert "unit_conversion" not in NATURAL[c["source_id"]]["variant"]
    for c in by["no_unit"] + by["telegraph"]:
        assert all(f["unit"] is None for f in c["facts"] if f["kind"] == "number")
    for c in by["telegraph"]:
        assert (c["expect"], c["auto"], c["checks"]) == ("code_after_questions", "allowed", [])
    for c in by["ineq_symbol"] + by["ineq_words"] + by["ineq_no_unit"]:
        assert any(f["op"] in (">=", "<=") for f in c["facts"]) and c["checks"][0]["type"] == "same_as"
    for c in by["lower_no_punct"]:
        assert not set(":;()«»!?") & set(c["text"])


# ---------------------------------------------------------------- ленивые числа по каталогу (синтетический каталог)
from benchmark.metamorphic import lazy_numbers as ln  # noqa: E402

FIX_PATH = ln.OUT_FIXTURE
FIX = [json.loads(l) for l in FIX_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def _fx(name_part: str, variant: str) -> dict:
    return next(c for c in FIX if name_part in c["name"] and c["variant"] == variant)


def test_lazy_numbers_fixture_matches_generator_and_manifest():
    assert [json.dumps(c, ensure_ascii=False) for c in ln.build_fixture()] == \
        [json.dumps(c, ensure_ascii=False) for c in FIX]
    assert frozen_status([str(FIX_PATH)])[FIX_PATH.stem]["ok"]


def test_lazy_numbers_reference_semantics():
    """Смысл ленивых записей на синтетическом каталоге — проверено вручную по fixture_catalog.py."""
    d = "31.01.10.000-9500000"            # стол: металлический 600–1000, 1000–1400, 1400–1800 (вкл.)
    assert _fx("Стол", "gt_lt")["gold_codes"] == [d + "2"]                        # 1000 < x < 1400
    assert _fx("Стол", "ge_le")["gold_codes"] == [d + "2", d + "3"]               # 1400 входит в [1400; 1800]
    assert _fx("Стол", "dash_range")["gold_codes"] == _fx("Стол", "ge_le")["gold_codes"]
    assert _fx("Стол", "gt_max")["expect"] == "no_code"                           # больше 1800 — нет
    assert _fx("Стол", "lt_min")["expect"] == "no_code"                           # меньше 600 — нет
    assert _fx("Стол", "point_no_unit")["gold_codes"] == _fx("Стол", "point_unit")["gold_codes"]
    assert _fx("Шуруповерт", "gt_max")["gold_codes"] == ["28.24.11.000-95000023"]  # открытый верх ≥ 800
    assert _fx("Халат", "gap")["expect"] == "no_code"                             # между 164 и 170 позиций нет
    assert all(c["expect"] == "no_code" for c in FIX if c["variant"] == "inverted")
    assert _fx("Пила", "lt_min")["gold_codes"] == ["25.73.30.110-95000011"]       # < 300
    # без свойства — только там, где числовая характеристика у семейства одна (у пилы их две)
    assert not [c for c in FIX if c["variant"] == "no_property" and "Пила" in c["name"]]


def test_lazy_numbers_same_as_pairs_have_equal_gold():
    texts = {c["text"]: c for c in FIX}
    for c in FIX:
        for chk in c["checks"]:
            assert texts[chk["text"]]["gold_codes"] == c["gold_codes"], c["id"]


# ---------------------------------------------------------------- пересчёт эталона по реальной базе (если она есть)
REAL_DB = ROOT / "data" / "ktru.sqlite"


@pytest.mark.skipif(not REAL_DB.exists(), reason="нет data/ktru.sqlite")
def test_gold_recomputed_on_real_catalog():
    from benchmark.independent.reference import Catalog
    cat = Catalog(REAL_DB)
    bad = []
    for n in ("invariance", "injection", "procurement_noise", "monotonicity", "glued_words", "lazy_user"):
        for c in SUITES[n]:
            if cat.gold(c["name"], c["facts"]) != c["gold_codes"]:
                bad.append(c["id"])
    real = ln.OUT_REAL
    if real.exists():
        for l in real.read_text(encoding="utf-8").splitlines():
            c = json.loads(l)
            if list(ln.gold_expect(cat, c["name"], c["facts"])) != [c["gold_codes"], c["expect"]]:
                bad.append(c["id"])
    assert not bad, bad[:20]


# ---------------------------------------------------------------- человеческие опечатки и ошибки в числах
from benchmark.metamorphic import typos as ty  # noqa: E402

VOCAB = ty.vocabulary({c["name"] for c in NATURAL.values()})


def test_typos_distances_dictionary_and_nearest():
    by = {}
    for c in SUITES["typos_human"]:
        by.setdefault(c["variant"], []).append(c)
    assert set(by) == {"short_word", "phonetic", "two_errors", "severe", "user_example", "ambiguous",
                       "out_of_scope_typo"}
    dist = {"short_word": 1, "phonetic": 1, "two_errors": 2, "severe": 3}
    for v, d in dist.items():
        for c in by[v]:
            t = c["typo"]
            assert ty.dl(t["typo"], t["word"]) == d == t["distance"], c["id"]
            assert not ty.known(t["typo"]) and ty.unique_nearest(t["typo"], t["word"], VOCAB)
            src = NATURAL[c["source_id"]]
            assert c["text"].lower().replace(t["typo"], t["word"], 1) == src["text"].lower()
    for c in by["short_word"]:
        assert len(c["typo"]["word"]) <= 4
    for c in by["phonetic"]:
        w, t = c["typo"]["word"], c["typo"]["typo"]
        i = next(i for i, (a, b) in enumerate(zip(w, t)) if a != b)
        assert ty.PHON[w[i]] == t[i]                                 # ошибка «как слышится»


def test_typos_expectations_by_severity():
    for c in SUITES["typos_human"]:
        v = c["variant"]
        if v in ("short_word", "phonetic") or (v == "user_example" and "source_id" in c):    # 1 ошибка, «стур»
            assert c["checks"][0]["type"] == "same_as" and c["expect"] == NATURAL[c["source_id"]]["expect"]
        elif v == "two_errors":
            assert (c["auto"], c["checks"]) == ("allowed", []) and c["gold_codes"]
        else:                                                      # 3+ ошибки, неоднозначные, вне области
            assert c["auto"] == "forbidden" and "matched" not in c["expected_status"]
    amb = [c for c in SUITES["typos_human"] if c["variant"] == "ambiguous"]
    assert amb
    for c in amb:
        w1, w2 = c["typo"]["word"].split(" | ")
        assert ty.dl(c["text"], w1) == ty.dl(c["text"], w2) == 1 and "matched" not in c["expected_status"]


def test_typos_user_examples_present():
    texts = [c["text"] for c in SUITES["typos_human"]]
    assert any("стур" in t for t in texts) and "одфертуа" in texts and "колоши резиновые" in texts


def test_number_errors_need_clarification():
    by = {}
    for c in SUITES["number_errors"]:
        by.setdefault(c["variant"], []).append(c)
        src = NATURAL[c["source_id"]]
        n = c["number"]
        assert c["auto"] == "forbidden" and "matched" not in c["expected_status"]
        assert "not_found" not in c["expected_status"]              # нужен вопрос, а не «не найдено»
        assert c["gold_codes"] == src["gold_codes"]                 # после уточнения — код исходного кейса
        assert c["checks"][0]["type"] == "no_feature"               # значение не принято молча
        assert n["written"] in c["text"] and n["written"] != n["intended"]
    assert set(by) == {"leading_zero", "letter_in_number", "double_separator", "bad_grouping"}
    for c in by["leading_zero"]:
        w = c["number"]["written"]
        assert w[0] == "0" and w[1:].isdigit() and w[1:] == c["number"]["intended"]
