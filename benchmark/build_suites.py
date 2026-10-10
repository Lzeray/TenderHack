"""Сборка наборов benchmark/suites/*.jsonl из размеченных кейсов eval/.

  python -m benchmark.build_suites            # manual_dev, manual_holdout (+ synthetic, если есть eval/synthetic.jsonl)

Поведенческий набор (behaviour.jsonl) ведётся вручную и этим скриптом не перезаписывается.
Кейсы отложенного набора копируются без изменений текста и эталона.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "suites"
STATUS = {"matched": "matched", "clarification_needed": "clarification", "conflict": "conflict",
          "not_found": "not_found", "manual_choice": "manual_choice"}


def convert(c: dict, suite: str, split: str | None) -> dict:
    exp = [STATUS[s] for s in c.get("expected_status", [])]
    acc = c.get("acceptable_codes") or ([c["expected_code"]] if c.get("expected_code") else [])
    if c.get("must_not_auto") or (exp and "matched" not in exp):
        auto = "forbidden"
    elif exp == ["matched"]:
        auto = "required"
    else:
        auto = "allowed"
    return {"id": c["id"], "suite": suite, "split": c.get("split", split), "source": c.get("source", "manual"),
            "category": c.get("category"), "text": c["text"], "acceptable_codes": acc, "auto": auto,
            "expected_status": exp, "forbidden_codes": [], "checks": [],
            "verified": c.get("verified", "")}


def write(name: str, cases: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases),
                                       encoding="utf-8")
    print(name, len(cases))


def read(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    write("manual_dev", [convert(c, "manual_dev", "dev") for c in read(ROOT / "eval" / "cases.jsonl")])
    write("manual_holdout", [convert(c, "manual_holdout", "test") for c in read(ROOT / "eval" / "holdout.jsonl")])
    syn = ROOT / "eval" / "synthetic.jsonl"
    if syn.exists():
        write("synthetic", [convert(c, "synthetic", None) for c in read(syn)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
