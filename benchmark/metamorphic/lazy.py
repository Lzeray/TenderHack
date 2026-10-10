"""Небрежный и ленивый ввод без базы: слитные слова, числа без единиц, сокращённые неравенства, телеграфный стиль.

Источник — benchmark/independent/suites/natural.jsonl (эталон посчитан по базе). Каждое преобразование либо
не меняет фактов (эталон исходного кейса), либо меняет их так, что эталон reference.py не меняется:
  * число без единицы сравнивается с каталогом в единице каталога (reference.value_compatible), а в исходных
    кейсах без приёма unit_conversion число и так записано в единице каталога;
  * «>=350», «минимум 350», «350 и более» — тот же факт `>=`, что «не менее 350» исходного кейса.
Числа и их значения не меняются — меняется только запись. Опечатки в числах не вносятся.
"""
from __future__ import annotations

import re
from decimal import Decimal

GLUE_PER_K = 50
NO_UNIT_N = 60
LOWER_N = 60
TELEGRAPH_N = 60
WORD = re.compile(r"[А-Яа-яЁё]{2,}")
YES_NO = {"да", "нет"}
GE_FORMS = (("ineq_symbol", ">={n}{u}"), ("ineq_symbol", "≥ {n}{u}"), ("ineq_words", "минимум {n}{u}"),
            ("ineq_words", "{n}{u} и более"), ("ineq_words", "не меньше {n}{u}"))
LE_FORMS = (("ineq_symbol", "<={n}{u}"), ("ineq_symbol", "≤ {n}{u}"), ("ineq_words", "максимум {n}{u}"),
            ("ineq_words", "{n}{u} и менее"), ("ineq_words", "не больше {n}{u}"))
GE_SRC = ("не менее", "от")
LE_SRC = ("не более", "до")


def _g():
    from benchmark.metamorphic import generate as g     # поздний импорт: generate импортирует этот модуль
    return g


def in_catalog_units(c: dict) -> bool:
    """Все числа записаны в единице каталога: генератор natural не переводил единицы."""
    return "unit_conversion" not in c["variant"]


# ---------------------------------------------------------------- слитные слова
def glue_spans(text: str, k: int) -> list[tuple[int, int]]:
    """Участки из k слов подряд, разделённых ровно одним пробелом; хотя бы одно слово — не служебное."""
    ws = list(WORD.finditer(text))
    out = []
    for i in range(len(ws) - k + 1):
        grp = ws[i:i + k]
        if any(text[a.end():b.start()] != " " for a, b in zip(grp, grp[1:])):
            continue
        if all(w.group(0).lower() in _g().SERVICE for w in grp):
            continue
        out.append((grp[0].start(), grp[-1].end()))
    return out


def t_glued(c: dict, k: int) -> str | None:
    spans = glue_spans(c["text"], k)
    if not spans:
        return None
    name_words = {w.lower() for w in WORD.findall(c["name"])}
    # сначала — участок со словом из наименования («пассатижислесарные»), иначе любой
    named = [s for s in spans if any(w.lower()[:4] in {n[:4] for n in name_words}
                                     for w in WORD.findall(c["text"][s[0]:s[1]]))]
    pool = named or spans
    s, e = pool[_g().rank(c["id"] + f"glue{k}") % len(pool)]
    return c["text"][:s] + c["text"][s:e].replace(" ", "") + c["text"][e:]


def build_glued(sources: list[dict]) -> list[dict]:
    g = _g()
    out = []
    for k in (2, 3):
        n = 0
        for src in g.ordered(sources, f"glue{k}"):
            t = t_glued(src, k)
            if t is None or t == src["text"]:
                continue
            out.append(g.derived(src, "glued_words", t, f"glue{k}"))
            n += 1
            if n == GLUE_PER_K:
                break
    return out


# ---------------------------------------------------------------- ленивый пользователь
def _unitless(f: dict) -> dict:
    return dict(f, unit=None, unit_key=None)


def t_no_unit(c: dict):
    """Все единицы при числах опущены: «высотой 805», «рост 164»."""
    g = _g()
    unit_facts = [f for f in c["facts"] if f["kind"] == "number" and f["unit"]]
    spots = g.numeric_spots(c)
    if not unit_facts or not in_catalog_units(c) or len(spots) != len(unit_facts):
        return None
    text = g.replace_spots(c["text"], spots, lambda f, n, s, u: n)
    return text, [_unitless(f) if f in unit_facts else f for f in c["facts"]]


def t_lower_no_punct(c: dict):
    """Всё строчными и без знаков препинания; запятая между цифрами и регистр единиц сохраняются."""
    g = _g()
    t = c["text"]
    low = list(t.lower())
    for _, (s, e, *_r) in g.numeric_spots(c):
        low[s:e] = list(t[s:e])                          # «кВт», «В» — регистр единицы значим
    t = "".join(low)
    t = re.sub(r"\s[—–-]\s", " ", t)
    t = re.sub(r"(?<!\d)[.,](?!\d)|(?<=\d)[.,](?!\d)|(?<!\d)[.,](?=\d)|[:;()«»\"!?]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if t != c["text"] else None


def _ineq_spot(c: dict, f: dict):
    """Фраза неравенства исходного кейса («не менее 350 мм», «до 190 см включительно»): (start, end, число, единица)."""
    g = _g()
    v = Decimal(f["value"])
    nums = "|".join(re.escape(x) for x in sorted({g.fmt(v, True), g.fmt(v, False)}, key=len, reverse=True))
    words = GE_SRC if f["op"] == ">=" else LE_SRC
    unit = rf"\s+{re.escape(f['unit'])}" if f["unit"] else ""
    tail = r"(?: включительно)?" if f["op"] == "<=" else ""
    pat = re.compile(rf"(?<![{g.LETTER}])(?:{'|'.join(words)})\s+({nums})({unit})(?![{g.LETTER}\d]){tail}")
    # «до N» без «включительно» не равно «<=» — такие фразы не трогаем
    ms = [m for m in pat.finditer(c["text"]) if not (m.group(0).startswith("до") and
                                                      not m.group(0).endswith("включительно"))]
    if len(ms) != 1:
        return None
    m = ms[0]
    return m.start(), m.end(), m.group(1), m.group(2)


def t_ineq(c: dict, drop_unit: bool):
    g = _g()
    ineq = [f for f in c["facts"] if f["op"] in (">=", "<=") and f["kind"] == "number"]
    if len(ineq) != 1:
        return None
    f = ineq[0]
    spot = _ineq_spot(c, f)
    if spot is None or (drop_unit and (not f["unit"] or not in_catalog_units(c))):
        return None
    s, e, num, unit = spot
    forms = GE_FORMS if f["op"] == ">=" else LE_FORMS
    if drop_unit:
        forms = [x for x in forms if x[0] == "ineq_words"]
    tag, tpl = forms[g.rank(c["id"] + ("nu" if drop_unit else "u")) % len(forms)]
    text = c["text"][:s] + tpl.format(n=num, u="" if drop_unit else unit) + c["text"][e:]
    facts = [_unitless(x) if (x is f and drop_unit) else x for x in c["facts"]]
    return ("ineq_no_unit" if drop_unit else tag), text, facts


def t_telegraph(c: dict):
    """Наименование и голые значения: «пижама детская 164 для девочки» — без свойств, единиц и связок."""
    if not c["facts"] or not in_catalog_units(c):
        return None
    if any(f["op"] != "=" for f in c["facts"]) or sum(f["kind"] == "number" for f in c["facts"]) > 1:
        return None                                      # несколько голых чисел подряд не разобрать никому
    vals = []
    for f in c["facts"]:
        if f["kind"] == "text":
            if f["value"].strip().lower() in YES_NO:
                return None                              # «да»/«нет» без свойства ничего не значит
            vals.append(f["value"].lower())
        else:
            vals.append(_g().fmt(Decimal(f["value"]), True))
    return " ".join([c["name"].lower()] + vals), [_unitless(f) for f in c["facts"]]


def build_lazy(sources: list[dict]) -> list[dict]:
    g = _g()
    out = []

    def take(tag, fn, n):
        k = 0
        for src in g.ordered(sources, tag):
            r = fn(src)
            if r is None:
                continue
            text, facts = r if isinstance(r, tuple) else (r, src["facts"])
            out.append(g.derived(src, "lazy_user", text, tag, facts=facts))
            k += 1
            if k == n:
                break

    take("no_unit", t_no_unit, NO_UNIT_N)
    take("lower_no_punct", t_lower_no_punct, LOWER_N)
    for src in g.ordered(sources, "ineq"):
        for drop in (False, True):
            r = t_ineq(src, drop)
            if r is not None:
                tag, text, facts = r
                out.append(g.derived(src, "lazy_user", text, tag, facts=facts))
    # телеграфный стиль: свойство угадывается по значению — однозначность не гарантирована, поэтому код можно
    # выдать только из эталона, а уточнение не считается ошибкой (expect = code_after_questions)
    k = 0
    for src in g.ordered(sources, "telegraph"):
        r = t_telegraph(src)
        if r is None:
            continue
        text, facts = r
        out.append(g.derived(src, "lazy_user", text, "telegraph", facts=facts, checks=[],
                             expect="code_after_questions", auto="allowed",
                             expected_status=["matched", "clarification", "manual_choice"]))
        k += 1
        if k == TELEGRAPH_N:
            break
    return out
