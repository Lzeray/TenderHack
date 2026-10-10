"""Ленивые числа с эталоном по каталогу: «больше 120», «меньше 500», «больше 120 но меньше 500», «120-500», без единиц.

Эталон считается собственным кодом (benchmark/independent/reference.py) по SQLite-каталогу, поэтому набор строится
там, где есть база:

  python -m benchmark.metamorphic.lazy_numbers --db data/ktru.sqlite        # → suites/lazy_numbers.jsonl
  python -m benchmark.metamorphic.lazy_numbers --fixture                    # → fixture/suites/lazy_numbers_fixture.jsonl

`--fixture` строит синтетический каталог (fixture_catalog.py, коды с 9, это НЕ реальные данные) — на нём набор
проверяется в тестах и на нём можно прогнать систему без реальной базы.

Смысл записей (зафиксирован здесь и в README, а не подобран под систему):
  «больше a» — x > a;  «меньше b» — x < b;  «больше a, но меньше b», «>a <b» — a < x < b;
  «не меньше a и не больше b», «a-b» — a ≤ x ≤ b;  число без единицы — в единице характеристики каталога;
  «больше b, но меньше a» при a < b — пустой интервал: кода нет.
Эталон двустороннего условия — позиции, у которых хотя бы одно допустимое значение пересекается с интервалом.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from decimal import Decimal, localcontext
from pathlib import Path

from benchmark.independent.generate import test_hash
from benchmark.independent.reference import (UNITS, Catalog, Interval, Position, dec, norm_text, unit_dimension,
                                             value_compatible)
from benchmark.metamorphic.generate import ABBR, NO_CODE_STATUS, fmt, rank, split_of

HERE = Path(__file__).resolve().parent
OUT_REAL = HERE / "suites" / "lazy_numbers.jsonl"
OUT_FIXTURE = HERE / "fixture" / "suites" / "lazy_numbers_fixture.jsonl"
UNIT_TEXT = dict(ABBR, pcs="шт")
MAX_FAMILIES = 90           # на реальной базе: не больше 30 семейств на направление
PER_CATEGORY = MAX_FAMILIES // 3


# ---------------------------------------------------------------- совместимость с интервальным фактом
def fact_interval(f: dict) -> Interval:
    if f["op"] == "range":
        return Interval(dec(f["lo"]), f["lo_inc"], dec(f["hi"]), f["hi_inc"])
    x = dec(f["value"])
    return {">": Interval(x, False, None, False), "<": Interval(None, False, x, False),
            ">=": Interval(x, True, None, False), "<=": Interval(None, False, x, True)}.get(f["op"],
                                                                                      Interval.point(x))


def value_ok(f: dict, v) -> bool:
    if f["op"] != "range":
        return value_compatible(f, v)
    # тот же путь, что reference.value_compatible для чисел, но с двусторонним интервалом факта
    fi = fact_interval(f)
    if v.kind == "quality":
        return False
    if v.interval is None:
        return False
    fu = f.get("unit_key")
    if fu is None:
        return fi.intersects(v.interval)
    if v.unit_key is None or unit_dimension(fu) != unit_dimension(v.unit_key):
        return False
    with localcontext() as ctx:
        ctx.prec = 60
        factor = UNITS[fu][1] / UNITS[v.unit_key][1]
    return fi.scaled(factor).intersects(v.interval)


def position_ok(facts: list[dict], p: Position) -> bool:
    for f in facts:
        ch = p.chars.get(norm_text(f["property"]))
        if ch is None or not any(value_ok(f, v) for v in ch.values):
            return False
    return True


def gold_expect(cat: Catalog, name: str, facts: list[dict]) -> tuple[list[str], str]:
    g = [p.code for p in cat.by_name.get(name, []) if position_ok(facts, p)]
    if not g:
        return [], "no_code"
    if len(g) == 1 and cat.positions[g[0]].must_state() <= {norm_text(f["property"]) for f in facts}:
        return g, "code_required"
    return g, "code_after_questions"


def labels(expect: str, gold: list[str]) -> tuple[str, list[str]]:
    """auto и допустимые статусы — как в natural."""
    if expect == "code_required":
        return "required", ["matched"]
    if expect == "no_code":
        return "forbidden", list(NO_CODE_STATUS)
    if len(gold) > 1:
        return "forbidden", ["clarification", "manual_choice"]
    return "allowed", ["clarification", "manual_choice", "matched"]


# ---------------------------------------------------------------- выбор семейств и чисел
def numeric_chars(fam: list[Position]) -> dict[str, str | None]:
    """Числовые характеристики семейства с одной единицей у всех значений: ключ -> unit_key."""
    out: dict[str, set] = {}
    bad = set()
    for p in fam:
        for k, ch in p.chars.items():
            for v in ch.values:
                if v.kind in ("range", "concrete") and v.interval is not None:
                    if v.has_okei and v.unit_key is None:
                        bad.add(k)
                    out.setdefault(k, set()).add(v.unit_key)
                elif v.kind == "quality":
                    bad.add(k)
    return {k: next(iter(u)) for k, u in out.items()
            if k not in bad and len(u) == 1 and (next(iter(u)) is None or next(iter(u)) in UNIT_TEXT)}


def bounds(fam: list[Position], key: str) -> list[Decimal]:
    bs = set()
    for p in fam:
        ch = p.chars.get(key)
        for v in (ch.values if ch else []):
            if v.interval is not None:
                bs |= {x for x in (v.interval.lo, v.interval.hi) if x is not None}
    return sorted(bs)


def inner_point(iv: Interval) -> Decimal | None:
    if iv.lo is not None and iv.hi is not None:
        x = (iv.lo + iv.hi) / 2
    elif iv.lo is not None:
        x = iv.lo * 2 if iv.lo > 0 else iv.lo + 1
    elif iv.hi is not None:
        x = iv.hi / 2
    else:
        return None
    x = x.normalize()
    return x if iv.contains(x) else None


def text_extras(p: Position, skip: str) -> list[dict]:
    """Обязательные и kind=1 характеристики позиции с единственным качественным значением — как текстовые факты."""
    out = []
    for k in sorted(p.must_state()):
        if k == skip:
            continue
        ch = p.chars[k]
        q = [v for v in ch.values if v.kind == "quality" and v.text]
        if len(q) == 1 and len(ch.values) == 1 and norm_text(q[0].text) not in ("да", "нет"):
            out.append({"property": ch.name, "kind": "text", "value": q[0].text.strip(), "unit": None,
                        "unit_key": None, "op": "="})
    return out


def pick_families(cat: Catalog, limit: bool) -> list[tuple[str, str]]:
    cands = []
    for name, fam in cat.by_name.items():
        if len(fam) < 2:
            continue
        nums = numeric_chars(fam)
        good = [k for k in nums if sum(k in p.chars for p in fam) >= 2 and len(bounds(fam, k)) >= 2]
        if good:
            cands.append((name, sorted(good, key=lambda k: rank(name + "|" + k))[0], fam[0].category))
    cands.sort(key=lambda x: rank("lazy-num|" + x[0]))
    if not limit:
        return [(n, k) for n, k, _ in cands]
    out, per = [], {}
    for n, k, cat_ in cands:
        if per.get(cat_, 0) < PER_CATEGORY:
            out.append((n, k))
            per[cat_] = per.get(cat_, 0) + 1
    return out


# ---------------------------------------------------------------- кейсы
def num_fact(prop: str, unit_key, op: str, value=None, lo=None, hi=None, lo_inc=False, hi_inc=False) -> dict:
    f = {"property": prop, "kind": "number", "unit": UNIT_TEXT.get(unit_key) if unit_key else None,
         "unit_key": unit_key, "op": op}
    if op == "range":
        f.update(value=None, lo=str(lo), hi=str(hi), lo_inc=lo_inc, hi_inc=hi_inc)
    else:
        f["value"] = str(value)
    return f


def family_cases(cat: Catalog, name: str, key: str) -> list[dict]:
    fam = cat.by_name[name]
    uk = numeric_chars(fam)[key]
    single_numeric = len(numeric_chars(fam)) == 1
    holders = sorted([p for p in fam if key in p.chars], key=lambda p: rank(name + p.code))
    p = holders[0]
    ch = p.chars[key]
    prop = ch.name
    pl = prop[:1].lower() + prop[1:]
    bs = bounds(fam, key)
    a, b = bs[len(bs) // 3], bs[(2 * len(bs)) // 3]
    if a == b:
        a, b = bs[0], bs[-1]
    iv = next((v.interval for v in ch.values if v.interval is not None), None)
    x = inner_point(iv) if iv else None
    extras = text_extras(p, key)
    ex_txt = "".join(f", {f['property'][:1].lower() + f['property'][1:]} {f['value'].lower()}" for f in extras)
    nl = name[:1].lower() + name[1:]
    u = f" {UNIT_TEXT[uk]}" if uk else ""
    A, B = fmt(a), fmt(b)

    # (variant, текст числовой части, факт, same_as-вариант)
    specs = []
    if x is not None:
        X = fmt(x)
        specs += [("point_unit", f"{pl} {X}{u}", num_fact(prop, uk, "=", x), None)]
        if uk:
            specs += [("point_no_unit", f"{pl} {X}", num_fact(prop, None, "=", x), "point_unit")]
    specs += [
        ("gt", f"{pl} больше {A}{u}", num_fact(prop, uk, ">", a), None),
        ("lt", f"{pl} меньше {B}{u}", num_fact(prop, uk, "<", b), None),
        ("gt_lt", f"{pl} больше {A}, но меньше {B}{u}", num_fact(prop, uk, "range", lo=a, hi=b), None),
        ("ge_le", f"{pl} не меньше {A} и не больше {B}{u}",
         num_fact(prop, uk, "range", lo=a, hi=b, lo_inc=True, hi_inc=True), None),
        ("dash_range", f"{pl} {A}-{B}{u}", num_fact(prop, uk, "range", lo=a, hi=b, lo_inc=True, hi_inc=True),
         "ge_le"),
        ("symbols", f"{pl} >{A} <{B}{u}", num_fact(prop, uk, "range", lo=a, hi=b), "gt_lt"),
        ("gt_max", f"{pl} больше {fmt(bs[-1])}{u}", num_fact(prop, uk, ">", bs[-1]), None),
        ("lt_min", f"{pl} меньше {fmt(bs[0])}{u}", num_fact(prop, uk, "<", bs[0]), None),
    ]
    # перепутанные границы: «больше b, но меньше a» при a < b — пустой интервал, кода нет
    specs += [("inverted", f"{pl} больше {B}, но меньше {A}{u}", num_fact(prop, uk, "range", lo=b, hi=a), None)]
    # разрыв между допустимыми значениями семейства: первый интервал (b_i; b_i+1) без совместимых позиций
    for lo, hi in zip(bs, bs[1:]):
        f = num_fact(prop, uk, "range", lo=lo, hi=hi)
        if not gold_expect(cat, name, extras + [f])[0]:
            specs += [("gap", f"{pl} больше {fmt(lo)}, но меньше {fmt(hi)}{u}", f, None)]
            break
    if uk:
        specs += [
            ("gt_no_unit", f"{pl} больше {A}", num_fact(prop, None, ">", a), "gt"),
            ("gt_lt_no_unit", f"{pl} больше {A} меньше {B}", num_fact(prop, None, "range", lo=a, hi=b), "gt_lt"),
        ]
    if single_numeric:
        # единственная числовая характеристика семейства: свойство можно не называть
        specs += [("no_property", f"больше {A}, но меньше {B}{u}", num_fact(prop, uk, "range", lo=a, hi=b),
                   "gt_lt")]
    texts = {v: f"{nl}{ex_txt}, {t}" for v, t, _, _ in specs}
    out = []
    for variant, _, f, same in specs:
        facts = extras + [f]
        gold, expect = gold_expect(cat, name, facts)
        auto, statuses = labels(expect, gold)
        out.append({"id": None, "suite": "lazy_numbers", "split": split_of("lazy-num|" + name),
                    "text": texts[variant], "acceptable_codes": gold, "auto": auto, "expected_status": statuses,
                    "forbidden_codes": sorted({q.code for q in fam} - set(gold))[:8],
                    "checks": [{"type": "same_as", "text": texts[same]}] if same else [],
                    "gold_codes": gold, "expect": expect, "facts": facts, "variant": variant, "name": name,
                    "category": p.category, "target_code": p.code})
    return out


def build(cat: Catalog, limit: bool = True, prefix: str = "mm-lnum") -> list[dict]:
    cases = [c for name, key in pick_families(cat, limit) for c in family_cases(cat, name, key)]
    for i, c in enumerate(cases, 1):
        c["id"] = f"{prefix}-{i:04d}"
    return cases


def write(cases: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")


def fixture_db(path: Path) -> Path:
    from benchmark.metamorphic.fixture_catalog import build_db
    return build_db(path)


def build_fixture() -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        return build(Catalog(fixture_db(Path(d))), limit=False, prefix="mm-lnf")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help="SQLite-каталог (data/ktru.sqlite)")
    ap.add_argument("--fixture", action="store_true", help="синтетический каталог вместо реальной базы")
    ap.add_argument("--out", default=None)
    ap.add_argument("--write-manifest", action="store_true", help="перезаписать строку набора в манифесте")
    a = ap.parse_args(argv)
    if a.fixture:
        cases, out = build_fixture(), Path(a.out or OUT_FIXTURE)
    else:
        if not a.db or not Path(a.db).exists():
            ap.error("нужна база: --db data/ktru.sqlite (или --fixture)")
        cases, out = build(Catalog(a.db)), Path(a.out or OUT_REAL)
    write(cases, out)
    h, k = test_hash(out)
    print(f"{out}: {len(cases)} кейсов, test {k}, sha256 test-части {h}")
    return 0 if update_manifest(out, a.write_manifest) else 1


def update_manifest(out: Path, force: bool) -> bool:
    """Строка набора в test_manifest.sha256 рядом с папкой suites/: добавляется, если её нет; заменяется — только
    с --write-manifest (изменение test-части = новая версия набора)."""
    man = out.resolve().parent.parent / "test_manifest.sha256"
    h, k = test_hash(out)
    rows = [l for l in man.read_text(encoding="utf-8").splitlines() if l.strip()] if man.exists() else []
    old = next((l for l in rows if l.split()[1] == out.name), None)
    new = f"{h}  {out.name}  test_cases={k}"
    if old == new:
        return True
    if old is not None and not force:
        print(f"ВНИМАНИЕ: test-часть {out.name} разошлась с {man} (перезапись: --write-manifest)", file=sys.stderr)
        return False
    rows = [l for l in rows if l.split()[1] != out.name] + [new]
    man.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"манифест: {man}")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
