"""Шаблон ручной разметки: 300 случайных карточек портала (по 100 на категорию).

  python -m benchmark.independent.make_labeling
  → benchmark/local_suites/labeling_template.csv (папка в .gitignore: это данные организаторов)

Колонки: id, category, text, gold_code, alternatives, expect, comment (последние четыре заполняет команда).
text = наименование карточки + 2 характеристики карточки без мусора: без «(не задано)», ссылок,
нулевых заглушек «0.00000» и хвостов «.00000». Выбор карточек и характеристик детерминирован (SEED).
Инструкция по разметке — benchmark/independent/README.md, раздел «Ручная разметка».
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ktru_assist.portal import xlsx  # noqa: E402 — разрешённый модуль: только чтение xlsx

SEED = 20261010
FILES = {"clothes": "Одежда.xlsx", "furniture": "Мебель.xlsx", "tools": "Инструменты.xlsx"}
SRC = ROOT / "Примеры выгрузок"
OUT = ROOT / "benchmark" / "local_suites" / "labeling_template.csv"
COLUMNS = ["id", "category", "text", "gold_code", "alternatives", "expect", "comment"]

JUNK = re.compile(r"\(не задано\)|https?://|www\.|\.ru\b|\.com\b", re.I)
ZERO = re.compile(r"(?<![\d.,])0\.0+(?![\d])")                 # заглушка «0.00000»
TRAIL = re.compile(r"(?<![\d.])(\d+)\.(\d{5})(?![\d.])")      # формат портала: 5 знаков после точки
PACKAGING = re.compile(r"упаковк", re.I)


def clean_number_tails(s: str) -> str:
    """«2.03000» → «2.03», «780.00000» → «780»."""
    def rep(m):
        frac = m.group(2).rstrip("0")
        return m.group(1) + ("." + frac if frac else "")
    return TRAIL.sub(rep, s)


def clean_chars(raw: str | None) -> list[str]:
    out = []
    for part in (raw or "").split("|"):
        p = re.sub(r"\s+", " ", part).strip()
        if not p or JUNK.search(p) or ZERO.search(p):
            continue
        p = clean_number_tails(p)
        if len(p) > 120:
            continue
        out.append(p)
    return out


def sample_cards(path: Path, k: int, rng: random.Random) -> list[list[str | None]]:
    """Равномерная выборка k строк (резервуарная), заголовок пропускается."""
    res: list[list[str | None]] = []
    n = 0
    for i, row in enumerate(xlsx.rows(path)):
        if i == 0:
            continue
        if not row or len(row) < 2 or not (row[1] or "").strip():
            continue
        n += 1
        if len(res) < k:
            res.append(row)
        else:
            j = rng.randrange(n)
            if j < k:
                res[j] = row
    return res


def card_text(row, rng: random.Random) -> str:
    name = re.sub(r"\s+", " ", (row[1] or "")).strip().strip(",")
    chars = clean_chars(row[5] if len(row) > 5 else None)
    main = [c for c in chars if not PACKAGING.search(c)]
    pool = main if len(main) >= 2 else chars
    picked = sorted(rng.sample(range(len(pool)), min(2, len(pool))))
    return ", ".join([name] + [pool[i] for i in picked])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-category", type=int, default=100)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    rows_out = []
    for cat, fname in FILES.items():
        rng = random.Random(f"{SEED}|{cat}")
        cards = sample_cards(SRC / fname, a.per_category, rng)
        cards.sort(key=lambda r: str(r[0]))
        for r in cards:
            rows_out.append({"id": r[0], "category": cat, "text": card_text(r, rng),
                             "gold_code": "", "alternatives": "", "expect": "", "comment": ""})
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows_out)
    print(f"{len(rows_out)} карточек → {out}")


if __name__ == "__main__":
    main()
