"""Синтетические кейсы из снимка КТРУ (план, п. 9.2). НЕ независимая оценка живых запросов.

Для активной конечной позиции с различающей качественной характеристикой (kind=1) строится описание:
наименование + значение(я) kind=1 + 0–2 числовых свойства со значением внутри допустимого диапазона
(иногда в другой единице той же размерности). Варианты одного исходного примера (group) — в одном split:
опечатка в слове наименования, перестановка, пропуск значения (нужно уточнение), конфликт значений,
запрос вне области.

Эталон считается по ВСЕЙ области типа: все активные конечные позиции с тем же наименованием проверяются
условиями генерации (validate.evaluate). Если подходят несколько — все они в acceptable_codes
и must_not_auto=true.

python -m eval.synth --db data/ktru.sqlite --out eval/synthetic.jsonl --per-family 2 --seed 7
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ktru_assist.catalog.repository import Catalog, Position  # noqa: E402
from ktru_assist.models import Feature  # noqa: E402
from ktru_assist.units import BY_KEY, fmt  # noqa: E402
from ktru_assist.validate import evaluate  # noqa: E402

OUT_OF_SCOPE = ["утюг паровой 2000 вт", "ноутбук 15 дюймов", "бумага офисная а4 80 г/м2", "кофемашина капсульная",
                "шины зимние 205/55 r16"]
ALT_UNIT = {"mm": "cm", "cm": "mm", "g": "kg", "kg": "g", "w": "kw", "kw": "w", "m": "cm"}


def split_of(name: str) -> str:
    return "test" if int(hashlib.sha256(name.encode()).hexdigest(), 16) % 5 == 0 else "dev"


def typo(word: str, rnd: random.Random) -> str | None:
    if len(word) < 7:
        return None
    i = rnd.randrange(2, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def numeric_value(prop, rnd: random.Random):
    """Значение внутри одного из допустимых интервалов: (Decimal, Unit) или None."""
    vals = [v for v in prop.values if v.interval is not None and v.unit is not None]
    if not vals:
        return None
    v = rnd.choice(vals)
    iv = v.interval
    if iv.lo is not None and iv.hi is not None:
        x = (iv.lo + iv.hi) / 2
    elif iv.lo is not None:
        x = iv.lo + (Decimal(1) if iv.lo >= 10 else Decimal("0.5"))
    elif iv.hi is not None:
        x = iv.hi - (Decimal(1) if iv.hi > 10 else iv.hi / 2)
    else:
        return None
    if x <= 0:
        return None
    x = x.quantize(Decimal("1")) if x >= 10 else x.quantize(Decimal("0.1"))
    if not iv.contains_point(x):
        return None
    return x, v.unit


def feature(prop, value, unit=None, fid="g"):
    return Feature(id=fid, source="text", status="bound", property_code=prop.code, property_name=prop.name,
                   value=value, unit=unit)


def acceptable(domain: list[Position], feats: list[Feature]) -> list[str]:
    out = []
    for q in domain:
        ev = evaluate(q, feats)
        if ev.invalid == 0 and all(c.status == "valid" for c in ev.checks if c.feature_id):
            out.append(q.code)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "ktru.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "synthetic.jsonl"))
    ap.add_argument("--per-family", type=int, default=2)
    ap.add_argument("--max-families", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    cat = Catalog(args.db)
    codes = [r[0] for r in cat.con.execute(
        "SELECT code FROM positions WHERE category IS NOT NULL AND active=1 AND is_template=0 ORDER BY code")]
    pos = cat.get_many(codes)
    by_name: dict[str, list[Position]] = {}
    for p in pos.values():
        by_name.setdefault(p.name, []).append(p)
    cases = []
    names = sorted(by_name)
    rnd.shuffle(names)
    for name in names[: args.max_families]:
        fam = sorted(by_name[name], key=lambda p: p.code)
        split = split_of(name)
        for p in rnd.sample(fam, min(args.per_family, len(fam))):
            k1 = [pr for pr in p.props.values() if pr.kind == 1 and pr.values and all(v.kind == "quality" for v in pr.values)
                  and len(pr.values) == 1 and pr.values[0].text not in ("Да", "Нет")]
            if not k1:
                continue
            group = p.code
            gt, words = [], [name.lower()]
            for pr in k1[:2]:
                gt.append(feature(pr, pr.values[0].text, fid=f"g{len(gt)}"))
                words.append(f"{pr.name.lower()}: {pr.values[0].text.lower()}")
            nums = [pr for pr in p.props.values() if pr.is_numeric and pr.kind != 1]
            rnd.shuffle(nums)
            for pr in nums[:rnd.choice([0, 1, 2])]:
                nv = numeric_value(pr, rnd)
                if nv is None:
                    continue
                x, u = nv
                alt = ALT_UNIT.get(u.key)
                if alt and rnd.random() < 0.4 and BY_KEY[alt].dimension == u.dimension:
                    x, u = x * u.factor / BY_KEY[alt].factor, BY_KEY[alt]
                gt.append(feature(pr, fmt(x), u.title, fid=f"g{len(gt)}"))
                words.append(f"{pr.name.lower()} {fmt(x)} {u.title}")
            acc = acceptable(fam, gt)
            if p.code not in acc:
                continue  # генерация не подтверждается проверкой — кейс не берём
            base = ", ".join(words)
            mk = lambda suffix, text, **kw: cases.append({  # noqa: E731
                "id": f"S-{p.code}-{suffix}", "split": split, "source": "synthetic", "group": group,
                "category": p.category, "text": text, **kw,
                "verified": "эталон проверен по всей области наименования (eval/synth.py)"})
            if len(acc) == 1:
                mk("base", base, acceptable_codes=acc, expected_code=acc[0],
                   expected_status=["matched", "clarification_needed"])
            else:
                mk("base", base, acceptable_codes=acc, expected_code=None, must_not_auto=True,
                   expected_status=["clarification_needed", "manual_choice"])
            t = typo(name.split()[0].lower(), rnd)
            if t:
                mk("typo", base.replace(name.lower().split()[0], t, 1), acceptable_codes=acc,
                   expected_code=acc[0] if len(acc) == 1 else None, must_not_auto=len(acc) > 1,
                   expected_status=["matched", "clarification_needed", "manual_choice", "not_found"])
            if len(words) > 2:
                perm = [words[0]] + list(reversed(words[1:]))
                mk("perm", ", ".join(perm), acceptable_codes=acc, expected_code=acc[0] if len(acc) == 1 else None,
                   must_not_auto=len(acc) > 1, expected_status=["matched", "clarification_needed", "manual_choice"])
            if len(fam) > 1:
                mk("missing", name.lower(), acceptable_codes=sorted(q.code for q in fam), expected_code=None,
                   must_not_auto=True, expected_status=["clarification_needed", "manual_choice"])
                other = next((q for q in fam if q.code != p.code and k1[0].code in q.props and
                              q.props[k1[0].code].values and q.props[k1[0].code].values[0].text != k1[0].values[0].text),
                             None)
                if other is not None:
                    v2 = other.props[k1[0].code].values[0].text
                    mk("conflict", f"{name.lower()}, {k1[0].name.lower()}: {k1[0].values[0].text.lower()} и "
                                   f"{v2.lower()}", acceptable_codes=[], expected_code=None, must_not_auto=True,
                       expected_status=["conflict", "clarification_needed", "manual_choice"])
    for i, t in enumerate(OUT_OF_SCOPE):
        cases.append({"id": f"S-OOS-{i}", "split": "test" if i % 2 else "dev", "source": "synthetic",
                      "group": f"oos{i}", "category": "out_of_scope", "text": t, "acceptable_codes": [],
                      "expected_code": None, "must_not_auto": True, "expected_status": ["not_found"],
                      "verified": "вне направлений MVP"})
    Path(args.out).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "dev": sum(c["split"] == "dev" for c in cases),
                      "test": sum(c["split"] == "test" for c in cases),
                      "by_variant": {v: sum(c["id"].endswith(v) for c in cases)
                                     for v in ("base", "typo", "perm", "missing", "conflict")}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
