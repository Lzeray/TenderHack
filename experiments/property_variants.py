"""Варианты написания одной характеристики и одного значения в КТРУ (docs/PROPERTY_VARIANTS.md).

В пределах области каждого типа (позиции, у которых тип — главное слово или слово наименования не после предлога,
как в поиске) ищутся:
* названия характеристик, которые система считает разными (ключ — слова названия), а по смыслу одинаковые:
  совпадают основы слов (бесловарный стеммер: «сидения» / «сиденья»), отличаются регистром, «ё», знаками;
  или отличаются одной-двумя буквами (опечатка в КТРУ);
* значения одной характеристики у разных позиций, совпадающие по основам («Женский» / «Женская»,
  «Для мальчика» / «Для мальчиков») — для качественных (категориальных) характеристик.
Отдельно — пары, похожие по написанию, но разные по смыслу (контроль ложных склеек): «Длина» / «Ширина» не должны
попасть в варианты.

python -m experiments.property_variants --out reports/exp/property_variants.json
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.morph import stem  # noqa: E402
from ktru_assist.text import damerau_levenshtein, norm, tokenize  # noqa: E402


def key(name: str) -> str:
    return " ".join(tokenize(name))


def stem_key(name: str) -> str:
    return " ".join(stem(w) for w in tokenize(name))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eng = get_engine()
    docs = [d for d in eng.catalog.search_documents() if d["active"] and not d["is_template"]]
    by_type: dict[str, list[str]] = collections.defaultdict(list)
    for d in docs:
        for h in d["head_parts"]:
            by_type[h].append(d["code"])
    pos = eng.catalog.get_many([d["code"] for d in docs])
    name_pairs, value_pairs = {}, {}
    for h, codes in sorted(by_type.items()):
        props = collections.defaultdict(lambda: {"names": set(), "codes": set(), "positions": set(), "values": collections.defaultdict(set)})
        for c in codes:
            for pr in pos[c].props.values():
                e = props[key(pr.name)]
                e["names"].add(pr.name)
                e["codes"].add(pr.code)
                e["positions"].add(c)
                for v in pr.values:
                    if v.kind == "quality" and v.text:
                        e["values"][v.text].add(c)
        keys = sorted(props)
        # 1. названия: одинаковые основы или 1–2 буквы разницы при разных ключах
        for a, b in itertools.combinations(keys, 2):
            sa, sb = stem_key(a), stem_key(b)
            same_stem = sa == sb
            dist = damerau_levenshtein(a, b, 3)
            if not (same_stem or (dist <= 2 and min(len(a), len(b)) >= 8)):
                continue
            pair = tuple(sorted((min(props[a]["names"]), min(props[b]["names"]))))
            rec = name_pairs.setdefault(pair, {"names": list(pair), "same_stem": same_stem, "distance": dist,
                                               "types": [], "positions": [0, 0]})
            rec["types"].append(h)
            rec["positions"][0] += len(props[a]["positions"])
            rec["positions"][1] += len(props[b]["positions"])
        # 2. значения внутри одной характеристики: разное написание, одинаковые основы
        for k, e in props.items():
            vals = sorted(e["values"])
            for a, b in itertools.combinations(vals, 2):
                if norm(a) != norm(b) and stem_key(a) != stem_key(b):
                    continue
                pair = (min(e["names"]), a, b)
                rec = value_pairs.setdefault(pair, {"property": pair[0], "values": [a, b], "types": [],
                                                    "positions": [len(e["values"][a]), len(e["values"][b])],
                                                    "same_position": bool(e["values"][a] & e["values"][b])})
                rec["types"].append(h)
    names = sorted(name_pairs.values(), key=lambda r: (-len(r["types"]), r["names"]))
    values = sorted(value_pairs.values(), key=lambda r: (-len(r["types"]), r["property"], r["values"]))
    summary = {"types": len(by_type), "name_variants": len(names),
               "name_variants_same_stem": sum(r["same_stem"] for r in names),
               "value_variants": len(values),
               "value_variants_in_same_position": sum(r["same_position"] for r in values)}
    Path(args.out).write_text(json.dumps({"summary": summary, "names": names, "values": values}, ensure_ascii=False,
                                         indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
