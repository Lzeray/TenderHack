"""Неразмеченный набор живых запросов из реальных карточек товаров портала (лист 1 выгрузок).

Кодов КТРУ в выгрузке нет, поэтому точность кода на этом наборе не считается: он показывает
поведение на живых формулировках (доля автокодов, статусы, ошибки, задержка).
Данные организаторов в git не попадают: набор пишется в benchmark/local_suites/ (в .gitignore).

  python -m benchmark.build_portal_suite --src "Примеры выгрузок" --per-category 150
  python -m benchmark.run --adapter ktru:core --suites benchmark/local_suites/portal_live.jsonl --out ...
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ktru_assist.portal.xlsx import rows  # noqa: E402

FILES = {"Одежда.xlsx": "clothes", "Мебель.xlsx": "furniture", "Инструменты.xlsx": "tools"}
NOISE = re.compile(r"\(не задано\)|http|видеообзор|производство|страна", re.IGNORECASE)


def clean(piece: str) -> str | None:
    piece = re.sub(r"(\d+)\.0+\b", r"\1", piece.strip())     # «2.03000 кг» → «2.03 кг», «450.00000» → «450»
    piece = re.sub(r"(\d+\.\d*?)0+\b", r"\1", piece)
    if not piece or NOISE.search(piece) or len(piece) > 80:
        return None
    return piece


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="Примеры выгрузок")
    ap.add_argument("--per-category", type=int, default=150)
    ap.add_argument("--chars", type=int, default=2, help="сколько характеристик карточки добавить к названию")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "local_suites" / "portal_live.jsonl"))
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    cases = []
    for fname, cat in FILES.items():
        items = [r for i, r in enumerate(rows(Path(args.src) / fname, sheet=1)) if i and len(r) > 5 and r[1]]
        for r in rnd.sample(items, min(args.per_category, len(items))):
            pieces = [p for p in (clean(x) for x in (r[5] or "").split(" | ")) if p]
            extra = rnd.sample(pieces, min(args.chars, len(pieces)))
            text = ", ".join([r[1].strip()] + extra)
            cases.append({"id": f"P-{cat}-{r[0]}", "suite": "portal_live", "split": "test", "source": "ste_export",
                          "category": cat, "text": text[:600], "acceptable_codes": [], "auto": "allowed",
                          "unlabeled": True, "expected_status": [], "forbidden_codes": [], "checks": []})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    print(f"{len(cases)} кейсов → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
