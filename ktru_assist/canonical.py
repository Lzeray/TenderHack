"""Скрытая строка запроса «тип; ключ: значение; …» (docs/PARSE_INPUT_PLAN.md, P4).

Видимая строка — только для ввода: в ней исправляется лишь орфография. Поиск идёт по скрытой строке:
* тип и характеристики, разобранные из видимого текста, пересчитываются при каждом запросе («столешница» перед
  «лдсп» сразу даёт привязку) и записываются как «ключ: значение»; что нельзя записать так без потери смысла
  (габариты, подставленная единица, неоднозначное значение), записывается исходным фрагментом;
* решения пользователя — ответы на вопросы, выбор варианта, ручные правки и удаления — передаются в поиск точными
  ограничениями и живут, пока их фрагмент есть в видимом тексте (или всегда, если фрагмента нет). Поэтому
  дописанная характеристика не сбрасывает сделанные уточнения, а стёртый фрагмент убирает своё решение.
"""
from __future__ import annotations

import re
from typing import Callable

from .clarify import TYPE_PROP
from .models import Canonical, CanonItem, Constraint, Feature, SearchRequest, SearchResponse
from .nlp.normalize import Tracked
from .text import norm

VERSION = "1.0"
OPS = {"eq": "", "ne": "не ", "ge": "не менее ", "gt": "более ", "le": "не более ", "lt": "менее "}
# предупреждения видимого текста, которых нет в поиске по скрытой строке (слов, к которым они относятся, там нет)
VISIBLE_ISSUES = {"typo_ambiguous", "not_a_characteristic"}


def present(fragment: str | None, text: str) -> bool:
    """Фрагмент есть в видимом тексте целыми словами (без регистра и «ё»)."""
    if not fragment:
        return False
    return re.search(r"(?<!\w)" + re.escape(norm(fragment).strip()) + r"(?!\w)", norm(text)) is not None


def _evidence(f: Feature, original: str) -> str | None:
    if f.raw_span and 0 <= f.raw_span[0] < f.raw_span[1] <= len(original):
        return original[f.raw_span[0]:f.raw_span[1]]
    return f.evidence


def _clean(s: str) -> str:
    """Запятая и «;» в названиях и значениях КТРУ разделили бы скрытую строку на части."""
    return re.sub(r"\s+", " ", re.sub(r"[,;]", " ", s)).strip()


def render_feature(f: Feature) -> str | None:
    """«ключ: значение» для признака, который разбор прочитает обратно так же; иначе None (пишется фрагмент)."""
    if f.dims or f.bare or f.unit_inferred or f.property_inferred or f.from_type_name or not f.value:
        return None
    if f.status == "bound" and f.property_name:
        unit = f" {f.unit}" if f.unit else ""
        if f.op == "between":
            if not (f.min_inclusive and f.max_inclusive) or not f.value_to:
                return None
            return f"{_clean(f.property_name)}: от {f.value} до {f.value_to}{unit}"
        if f.op not in OPS:
            return None
        return f"{_clean(f.property_name)}: {OPS[f.op]}{_clean(f.value)}{unit}"
    if f.status == "unknown_property" and f.named_property and f.op == "eq":
        return f"{_clean(f.named_property)}: {_clean(f.value)}" + (f" {f.unit}" if f.unit else "")
    return None


def text_items(resp: SearchResponse, original: str) -> list[CanonItem]:
    out, seen = [], set()
    for f in resp.features:
        if f.source != "text" or f.status in ("removed", "overridden") or f.from_type_name:
            continue
        ev = _evidence(f, original)
        text = render_feature(f) or ev
        if not text or norm(text) in seen:
            continue
        seen.add(norm(text))
        out.append(CanonItem(source="text", key=f.property_name or f.named_property, value=f.value, text=text,
                             evidence=ev))
    return out


def _decision(c: Constraint, source: str, resp: SearchResponse, idx: int, original: str) -> CanonItem:
    """Решение пользователя: свойство — по признаку, который из него получился; фрагмент — текстовый признак,
    который оно заменило или удалило (выбор варианта «лдсп» помнит «лдсп»)."""
    if c.property == TYPE_PROP:
        return CanonItem(source=source, key="тип", value=c.value, text=f"тип: {c.value}", constraint=c)
    made = next((f for f in resp.features if f.id == f"{source[0]}{idx + 1}" and f.source == source), None)
    name = made.property_name if made is not None else None
    replaced = None
    for f in resp.features:
        if f.source != "text" or f.status not in ("overridden", "removed"):
            continue
        names = {norm(o.get("property_name") or "") for o in f.options} | {norm(f.property_name or "")}
        codes = {o.get("property_code") for o in f.options} | set(sum((o.get("codes", []) for o in f.options), [])) \
            | {f.property_code}
        if (name and norm(name) in names) or c.property in codes or norm(c.property) in names:
            replaced = f
            break
    key = name or (replaced.property_name if replaced is not None else None) or c.property
    if c.remove:
        text = f"{key}: удалено"
    elif c.op == "between":
        text = f"{key}: от {c.value} до {c.value_to}" + (f" {c.unit}" if c.unit else "")
    else:
        text = f"{key}: {OPS.get(c.op, '')}{c.value or ''}" + (f" {c.unit}" if c.unit else "")
    return CanonItem(source=source, key=key, value=c.value, text=text, constraint=c,
                     evidence=_evidence(replaced, original) if replaced is not None else None)


def corrected_text(original: str, resp: SearchResponse) -> str | None:
    """Видимая строка с исправленной орфографией: раскладка и однозначные опечатки; остальное не трогается."""
    text = original
    if any(h.get("step") == "раскладка" for h in resp.query.get("history", [])):
        t = Tracked(original)
        t.lower()
        if t.fix_layout():
            text = t.text
    for c in resp.corrections:
        if c.status != "corrected" or not c.corrected:
            continue
        def keep_case(m: re.Match, new=c.corrected) -> str:
            return new[:1].upper() + new[1:] if m.group(0)[:1].isupper() else new
        text = re.sub(r"(?<!\w)" + re.escape(c.original) + r"(?!\w)", keep_case, text, count=1, flags=re.I)
    return text if text != original else None


def process(req: SearchRequest, core, run: Callable[[SearchRequest], SearchResponse]) -> SearchResponse:
    """core — движок (разбор видимого текста), run — полный путь поиска (оркестратор)."""
    prev = req.canonical or Canonical()
    original = req.text
    # 1. видимый текст: разбор и привязка новых решений к фрагментам
    parsed = core.search(SearchRequest(text=original, corrections=req.corrections, overrides=req.overrides,
                                       answers=req.answers))
    decisions = [i for i in prev.items if i.source != "text" and i.constraint is not None
                 and (i.evidence is None or present(i.evidence, original))]
    new = [_decision(c, "answer", parsed, k, original) for k, c in enumerate(req.answers)] + \
          [_decision(c, "override", parsed, k, original) for k, c in enumerate(req.overrides)]
    for d in new:   # более новое решение о том же свойстве заменяет прежнее
        decisions = [x for x in decisions if not (x.constraint.property == d.constraint.property
                                                  or (x.key and d.key and norm(x.key) == norm(d.key)))]
        decisions.append(d)
    # фрагмент, о котором пользователь уже решил («лдсп» → «Вид материала столешницы: ЛДСП»), не повторяется
    decided = {norm(d.evidence) for d in decisions if d.evidence}
    items = [i for i in text_items(parsed, original) if not (i.evidence and norm(i.evidence) in decided)]
    search_text = "; ".join(x for x in [parsed.type_text] + [i.text for i in items] if x) or original
    # 2. поиск по скрытой строке; решения — точными ограничениями
    final = run(req.model_copy(update={
        "text": search_text, "canonical": None, "corrections": {}, "answers_query_hash": None,
        "answers": [d.constraint for d in decisions if d.source == "answer"],
        "overrides": [d.constraint for d in decisions if d.source == "override"]}))
    # 3. ответ: видимый текст, скрытая строка, фрагменты признаков — из видимого текста
    by_text = {norm(i.text): i for i in items}
    for f in final.features:
        if f.source == "text" and f.evidence:
            # фрагмент скрытой строки → фрагмент видимой: запись «ключ: значение» целиком или исходный фрагмент
            item = by_text.get(norm(f.evidence)) or next(
                (i for i in items if f.property_name and norm(i.text).startswith(norm(f.property_name) + ":")), None)
            if item is not None and item.evidence:
                f.evidence = item.evidence
            elif not present(f.evidence, original):
                f.evidence = None
            f.raw_span = None
    full = "; ".join(x for x in [parsed.type_text] + [i.text for i in items] + [d.text for d in decisions] if x)
    final.canonical = Canonical(type=parsed.type_text or None, items=items + decisions, text=full)
    final.query = {**final.query, "original": original, "canonical": full, "search_text": search_text}
    final.corrections = parsed.corrections
    final.unrecognized = parsed.unrecognized
    final.corrected_text = corrected_text(original, parsed)
    have = {(i.code, i.message) for i in final.issues}
    final.issues += [i for i in parsed.issues if i.code in VISIBLE_ISSUES and (i.code, i.message) not in have]
    return final


__all__ = ["process", "present", "render_feature", "text_items", "corrected_text", "VERSION"]
