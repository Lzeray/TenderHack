"""Стенд полноты подбора по КТРУ (docs/KTRU_SEARCH_PLAN.md, шаг K0).

Запросы строятся из каталога: тип (главное слово или полное наименование) + 0–3 характеристики целевой позиции
в виде «название свойства значение». Характеристика основная, если обязательна хотя бы в одной позиции типа.
Варианты: только тип; только основные; только неосновные; вперемешку.

Эталон считается по базе, без кода движка: позиции того же типа (главное слово наименования; для запроса по
наименованию — наименования, содержащие все его слова), активные, конечные; без позиций, чей «Вид товара» —
другое изделие («Секция шкафа»), если вид товара не назван; позиция остаётся, если у неё нет названного свойства
или значение есть среди допустимых (одно из списка). Сравнивается с полным набором совместимых конечных кодов ответа (`compatible_codes`).

Метрики: recall — доля эталона в ответе; full — эталон найден целиком; precision — доля ответа в эталоне;
exact — множества совпали; bound — характеристика привязана к своему свойству; code_missing_req — код выдан,
хотя обязательные характеристики не заполнены.

python -m experiments.ktru_recall --out reports/exp/kr_base.json
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402
from ktru_assist.text import content_lemmas, norm  # noqa: E402

KIND = "вид товара"
PREPOSITIONS = {"для", "под", "к", "ко", "с", "со", "на", "из", "от", "по", "в", "во", "без", "при", "над", "о", "об",
                "у", "за", "до"}


def item_words(name: str, heads: set[str]) -> set[str]:
    """Эталон без кода ядра: слова типа в наименовании, не стоящие после предлога в своей группе (до запятой, «/»,
    скобки или начала) — решение команды (docs/QUESTIONS_PLAN.md, Q1)."""
    import re
    from ktru_assist.text import lemma
    parts = re.findall(r"[а-яёa-z]+(?:-[а-яёa-z]+)*|[,/()]", name.lower())
    out = set()
    for i, w in enumerate(parts):
        if w in ",/()" or lemma(w) not in heads:
            continue
        j = i - 1
        while j >= 0 and parts[j] not in ",/()" and parts[j] not in PREPOSITIONS:
            j -= 1
        if j < 0 or parts[j] in ",/()":
            out.add(lemma(w))
    return out

PROBES = ["стол", "шкаф", "стул", "куртка", "молоток", "пассатижи", "стол деревянный", "стол письменный",
          "стол письменный деревянный", "шкаф для одежды металлический", "куртка зимняя женская",
          "стул на металлическом каркасе"]


def finals_by_type(cat) -> tuple[dict[str, list], dict[str, list]]:
    rows = cat.con.execute("SELECT code, name, head FROM positions WHERE active=1 AND is_template=0 "
                           "AND category IS NOT NULL AND head IS NOT NULL").fetchall()
    pos = cat.get_many([r["code"] for r in rows])
    by_head, by_name = collections.defaultdict(list), collections.defaultdict(list)
    for r in rows:
        p = pos[r["code"]]
        by_head[r["head"]].append(p)
        by_name[r["name"]].append(p)
    # эталонная область типа — как определено решением команды (docs/QUESTIONS_PLAN.md, Q1): главное слово и слова
    # типа в наименовании не после предлога («Секция стульев многоместная» — стул); выборка запросов — по главному
    heads = set(by_head)
    by_type = collections.defaultdict(list)
    for r in rows:
        for h in {r["head"]} | item_words(r["name"], heads):
            by_type[h].append(pos[r["code"]])
    return by_head, by_name, by_type


def quality_props(p) -> list:
    return [pr for pr in p.props.values() if pr.values and all(v.kind == "quality" for v in pr.values)
            and not pr.is_boolean]


def other_item(p, head: str) -> bool:
    """«Вид товара» позиции — другое изделие: слова типа нет ни в одном значении («Тумба» у «стол»); «Секция стола» —
    тоже стол (решение команды, docs/QUESTIONS_PLAN.md, Q1)."""
    pr = next((x for x in p.props.values() if norm(x.name) == KIND), None)
    vals = [v.text for v in pr.values if v.kind == "quality" and v.text] if pr else []
    return bool(vals) and all(head not in content_lemmas(v) for v in vals)


def reference(universe: list, stated: list[tuple[str, str]], head: str) -> set[str]:
    out = set()
    explicit_kind = any(norm(n) == KIND for n, _ in stated)
    for p in universe:
        if not explicit_kind and other_item(p, head):
            continue
        ok = True
        for name, value in stated:
            pr = next((x for x in p.props.values() if norm(x.name) == norm(name)), None)
            if pr is not None and norm(value) not in {norm(v.text or "") for v in pr.values if v.kind == "quality"}:
                ok = False
                break
        if ok:
            out.add(p.code)
    return out


def make_cases(by_head, by_name, rnd: random.Random, n_types: int, by_type=None) -> list[dict]:
    heads = sorted(h for h, ps in by_head.items() if len(ps) >= 2)
    rnd.shuffle(heads)
    cases = []
    for h in heads[:n_types]:
        universe_h = by_head[h]
        required = {norm(pr.name) for p in universe_h for pr in p.props.values() if pr.required}
        t = rnd.choice(universe_h)
        props = quality_props(t)
        main = [pr for pr in props if norm(pr.name) in required]
        other = [pr for pr in props if norm(pr.name) not in required]
        variants = {"type": []}
        if main:
            variants["main1"] = rnd.sample(main, 1)
        if len(main) >= 2:
            variants["main2"] = rnd.sample(main, 2)
        if other:
            variants["other1"] = rnd.sample(other, 1)
        if main and other:
            variants["mixed"] = rnd.sample(main, min(2, len(main))) + rnd.sample(other, 1)
        # по наименованию подходят и более частные наименования с теми же словами («Джинсы» → «Джинсы детские»)
        core = set(t.name_lemmas)
        # эталонная область — по определению типа (by_type); выборка запросов — по главному слову (как раньше)
        universe_t = (by_type or {}).get(h) or universe_h
        universe_n = [p for p in universe_t if core <= set(p.name_lemmas)]
        for level, word, universe in (("head", h, universe_t), ("name", t.name, universe_n)):
            for var, chosen in variants.items():
                stated = [(pr.name, rnd.choice([v.text for v in pr.values])) for pr in chosen]
                text = ", ".join([word.lower()] + [f"{n.lower()} {v.lower()}" for n, v in stated])
                cases.append({"head": h, "level": level, "variant": var, "text": text, "stated": stated,
                              "main": [norm(n) in required for n, _ in stated],
                              "ref": sorted(reference(universe, stated, h)), "universe": len(universe)})
    return cases


CANONICAL = False


def run_case(eng, c: dict) -> dict:
    if CANONICAL:      # поиск по скрытой строке «тип; ключ: значение» (docs/PARSE_INPUT_PLAN.md, P4)
        from ktru_assist.canonical import process
        from ktru_assist.models import Canonical
        r = process(SearchRequest(text=c["text"], canonical=Canonical()), eng, eng.search)
    else:
        r = eng.search(SearchRequest(text=c["text"]))
    found, ref = set(r.compatible_codes), set(c["ref"])
    bound = {norm(f.property_name or "") for f in r.features if f.status == "bound"}
    missing_req = any(x.status == "missing" for x in r.required_characteristics)
    return {"status": r.status, "found": sorted(found),
            "recall": len(found & ref) / len(ref) if ref else None,
            "precision": len(found & ref) / len(found) if found else None,
            "full": ref <= found, "exact": found == ref,
            "bound": [norm(n) in bound for n, _ in c["stated"]],
            "code_missing_req": r.status == "matched" and missing_req}


def summarize(rows: list[dict]) -> dict:
    out = {}
    keyf = lambda r: f'{r["level"]}/{r["variant"]}'  # noqa: E731
    groups = collections.defaultdict(list)
    for r in rows:
        groups[keyf(r)].append(r)
        groups["ALL"].append(r)
    for k, rs in sorted(groups.items()):
        rec = [r["res"]["recall"] for r in rs if r["res"]["recall"] is not None]
        prec = [r["res"]["precision"] for r in rs if r["res"]["precision"] is not None]
        b = [x for r in rs for x in r["res"]["bound"]]
        out[k] = {"n": len(rs), "recall": round(sum(rec) / max(1, len(rec)), 3),
                  "full": round(sum(r["res"]["full"] for r in rs) / len(rs), 3),
                  "precision": round(sum(prec) / max(1, len(prec)), 3),
                  "exact": round(sum(r["res"]["exact"] for r in rs) / len(rs), 3),
                  "bound": round(sum(b) / max(1, len(b)), 3) if b else None,
                  "empty_answer": sum(not r["res"]["found"] for r in rs),
                  "code_missing_req": sum(r["res"]["code_missing_req"] for r in rs),
                  "status": dict(collections.Counter(r["res"]["status"] for r in rs))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--types", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--canonical", action="store_true", help="поиск по скрытой строке запроса")
    args = ap.parse_args()
    global CANONICAL
    CANONICAL = args.canonical
    eng = get_engine()
    by_head, by_name, by_type = finals_by_type(eng.catalog)
    cases = make_cases(by_head, by_name, random.Random(args.seed), args.types, by_type)
    rows = [{**c, "res": run_case(eng, c)} for c in cases]
    probes = []
    for t in PROBES:
        r = eng.search(SearchRequest(text=t))
        probes.append({"text": t, "status": r.status, "compatible": len(r.compatible_codes),
                       "features": [(f.property_name, f.op, f.value, f.status) for f in r.features]})
    worst = sorted((r for r in rows if not r["res"]["full"]), key=lambda r: r["res"]["recall"] or 0)[:40]
    summary = summarize(rows)
    Path(args.out).write_text(json.dumps({"summary": summary, "probes": probes,
                                          "worst": [{k: r[k] for k in ("text", "level", "variant", "ref")}
                                                    | {"found": r["res"]["found"], "recall": r["res"]["recall"]}
                                                    for r in worst],
                                          "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"summary": summary, "probes": [(p["text"], p["status"], p["compatible"]) for p in probes]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
