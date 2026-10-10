"""Генератор независимых наборов: natural, contradictions, out_of_scope.

  python -m benchmark.independent.generate                 # пишет benchmark/independent/suites/*.jsonl
  python -m benchmark.independent.generate --stats         # только распределение по expect × split
  python -m benchmark.independent.generate --write-manifest  # заодно пересчитать test_manifest.sha256

Эталон считается только по data/ktru.sqlite (benchmark/independent/reference.py), без кода системы.
Генерация детерминирована (фиксированный SEED, сортировка по кодам).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from . import phrasing as ph
from .reference import DEFAULT_DB, UNITS, Catalog, Char, Position, Value, convert, norm_text

SEED = 20261010
SPLIT_SALT = "iv2-a"
TEST_SHARE = 30
HERE = Path(__file__).resolve().parent
SUITES = HERE / "suites"
MANIFEST = HERE / "test_manifest.sha256"
SUITE_NAMES = ("natural", "contradictions", "out_of_scope")

BRANDS = ["ЗУБР", "Stayer", "Kraft", "Matrix", "Сибртех", "Gigant", "Шатура", "Восток-Сервис",
          "Техноавиа", "Bosch", "Ангстрем", "Глория"]
NOISE = ["{t}, производитель {brand}", "{t} ({brand})", "{t}, производство Россия",
         "{t}, страна происхождения — Китай", "{t}, арт. {art}", "{brand}: {t}", "{t} — для нужд учреждения"]
KEYB = "йцукенгшщзхъфывапролджэячсмитьбю"
MATERIAL_PROP = re.compile(r"^(?:вид материала|материал|тип материала|тип основного материала)(?: .+)?$")
TYPE_PROPS = {"вид", "тип", "назначение", "исполнение", "скорость", "половой признак", "вариант исполнения",
              "вид изделия", "конструкция"}


def split_of(key: str) -> str:
    h = int(hashlib.sha256((SPLIT_SALT + "|" + key).encode("utf-8")).hexdigest(), 16)
    return "test" if h % 100 < TEST_SHARE else "dev"


# ---------------------------------------------------------------- факты
def text_fact(ch: Char, value: str) -> dict:
    return {"property": ch.name, "kind": "text", "value": value, "unit": None, "unit_key": None, "op": "="}


def num_fact(ch: Char, value: Decimal, unit: str | None, unit_key: str | None, op: str = "=") -> dict:
    return {"property": ch.name, "kind": "number", "value": ph.fmt_dec(value, False), "unit": unit,
            "unit_key": unit_key, "op": op}


def _step(d: Decimal) -> Decimal:
    return Decimal(1).scaleb(-ph.decimals(d))


def pick_number(v: Value, rng: random.Random) -> tuple[Decimal, str] | None:
    """Число внутри допустимого значения (в единице каталога) и оператор факта."""
    iv = v.interval
    if iv is None:
        return None
    lo, hi = iv.lo, iv.hi
    if v.kind == "concrete":
        return lo, "="
    # иногда — неравенство «не менее / не более» по включённой границе
    if lo is not None and iv.lo_inc and rng.random() < 0.08:
        return lo, ">="
    if hi is not None and iv.hi_inc and rng.random() < 0.08:
        return hi, "<="
    cands: list[Decimal] = []
    if lo is not None and iv.lo_inc:
        cands.append(lo)                     # проверка включённой границы
    if hi is not None and iv.hi_inc:
        cands.append(hi)
    if lo is not None and hi is not None:
        q = min(_step(lo), _step(hi))
        mid = ((lo + hi) / 2).quantize(q, rounding="ROUND_FLOOR")
        cands.append(mid)
    elif lo is not None:
        cands.append(lo + _step(lo) * rng.choice([1, 2, 5, 10, 20]) if lo >= 10 else lo + _step(lo))
    elif hi is not None:
        x = hi - _step(hi) * rng.choice([1, 2, 5, 10])
        if x > 0:
            cands.append(x)
    cands = [c for c in cands if iv.contains(c) and c > 0]
    if not cands:
        return None
    return rng.choice(cands), "="


UNIT_SUFFIX = re.compile(r"^(.*?)(?:,\s*([^,()]+)|\s*\(([^()]+)\))\s*$")


def prop_base(name: str, strip_unit: bool) -> tuple[str, str | None]:
    """Имя свойства для текста и единица, записанная в самом имени («Момент (Нм)»)."""
    if strip_unit:
        m = UNIT_SUFFIX.match(name)
        if m:
            return ph.lower_first(m.group(1).strip()), (m.group(2) or m.group(3)).strip()
    return ph.lower_first(name.split(",")[0].strip()), None


def make_fact(ch: Char, rng: random.Random, value: Value | None = None):
    """Факт для характеристики позиции + сведения для формулировки. None — выразить нельзя."""
    vals = [v for v in ch.values if v.kind in ("quality", "range", "concrete")]
    if not vals:
        return None
    v = value or rng.choice(vals)
    if v.kind == "quality":
        if not v.text or len(v.text) > 80:
            return None
        return text_fact(ch, v.text.strip()), {"kind": "text"}
    if v.has_okei and v.unit_key is None:
        return None
    picked = pick_number(v, rng)
    if picked is None:
        return None
    x, op = picked
    if v.unit_key is None:
        base, suffix = prop_base(ch.name, True)
        return num_fact(ch, x, None, None, op), {"kind": "number", "num": x, "unit_key": None, "suffix": suffix,
                                                  "base": base}
    unit = v.unit_key
    alts = ph.UNIT_ALTERNATIVES.get(unit, [unit])
    disp = unit
    if len(alts) > 1 and rng.random() < 0.4:
        cand = rng.choice(alts[1:])
        y = convert(x, unit, cand)
        if y is not None and ph.decimals(y) <= 2 and Decimal("0.05") <= y <= Decimal("10000"):
            disp, x = cand, y.normalize()
    variant = rng.randrange(len(ph.UNIT_FORMS[disp]))
    num = ph.fmt_dec(x, rng.random() < 0.5)
    utext = ph.unit_text(disp, num, variant)
    base, _ = prop_base(ch.name, False)
    return num_fact(ch, x, utext, disp, op), {"kind": "number", "num_str": num, "unit_text": utext, "base": base,
                                              "converted": disp != unit}


# ---------------------------------------------------------------- формулировки
def _yes(value: str) -> bool | None:
    t = norm_text(value)
    return True if t == "да" else False if t == "нет" else None


def render_fact(fact: dict, info: dict, name_head_lemma: str | None, rng: random.Random) -> dict:
    """{'slot': 'adj', 'prefix', 'word', 'fallback'} или {'slot': 'tail', 'text'}."""
    prop = fact["property"]
    pl = ph.lower_first(prop.split(",")[0].strip()) if fact["kind"] == "text" else info["base"]
    if fact["kind"] == "number":
        if info.get("unit_key", "x") is None and "num_str" not in info:
            num = ph.fmt_dec(Decimal(fact["value"]), rng.random() < 0.5)
            u = f" {info['suffix']}" if info.get("suffix") else ""
            return {"slot": "tail", "text": rng.choice([f"{pl} {num}{u}", f"{pl} — {num}{u}"])}
        num, u = info["num_str"], info["unit_text"]
        if fact["op"] == ">=":
            return {"slot": "tail", "text": rng.choice([f"{pl} не менее {num} {u}", f"{pl} от {num} {u}"])}
        if fact["op"] == "<=":
            return {"slot": "tail", "text": rng.choice([f"{pl} не более {num} {u}",
                                                         f"{pl} до {num} {u} включительно"])}
        opts = [f"{pl} {num} {u}", f"{pl} {num} {u}", f"{pl} — {num} {u}", f"{pl}: {num} {u}"]
        first = pl.split(" ", 1)
        p0 = ph.parse(first[0], {"NOUN"}, "nomn")
        abl = None
        if p0 is not None and p0.inflect({"ablt"}):
            abl = p0.inflect({"ablt"}).word.replace("ё", "е") + (" " + first[1] if len(first) > 1 else "")
        else:
            r = ph.inflect_np(pl, "ablt")
            abl = r[0] if r else None
        if abl:
            opts = [f"{abl} {num} {u}"] * 6 + opts
        return {"slot": "tail", "text": rng.choice(opts)}

    value = fact["value"]
    yn = _yes(value)
    if yn is not None:
        return {"slot": "tail", "text": render_yesno(prop, yn, rng)} if not _single_adj(prop) else \
            {"slot": "adj", "prefix": "" if yn else "не ", "word": prop,
             "fallback": f"{ph.lower_first(prop)}: {'да' if yn else 'нет'}"}
    val = value if (len(value) <= 4 and value.isupper()) else ph.lower_first(value)
    generic = [f"{pl} {val}", f"{pl} — {val}", f"{pl}: {val}"]
    toks = value.split()
    plow = norm_text(prop)
    type_like = plow in TYPE_PROPS or (len(plow.split()) == 2 and plow.split()[0] in ("вид", "тип")
                                       and _lemma(plow.split()[1]) == name_head_lemma)
    if len(toks) == 1 and type_like and ph.parse(toks[0], {"ADJF", "PRTF"}, "nomn") is not None:
        return {"slot": "adj", "prefix": "", "word": value, "fallback": rng.choice(generic)}
    if toks and toks[0].lower() in ph.PREPS:
        return {"slot": "tail", "text": ph.lower_first(value)}
    if MATERIAL_PROP.match(plow):
        g = ph.inflect_np(value, "gent")
        if g:
            m = re.match(r"^(?:вид материала|материал)\s+(.+)$", plow)
            if m and m.group(1) != "изделия":
                part = ph.inflect_np(m.group(1), "nomn", "gent")
                if part:
                    return {"slot": "tail", "text": f"{part[0].lower()} из {g[0].lower()}"}
            return {"slot": "tail", "text": f"из {g[0].lower()}"}
    if plow in ("российский размер", "размер"):
        return {"slot": "tail", "text": rng.choice([f"размер {val}", f"{pl} {val}"])}
    return {"slot": "tail", "text": rng.choice(generic[:2] * 6 + generic[2:])}


def _lemma(word: str) -> str | None:
    p = ph.parse(word, {"NOUN"})
    return p.normal_form if p else None


def _single_adj(prop: str) -> bool:
    toks = prop.split()
    return len(toks) == 1 and ph.parse(toks[0], {"ADJF", "PRTF"}, "nomn") is not None


def render_yesno(prop: str, yes: bool, rng: random.Random) -> str:
    pl = ph.lower_first(prop.strip())
    opts: list[str] = []
    if norm_text(prop).startswith("наличие "):
        x = prop.strip()[len("Наличие"):].strip()
        xl = ph.lower_first(x)
        if yes:
            a = ph.inflect_np(x, "ablt", "gent")
            if a:
                opts += [ph.with_prep(a[0].lower())] * 2
            opts.append(f"наличие {xl}")
        else:
            opts += [f"без {xl}"] * 2 + [f"нет {xl}"]
            n = ph.inflect_np(x, "nomn", "gent")
            if n:
                verb = "отсутствуют" if ("plur" in n[1].tag or "Pltm" in n[1].tag) else "отсутствует"
                opts.append(f"{n[0].lower()} {verb}")
    else:
        toks = prop.split()
        first_adj = ph.parse(toks[0], {"ADJF", "PRTF"}, "nomn") is not None and len(toks) > 1
        if yes:
            a = ph.inflect_np(prop, "ablt")
            if a:
                opts += [ph.with_prep(a[0].lower())] * 2
            if first_adj:
                opts.append(pl.lower())
        else:
            g = ph.inflect_np(prop, "gent")
            if g:
                opts += [f"без {g[0].lower()}"] * 2
            if first_adj:
                opts.append(f"{' '.join(toks[1:]).lower()} не {toks[0].lower()}")
    if not opts:
        opts = [f"{pl} — {'да' if yes else 'нет'}"] * 3 + [f"{pl}: {'да' if yes else 'нет'}"]
    return rng.choice(opts)


class NameForms:
    def __init__(self, name: str):
        self.name = name
        self.nomn = ph.lower_first(name)
        r = ph.inflect_np(name, "nomn")
        self.head = r[1] if r else None
        self.head_lemma = self.head.normal_form if self.head else None
        g = ph.inflect_np(name, "gent")
        self.gent = g[0].lower() if g and r else None
        self.has_prep = any(t.lower() in ph.PREPS for t in name.split()) or "," in name or "(" in name
        toks = name.split()
        self.swapped = None
        if len(toks) == 2 and self.head is not None and ph.parse(toks[1], {"ADJF"}, "nomn") is not None \
                and ph.parse(toks[0], {"NOUN"}, "nomn") is not None:
            self.swapped = f"{toks[1].lower()} {toks[0].lower()}"


def assemble(nf: NameForms, rendered: list[dict], rng: random.Random) -> tuple[str, list[str]]:
    """Текст запроса и список приёмов (для поля variant)."""
    tricks: list[str] = []
    case = "gent" if nf.gent and rng.random() < 0.3 else "nomn"
    adjs, tails = [], []
    for r in rendered:
        if r["slot"] == "adj":
            w = ph.agree_adj(r["word"], nf.head, case)
            if w is None:
                tails.append(r["fallback"])
            else:
                adjs.append(r["prefix"] + w)
        else:
            tails.append(r["text"])
    rng.shuffle(adjs)
    rng.shuffle(tails)
    if case == "gent":
        nm = nf.gent
    elif nf.swapped and not adjs and rng.random() < 0.4:
        nm = nf.swapped
        tricks.append("name_swap")
    else:
        nm = nf.nomn
    if adjs:
        if not nf.has_prep and rng.random() < 0.5:
            nm = f"{nm} {' '.join(adjs)}"
        else:
            nm = f"{' '.join(adjs)} {nm}"
    body = nm
    if tails:
        style = rng.random()
        if style < 0.45:
            joined = ", ".join(tails)
        elif style < 0.75 and len(tails) > 1:
            joined = ", ".join(tails[:-1]) + " и " + tails[-1]
        else:
            joined = " ".join(tails)
        body = f"{nm}{rng.choice([' ', ', '])}{joined}"
    if case == "gent":
        text = rng.choice(["закупка {b}", "поставка {b}", "приобретение {b}", "закупка: поставка {b}"]).format(b=body)
        tricks.append("genitive")
    else:
        need = ph.need_word(nf.head)
        wrappers = ["{b}", "{b}", "{b}", "требуется {b}", "подберите КТРУ: {b}", "код КТРУ для товара: {b}"]
        if need:
            wrappers += [need + " {b}"] * 2
        text = rng.choice(wrappers).format(b=body)
    if rng.random() < 0.25:
        text = rng.choice(NOISE).format(t=text, brand=rng.choice(BRANDS),
                                        art=f"{rng.choice('ABKZTM')}{rng.choice('ABKZTM')}-{rng.randint(100, 9999)}")
        tricks.append("noise")
    if rng.random() < 0.5:
        text = text[0].upper() + text[1:]
    return text, tricks


UNIT_WORDS = {w.lower() for forms in ph.UNIT_FORMS.values() for f in forms for w in " ".join(f).split()}


def apply_typo(text: str, rng: random.Random) -> tuple[str, dict] | None:
    toks = text.split(" ")
    cands = []
    for i, t in enumerate(toks):
        b = t.strip(",.:;()—\"")
        if len(b) >= 5 and ph.CYR.match(b) and ph.known(b) and b.lower() not in UNIT_WORDS:
            cands.append((i, b))
    rng.shuffle(cands)
    for i, b in cands:
        for _ in range(8):
            w = list(b)
            op = rng.choice(["swap", "drop", "double", "near"])
            k = rng.randrange(1, len(w) - 1)
            if op == "swap":
                w[k], w[k + 1] = w[k + 1], w[k]
            elif op == "drop":
                del w[k]
            elif op == "double":
                w.insert(k, w[k])
            else:
                c = w[k].lower()
                if c not in KEYB:
                    continue
                j = KEYB.index(c)
                w[k] = KEYB[max(0, min(len(KEYB) - 1, j + rng.choice([-1, 1])))]
            nw = "".join(w)
            if nw.lower() != b.lower() and not ph.M.word_is_known(nw.lower()):
                toks[i] = toks[i].replace(b, nw, 1)
                return " ".join(toks), {"word": b, "typo": nw}
    return None


# ---------------------------------------------------------------- кейсы
def legacy_fields(gold: list[str], expect: str) -> dict:
    """Поля, совместимые с форматом benchmark/README.md."""
    if expect == "code_required":
        auto, status = "required", ["matched"]
    elif expect == "code_after_questions":
        auto = "allowed" if len(gold) == 1 else "forbidden"
        status = ["clarification", "manual_choice"] + (["matched"] if len(gold) == 1 else [])
    else:
        auto, status = "forbidden", ["conflict", "not_found", "clarification"]
    return {"acceptable_codes": gold, "auto": auto, "expected_status": status}


def make_case(suite: str, key: str, text: str, gold: list[str], expect: str, facts: list[dict], variant: str,
              forbidden: list[str], extra: dict) -> dict:
    case = {"id": None, "suite": suite, "split": split_of(key), "text": text}
    case.update(legacy_fields(gold, expect))
    case.update({"forbidden_codes": sorted(set(forbidden) - set(gold)),
                 "checks": [{"type": "warning"}] if suite == "contradictions" else [],
                 "gold_codes": gold, "expect": expect, "facts": facts, "variant": variant})
    case.update(extra)
    return case


def facts_for(p: Position, keys: list[str], rng: random.Random):
    out = []
    for k in keys:
        r = make_fact(p.chars[k], rng)
        if r is not None:
            out.append(r)
    return out


def build_natural(cat: Catalog, rng: random.Random) -> list[dict]:
    cases: list[dict] = []
    seen: set[str] = set()
    for name in sorted(cat.by_name):
        fam = cat.by_name[name]
        nf = NameForms(name)
        sample = fam if len(fam) <= 4 else sorted(rng.sample(fam, 4), key=lambda p: p.code)
        plan: list[tuple[Position | None, str, list]] = []
        for p in sample:
            must = sorted(p.must_state(), key=lambda k: list(p.chars).index(k))
            optional = [k for k in p.chars if k not in must]
            extra = rng.sample(optional, min(len(optional), rng.choice([0, 0, 1, 2])))
            full = facts_for(p, must + extra, rng)
            plan.append((p, "full_extra" if extra else "full", full))
            if (must or extra) and rng.random() < 0.25:
                plan.append((p, "full_rephrased", facts_for(p, must + extra, rng)))
            if len(must) >= 1 and rng.random() < 0.6:
                drop = rng.choice(must)
                plan.append((p, "partial", facts_for(p, [k for k in must + extra if k != drop], rng)))
        # «голое» наименование (иногда с одним необязательным свойством)
        p0 = fam[0]
        opt = [k for k in p0.chars if k not in p0.must_state()] if len(fam) == 1 else []
        if rng.random() < 0.6:
            plan.append((p0, "bare", facts_for(p0, opt[:1], rng) if opt and rng.random() < 0.5 else []))
        for p, variant, fr in plan:
            facts = [f for f, _ in fr]
            gold, expect = cat.expect(name, facts)
            assert p.code in gold, (name, p.code, facts)
            rendered = [render_fact(f, info, nf.head_lemma, rng) for f, info in fr]
            text, tricks = assemble(nf, rendered, rng)
            if any(f["op"] != "=" for f in facts):
                tricks.append("inequality")
            if any(info.get("converted") for _, info in fr):
                tricks.append("unit_conversion")
            if any(_yes(f["value"]) is False for f in facts):
                tricks.append("negation")
            typo = None
            if rng.random() < 0.2:
                t = apply_typo(text, rng)
                if t:
                    text, typo = t
                    tricks.append("typo")
            extra = {"name": name, "category": p.category, "target_code": p.code}
            if typo:
                extra["typo"] = typo
            if text.lower() in seen:
                continue
            seen.add(text.lower())
            cases.append(make_case("natural", name, text, gold, expect, facts, "+".join([variant] + tricks),
                                   [q.code for q in fam], extra))
    return cases


WRONG_UNITS = {"power": ["kg", "V", "mm"], "length": ["kg", "W"], "mass": ["mm", "W"], "voltage": ["W"]}


def build_contradictions(cat: Catalog, rng: random.Random) -> list[dict]:
    out: list[dict] = []
    names = sorted(cat.by_name)
    # A. два несовместимых значения kind=1 одной характеристики
    a_cases = []
    for name in names:
        fam = cat.by_name[name]
        by_key: dict[str, dict[str, Position]] = {}
        for p in fam:
            for k, ch in p.chars.items():
                if ch.kind == 1:
                    q = [v for v in ch.values if v.kind == "quality" and v.text]
                    if len(q) == 1 and len(ch.values) == 1:
                        by_key.setdefault(k, {}).setdefault(q[0].text.strip(), p)
        opts = [(k, vals) for k, vals in sorted(by_key.items()) if len(vals) >= 2]
        if opts:
            a_cases.append((name, opts))
    for name, opts in a_cases:
        k, vals = rng.choice(opts)
        v1, v2 = rng.sample(sorted(vals), 2)
        pa, pb = vals[v1], vals[v2]
        ch = pa.chars[k]
        others = [x for x in sorted(pa.must_state()) if x != k]
        fr = facts_for(pa, others, rng)
        f1 = (text_fact(ch, v1), {"kind": "text"})
        f2 = (text_fact(pb.chars[k], v2), {"kind": "text"})
        out.append(_contra(cat, name, [f1, f2] + fr, "kind1_conflict", [pa.code, pb.code], pa, rng, pair=True))
    # B. физически несовместимая единица; C. значение вне всех диапазонов
    for name in names:
        fam = cat.by_name[name]
        nums: dict[str, list[tuple[Position, Char]]] = {}
        for p in fam:
            for k, ch in p.chars.items():
                units = {v.unit_key for v in ch.values if v.interval is not None}
                if len(units) == 1 and next(iter(units)) in UNITS:
                    nums.setdefault(k, []).append((p, ch))
        if not nums:
            continue
        k = rng.choice(sorted(nums))
        p, ch = nums[k][0]
        unit = next(v.unit_key for v in ch.values if v.interval is not None)
        dim = UNITS[unit][0]
        others = [x for x in sorted(p.must_state()) if x != k]
        if dim in WRONG_UNITS:
            v = rng.choice([v for v in ch.values if v.interval is not None])
            picked = pick_number(v, rng)
            if picked:
                wu = rng.choice(WRONG_UNITS[dim])
                num = ph.fmt_dec(picked[0], rng.random() < 0.5)
                utext = ph.unit_text(wu, num, 0)
                f = num_fact(ch, picked[0], utext, wu)
                info = {"kind": "number", "num_str": num, "unit_text": utext, "base": prop_base(ch.name, False)[0]}
                out.append(_contra(cat, name, [(f, info)] + facts_for(p, others, rng), "unit_mismatch",
                                   [p.code], p, rng))
        # C: за пределами объединения всех значений семейства
        ivs = [v.interval for _, c in nums[k] for v in c.values if v.interval is not None]
        bad = None
        if all(iv.hi is not None for iv in ivs):
            top = max(iv.hi for iv in ivs)
            bad = (top * 3).quantize(Decimal(1)) if top >= 1 else top * 3
        elif all(iv.lo is not None and iv.lo > 0 for iv in ivs):
            low = min(iv.lo for iv in ivs)
            bad = (low / 4).quantize(_step(low) / 10) if low < 4 else (low / 4).quantize(Decimal(1))
            if bad <= 0:
                bad = None
        if bad is not None:
            num = ph.fmt_dec(bad, rng.random() < 0.5)
            utext = ph.unit_text(unit, num, 0)
            f = num_fact(ch, bad, utext, unit)
            info = {"kind": "number", "num_str": num, "unit_text": utext, "base": prop_base(ch.name, False)[0]}
            out.append(_contra(cat, name, [(f, info)] + facts_for(p, others, rng), "out_of_range",
                               [q.code for q in fam], p, rng))
    return [c for c in out if c is not None]


def _contra(cat, name, fr, variant, tempting, p, rng, pair=False):
    facts = [f for f, _ in fr]
    gold, expect = cat.expect(name, facts)
    if expect != "no_code":
        return None
    nf = NameForms(name)
    rendered = [render_fact(f, info, nf.head_lemma, rng) for f, info in fr]
    if pair:
        # оба конфликтующих значения — явно и рядом, чтобы противоречие было в тексте, а не в морфологии
        pl = ph.lower_first(facts[0]["property"])
        a, b = facts[0]["value"], facts[1]["value"]
        rendered[0] = {"slot": "tail", "text": rng.choice([f"{pl} {ph.lower_first(a)} и {ph.lower_first(b)} одновременно",
                                                            f"{pl}: {a}, {pl}: {b}",
                                                            f"{pl} — {ph.lower_first(a)}; {pl} — {ph.lower_first(b)}"])}
        rendered.pop(1)
        if _yes(a) is not None:
            rendered[0] = {"slot": "tail", "text": f"{render_yesno(facts[0]['property'], True, rng)}, "
                                                   f"{render_yesno(facts[0]['property'], False, rng)}"}
    text, tricks = assemble(nf, rendered, rng)
    return make_case("contradictions", name, text, gold, expect, facts, "+".join([variant] + tricks), tempting,
                     {"name": name, "category": p.category, "target_code": None})


# товары вне трёх направлений: (тип для сплита, формулировки)
OUT_OF_SCOPE = [
    ("холодильник", ["холодильник двухкамерный 300 л", "закупка холодильника бытового, объём 250 литров"]),
    ("микроволновая печь", ["микроволновая печь 20 л, мощность 700 Вт"]),
    ("чайник", ["чайник электрический 1,7 л 2200 Вт", "чайник электрический со стеклянной колбой"]),
    ("пылесос", ["пылесос бытовой мощностью 1800 Вт", "пылесос с контейнером для пыли"]),
    ("стиральная машина", ["стиральная машина с фронтальной загрузкой 6 кг"]),
    ("утюг", ["утюг с паровым ударом 2400 Вт"]),
    ("телевизор", ["телевизор диагональ 55 дюймов"]),
    ("ноутбук", ["ноутбук 15,6 дюйма, 16 ГБ ОЗУ", "закупка ноутбуков для учебного класса"]),
    ("монитор", ["монитор 27 дюймов IPS"]),
    ("принтер", ["принтер лазерный монохромный А4"]),
    ("картридж", ["картридж для лазерного принтера черный"]),
    ("бумага", ["бумага офисная А4 80 г/м2, 500 листов", "поставка бумаги для принтера формата А4"]),
    ("ручка", ["ручка шариковая синяя 0,7 мм", "ручки гелевые черные, 12 штук"]),
    ("карандаш", ["карандаш чернографитный HB с ластиком"]),
    ("степлер", ["степлер канцелярский №24/6 на 25 листов"]),
    ("скрепки", ["скрепки металлические 28 мм, 100 шт"]),
    ("тетрадь", ["тетрадь в клетку 48 листов"]),
    ("папка", ["папка-регистратор 75 мм"]),
    ("клей", ["клей-карандаш 21 г"]),
    ("молоко", ["молоко питьевое 3,2% 1 л", "молоко ультрапастеризованное"]),
    ("хлеб", ["хлеб пшеничный формовой 500 г"]),
    ("сахар", ["сахар-песок 1 кг"]),
    ("гречка", ["крупа гречневая ядрица 900 г"]),
    ("масло подсолнечное", ["масло подсолнечное рафинированное 1 л"]),
    ("кофе", ["кофе зерновой 1 кг"]),
    ("чай", ["чай черный листовой 100 г"]),
    ("вода питьевая", ["вода питьевая бутилированная 19 л"]),
    ("кроссовки", ["кроссовки мужские 42 размер", "закупка кроссовок беговых"]),
    ("ботинки", ["ботинки зимние детские 32 размер"]),
    ("туфли", ["туфли женские кожаные на каблуке"]),
    ("сапоги", ["сапоги резиновые 44 размер"]),
    ("тапочки", ["тапочки домашние"]),
    ("лампа", ["лампа светодиодная E27 10 Вт", "лампа люминесцентная 18 Вт"]),
    ("светильник", ["светильник потолочный светодиодный 36 Вт"]),
    ("батарейка", ["батарейка AA щелочная"]),
    ("кабель", ["кабель ВВГнг 3х2,5 мм2"]),
    ("розетка", ["розетка двойная с заземлением"]),
    ("цемент", ["цемент М500, мешок 50 кг"]),
    ("краска", ["краска водоэмульсионная белая 10 кг", "эмаль ПФ-115 синяя 2,7 кг"]),
    ("плитка", ["плитка керамическая напольная 30х30 см"]),
    ("бензин", ["бензин АИ-95"]),
    ("моторное масло", ["масло моторное 5W-40 4 л"]),
    ("шины", ["шины зимние 205/55 R16"]),
    ("мыло", ["мыло жидкое 5 л", "мыло туалетное 100 г"]),
    ("антисептик", ["антисептик для рук 1 л"]),
    ("туалетная бумага", ["бумага туалетная двухслойная, 8 рулонов"]),
    ("шампунь", ["шампунь для волос 400 мл"]),
    ("порошок", ["стиральный порошок автомат 3 кг"]),
    ("огнетушитель", ["огнетушитель порошковый ОП-4"]),
    ("велосипед", ["велосипед горный 26 дюймов"]),
    ("мяч", ["мяч футбольный размер 5", "мяч волейбольный"]),
    ("смартфон", ["смартфон 128 ГБ, 6,5 дюйма"]),
    ("кондиционер", ["кондиционер сплит-система 2,5 кВт"]),
    ("обогреватель", ["обогреватель масляный 2000 Вт"]),
    ("термометр", ["термометр медицинский цифровой"]),
    ("шприц", ["шприц одноразовый 5 мл"]),
    ("бинт", ["бинт марлевый стерильный 7 м х 14 см"]),
    ("учебник", ["учебник по математике 5 класс"]),
    ("цветы", ["букет живых цветов"]),
    ("корм", ["корм для кошек сухой 10 кг"]),
    ("смеситель", ["смеситель для кухни однорычажный"]),
    ("унитаз", ["унитаз-компакт с сиденьем"]),
    ("гитара", ["гитара акустическая шестиструнная"]),
    ("палатка", ["палатка туристическая четырехместная"]),
    ("рюкзак", ["рюкзак школьный ортопедический"]),
    ("сумка", ["сумка женская кожаная"]),
    ("зонт", ["зонт складной автоматический"]),
    ("часы", ["часы настенные кварцевые"]),
    ("кирпич", ["кирпич керамический полнотелый М150"]),
    ("песок", ["песок строительный 1 т"]),
    ("линолеум", ["линолеум бытовой ширина 3 м"]),
    ("обои", ["обои флизелиновые под покраску"]),
    ("клавиатура", ["клавиатура проводная USB"]),
    ("мышь", ["мышь компьютерная беспроводная"]),
    ("флешка", ["флешка 64 ГБ USB 3.0"]),
    ("роутер", ["роутер Wi-Fi двухдиапазонный"]),
    ("проектор", ["проектор мультимедийный 3500 лм"]),
    ("калькулятор", ["калькулятор бухгалтерский 12 разрядов"]),
    ("глобус", ["глобус физический 320 мм"]),
    ("говядина", ["говядина охлажденная, лопатка"]),
    ("яблоки", ["яблоки свежие, сорт Антоновка"]),
    ("сыр", ["сыр полутвердый 45%"]),
    ("макароны", ["макаронные изделия, спагетти 450 г"]),
    ("рис", ["рис круглозерный шлифованный 1 кг"]),
    ("соль", ["соль поваренная пищевая йодированная"]),
    ("яйца", ["яйца куриные С1, 10 шт"]),
    ("парацетамол", ["парацетамол таблетки 500 мг"]),
    ("автомобиль", ["автомобиль легковой седан"]),
    ("пианино", ["пианино акустическое"]),
    ("аквариум", ["аквариум 100 л с крышкой"]),
    ("саженцы", ["саженцы яблони"]),
    ("пленка", ["пленка полиэтиленовая 150 мкм"]),
]


def build_out_of_scope(cat: Catalog, rng: random.Random) -> list[dict]:
    heads = set()
    for name in cat.by_name:
        for t in re.split(r"[\s,()/-]+", name):
            p = ph.parse(t, {"NOUN"}) if t else None
            if p:
                heads.add(p.normal_form)
    out = []
    for key, texts in OUT_OF_SCOPE:
        lem = {ph.parse(t, {"NOUN"}).normal_form for t in re.split(r"[\s,()/-]+", key) if ph.parse(t, {"NOUN"})}
        if lem & heads:
            print(f"  out_of_scope: «{key}» пропущен — пересекается с наименованиями каталога: {sorted(lem & heads)}")
            continue
        for t in texts:
            if rng.random() < 0.3:
                t = rng.choice(["нужен товар: {t}", "закупка: {t}", "подберите КТРУ: {t}"]).format(t=t)
            out.append(make_case("out_of_scope", "oos|" + key, t, [], "no_code", [], "out_of_scope", [],
                                 {"name": None, "category": None, "target_code": None, "item": key}))
    return out


# ---------------------------------------------------------------- запись
def build_all(db: Path = DEFAULT_DB) -> dict[str, list[dict]]:
    cat = Catalog(db)
    suites = {
        "natural": build_natural(cat, random.Random(SEED)),
        "contradictions": build_contradictions(cat, random.Random(SEED + 1)),
        "out_of_scope": build_out_of_scope(cat, random.Random(SEED + 2)),
    }
    prefix = {"natural": "nat", "contradictions": "con", "out_of_scope": "oos"}
    for s, cases in suites.items():
        for i, c in enumerate(cases, 1):
            c["id"] = f"ind-{prefix[s]}-{i:04d}"
    return suites


def dump_line(case: dict) -> str:
    return json.dumps(case, ensure_ascii=False, sort_keys=False)


def test_hash(path: Path) -> tuple[str, int]:
    """sha256 тестовой части набора: точные строки файла со split=test, в порядке файла."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines()
             if l.strip() and json.loads(l).get("split") == "test"]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(), len(lines)


def write_manifest(names=SUITE_NAMES) -> str:
    rows = []
    for n in names:
        h, k = test_hash(SUITES / f"{n}.jsonl")
        rows.append(f"{h}  {n}.jsonl  test_cases={k}")
    MANIFEST.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return "\n".join(rows)


def stats(suites: dict[str, list[dict]]) -> str:
    lines = []
    for s, cases in suites.items():
        c = Counter((x["expect"], x["split"]) for x in cases)
        lines.append(f"{s}: {len(cases)} кейсов")
        for e in ("code_required", "code_after_questions", "no_code"):
            lines.append(f"  {e:22s} dev={c[(e, 'dev')]:4d} test={c[(e, 'test')]:4d}")
        sp = Counter(x["split"] for x in cases)
        lines.append(f"  доля test: {sp['test'] / max(1, len(cases)):.1%}")
        if s == "natural":
            tr = Counter(t for x in cases for t in x["variant"].split("+")[1:])
            lines.append("  приёмы: " + ", ".join(f"{k}={v}" for k, v in sorted(tr.items())))
            lines.append("  категории: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(x['category'] for x in cases).items())))
            expl = sum(any(f"{ph.lower_first(f['property'].split(',')[0].strip()).lower()}:" in x["text"].lower()
                           for f in x["facts"]) for x in cases)
            lines.append(f"  кейсов с конструкцией «свойство: значение»: {expl} ({expl / len(cases):.0%})")
            lines.append("  фактов на кейс: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(len(x['facts']) for x in cases).items())))
        if s == "contradictions":
            lines.append("  виды: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(x['variant'].split('+')[0] for x in cases).items())))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--stats", action="store_true", help="не писать файлы, только распределение")
    ap.add_argument("--write-manifest", action="store_true", help="пересчитать test_manifest.sha256")
    a = ap.parse_args(argv)
    suites = build_all(Path(a.db))
    print(stats(suites))
    if a.stats:
        return
    SUITES.mkdir(parents=True, exist_ok=True)
    for s, cases in suites.items():
        (SUITES / f"{s}.jsonl").write_text("".join(dump_line(c) + "\n" for c in cases), encoding="utf-8")
    print(f"записано в {SUITES}")
    if a.write_manifest or not MANIFEST.exists():
        print(write_manifest())
    else:
        for n in SUITE_NAMES:
            h, _ = test_hash(SUITES / f"{n}.jsonl")
            frozen = {l.split()[1]: l.split()[0] for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()}
            if frozen.get(f"{n}.jsonl") != h:
                print(f"ВНИМАНИЕ: test-часть {n}.jsonl отличается от замороженной (test_manifest.sha256)")


if __name__ == "__main__":
    main()
