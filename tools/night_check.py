"""Проверка приёмки изменения ядра (ночной цикл улучшений). Только dev-части, test — не смотрим.

  python tools/night_check.py --tag h1            # прогон и сравнение с принятым эталоном
  python tools/night_check.py --tag base --accept # записать текущее состояние как принятый эталон

Критерии (все обязательны):
  1. pytest: все тесты проходят;
  2. независимые наборы, split=dev (natural, contradictions, out_of_scope):
     wrong_auto суммарно не растёт; no_code_respected не падает; code_reached@2 (natural) не падает
     больше чем на 0,5 п.п.; required_hit не падает больше чем на 1 п.п.;
  3. наборы v1 (behaviour, manual_dev, manual_holdout, synthetic): auto_incorrect = 0 и pass_rate не ниже эталона;
  4. eval/run_eval.py: false_unique = 0.
Эталон — reports/night/accepted.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
NIGHT = ROOT / "reports" / "night"


def sh(cmd: list[str], timeout: int = 7200) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def independent(tag: str) -> dict:
    out = NIGHT / f"dev_{tag}.json"
    r = sh([PY, "-m", "benchmark.independent.run", "--adapters", "ktru:core", "--split", "dev", "--no-baselines",
            "--suites", "natural", "contradictions", "out_of_scope", "--ks", "1", "2", "--out", str(out)])
    if r.returncode:
        raise SystemExit("независимый прогон упал:\n" + r.stderr[-2000:])
    s = json.loads(out.read_text(encoding="utf-8"))["adapters"]["ktru:core"]["suites"]
    nat = s["natural"]["summary"]
    c, o = s["contradictions"]["summary"], s["out_of_scope"]["summary"]
    return {
        "wrong_auto": sum(s[k]["summary"]["wrong_auto"] for k in s),
        "wrong_natural": nat["wrong_auto"], "wrong_contr": c["wrong_auto"], "wrong_oos": o["wrong_auto"],
        "no_code_respected": round((c["no_code_respected"] * c["cases"] + o["no_code_respected"] * o["cases"])
                                   / (c["cases"] + o["cases"]), 4),
        "reached0": nat["code_reached@0"], "reached2": nat.get("code_reached@2"),
        "required_hit": nat["required_hit"], "auto_coverage": nat["auto_coverage"],
        "latency_p50": nat["latency_ms_p50"],
    }


def v1(tag: str) -> dict:
    out = NIGHT / f"v1_{tag}.json"
    r = sh([PY, "-m", "benchmark.run", "--adapter", "ktru:core", "--suites", "behaviour", "manual_dev",
            "manual_holdout", "synthetic", "--out", str(out)])
    if r.returncode:
        raise SystemExit("прогон v1 упал:\n" + r.stderr[-2000:])
    s = json.loads(out.read_text(encoding="utf-8"))["suites"]
    return {k: {"pass_rate": v["summary"]["pass_rate"], "auto_incorrect": v["summary"]["auto_incorrect"],
                "auto_correct": v["summary"]["auto_correct"]} for k, v in s.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--accept", action="store_true", help="записать как принятый эталон без сравнения")
    args = ap.parse_args()
    NIGHT.mkdir(parents=True, exist_ok=True)
    t = sh([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    tests = t.stdout.strip().splitlines()[-1] if t.stdout.strip() else t.stderr[-300:]
    ev = sh([PY, "-m", "eval.run_eval", "--repeat", "1", "--out", str(NIGHT / f"eval_{args.tag}.json")])
    false_unique = json.loads((NIGHT / f"eval_{args.tag}.json").read_text(encoding="utf-8"))["summary"]["false_unique"] \
        if ev.returncode == 0 else None
    res = {"tag": args.tag, "pytest": tests, "pytest_ok": t.returncode == 0, "eval_false_unique": false_unique,
           "independent_dev": independent(args.tag), "v1": v1(args.tag)}
    acc_path = NIGHT / "accepted.json"
    if args.accept or not acc_path.exists():
        acc_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1))
        print("ПРИНЯТО КАК ЭТАЛОН")
        return 0
    acc = json.loads(acc_path.read_text(encoding="utf-8"))
    a, b = acc["independent_dev"], res["independent_dev"]
    fails = []
    if not res["pytest_ok"]:
        fails.append("pytest: " + tests)
    if res["eval_false_unique"] != 0:
        fails.append(f"eval false_unique = {res['eval_false_unique']}")
    if b["wrong_auto"] > a["wrong_auto"]:
        fails.append(f"wrong_auto {a['wrong_auto']} → {b['wrong_auto']}")
    if b["no_code_respected"] < a["no_code_respected"]:
        fails.append(f"no_code_respected {a['no_code_respected']} → {b['no_code_respected']}")
    if a["reached2"] is not None and b["reached2"] is not None and b["reached2"] < a["reached2"] - 0.005:
        fails.append(f"reached@2 {a['reached2']} → {b['reached2']}")
    if b["required_hit"] < a["required_hit"] - 0.01:
        fails.append(f"required_hit {a['required_hit']} → {b['required_hit']}")
    for k, v in res["v1"].items():
        if v["auto_incorrect"] > 0:
            fails.append(f"v1 {k}: auto_incorrect {v['auto_incorrect']}")
        if v["pass_rate"] < acc["v1"][k]["pass_rate"]:
            fails.append(f"v1 {k}: pass_rate {acc['v1'][k]['pass_rate']} → {v['pass_rate']}")
    res["verdict"] = "ПРИНЯТЬ" if not fails else "ОТКЛОНИТЬ"
    res["fails"] = fails
    res["delta"] = {k: (a.get(k), b.get(k)) for k in b}
    (NIGHT / f"check_{args.tag}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"delta": res["delta"], "v1": res["v1"], "pytest": tests, "eval_false_unique": false_unique},
                     ensure_ascii=False, indent=1))
    print(res["verdict"], fails)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
