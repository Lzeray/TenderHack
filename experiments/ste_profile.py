"""Профиль выгрузок СТЕ до построения статистики (шаг 3 плана трёхуровневой проверки).

Потоком читает XLSX (разбор — ktru_assist.catalog.ste_importer), большую базу не строит.
python -m experiments.ste_profile --src "Примеры выгрузок" --out reports/exp/ste_profile.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.catalog.ste_importer import MISSING, VALUE_START, key, xlsx_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "Примеры выгрузок"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = {}
    for path in sorted(Path(args.src).glob("*.xlsx")):
        c = collections.Counter()
        models = collections.Counter()
        manufacturers = collections.Counter()
        prop_names = collections.Counter()
        heads = collections.Counter()
        kpgz = set()
        kpgz_props = 0
        sheet_kind = {}
        for sheet, row, cells in xlsx_rows(path):
            if sheet not in sheet_kind:
                sheet_kind[sheet] = "reference" if cells.get("A", "").startswith("Конечная категория") else "products"
                continue
            if sheet_kind[sheet] == "reference":
                if cells.get("B"):
                    kpgz.add(cells["B"])
                kpgz_props += 1
                continue
            if not any(cells.values()):
                continue
            c["products"] += 1
            name, model, man = cells.get("B", ""), key(cells.get("C", "")), key(cells.get("D", ""))
            c["model_empty"] += key(model) in MISSING
            c["manufacturer_empty"] += key(man) in MISSING
            if key(model) not in MISSING:
                models[(man, model)] += 1
            if key(man) not in MISSING:
                manufacturers[man] += 1
            w = key(name).split()
            if w:
                heads[w[0]] += 1
            segs = [s.strip() for s in cells.get("F", "").split("|") if s.strip()]
            c["segments"] += len(segs)
            c["no_characteristics"] += not segs
            for s in segs:
                m = VALUE_START.search(s)
                if m:
                    prop_names[key(s[:m.start()])] += 1
                    v = s[m.end():].strip()
                    if v.startswith("0.00000") or v == "0" or v.startswith("0 "):
                        c["zero_segments"] += 1
                    if "не задано" in v:
                        c["missing_segments"] += 1
        multi = sum(1 for n in models.values() if n > 1)
        out[path.stem] = {
            **c,
            "model_empty_share": round(c["model_empty"] / c["products"], 3),
            "manufacturer_empty_share": round(c["manufacturer_empty"] / c["products"], 3),
            "distinct_models": len(models),
            "models_with_several_cards": multi,
            "cards_per_model_max": max(models.values()) if models else 0,
            "distinct_manufacturers": len(manufacturers),
            "numeric_property_names": len(prop_names),
            "top_property_names": prop_names.most_common(25),
            "top_head_words": heads.most_common(40),
            "kpgz_codes": len(kpgz),
            "kpgz_property_rows": kpgz_props,
            "sheets": sheet_kind,
        }
        print(path.stem, c["products"], file=sys.stderr)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
