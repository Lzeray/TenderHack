"""Стресс-набор: те же позиции КТРУ, но формулировки ближе к живому вводу, чем в eval/synth.py.

НЕ независимая оценка: тексты сгенерированы из каталога. Цель — измерить, насколько ядро опирается
на дословные формулировки КТРУ («свойство: значение») и словари.

Варианты для активной конечной позиции с различающими качественными значениями kind=1:
  free      наименование + значения без названий свойств («пассатижи слесарные»)
  agree     значение-прилагательное согласовано с главным словом и стоит перед ним («слесарные пассатижи»)
  typo_val  опечатка (перестановка букв) в слове значения
  typo2     опечатки и в главном слове, и в значении
  caps      ВЕРХНИЙ РЕГИСТР без запятых
  noise     посторонние слова: артикул, производитель, «в наличии»
  excess    лишние свойства, которых нет у позиции («цвет: синий», «гарантия 2 года»)
  conflict  два разных значения одного различающего свойства без названия свойства → нужен отказ от кода

Эталон: все активные конечные позиции с тем же наименованием проверяются условиями генерации
(validate.evaluate); если подходит несколько — автоматический код запрещён.

python -m experiments.stress --out experiments/suites/stress.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymorphy3  # noqa: E402

from eval.synth import acceptable, feature, split_of  # noqa: E402
from ktru_assist.catalog.repository import Catalog, Position  # noqa: E402

MORPH = pymorphy3.MorphAnalyzer()
NOISE = ["артикул ZX-{n}", "производство Россия", "в наличии на складе", "бренд Standart", "модель PRO-{n}"]
EXCESS = ["цвет: синий", "гарантия 2 года", "страна происхождения: Китай"]


def swap_typo(word: str, rnd: random.Random) -> str | None:
    if len(word) < 6:
        return None
    i = rnd.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def typo_in(text: str, rnd: random.Random) -> str | None:
    words = [w for w in text.split() if len(w) >= 6 and w.isalpha()]
    if not words:
        return None
    w = max(words, key=len)
    t = swap_typo(w, rnd)
    return text.replace(w, t, 1) if t else None


def head_form(name: str):
    """Разбор главного существительного наименования (род/число) — для согласования прилагательного."""
    for w in name.lower().split():
        p = MORPH.parse(w)[0]
        if "NOUN" in p.tag and p.tag.case == "nomn":
            return p
    return None


def agree(adj: str, head) -> str | None:
    words = adj.lower().split()
    if len(words) != 1 or head is None:
        return None
    p = next((x for x in MORPH.parse(words[0]) if "ADJF" in x.tag or "PRTF" in x.tag), None)
    if p is None:
        return None
    gr = {"nomn", head.tag.number or "sing"}
    if (head.tag.number or "sing") == "sing" and head.tag.gender:
        gr.add(head.tag.gender)
    f = p.inflect(gr)
    return f.word if f else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "ktru.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "experiments" / "suites" / "stress.jsonl"))
    ap.add_argument("--max-families", type=int, default=300)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    cat = Catalog(args.db)
    codes = [r[0] for r in cat.con.execute(
        "SELECT code FROM positions WHERE category IS NOT NULL AND active=1 AND is_template=0 ORDER BY code")]
    pos = cat.get_many(codes)
    by_name: dict[str, list[Position]] = {}
    for p in pos.values():
        by_name.setdefault(p.name, []).append(p)
    names = sorted(by_name)
    rnd.shuffle(names)
    cases = []

    def mk(p, variant, text, acc, gt, auto=None):
        if auto is None:
            auto = "allowed" if len(acc) == 1 else "forbidden"
        exp = ["matched", "clarification"] if auto == "allowed" else ["clarification", "manual_choice", "conflict"]
        cases.append({"id": f"X-{p.code}-{variant}", "suite": "stress", "split": split_of(p.name),
                      "source": "stress", "category": p.category, "variant": variant, "text": text,
                      "acceptable_codes": acc, "auto": auto, "expected_status": exp, "forbidden_codes": [],
                      "checks": [], "gt": gt,
                      "verified": "эталон по всей области наименования (experiments/stress.py)"})

    for name in names[: args.max_families]:
        fam = sorted(by_name[name], key=lambda p: p.code)
        p = rnd.choice(fam)
        k1 = [pr for pr in p.props.values() if pr.kind == 1 and len(pr.values) == 1
              and pr.values[0].kind == "quality" and pr.values[0].text not in ("Да", "Нет")]
        if not k1:
            continue
        k1 = k1[:2]
        feats = [feature(pr, pr.values[0].text, fid=f"g{i}") for i, pr in enumerate(k1)]
        acc = acceptable(fam, feats)
        if p.code not in acc:
            continue
        gt = [{"property": pr.name, "value": pr.values[0].text} for pr in k1]
        vals = [pr.values[0].text.lower() for pr in k1]
        free = " ".join([name.lower()] + vals)
        mk(p, "free", free, acc, gt)
        head = head_form(name)
        ag = [agree(v, head) for v in vals]
        if ag[0]:
            rest = [v for v, a in zip(vals[1:], ag[1:])]
            mk(p, "agree", " ".join([ag[0], name.lower()] + rest), acc, gt)
        t = typo_in(" ".join(vals), rnd)
        if t:
            mk(p, "typo_val", f"{name.lower()} {t}", acc, gt)
            t2 = typo_in(name.lower().split()[0], rnd)
            if t2:
                mk(p, "typo2", f"{t2} {' '.join(name.lower().split()[1:])} {t}".replace("  ", " "), acc, gt)
        mk(p, "caps", free.upper().replace(",", ""), acc, gt)
        noise = rnd.choice(NOISE).format(n=rnd.randrange(1000, 9999))
        mk(p, "noise", f"{free}, {noise}", acc, gt)
        mk(p, "excess", f"{free}, {rnd.choice(EXCESS)}", acc, gt)
        # dup: одно числовое свойство дважды, значения из непересекающихся диапазонов (переизбыток данных)
        drnd = random.Random(f"dup-{p.code}")
        nums = [pr for pr in p.props.values() if pr.is_numeric and pr.kind == 2
                and len([v for v in pr.values if v.interval is not None and v.unit is not None]) >= 2]
        if nums:
            pr = drnd.choice(sorted(nums, key=lambda x: x.code))
            vals2 = sorted([v for v in pr.values if v.interval is not None and v.unit is not None
                            and v.interval.lo is not None and v.interval.hi is not None],
                           key=lambda v: v.interval.lo)
            if len(vals2) >= 2 and not vals2[0].interval.intersects(vals2[-1].interval):
                from ktru_assist.units import fmt
                a = (vals2[0].interval.lo + vals2[0].interval.hi) / 2
                b = (vals2[-1].interval.lo + vals2[-1].interval.hi) / 2
                u = vals2[0].unit.title
                mk(p, "dup", f"{free}, {pr.name.lower()} {fmt(a)} {u}, {pr.name.lower()} {fmt(b)} {u}", acc, gt,
                   auto="forbidden")
        pr0 = k1[0]
        other = next((q for q in fam if q.code != p.code and pr0.code in q.props and len(q.props[pr0.code].values) == 1
                      and q.props[pr0.code].values[0].text != pr0.values[0].text), None)
        if other is not None:
            v2 = other.props[pr0.code].values[0].text.lower()
            mk(p, "conflict", f"{name.lower()} {vals[0]} и {v2}", [], gt=[], auto="forbidden")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    by = {}
    for c in cases:
        by[c["variant"]] = by.get(c["variant"], 0) + 1
    print(json.dumps({"cases": len(cases), "by_variant": by}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
