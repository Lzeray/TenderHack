"""Человеческие опечатки и ошибки в числах — без базы, из кейсов natural.

Опечатки natural и synthetic — механические: одна перестановка, пропуск, удвоение или соседняя клавиша в слове
от 5 букв. Здесь — то, как ошибаются люди:
  short_word   — одна замена в коротком слове типа товара: «стур» (стул), «шкав» (шкаф);
  phonetic     — одна ошибка «как слышится»: оглушение/озвончение (д↔т, в↔ф, г↔к …), безударные гласные (о↔а, е↔и),
                 л↔р: «атвертка», «тобурет», «пасотижи»;
  two_errors   — две ошибки в длинном слове: фонетическая + клавиатурная/пропуск/перестановка;
  severe       — три ошибки и больше, как «одфертуа» (отвертка);
  ambiguous    — опечатка на расстоянии 1 от двух разных типов товара каталога: «стил» (стол или стул);
  out_of_scope_typo — опечатка в товаре вне области: «колоши», «утуг» — не должны «исправиться» в товар КТРУ.
Ошибки в числах: «0180 мм», «010 шт», «18о мм», «1,,5 м», «1 80 мм» — значение неоднозначно, нужно уточнение.

Правила эталона (ожидание задано здесь, а не подобрано под систему):
  * 1 ошибка, ближайшее слово каталога единственное → тот же ответ, что на исходный текст (same_as);
  * 2 ошибки → код можно выдать только из эталона, уточнение не ошибка;
  * 3+ ошибки, неоднозначная опечатка, ошибка в числе → код без подтверждения пользователя запрещён;
  * товар вне области → кода нет.
Каждая опечатка проверяется: слова нет в словаре pymorphy3, ближайшее к ней слово среди слов наименований
каталога (те, что есть в наборах) — исходное, и только оно.
"""
from __future__ import annotations

import re
from decimal import Decimal

from benchmark.independent import phrasing as ph

PHON = {"о": "а", "а": "о", "е": "и", "и": "е", "я": "е", "д": "т", "т": "д", "б": "п", "п": "б", "в": "ф",
        "ф": "в", "г": "к", "к": "г", "з": "с", "с": "з", "ж": "ш", "ш": "ж", "л": "р", "р": "л"}
ROWS = ("йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю")
N_SHORT, N_PHON, N_TWO, N_SEVERE, N_AMBIG = 40, 60, 40, 40, 20
N_LEAD, N_LETTER, N_SEP, N_GROUP = 60, 40, 30, 30
PER_WORD = 4                # не больше кейсов на одно слово типа товара — разнообразие
ASK = ["clarification", "manual_choice"]
ASK_OR_NOT_FOUND = ["clarification", "manual_choice", "not_found"]
NUM_ASK = ["clarification", "manual_choice", "conflict"]

# товары вне трёх направлений с опечатками (вручную)
OUT_OF_SCOPE_TYPOS = (
    "колоши резиновые", "калоши резиновые мужские 44 размер", "утуг электрический с паром", "халодильник двухкамерный",
    "чяйник электрический 1,7 л", "кросовки мужские беговые", "батинки зимние детские", "сапаги резиновые",
    "микроволнофка 20 л", "пылисос бытовой", "тетрать в клетку 48 листов", "ручька шариковая синяя",
)
# примеры из постановки: тип отвертки по базе не проверен, поэтому эталон пуст — код без подтверждения запрещён
SEVERE_MANUAL = (("одфертуа", "отвертка"), ("одфертуа крестовая", "отвертка крестовая"),
                 ("атвертка плоская", "отвертка плоская"))


def _g():
    from benchmark.metamorphic import generate as g
    return g


# ---------------------------------------------------------------- расстояние и словарь
def dl(a: str, b: str) -> int:
    """Расстояние Дамерау–Левенштейна (с перестановкой соседних букв)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            c = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def vocabulary(names) -> set[str]:
    return {w.lower().replace("ё", "е") for n in names for w in re.findall(r"[А-Яа-яЁё]{3,}", n)}


def unique_nearest(typo: str, word: str, vocab: set[str]) -> bool:
    d0 = dl(typo, word)
    return all(dl(typo, v) > d0 for v in vocab if v != word)


def known(w: str) -> bool:
    return ph.M.word_is_known(w)


# ---------------------------------------------------------------- правки слова
def key_near(ch: str) -> list[str]:
    for r in ROWS:
        i = r.find(ch)
        if i >= 0:
            return [r[j] for j in (i - 1, i + 1) if 0 <= j < len(r)]
    return []


def edits(w: str, kinds: set[str]) -> list[str]:
    out = []
    for i, ch in enumerate(w):
        if "phon" in kinds and ch in PHON and (i > 0 or ch in "оаеи"):
            out.append(w[:i] + PHON[ch] + w[i + 1:])
        if "key" in kinds and i > 0:
            out += [w[:i] + c + w[i + 1:] for c in key_near(ch)]
        if "drop" in kinds and 0 < i < len(w) - 1:
            out.append(w[:i] + w[i + 1:])
        if "swap" in kinds and 0 < i < len(w) - 1:
            out.append(w[:i] + w[i + 1] + w[i] + w[i + 2:])
    return sorted(set(out) - {w})


def make_typo(word: str, plan: list[set[str]], vocab: set[str], key: str) -> str | None:
    """Последовательно применяет правки по плану; первая подходящая цепочка в порядке sha256 — детерминированно."""
    g = _g()
    frontier = [word]
    for step, kinds in enumerate(plan):
        nxt = []
        for w in frontier:
            nxt += edits(w, kinds)
        nxt = sorted(set(nxt), key=lambda x: g.rank(key + "|" + str(step) + "|" + x))[:200]
        frontier = [x for x in nxt if dl(x, word) == step + 1]
        if not frontier:
            return None
    for t in frontier:
        if not known(t) and unique_nearest(t, word, vocab):
            return t
    return None


def type_token(c: dict):
    """Первое слово наименования, если оно стоит в тексте как отдельное слово: (start, end, слово)."""
    head = re.findall(r"[А-Яа-яЁё]+", c["name"])
    if not head:
        return None
    m = re.search(rf"(?<![А-Яа-яЁё]){re.escape(head[0])}(?![А-Яа-яЁё])", c["text"], re.IGNORECASE)
    return (m.start(), m.end(), m.group(0)) if m else None


def put(text: str, s: int, e: int, orig: str, typo: str) -> str:
    if orig[:1].isupper():
        typo = typo[:1].upper() + typo[1:]
    return text[:s] + typo + text[e:]


# ---------------------------------------------------------------- набор опечаток
def build_typos(sources: list[dict], natural: list[dict], out_of_scope: list[dict]) -> list[dict]:
    g = _g()
    vocab = vocabulary({c["name"] for c in natural})
    out = []

    def run(tag, n, plan_for, word_ok, over):
        k, per_word = 0, {}
        for src in g.ordered(sources, tag):
            tok = type_token(src)
            if tok is None:
                continue
            s, e, w = tok
            wl = w.lower().replace("ё", "е")
            if not word_ok(wl) or per_word.get(wl, 0) >= PER_WORD:
                continue
            per_word[wl] = per_word.get(wl, 0) + 1
            t = make_typo(wl, plan_for(wl), vocab, src["id"] + tag)
            if t is None:
                continue
            extra = {"typo": {"word": wl, "typo": t, "distance": dl(t, wl)}}
            out.append(g.derived(src, "typos_human", put(src["text"], s, e, w, t), tag, **extra, **over(src)))
            k += 1
            if k == n:
                break

    same = lambda src: {}  # noqa: E731 — 1 ошибка: ответ как на исходный текст (same_as от derived)
    run("short_word", N_SHORT, lambda w: [{"phon", "key"}], lambda w: 3 <= len(w) <= 4, same)
    run("phonetic", N_PHON, lambda w: [{"phon"}], lambda w: len(w) >= 5, same)
    allowed = lambda src: {"checks": [], "expect": "code_after_questions", "auto": "allowed",  # noqa: E731
                           "expected_status": ["matched"] + ASK}
    run("two_errors", N_TWO, lambda w: [{"phon"}, {"key", "drop", "swap"}], lambda w: len(w) >= 7, allowed)
    ask = lambda src: {"checks": [], "expect": "code_after_questions", "auto": "forbidden",  # noqa: E731
                       "expected_status": list(ASK_OR_NOT_FOUND)}
    run("severe", N_SEVERE, lambda w: [{"phon"}, {"phon"}, {"key", "drop", "swap", "phon"}],
        lambda w: len(w) >= 6, ask)

    # примеры из постановки
    stul = next((c for c in g.ordered(sources, "stur") if (type_token(c) or (0, 0, ""))[2].lower() == "стул"), None)
    if stul:
        s, e, w = type_token(stul)
        out.append(g.derived(stul, "typos_human", put(stul["text"], s, e, w, "стур"), "user_example",
                             typo={"word": "стул", "typo": "стур", "distance": 1}))
    for text, meant in SEVERE_MANUAL:
        out.append(g.no_code("typos_human", g.split_of("typo|" + text), text, "user_example",
                             expected_status=list(ASK_OR_NOT_FOUND), category="tools",
                             typo={"word": meant, "typo": text, "distance": dl(text.split()[0], meant.split()[0])},
                             note="наименование «Отвертка» по базе не проверено: эталон пуст, код без подтверждения "
                                  "запрещён"))

    # неоднозначные: одна правка от двух разных слов-типов каталога
    heads = sorted({re.findall(r"[А-Яа-яЁё]+", n)[0].lower() for n in {c["name"] for c in natural}})
    amb = []
    for i, w1 in enumerate(heads):
        for w2 in heads[i + 1:]:
            if abs(len(w1) - len(w2)) > 1 or dl(w1, w2) != 2:
                continue
            for t in edits(w1, {"phon", "key", "drop", "swap"}) + [w1[:j] + c + w1[j + 1:] for j in range(len(w1))
                                                                     for c in "аеиоуы"]:
                if t not in (w1, w2) and dl(t, w1) == 1 and dl(t, w2) == 1 and not known(t):
                    amb.append((t, w1, w2))
    seen = set()
    for t, w1, w2 in sorted(set(amb), key=lambda x: g.rank("amb|" + x[0])):
        if t in seen:
            continue
        seen.add(t)
        out.append(g.no_code("typos_human", g.split_of("typo|" + t), t, "ambiguous",
                             expected_status=list(ASK), category=None,
                             typo={"word": f"{w1} | {w2}", "typo": t, "distance": 1}))
        if len(seen) == N_AMBIG:
            break

    for text in OUT_OF_SCOPE_TYPOS:
        out.append(g.no_code("typos_human", g.split_of("typo|" + text), text, "out_of_scope_typo", category=None))
    return out


# ---------------------------------------------------------------- ошибки в числах
LETTERS = {"0": ("о", "O"), "3": ("з",), "1": ("l",)}


def number_spots(c: dict) -> list[tuple]:
    """Числа фактов, найденные в тексте ровно один раз: с единицей (numeric_spots) и без неё."""
    g = _g()
    spots = g.numeric_spots(c)
    found = {id(f) for f, _ in spots}
    for f in c["facts"]:
        if f["kind"] != "number" or f["unit"] or id(f) in found:
            continue
        v = Decimal(f["value"])
        nums = "|".join(re.escape(x) for x in sorted({g.fmt(v, True), g.fmt(v, False)}, key=len, reverse=True))
        ms = list(re.finditer(rf"(?<![\d.,])({nums})(?![\d.,]?\d)", c["text"]))
        if len(ms) == 1:
            m = ms[0]
            spots.append((f, (m.start(), m.end(), m.group(1), "", "")))
    return spots


def _num_case(src, text, tag, f, num):
    g = _g()
    prop = f["property"].split(",")[0].lower()
    return g.derived(src, "number_errors", text, tag, auto="forbidden", expect="code_after_questions",
                     expected_status=list(NUM_ASK),
                     checks=[{"type": "no_feature", "property": prop, "value": g.fmt(Decimal(f["value"]), False)}],
                     number={"intended": g.fmt(Decimal(f["value"]), True), "written": num})


def build_numbers(sources: list[dict]) -> list[dict]:
    g = _g()
    out = []

    def run(tag, n, mutate):
        k = 0
        for src in g.ordered(sources, tag):
            for f, (s, e, num, *_r) in number_spots(src):
                bad = mutate(num, src["id"])
                if bad is None:
                    continue
                text = src["text"][:s] + bad + src["text"][s + len(num):]
                out.append(_num_case(src, text, tag, f, bad))
                k += 1
                break
            if k == n:
                break

    # «010» вместо «10», «0180» вместо «180»: ведущий ноль у целого — ошибка ввода (0,5 — не ошибка)
    run("leading_zero", N_LEAD, lambda n, _: "0" + n if n.isdigit() else None)

    def letter(n, key):
        pos = [i for i, ch in enumerate(n) if ch in LETTERS]
        if not pos:
            return None
        i = pos[g.rank(key + "let") % len(pos)]
        opts = LETTERS[n[i]]
        return n[:i] + opts[g.rank(key + "opt") % len(opts)] + n[i + 1:]
    run("letter_in_number", N_LETTER, letter)
    run("double_separator", N_SEP, lambda n, _: re.sub(r"([,.])", r"\1\1", n, count=1) if re.search(r"\d[,.]\d", n)
        else None)
    # «1 80»: группа из двух цифр после пробела — не разделитель тысяч
    run("bad_grouping", N_GROUP, lambda n, _: n[:-2] + " " + n[-2:] if n.isdigit() and len(n) >= 3 else None)
    return out
