"""Выборка реальных наименований СТЕ из «Примеры выгрузок/*.xlsx» (живые формулировки поставщиков).

Разметки «СТЕ → КТРУ» нет, поэтому это не оценка точности кода: измеряется, распознаёт ли ядро тип,
сколько признаков привязывает и какая доля значимых слов остаётся нераспознанной.
Выборка пишется в data/exp_ste_sample.jsonl (производные данные организаторов — в git не попадают).

python -m experiments.ste_sample --per-file 200
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-file", type=int, default=200)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "data" / "exp_ste_sample.jsonl"))
    args = ap.parse_args()
    import openpyxl
    rnd = random.Random(args.seed)
    rows = []
    for cat, fn in (("clothes", "Одежда"), ("furniture", "Мебель"), ("tools", "Инструменты")):
        wb = openpyxl.load_workbook(ROOT / "Примеры выгрузок" / f"{fn}.xlsx", read_only=True)
        ws = wb.worksheets[0]
        items = []
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            if i == 0 or not r or not r[1]:
                continue
            items.append({"ste_id": str(r[0]), "category": cat, "name": str(r[1]).strip(),
                          "chars": str(r[5] or "")[:600]})
        wb.close()
        rnd.shuffle(items)
        rows += items[: args.per_file]
        print(fn, len(items), file=sys.stderr)
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(len(rows), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
