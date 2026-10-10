"""Верхние границы для двух уточняющих вопросов (docs/QUESTIONS_PLAN.md, Q2).

Для стартового множества каждого типа (ответ ядра на главное слово) и тех же кандидатов в вопросы, что у ядра
(`clarify.build_plans`), для каждой позиции T:
* различима — существуют правдивые ответы на все вопросы, после которых совместимой остаётся только T
  (иначе T не отличить ни при каком числе вопросов: у другой позиции те же значения);
* оракул-2 — существует пара вопросов (q1, q2) и правдивые ответы, после которых остаётся только T. Это верхняя
  граница для любого алгоритма из двух вопросов: алгоритм не знает T заранее и задаёт один и тот же первый вопрос
  всем;
* модель — оценка планировщика P(определена за 2) для стартового множества.

python -m experiments.question_bounds --out reports/exp/qbounds_head.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.clarify import build_plans  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402
from ktru_assist.qplan import Planner  # noqa: E402
from ktru_assist.text import tokenize  # noqa: E402


def truthful(q, code):
    """Ответы, которые может дать пользователь, которому нужна позиция code."""
    own = q.own.get(code)
    if own:
        return [a for a in own if a in q.members]
    return [a for a, m in q.members.items() if code in m]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eng = get_engine()
    heads = sorted({r[0] for r in eng.catalog.con.execute(
        "SELECT head FROM positions WHERE active=1 AND is_template=0 AND category IS NOT NULL AND head IS NOT NULL")})
    total = {"positions": 0, "distinguishable": 0, "oracle2": 0, "model_mass": 0.0}
    report = []
    for h in heads:
        r0 = eng.search(SearchRequest(text=h))
        codes = list(r0.compatible_codes)
        if not codes:
            continue
        pos = eng.catalog.get_many(codes)
        cands = [pos[c] for c in codes if c in pos]
        constrained = {" ".join(tokenize(f.property_name)) for f in r0.features
                       if f.status == "bound" and f.property_name and not f.from_type_name}
        plans, _ = build_plans(cands, constrained, len({c.name for c in cands}) > 1)
        S = frozenset(c.code for c in cands)
        model = Planner(plans, S).choose(S, 2)[1] if len(S) > 1 else (1.0, 0.0)
        p_model = model[0] if model else 0.0
        dist = orc = 0
        for c in S:
            if len(S) == 1:
                dist += 1; orc += 1
                continue
            # различима: по каждому вопросу — ответ c с наименьшей веткой, пересечение
            left = S
            single = []
            for q in plans:
                ans = truthful(q, c)
                if not ans:
                    continue
                best = min((q.members[a] & S for a in ans), key=len)
                single.append(best)
                left &= best
            if left == {c}:
                dist += 1
            if any(b == {c} for b in single) or any((b1 & b2) == {c} for b1, b2 in itertools.combinations(single, 2)):
                orc += 1
        n = len(S)
        total["positions"] += n
        total["distinguishable"] += dist
        total["oracle2"] += orc
        total["model_mass"] += p_model * n
        report.append({"head": h, "n": n, "distinguishable": dist, "oracle2": orc, "model_p": round(p_model, 3)})
    n = total["positions"]
    summary = {"positions": n, "distinguishable": round(total["distinguishable"] / n, 3),
               "oracle2": round(total["oracle2"] / n, 3), "model_p2": round(total["model_mass"] / n, 3)}
    report.sort(key=lambda x: -(x["n"] - x["oracle2"]))
    Path(args.out).write_text(json.dumps({"summary": summary, "types": report}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
