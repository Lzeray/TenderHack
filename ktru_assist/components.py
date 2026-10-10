"""Части товара и канонические ключи «компонент.свойство».

Компонент свойства КТРУ определяется по словам его названия: «Цвет каркаса» → frame,
«Материал обивки сиденья» → seat (последний упомянутый компонент — владелец свойства,
«обивка сиденья» относится к сиденью). Канонический ключ — внутренняя сущность
(«frame.цвет»): он не доказывает одинаковую семантику одноимённых свойств разных позиций,
привязка к КТРУ по-прежнему идёт через код и название свойства.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .config import ROOT
from .text import content_lemmas, fuzzy_equal, lemma, lemma_set

GENERIC = lemma_set({"наличие", "вид", "тип", "функция", "возможность", "количество", "показатель", "конструкция",
                     "значение", "характеристика", "исполнение"})


@lru_cache(maxsize=1)
def lexicon() -> dict[str, str]:
    raw = json.loads((ROOT / "data" / "components.json").read_text(encoding="utf-8"))
    return {lemma(k): v for k, v in raw["components"].items()}


def components_version() -> str:
    raw = json.loads((ROOT / "data" / "components.json").read_text(encoding="utf-8"))
    return raw["version"]


@lru_cache(maxsize=100_000)
def component_of_lemma(lem: str) -> str | None:
    lx = lexicon()
    if lem in lx:
        return lx[lem]
    for k, v in lx.items():
        if fuzzy_equal(k, lem):
            return v
    return None


@lru_cache(maxsize=50_000)
def property_component(name: str) -> str | None:
    """Компонент из названия свойства: последний упомянутый («Материал обивки сиденья» → seat)."""
    comps = [c for c in (component_of_lemma(l) for l in content_lemmas(name)) if c]
    return comps[-1] if comps else None


@lru_cache(maxsize=50_000)
def canonical_key(name: str, core: str | None) -> str:
    comp = property_component(name)
    lems = [l for l in content_lemmas(name) if l not in GENERIC and component_of_lemma(l) is None]
    prop = core if core and component_of_lemma(core) is None else (lems[0] if lems else (core or name.lower()))
    return f"{comp}.{prop}" if comp else prop
