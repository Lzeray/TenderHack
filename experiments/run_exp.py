"""Прогон наборов с аблациями ядра (без изменения кода ядра — подменой атрибутов в процессе).

python -m experiments.run_exp --ablate none --out reports/exp/none.json
python -m experiments.run_exp --ablate typos,value_alias --out reports/exp/x.json

Аблации:
  type_alias   без data/aliases.json
  value_alias  без data/value_aliases.json
  components   без data/components.json (части товара)
  plaus        без правил правдоподобия
  typos        без исправления опечаток
  fuzzy        fuzzy_equal → точное совпадение лемм
Метрики: метрики benchmark/run.py по наборам + по стресс-набору разбивка по вариантам
и точность извлечения эталонных признаков (feature_recall / feature_wrong).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.run import run_suite  # noqa: E402

SUITE_DIRS = [ROOT / "benchmark" / "suites", ROOT / "experiments" / "suites"]


def load(name: str) -> list[dict]:
    for d in SUITE_DIRS:
        p = d / f"{name}.jsonl"
        if p.exists():
            return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    raise FileNotFoundError(name)


def apply_ablations(adapter, names: set[str]) -> None:
    eng = adapter.engine
    import ktru_assist.engine as engine_mod
    import ktru_assist.nlp.extract as ex
    import ktru_assist.text as text
    import ktru_assist.components as comp
    if "type_alias" in names:
        eng.registry.aliases = []
        eng.aliases = {} if hasattr(eng, "aliases") else None
    if "value_alias" in names:
        ex.value_aliases = lambda: ()
    if "components" in names:
        comp.lexicon.cache_clear()
        comp.component_of_lemma.cache_clear()
        comp.property_component.cache_clear()
        comp.canonical_key.cache_clear()
        comp.lexicon = lambda: {}
    if "plaus" in names:
        engine_mod.plausibility_check = lambda features, categories: []
    if "typos" in names:
        eng.typos.correct = lambda tokens, choices: []
    if "fuzzy" in names:
        exact = lambda a, b: a == b  # noqa: E731
        for mod in (text, ex, engine_mod):
            if hasattr(mod, "fuzzy_equal"):
                setattr(mod, "fuzzy_equal", exact)
        import ktru_assist.registry as reg
        import ktru_assist.rank as rank
        reg.fuzzy_equal = exact
        rank.fuzzy_equal = exact


def feature_metrics(rows, cases, adapter) -> dict:
    """Для кейсов с эталонными признаками: найден ли признак (свойство и значение совпали)."""
    by_id = {c["id"]: c for c in cases}
    found = wrong = total = 0
    for r in rows:
        c = by_id[r["id"]]
        gt = c.get("gt") or []
        if not gt:
            continue
        feats = r.get("_features") or []
        for g in gt:
            total += 1
            same_prop = [f for f in feats if (f.get("property") or "").lower() == g["property"].lower()]
            if any((f.get("value") or "").lower() == g["value"].lower() for f in same_prop):
                found += 1
            elif same_prop:
                wrong += 1
    return {"gt_features": total, "feature_recall": round(found / total, 3) if total else None,
            "feature_wrong": wrong}


class Recording:
    """Обёртка адаптера: запоминает признаки последнего ответа для метрик извлечения."""

    def __init__(self, a):
        self.a, self.last = a, {}

    def predict(self, text):
        p = self.a.predict(text)
        self.last[text] = p.get("features")
        return p

    def dialog(self, *args, **kw):
        return self.a.dialog(*args, **kw)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablate", default="none")
    ap.add_argument("--suites", nargs="+", default=["behaviour", "manual_dev", "manual_holdout", "synthetic", "stress"])
    ap.add_argument("--dialog", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    from benchmark.adapters.ktru import KtruInProcess
    t0 = time.perf_counter()
    base = KtruInProcess("core")
    abl = {a for a in args.ablate.split(",") if a and a != "none"}
    apply_ablations(base, abl)
    adapter = Recording(base)
    report = {"ablate": sorted(abl), "init_s": round(time.perf_counter() - t0, 2), "suites": {}}
    for name in args.suites:
        cases = load(name)
        summary, rows = run_suite(adapter, cases, args.dialog, 1)
        for r in rows:
            r["_features"] = adapter.last.get(r["text"])
        summary.update(feature_metrics(rows, cases, adapter))
        if any("variant" in c for c in cases):
            var = {}
            by_id = {c["id"]: c for c in cases}
            for r in rows:
                v = by_id[r["id"]]["variant"]
                d = var.setdefault(v, {"n": 0, "pass": 0, "auto_correct": 0, "auto_incorrect": 0, "recall": 0,
                                       "not_found": 0})
                d["n"] += 1
                d["pass"] += r["pass"]
                d["auto_incorrect"] += r["auto_incorrect"]
                d["auto_correct"] += r["status"] == "matched" and not r["auto_incorrect"]
                d["recall"] += bool(r["compatible_recall"])
                d["not_found"] += r["status"] == "not_found"
            for v, d in var.items():
                fm = feature_metrics([r for r in rows if by_id[r["id"]]["variant"] == v], cases, adapter)
                d.update(fm)
            summary["by_variant"] = var
        for r in rows:
            r.pop("_features", None)
        report["suites"][name] = {"summary": summary, "cases": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    keys = ["cases", "pass_rate", "auto_correct", "auto_incorrect", "forbidden_auto_violations",
            "compatible_recall", "feature_recall", "feature_wrong"]
    print("ablate:", sorted(abl) or "none")
    for name, s in report["suites"].items():
        print(f"  {name:15}", " ".join(f"{k}={s['summary'].get(k)}" for k in keys))
        for v, d in sorted((s["summary"].get("by_variant") or {}).items()):
            print(f"      {v:9} n={d['n']} pass={d['pass']} auto+={d['auto_correct']} auto-={d['auto_incorrect']} "
                  f"recall={d['recall']} nf={d['not_found']} feat={d['feature_recall']} wrong={d['feature_wrong']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
