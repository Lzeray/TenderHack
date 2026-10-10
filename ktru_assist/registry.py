"""Реестр типов товаров: группы (направления) → виды (главные слова) → наименования позиций.

Группа и тип — разные уровни: «мебель» не заменяет «стул» или «шкаф».

Источники реестра:
* каталог — главные слова и наименования всех позиций направлений MVP (полный охват);
* `data/aliases.json` — проверенные алиасы типа. Значение алиаса — главное слово или список
  главных слов. Список означает разговорное слово с несколькими трактовками («сидушка»):
  такой тип не подтверждается автоматически, пользователь выбирает вариант.
  Ключ из нескольких слов («угловая шлифовальная машина») сопоставляется по последовательности лемм.

Определение типа детерминированное: главное слово наименования КТРУ в описании (с допуском
одной правки для длинных слов) или алиас. Слова после предлога считаются уточнением, а не типом.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import CATEGORIES, ROOT
from .text import content_lemmas, fuzzy_equal, lemma

PREPOSITIONS = {"для", "от", "на", "под", "с", "со", "из", "к", "по", "в", "во", "без"}


@dataclass
class TypeAlias:
    key: tuple[str, ...]          # леммы
    targets: list[str]            # главные слова
    note: str = ""

    @property
    def ambiguous(self) -> bool:
        return len(self.targets) > 1


@dataclass
class TypeDetection:
    heads: list[str]
    modifiers: list[str]
    basis: list[str] = field(default_factory=list)
    alias_terms: list[str] = field(default_factory=list)          # все цели алиасов (для поиска)
    unique_alias_terms: list[str] = field(default_factory=list)   # цели однозначных алиасов (для типа)
    ambiguous_aliases: list[str] = field(default_factory=list)   # исходные слова с несколькими трактовками
    alias_token_idx: set[int] = field(default_factory=set)
    type_token_idx: set[int] = field(default_factory=set)          # слова, по которым распознан составной тип


def load_aliases(path: Path = ROOT / "data" / "aliases.json") -> list[TypeAlias]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for k, v in raw["aliases"].items():
        targets = [v] if isinstance(v, str) else list(v)
        key = tuple(content_lemmas(k)) or (lemma(k),)
        out.append(TypeAlias(key, targets))
    # длинные ключи раньше коротких: «угловая шлифмашина» важнее «шлифмашина»
    return sorted(out, key=lambda a: (-len(a.key), a.key))


class TypeRegistry:
    def __init__(self, documents: list[dict], aliases: list[TypeAlias] | None = None):
        self.aliases = aliases if aliases is not None else load_aliases()
        self.heads: dict[str, dict] = {}      # главное слово → {category, names, finals, templates}
        self.names: dict[str, dict] = {}      # наименование → {head, category, finals, templates}
        for d in documents:
            if not d["active"]:
                continue
            for h in d["head_parts"]:
                e = self.heads.setdefault(h, {"categories": set(), "names": set(), "finals": 0, "templates": 0})
                e["categories"].add(d["category"])
                e["names"].add(d["name"])
                e["templates" if d["is_template"] else "finals"] += 1
            n = self.names.setdefault(d["name"], {"head": d["head"], "category": d["category"], "finals": 0,
                                                  "templates": 0})
            n["templates" if d["is_template"] else "finals"] += 1
        self.head_vocab = sorted(self.heads)

    # ------------------------------------------------------------------
    def group_of(self, head: str) -> list[str]:
        cats = self.heads.get(head, {}).get("categories", set())
        return sorted(CATEGORIES[c]["title"] for c in cats if c in CATEGORIES)

    def type_names(self) -> list[str]:
        return sorted(n for n, e in self.names.items() if e["finals"])

    def _alias_hits(self, tokens) -> list[tuple[list[int], TypeAlias]]:
        words = [t for t in tokens if t.kind == "word"]
        hits, used = [], set()
        for a in self.aliases:
            n = len(a.key)
            for k in range(len(words) - n + 1):
                seq = words[k:k + n]
                if any(t.i in used for t in seq):
                    continue
                if all(t.lemma == key for t, key in zip(seq, a.key)):
                    idx = [t.i for t in seq]
                    hits.append((idx, a))
                    used.update(idx)
        return hits

    def _compound(self, t, tokens) -> list[str]:
        """Тип по составу слова, без словаря синонимов.

        1. Слово через дефис: «дрель-шуруповерт», «вешалка-стойка» — части как кандидаты в тип.
        2. Сложное слово каталога = начало соседнего слова + слово запроса:
           «лобзик электрический» → «электро|лобзик», «машина шлифовальная» → «шлиф|машин(а)».
        3. Сложное слово запроса = начало слова наименования + тип каталога: «электро|лобзик» → «лобзик»,
           если у позиций этого типа есть слово, начинающееся так же.
        Соединительная гласная «о/е» допускается; части не короче 3–4 букв.
        """
        lem = t.lemma
        if "-" in lem:
            parts = [p for p in lem.split("-") if p in self.heads]
            if parts:
                return sorted(set(parts)), {t.i}
        near = [(j, tokens[j].lemma) for j in range(max(0, t.i - 2), min(len(tokens), t.i + 3))
                if j != t.i and tokens[j].kind == "word" and len(tokens[j].lemma) >= 3]
        out, used = set(), set()
        stems = {lem[:k] for k in range(len(lem), max(3, len(lem) - 2), -1)}
        for h in self.head_vocab:
            if "-" in h or len(h) < 6:
                continue
            for s in stems:                                  # 2: тип каталога сложнее слова запроса
                if len(s) >= 4 and h.endswith(s) and len(h) - len(s) >= 3:
                    p = h[: len(h) - len(s)]
                    p = p[:-1] if p[-1] in "ое" and len(p) > 3 else p
                    hit = [j for j, w in near if w.startswith(p)]
                    if hit:
                        out.add(h)
                        used.update([t.i, hit[0]])
            if len(lem) > len(h) + 2 and lem.endswith(h) and len(h) >= 4:   # 3: запрос сложнее типа
                p = lem[: len(lem) - len(h)]
                p = p[:-1] if p[-1] in "ое" and len(p) > 3 else p
                words = {w for n in self.heads[h]["names"] for w in content_lemmas(n)}
                if len(p) >= 3 and any(w.startswith(p) for w in words):
                    out.add(h)
                    used.add(t.i)
        return sorted(out), used

    def detect(self, tokens) -> TypeDetection:
        """Главные слова типа в описании: (основные, после предлога)."""
        found: list[tuple[int, str, bool]] = []
        det = TypeDetection([], [])
        alias_at: dict[int, TypeAlias] = {}
        for idx, a in self._alias_hits(tokens):
            alias_at[idx[0]] = a
            det.alias_token_idx.update(idx)
            if a.ambiguous:
                det.ambiguous_aliases.append(" ".join(tokens[i].text for i in idx))
        for t in tokens:
            if t.kind != "word" or not t.significant:
                continue
            prev = tokens[t.i - 1].lemma if t.i > 0 else ""
            after_prep = prev in PREPOSITIONS
            if t.i in alias_at:
                a = alias_at[t.i]
                det.alias_terms.extend(a.targets)
                if not a.ambiguous:
                    det.unique_alias_terms.extend(a.targets)
                for h in a.targets:
                    if h in self.heads:
                        found.append((t.i, h, after_prep))
                det.basis.append(f"алиас «{t.text}» → {', '.join(a.targets)}"
                                 + (" (несколько трактовок)" if a.ambiguous else ""))
                continue
            if t.i in det.alias_token_idx:
                continue
            exact = [h for h in self.head_vocab if h == t.lemma]
            heads = exact or [h for h in self.head_vocab if fuzzy_equal(h, t.lemma)]
            how = "главное слово"
            if not heads:
                heads, used, how = *self._compound(t, tokens), "составное слово"
                det.alias_terms.extend(heads)
                det.type_token_idx.update(used)
                if len(heads) == 1:
                    det.unique_alias_terms.extend(heads)
                elif heads:
                    # «дрель-шуруповерт», «вешалка-стойка»: несколько типов — подтверждает пользователь
                    det.ambiguous_aliases.append(t.text)
            for h in heads:
                found.append((t.i, h, after_prep))
            if heads:
                det.basis.append(f"{how} «{t.text}» → {', '.join(heads)}")
        main = sorted({h for _, h, after_prep in found if not after_prep})
        mods = sorted({h for _, h, after_prep in found if after_prep} - set(main))
        # Слова после предлога («утюг с паром», «подставка для паяльника») описывают назначение или
        # материал, а не тип: если основного типа нет, тип не распознан — честнее, чем подставить другой.
        det.heads, det.modifiers = main, mods
        return det
