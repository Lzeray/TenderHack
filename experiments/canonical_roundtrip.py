"""Поиск по скрытой строке против поиска по тексту (docs/PARSE_INPUT_PLAN.md, P4).

Для каждого запроса стенда полноты (`experiments/ktru_recall.py`) и проб: ответ ядра на видимый текст и ответ на
скрытую строку «тип; ключ: значение» (`ktru_assist.canonical.process`, без решений пользователя) должны совпасть:
те же совместимые позиции, статус и привязанные характеристики.

python -m experiments.canonical_roundtrip --cases reports/exp/kr_p2.json --out reports/exp/canon_rt.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.canonical import process  # noqa: E402
from ktru_assist.models import Canonical, SearchRequest  # noqa: E402
from ktru_assist.text import norm  # noqa: E402

PROBES = ["стол деревянный столешница лдсп", "стол деревянный, столешница лдсп", "стул без мягкого сиденья",
          "пассатижи слесарные 190 мм, цвет: красный", "стол обеденный 120 на 80 на 75 см", "шуруповерт 18",
          "куртка зимняя женская размер 48-50", "молоток 500 г", "стулл деревяный", "дрель мощностью от 500 до 700 вт",
          "стол письменный высотой не менее 70 см", "брюки мужские из ткани размер 50"]


def bound(r) -> set:
    return {(norm(f.property_name or ""), f.op, norm(f.value or ""), f.value_to, f.unit)
            for f in r.features if f.status == "bound" and f.source == "text"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eng = get_engine()
    texts = [r["text"] for r in json.loads(Path(args.cases).read_text(encoding="utf-8"))["rows"]] + PROBES
    stats, diffs = collections.Counter(), []
    for t in texts:
        a = eng.search(SearchRequest(text=t))
        b = process(SearchRequest(text=t, canonical=Canonical()), eng, eng.search)
        same_codes = set(a.compatible_codes) == set(b.compatible_codes)
        same_status = a.status == b.status
        same_feats = bound(a) == bound(b)
        stats["n"] += 1
        stats["codes"] += same_codes
        stats["status"] += same_status
        stats["features"] += same_feats
        if not (same_codes and same_status and same_feats):
            diffs.append({"text": t, "canonical": b.query.get("search_text"), "status": [a.status, b.status],
                          "codes": [len(a.compatible_codes), len(b.compatible_codes)],
                          "only_text": sorted(map(str, bound(a) - bound(b))),
                          "only_canonical": sorted(map(str, bound(b) - bound(a)))})
    summary = {k: (v if k == "n" else round(v / stats["n"], 4)) for k, v in stats.items()}
    Path(args.out).write_text(json.dumps({"summary": summary, "diffs": diffs}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps({"summary": summary, "diffs": len(diffs)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
