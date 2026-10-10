"""Прогон наборов с бесловарным стеммером вместо pymorphy3.

python -m experiments.morph_variant --stemmer snowball --out reports/exp/stem_snowball.json [--ablate ...]

Каталог переимпортируется в data/exp_<stemmer>.sqlite (леммы наименований и главные слова зависят от
лемматизатора), затем — тот же прогон, что experiments.run_exp.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stemmer", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ablate", default="none")
    ap.add_argument("--src", default=str(ROOT / "КТРУ" / "КТРУ xml" / "КТРУ"))
    args = ap.parse_args()
    from experiments.stemmers import install
    install(args.stemmer)
    from ktru_assist.catalog.importer import run_import
    db = ROOT / "data" / f"exp_{args.stemmer}.sqlite"
    if not db.exists():
        run_import(Path(args.src), db, dt.date(2026, 10, 9), log=lambda *_: None)
    os.environ["KTRU_DB"] = str(db)
    from experiments import run_exp
    sys.argv = ["run_exp", "--ablate", args.ablate, "--out", args.out]
    return run_exp.main()


if __name__ == "__main__":
    raise SystemExit(main())
