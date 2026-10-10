"""Полный перебор диалога из двух вопросов (docs/QUESTIONS_PLAN.md, Q2).

Для каждого стартового запроса (главное слово каждого типа направлений MVP или наименование каждой позиции)
перебираются ВСЕ варианты ответа на первый вопрос и для каждого — все варианты ответа на второй; каждый путь
проходит через ядро (`Engine.search` с ответами), как в интерфейсе. Ничего не моделируется и не выбирается
случайно.

Для каждой позиции T стартового множества: правдивый путь — ответы, при которых T остаётся совместимой и значение
ответа есть у T. Если у T нет спрашиваемой характеристики, правдивого ответа нет: берётся худший из вариантов, при
которых T сохраняется (консервативно). Позиция определена за k вопросов, если на правдивом пути после k ответов
выдан её код или совместимой осталась только она.

python -m experiments.question_bruteforce --start head --out reports/exp/qb_head.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.clarify import TYPE_PROP  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402


def answers_of(o):
    return list(o.answers or ([o.answer] if o.answer else []))


def owns(target, q, o) -> bool | None:
    """Есть ли у позиции значение варианта: True / False; None — у позиции нет этой характеристики."""
    if q.kind == "type":
        return o.answer is not None and o.answer.value == target.name
    prop = next((p for p in target.props.values() if p.code == q.property_code or p.name == q.property_name), None)
    if prop is None:
        return None
    return True        # совместимость (значение подходит) проверяет ядро: позиция осталась в ответе


def done(r, code) -> bool:
    return (r.status == "matched" and r.final_code == code) or list(r.compatible_codes) == [code]


def explore(eng, text):
    """Дерево ответов глубины 2: (ответ ядра на старт, [(вариант1, ответ1, [(вариант2, ответ2)])])."""
    calls = 1
    r0 = eng.search(SearchRequest(text=text))
    tree = []
    q1 = r0.question
    if q1 is not None and q1.kind not in ("manual_choice",) and r0.status != "matched":
        for o1 in q1.options:
            a1 = answers_of(o1)
            r1 = eng.search(SearchRequest(text=text, answers=a1)); calls += 1
            sub = []
            q2 = r1.question
            if q2 is not None and q2.kind != "manual_choice" and r1.status != "matched":
                for o2 in q2.options:
                    r2 = eng.search(SearchRequest(text=text, answers=a1 + answers_of(o2))); calls += 1
                    sub.append((o2, r2))
            tree.append((o1, r1, sub))
    return r0, tree, calls


def depth_for(target, r0, tree) -> int | None:
    """Сколько вопросов нужно позиции на правдивом пути (худший вариант, если характеристики у неё нет); None — >2."""
    code = target.code
    if code not in r0.compatible_codes:
        return None
    if done(r0, code):
        return 0
    q1 = r0.question
    if q1 is None or not tree:
        return None
    paths1 = [(o1, r1, sub) for o1, r1, sub in tree if code in r1.compatible_codes]
    own1 = [(o1, r1, sub) for o1, r1, sub in paths1 if owns(target, q1, o1) is not False]
    if not own1:
        return None

    def after1(o1, r1, sub):
        if done(r1, code):
            return 1
        q2 = r1.question
        paths2 = [(o2, r2) for o2, r2 in sub if code in r2.compatible_codes]
        if q2 is None or not paths2:
            return None
        res = [2 if done(r2, code) else None for _, r2 in paths2]
        if owns(target, q2, paths2[0][0]) is None:       # характеристики нет — худший вариант
            return None if any(x is None for x in res) else 2
        return 2 if any(x == 2 for x in res) else None

    res = [after1(*p) for p in own1]
    if owns(target, q1, own1[0][0]) is None:              # характеристики нет — худший вариант
        return None if any(x is None for x in res) else max(res)
    good = [x for x in res if x is not None]
    return min(good) if good else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", choices=("head", "name"), default="head")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    eng = get_engine()
    rows = eng.catalog.con.execute("SELECT code, name, head FROM positions WHERE active=1 AND is_template=0 "
                                   "AND category IS NOT NULL AND head IS NOT NULL ORDER BY code").fetchall()
    pos = eng.catalog.get_many([r["code"] for r in rows])
    starts = sorted({(r["head"] if args.start == "head" else r["name"]) for r in rows})
    t0 = time.perf_counter()
    covered, report, calls = {}, [], 0
    for text in starts:
        r0, tree, c = explore(eng, text)
        calls += c
        n0 = len(r0.compatible_codes)
        depths = {}
        for code in r0.compatible_codes:
            if code in pos:
                depths[code] = depth_for(pos[code], r0, tree)
        report.append({"start": text, "candidates": n0, "first_question": r0.question.property_name or r0.question.kind
                       if r0.question else None, "options1": len(tree),
                       "le0": sum(1 for d in depths.values() if d == 0), "le1": sum(1 for d in depths.values() if d is not None and d <= 1),
                       "le2": sum(1 for d in depths.values() if d is not None), "n": len(depths)})
        # позиция учитывается по старту своего типа (главное слово) или своему наименованию
        for code, d in depths.items():
            p = pos[code]
            mine = (p.head == text) if args.start == "head" else (p.name == text)
            if mine:
                covered[code] = d
    n = len(covered)
    dist = collections.Counter("≤2" if d is not None else ">2" for d in covered.values())
    summary = {"start": args.start, "starts": len(starts), "positions": n, "engine_calls": calls,
               "seconds": round(time.perf_counter() - t0, 1),
               "identified_0": round(sum(1 for d in covered.values() if d == 0) / n, 3),
               "identified_le1": round(sum(1 for d in covered.values() if d is not None and d <= 1) / n, 3),
               "identified_le2": round(sum(1 for d in covered.values() if d is not None) / n, 3),
               "not_identified_in_2": dist[">2"]}
    report.sort(key=lambda x: x["le2"] / max(1, x["n"]))
    Path(args.out).write_text(json.dumps({"summary": summary, "starts": report,
                                          "positions": covered}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
