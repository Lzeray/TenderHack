"""Покрытие свойств КТРУ статистикой выгрузок по точному совпадению названия (оценка нужности шага B2).

Для каждого типа с достаточной поддержкой: свойства КТРУ его позиций → есть ли в артефакте свойство с тем же
ключом названия. Для ненайденных — кандидаты СТЕ той же размерности (по числу моделей), для ручного просмотра.
python -m experiments.prop_coverage --out reports/exp/prop_coverage.txt
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.catalog.repository import Catalog  # noqa: E402
from ktru_assist.catalog.ste_stats import prop_key  # noqa: E402
from ktru_assist.empirical import THRESHOLDS  # noqa: E402
from ktru_assist.registry import TypeRegistry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", default=str(ROOT / "data" / "ste_stats.sqlite"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cat = Catalog(ROOT / "data" / "ktru.sqlite")
    docs = cat.search_documents()
    reg = TypeRegistry(docs)
    con = sqlite3.connect(args.stats)
    types = {t: n for t, n in con.execute("SELECT type_key, n_models FROM types")}
    ste = collections.defaultdict(dict)
    for t, pk, kind, dim, n in con.execute("SELECT type_key, prop_key, kind, dimension, n_models FROM props"):
        ste[t][(pk, kind, dim)] = n
    codes_by_head = collections.defaultdict(list)
    for d in docs:
        if d["active"] and not d["is_template"]:
            codes_by_head[d["head"]].append(d["code"])
    tot = collections.Counter()
    lines = []
    for t, n_models in sorted(types.items(), key=lambda x: -x[1]):
        if n_models < THRESHOLDS["n1_models"] or "|" in t:
            continue
        props = {}
        for p in cat.get_many(codes_by_head.get(t, [])).values():
            for pr in p.props.values():
                dims = {u.dimension for u in pr.units} if pr.is_numeric else set()
                props[prop_key(pr.name)] = ("number" if pr.is_numeric else "text", dims, pr.name)
        hit, miss = [], []
        for pk, (kind, dims, name) in sorted(props.items()):
            ok = any(k[0] == pk and k[1] == kind for k in ste[t])
            (hit if ok else miss).append((pk, kind, dims, name))
        tot["props"] += len(props)
        tot["hit"] += len(hit)
        lines.append(f"## {t} ({n_models} моделей): найдено {len(hit)} из {len(props)}")
        for pk, kind, dims, name in miss:
            cands = sorted(((n, k[0]) for k, n in ste[t].items() if k[1] == kind and (not dims or k[2] in dims)),
                           reverse=True)[:5]
            lines.append(f"   нет: {name} [{kind} {','.join(sorted(dims))}] — кандидаты: "
                         + "; ".join(f"{c}({n})" for n, c in cands))
    head = f"ИТОГО: свойств КТРУ {tot['props']}, найдено по точному названию {tot['hit']} " \
           f"({tot['hit'] / max(1, tot['props']):.0%})\n\n"
    Path(args.out).write_text(head + "\n".join(lines), encoding="utf-8")
    print(head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
