"""Сверка области поиска с КТРУ по каждому типу (docs/QUESTIONS_PLAN.md, шаг Q0).

Для каждого главного слова типа (направления MVP) — запрос из одного слова. Эталон без кода движка: все активные
конечные позиции КТРУ, в наименовании которых есть это слово (лемма любого слова наименования). Потери
раскладываются по причинам: вне направлений MVP (ОКПД2), другое главное слово (секция, платформа …), исключена
проверкой, не попала в область.

python -m experiments.scope_audit --out reports/exp/scope_audit.json
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
from ktru_assist.models import SearchRequest  # noqa: E402
from ktru_assist.text import content_lemmas  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eng = get_engine()
    con = eng.catalog.con
    rows = con.execute("SELECT code, name, head, category, okpd2_code FROM positions "
                       "WHERE active=1 AND is_template=0").fetchall()
    by_lemma: dict[str, list] = collections.defaultdict(list)
    for r in rows:
        for lem in set(content_lemmas(r["name"])):
            by_lemma[lem].append(r)
    heads = sorted({r["head"] for r in rows if r["category"] and r["head"]})
    report, total = [], collections.Counter()
    for h in heads:
        ref = by_lemma.get(h, [])
        if not ref:
            continue
        res = eng.search(SearchRequest(text=h))
        found = set(res.compatible_codes)
        cands = {c.code: c for c in res.candidates}
        lost = collections.Counter()
        examples = collections.defaultdict(list)
        for r in ref:
            if r["code"] in found:
                continue
            if r["category"] is None:
                why = "вне MVP (ОКПД2 " + (r["okpd2_code"] or "?")[:5] + ")"
            elif r["head"] != h:
                why = "главное слово «" + str(r["head"]) + "»"
            elif r["code"] in cands:
                why = "исключена: " + (cands[r["code"]].excluded_reason or "?")[:60]
            else:
                why = "не в области"
            lost[why] += 1
            if len(examples[why]) < 3:
                examples[why].append(r["name"][:70])
        same_head = sum(1 for r in ref if r["head"] == h)
        same_found = sum(1 for r in ref if r["head"] == h and r["code"] in found)
        total["ref"] += len(ref)
        total["found"] += len(found & {r["code"] for r in ref})
        total["same_head"] += same_head
        total["same_head_found"] += same_found
        for k, v in lost.items():
            total[k.split(" (")[0].split(":")[0].split("«")[0].strip()] += v
        report.append({"head": h, "ref": len(ref), "found": len(found), "same_head": same_head,
                       "same_head_found": same_found, "lost": dict(lost), "examples": examples})
    report.sort(key=lambda x: -(x["same_head"] - x["same_head_found"]) * 1000 - sum(x["lost"].values()))
    Path(args.out).write_text(json.dumps({"total": total, "types": report}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
