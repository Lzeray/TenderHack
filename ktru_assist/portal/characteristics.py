"""Характеристики портала (лист 2 выгрузок «Примеры выгрузок/*.xlsx») — второй источник после КТРУ.

Порядок источников характеристики СТЕ: сначала КТРУ, если у позиции её нет — характеристика
категории портала, если нет и там — новая. Индекс строится командой
  python -m ktru_assist.cli portal --src "Примеры выгрузок"
и пишется в data/portal_characteristics.json; в git лежит сжатая копия data/portal_characteristics.json.gz,
она распаковывается при первом обращении.

Особенность листа 2: ячейки длиннее лимита Excel разорваны, хвост значения уезжает в первую
колонку следующей строки — такие строки приклеиваются к предыдущей.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..config import ROOT, unpack_gz
from ..text import content_lemmas
from .xlsx import rows

INDEX = ROOT / "data" / "portal_characteristics.json"
FILES = {"Одежда.xlsx": "clothes", "Мебель.xlsx": "furniture", "Инструменты.xlsx": "tools"}
GENERIC = {"вид", "тип", "наличие", "характеристика"}


def build(src: Path, out: Path = INDEX) -> dict:
    index: dict[str, dict[str, dict]] = {}
    stats = {}
    for fname, cat in FILES.items():
        path = Path(src) / fname
        if not path.exists():
            continue
        chars: dict[str, dict] = {}
        prev = None
        n = 0
        for i, r in enumerate(rows(path, sheet=2)):
            if i == 0:
                continue
            if len(r) < 4 or not r[3]:
                # хвост разорванной ячейки: продолжение значения предыдущей строки
                if prev is not None and r and r[0]:
                    prev["values"][-1:] = [(prev["values"][-1] if prev["values"] else "") + r[0]]
                continue
            n += 1
            name = r[3].strip()
            e = chars.setdefault(name, {"name": name, "kind": r[4] or "", "type": r[5] if len(r) > 5 else "",
                                        "unit": (r[7] if len(r) > 7 else None) or None, "values": [],
                                        "categories": 0})
            e["categories"] += 1
            val = r[6] if len(r) > 6 else None
            if val and len(e["values"]) < 15 and val not in e["values"] and not val.startswith("[не найдено"):
                e["values"].append(val[:200])
            prev = e
        # в листе встречаются описания и склейки вместо названий: оставляем названия, которые повторяются
        # хотя бы в двух категориях портала, без склеек и разумной длины
        kept = {k: v for k, v in chars.items() if v["categories"] >= 2 and "|" not in k and len(k) <= 80}
        for v in kept.values():
            v["lemmas"] = sorted(set(content_lemmas(v["name"])) - GENERIC) or sorted(set(content_lemmas(v["name"])))
        index[cat] = kept
        stats[cat] = {"rows": n, "names": len(chars), "kept": len(kept)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source": str(src), "index": index}, ensure_ascii=False), encoding="utf-8")
    lookup_index.cache_clear()
    return stats


@lru_cache(maxsize=1)
def lookup_index() -> dict[str, list[tuple[frozenset[str], str]]] | None:
    if not unpack_gz(INDEX).exists():
        return None
    raw = json.loads(INDEX.read_text(encoding="utf-8"))["index"]
    out = {}
    for cat, chars in raw.items():
        items = [(frozenset(v["lemmas"]), v["name"]) for v in chars.values() if v.get("lemmas")]
        out[cat] = sorted(items, key=lambda x: (-len(x[0]), x[1]))
    return out


def available() -> bool:
    return lookup_index() is not None


def lookup(text: str, categories: set[str]) -> str | None:
    """Характеристика портала, все ключевые слова которой есть в тексте (самая длинная)."""
    idx = lookup_index()
    if not idx or not text:
        return None
    words = set(content_lemmas(text))
    best = None
    for cat in sorted(categories):
        for lem, name in idx.get(cat, []):     # от длинных названий к коротким
            if lem <= words:
                if best is None or len(lem) > len(best[0]):
                    best = (lem, name)
                break
    return best[1] if best else None
