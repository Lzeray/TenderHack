"""Стенд оценки исправления орфографии (docs/SPELLING_VALIDATION.md, шаг 0).

Наборы:
* A — чистые тексты из КТРУ (синтетический набор бенчмарка): ложные исправления;
* B — реальные наименования выгрузок, где все слова известны словарю (без чисел и латиницы): ложные исправления;
* C — синтетика по видам ошибок: в слово (≥ 4 букв, кириллица) чистого текста A вносится одна ошибка заданного вида;
* F — пробы (`PROBES`): реальные примеры с ожидаемым результатом.
Исправление считается верным, если леммы значимых слов после исправления совпали с леммами чистого текста;
«вопрос» — система предложила варианты (неоднозначно); «пропуск» — ошибка осталась.

Конвейер — тот же, что в движке: normalize → typos.correct (функция `pipeline`).

python -m experiments.spell_eval --out reports/exp/spell_base.json
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
from ktru_assist.nlp.normalize import normalize  # noqa: E402
from ktru_assist.text import STOPWORDS, content_lemmas, is_known_word, lemma  # noqa: E402

KEYBOARD = ["йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю"]
HOMO = {"а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y", "к": "k"}
LAYOUT = dict(zip("йцукенгшщзхъфывапролджэячсмитьбю", "qwertyuiop[]asdfghjkl;'zxcvbnm,."))
DOUBLE = "лнсмтрк"

PROBES = [
    ("шкаф металичский для одежды", "шкаф металлический для одежды"),
    ("стул на металллическом каркасе", "стул на металлическом каркасе"),
    ("пассатижи слсеарные", "пассатижи слесарные"),
    ("куртка зимяя мужская", "куртка зимняя мужская"),
    ("стул мягкй сиденье", "стул мягкий сиденье"),
    ("стол обеденный кругой", "стол обеденный круглый"),
    ("шкaф для одежды", "шкаф для одежды"),
    ("irfa lkz jlt;ls", "шкаф для одежды"),
    ("шкафдля одежды", "шкаф для одежды"),
    ("шуруп оверт аккумуляторный", "шуруповерт аккумуляторный"),
    ("пасатижи слесарные", "пассатижи слесарные"),
    ("стулл на деревяном каркасе", "стул на деревянном каркасе"),
    ("кресло офиссное", "кресло офисное"),
    ("cтол письменный", "стол письменный"),
    ("стул мужcкой", "стул мужской"),
]


def pipeline(eng, text: str):
    """(значимые леммы после исправления, исправления) — как в движке."""
    nq = normalize(text)
    corr = eng.typos.correct(nq.tokens, {}, type_heads=eng._head_set)
    lems = [t.lemma for t in nq.tokens if t.kind == "word" and t.lemma not in STOPWORDS]
    return lems, corr


def neighbors(ch: str) -> str:
    for row in KEYBOARD:
        i = row.find(ch)
        if i >= 0:
            return row[max(0, i - 1):i] + row[i + 1:i + 2]
    return ""


def corrupt(text: str, kind: str, rnd: random.Random) -> str | None:
    words = text.split()
    idx = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha() and all("а" <= c <= "я" or c == "ё" for c in w.lower())
           and w.lower() not in STOPWORDS]
    if kind == "layout":
        return "".join(LAYOUT.get(c, c) for c in text.lower())
    if kind == "merge":
        gaps = [i for i in range(len(words) - 1) if words[i].isalpha() and words[i + 1].isalpha()]
        if not gaps:
            return None
        i = rnd.choice(gaps)
        return " ".join(words[:i] + [words[i] + words[i + 1]] + words[i + 2:])
    if not idx:
        return None
    i = rnd.choice(idx)
    w = words[i].lower()
    p = rnd.randrange(1, len(w) - 1)
    if kind == "keyboard":
        nb = neighbors(w[p])
        if not nb:
            return None
        w2 = w[:p] + rnd.choice(nb) + w[p + 1:]
    elif kind == "delete":
        w2 = w[:p] + w[p + 1:]
    elif kind == "insert":
        nb = neighbors(w[p]) or w[p]
        w2 = w[:p] + rnd.choice(nb) + w[p:]
    elif kind == "transpose":
        w2 = w[:p] + w[p + 1] + w[p] + w[p + 2:]
    elif kind == "double":
        pos = [k for k in range(1, len(w)) if w[k] in DOUBLE]
        dbl = [k for k in range(1, len(w)) if w[k] == w[k - 1]]
        if dbl:
            k = rnd.choice(dbl)
            w2 = w[:k] + w[k + 1:]
        elif pos:
            k = rnd.choice(pos)
            w2 = w[:k] + w[k] + w[k:]
        else:
            return None
    elif kind == "homoglyph":
        pos = [k for k, c in enumerate(w) if c in HOMO]
        if not pos:
            return None
        k = rnd.choice(pos)
        w2 = w[:k] + HOMO[w[k]] + w[k + 1:]
    elif kind == "split":
        if len(w) < 7:
            return None
        k = rnd.randrange(3, len(w) - 3)
        w2 = w[:k] + " " + w[k:]
    else:
        raise ValueError(kind)
    if w2 == w or (" " not in w2 and is_known_word(w2)) or (" " in w2 and all(map(is_known_word, w2.split()))):
        return None                      # получилось настоящее слово (слова) — это другой класс ошибок
    return " ".join(words[:i] + [w2] + words[i + 1:])


KINDS = ["keyboard", "delete", "insert", "transpose", "double", "homoglyph", "layout", "merge", "split"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-kind", type=int, default=300)
    args = ap.parse_args()
    eng = get_engine()
    rnd = random.Random(0)
    # A: варианты синтетики без внесённых опечаток (у «-typo» опечатки намеренные)
    clean_a = [r["text"] for r in (json.loads(l) for l in (ROOT / "benchmark" / "suites" / "synthetic.jsonl")
                                   .read_text(encoding="utf-8").splitlines()) if not r["id"].endswith("-typo")]
    # B: реальные наименования отложенных производителей, где все русские слова есть в словаре
    #    (числа, латиница, коды допускаются — их исправлять нельзя)
    names = set()
    hold = ROOT / "reports" / "exp" / "ste_holdout0.jsonl"
    if hold.exists():
        for l in hold.read_text(encoding="utf-8").splitlines():
            names.add(json.loads(l)["name"])
    import re as _re
    clean_b = sorted(n for n in names if all(is_known_word(w) for w in _re.findall(r"[а-яё]{3,}", n.lower())))[:3000]
    res: dict = {}
    ex = collections.defaultdict(list)
    for name, texts in (("A_clean_ktru", clean_a), ("B_clean_ste", clean_b)):
        n = fc = 0
        for t in texts:
            _, corr = pipeline(eng, t)
            n += 1
            bad = [c for c in corr if c.status == "corrected"]
            fc += bool(bad)
            if bad and len(ex[name]) < 15:
                ex[name].append({"text": t, "corr": [(c.original, c.corrected) for c in bad]})
        res[name] = {"n": n, "false_corrections": fc, "rate": round(fc / max(1, n), 4)}
    for kind in KINDS:
        c = collections.Counter()
        tries = 0
        while c["n"] < args.per_kind and tries < args.per_kind * 20:
            tries += 1
            t = rnd.choice(clean_a)
            bad = corrupt(t, kind, rnd)
            if bad is None:
                continue
            want = pipeline(eng, t)[0]          # эталон — тем же конвейером по чистому тексту (единицы ≠ слова)
            got, corr = pipeline(eng, bad)
            c["n"] += 1
            if got == want:
                c["fixed"] += 1
            elif any(x.status == "ambiguous" for x in corr):
                c["asked"] += 1
            else:
                c["missed"] += 1
                if len(ex[kind]) < 8:
                    ex[kind].append({"bad": bad, "clean": t})
        res[kind] = {**c, "fixed_share": round(c["fixed"] / max(1, c["n"]), 3)}
    probes = []
    for bad, clean in PROBES:
        got, corr = pipeline(eng, bad)
        ok = got == pipeline(eng, clean)[0]
        probes.append({"text": bad, "ok": ok, "corr": [(x.original, x.status, x.corrected) for x in corr]})
    res["F_probes"] = {"n": len(probes), "ok": sum(p["ok"] for p in probes)}
    Path(args.out).write_text(json.dumps({"summary": res, "probes": probes, "examples": ex}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
