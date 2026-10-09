"""Сквозной конвейер: описание → характеристики → кандидаты → уточнение → конечный код."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from . import __version__
from .catalog.repository import Catalog, Position
from .clarify import TYPE_PROP, choose_question
from .config import ROOT, VERSIONS, Settings
from .models import (Candidate, Completeness, Constraint, DomainProperty, Feature, Issue, SearchRequest,
                     SearchResponse, Stage, Step)
from .units import BY_KEY
from .nlp.extract import Extractor, PropGroup, build_groups
from .nlp.normalize import normalize
from .nlp.typos import TypoCorrector
from .rank import components, name_match, term_coverage
from .search.base import SearchBackend
from .text import fuzzy_equal, lemma, norm, tokenize
from .validate import evaluate

PREPOSITIONS = {"для", "от", "на", "под", "с", "со", "из", "к", "по", "в", "во", "без"}
MAX_CANDIDATES_OUT = 100


def load_aliases(path: Path = ROOT / "data" / "aliases.json") -> dict[str, str]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {lemma(k): v for k, v in raw["aliases"].items()}


class Engine:
    def __init__(self, catalog: Catalog, backend: SearchBackend, settings: Settings):
        self.catalog = catalog
        self.backend = backend
        self.settings = settings
        self.typos = TypoCorrector(catalog.vocabulary_texts())
        docs = catalog.search_documents()
        self.head_vocab = sorted({h for d in docs if d["active"] for h in d["head_parts"]})
        self.aliases = load_aliases()
        self.known_terms = catalog.property_core_terms()

    # ------------------------------------------------------------------
    def versions(self) -> dict[str, str]:
        v = dict(VERSIONS)
        v["package"] = __version__
        v["catalog_snapshot"] = str(self.catalog.meta.get("snapshot"))
        v["catalog_as_of"] = str(self.catalog.meta.get("as_of"))
        v["search_backend"] = self.backend.name
        return v

    def _detect_heads(self, nq) -> tuple[list[str], list[str]]:
        found: list[tuple[int, str, bool]] = []
        for t in nq.tokens:
            if t.kind != "word" or not t.significant:
                continue
            lem = self.aliases.get(t.lemma, t.lemma)
            exact = [h for h in self.head_vocab if h == lem]
            heads = exact or [h for h in self.head_vocab if fuzzy_equal(h, lem)]
            prev = nq.tokens[t.i - 1].lemma if t.i > 0 else ""
            for h in heads:
                found.append((t.i, h, prev in PREPOSITIONS))
        main = sorted({h for _, h, after_prep in found if not after_prep})
        mods = sorted({h for _, h, after_prep in found if after_prep} - set(main))
        if not main and mods:
            main, mods = mods, []
        return main, mods

    # ------------------------------------------------------------------
    def search(self, req: SearchRequest) -> SearchResponse:
        t0 = time.perf_counter()
        issues: list[Issue] = []
        stages: list[Stage] = []
        nq = normalize(req.text)
        corrections = self.typos.correct(nq.tokens, req.corrections)
        if corrections:
            fixed = [c for c in corrections if c.corrected]
            if fixed:
                nq.history.append(Step(step="опечатки", before=nq.text,
                                       after=" ".join(t.text for t in nq.tokens),
                                       note=", ".join(f"{c.original}→{c.corrected}" for c in fixed)))
            for c in corrections:
                if c.status == "ambiguous":
                    issues.append(Issue(level="warning", code="typo_ambiguous",
                                        message=f"«{c.original}»: несколько вариантов исправления "
                                                f"({', '.join(c.options)}) — выберите вариант"))
        alias_terms = []
        for t in nq.tokens:
            if t.kind == "word" and t.lemma in self.aliases:
                alias_terms.append(self.aliases[t.lemma])
                nq.history.append(Step(step="алиас", before=t.text, after=self.aliases[t.lemma],
                                       note="проверенный алиас из data/aliases.json"))
        terms = nq.lemmas() + alias_terms
        qhash = hashlib.sha256(" ".join(t.lemma for t in nq.tokens).encode()).hexdigest()[:16]
        answers = list(req.answers)
        if answers and req.answers_query_hash and req.answers_query_hash != qhash:
            issues.append(Issue(level="warning", code="stale_answers",
                                message="Описание изменилось — прежние ответы на уточнения не применены"))
            answers = []

        top_k = req.top_k or self.settings.top_k
        res_a = self.backend.search(terms, top_k)
        stages.append(Stage(stage="поиск по названию и словоформам", remaining=len(res_a.hits),
                            note=f"{self.backend.name}: найдено {res_a.total}, показано top-{top_k}"))
        heads, modifiers = self._detect_heads(nq)
        # тип, выбранный вручную, задаёт главное слово
        type_choice = next((c for c in [*req.overrides, *answers] if c.property == TYPE_PROP and not c.remove), None)
        if type_choice is not None:
            chosen = self.catalog.get(type_choice.value or "")
            if chosen is not None and chosen.head:
                heads = [chosen.head]
            else:
                h = self._head_of_name(type_choice.value or "")
                if h:
                    heads = [h]
        if modifiers:
            issues.append(Issue(level="info", code="modifier_heads",
                                message=f"Слова после предлога не считаются типом товара: {', '.join(modifiers)}"))
        base = dict(query={"original": req.text, "normalized": nq.text, "history": [h.model_dump() for h in nq.history],
                           "terms": terms}, query_hash=qhash, corrections=corrections, versions=self.versions())
        if not heads:
            sugg = self.catalog.get_many([h.code for h in res_a.hits[:5]])
            names = sorted({p.name for p in sugg.values()})
            msg = "Тип товара не распознан среди направлений MVP (одежда, мебель, инструменты)."
            if names:
                msg += " Ближайшие по словам наименования: " + "; ".join(names)
            return SearchResponse(status="not_found", message=msg, features=[], unrecognized=self._unrecognized(nq),
                                  detected_types=[], candidates=[], candidates_total=0, stages=stages,
                                  issues=issues, completeness=Completeness(
                                      backend=self.backend.name, retrieval_total_hits=res_a.total,
                                      retrieval_returned=len(res_a.hits), retrieval_complete=res_a.complete,
                                      type_domain_total=0, type_domain_returned=0, type_domain_complete=False,
                                      type_confirmed=False, note="тип товара не определён"),
                                  elapsed_ms=round((time.perf_counter() - t0) * 1000, 2), **base)

        res_b = self.backend.by_heads(heads, self.settings.type_fetch_limit)
        domain = self.catalog.get_many([h.code for h in res_b.hits])
        scores = {h.code: h.score for h in res_a.hits}
        positions = [domain[c] for c in sorted(domain)]
        inactive = self.catalog.inactive_count_by_heads(heads)
        stages.append(Stage(stage=f"все активные позиции типа «{', '.join(heads)}»", remaining=len(positions),
                            note=f"исчерпывающая выборка по главному слову ({res_b.total} в индексе); "
                                 f"неактивных/вне срока исключено: {inactive}"))
        if not res_b.complete:
            issues.append(Issue(level="warning", code="domain_truncated",
                                message=f"Позиций типа больше лимита {self.settings.type_fetch_limit}: "
                                        "проверена не вся область"))

        # --- тип по наименованию ---------------------------------------------
        type_confirmed = False
        q_lemmas = [t.lemma for t in nq.tokens if t.kind in ("word", "code")] + alias_terms
        if type_choice is not None:
            v = type_choice.value or ""
            sel = [p for p in positions if p.code == v or norm(p.name) == norm(v)]
            if sel:
                stages.append(Stage(stage="тип выбран пользователем", remaining=len(sel),
                                    removed=len(positions) - len(sel), note=v))
                positions, type_confirmed = sel, True
            else:
                issues.append(Issue(level="warning", code="type_choice_unknown",
                                    message=f"Выбранный тип «{v}» не найден в области поиска"))
        if not type_confirmed:
            by_name: dict[str, list[Position]] = {}
            for p in positions:
                by_name.setdefault(p.name, []).append(p)
            full = []
            for nm, ps in by_name.items():
                tier, cov, _ = name_match(ps[0], q_lemmas)
                if tier == 3:
                    full.append((len(set(ps[0].name_lemmas)), nm))
            if full:
                top = max(n for n, _ in full)
                names = sorted(nm for n, nm in full if n == top)
                sel = [p for p in positions if p.name in names]
                if len(sel) < len(positions):
                    stages.append(Stage(stage="тип по наименованию", remaining=len(sel),
                                        removed=len(positions) - len(sel),
                                        note="все слова наименования есть в описании: " + "; ".join(names)))
                positions = sel
                type_confirmed = len(names) == 1
            elif len(by_name) == 1:
                type_confirmed = True

        groups = build_groups(positions)
        domain_name_lemmas = {l for p in positions for l in p.name_lemmas}
        extractor = Extractor(groups, self.known_terms - domain_name_lemmas)
        features = extractor.extract(nq)
        features = self._apply_constraints(features, req.overrides, "override", groups, issues)
        features = self._apply_constraints(features, [a for a in answers if a.property != TYPE_PROP], "answer",
                                           groups, issues)
        for f in features:
            if f.status == "ambiguous":
                issues.append(Issue(level="warning", code="feature_ambiguous",
                                    message=f"«{f.evidence}»: {f.note}"))
            elif f.status == "unknown_property" and f.source == "text":
                issues.append(Issue(level="warning", code="unknown_property",
                                    message=f"«{f.evidence}»: {f.note}"))
        # слова наименований области считаются объяснёнными типом
        name_lemmas = {l for p in positions for l in p.name_lemmas}
        for t in nq.tokens:
            if t.used_by is None and t.kind in ("word", "code") and any(fuzzy_equal(t.lemma, n) for n in name_lemmas):
                t.used_by = "type"

        # --- проверка кандидатов ------------------------------------------------
        evals = {p.code: evaluate(p, features) for p in positions}
        ranked = []
        cand_out: list[Candidate] = []
        for p in positions:
            ev = evals[p.code]
            tier, ncov, matched = name_match(p, q_lemmas)
            ok_ids = {c.feature_id for c in ev.checks if c.status == "valid" and c.feature_id}
            tcov = term_coverage(nq.tokens, matched, ok_ids)
            rc, key = components(p, tier, ncov, tcov, ev.valid, ev.unknown, scores.get(p.code))
            compatible = ev.invalid == 0
            c = Candidate(code=p.code, name=p.name, version=p.version, okpd2=p.okpd2_code, category=p.category,
                          is_template=p.is_template, active=p.active, parent_code=p.parent_code,
                          no_new_features=p.no_new_features, compatible=compatible,
                          excluded_reason="; ".join(ev.invalid_reasons) if not compatible else None,
                          rank_components=rc, checks=ev.checks)
            ranked.append((key, c, p))
        ranked.sort(key=lambda x: x[0])
        compatible = [(k, c, p) for k, c, p in ranked if c.compatible]
        n_invalid = len(ranked) - len(compatible)
        stages.append(Stage(stage="проверка характеристик", remaining=len(compatible), removed=n_invalid,
                            note="исключены позиции с противоречием (invalid)"))
        finals = [(k, c, p) for k, c, p in compatible if not p.is_template]
        templates = len(compatible) - len(finals)
        stages.append(Stage(stage="только конечные позиции", remaining=len(finals), removed=templates,
                            note="укрупнённые позиции (шаблоны) не являются конечным результатом"))
        for i, (_, c, _) in enumerate(finals, 1):
            c.rank = i
        out = [c for _, c, _ in finals][:MAX_CANDIDATES_OUT]
        out += [c for _, c, p in compatible if p.is_template][:20]
        out += [c for _, c, _ in ranked if not c.compatible][:30]

        # --- решение ------------------------------------------------------------
        blocking_feats = [f for f in features if f.status == "ambiguous"] + \
            [None for c in corrections if c.status == "ambiguous"]
        constrained = {" ".join(tokenize(f.property_name)) for f in features
                       if f.status == "bound" and f.property_name}
        final_code = final_name = None
        question = None
        completeness = Completeness(
            backend=self.backend.name, retrieval_total_hits=res_a.total, retrieval_returned=len(res_a.hits),
            retrieval_complete=res_a.complete, type_domain_total=res_b.total, type_domain_returned=len(res_b.hits),
            type_domain_complete=res_b.complete, type_confirmed=type_confirmed,
            note="область = все активные позиции с тем же главным словом наименования; "
                 "top-K поиска используется только для выбора типа")
        finals_pos = [p for _, _, p in finals]
        if not finals:
            if positions and n_invalid:
                reasons = sorted({r for _, c, _ in ranked if c.excluded_reason for r in [c.excluded_reason]})[:5]
                status, message = "conflict", ("Все позиции типа противоречат описанию. Причины: " + " | ".join(reasons))
            elif templates:
                status, message = "conflict", "Совместимы только укрупнённые позиции (шаблоны) — конечного кода нет"
            else:
                status, message = "not_found", "Подходящих позиций не найдено"
        else:
            single = len(finals) == 1
            ev = evals[finals[0][2].code]
            ambiguous_feature = next((f for f in features if f.status == "ambiguous"), None)
            if single and type_confirmed and res_b.complete and not blocking_feats and not ev.blocking:
                status = "matched"
                final_code, final_name = finals[0][2].code, finals[0][2].name
                message = (f"Определена конечная позиция {final_code}: все условия проверены в полной области "
                           f"типа ({len(positions)} поз.)")
            else:
                if ambiguous_feature is not None and ambiguous_feature.options:
                    question = self._feature_question(ambiguous_feature, len(finals))
                else:
                    req_unknown = []
                    if single:
                        p = finals_pos[0]
                        req_unknown = [p.props[c.property_code] for c in ev.checks
                                       if c.status == "unknown" and c.required and c.property_code in p.props]
                    question = choose_question(finals_pos, constrained, type_confirmed, req_unknown)
                if question is not None and question.kind == "manual_choice":
                    status = "manual_choice"
                    message = question.text
                else:
                    status = "clarification_needed"
                    parts = [f"Совместимых конечных позиций: {len(finals)}"]
                    if single:
                        parts.append(f"лидирует {finals[0][2].code}, но код ещё не подтверждён")
                    if not type_confirmed:
                        parts.append("тип товара не подтверждён")
                    if blocking_feats:
                        parts.append("есть неоднозначности в описании")
                    if single and ev.blocking:
                        parts.append("не проверено: " + "; ".join(ev.blocking[:3]))
                    message = ". ".join(parts)
        return SearchResponse(
            status=status, message=message, features=features, unrecognized=self._unrecognized(nq),
            detected_types=heads, candidates=out, candidates_total=len(ranked), stages=stages, question=question,
            properties=[DomainProperty(code=g.codes[0], codes=g.codes, name=g.name, required=g.required,
                                       numeric=g.numeric, boolean=g.boolean,
                                       units=sorted(BY_KEY[k].title for k in g.unit_keys),
                                       values=sorted(g.quality.values())[:50], positions=g.positions)
                        for g in sorted(groups.values(), key=lambda g: (-g.positions, g.key))],
            final_code=final_code, final_name=final_name, issues=issues, completeness=completeness,
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 2), **base)

    # ------------------------------------------------------------------
    def _head_of_name(self, name: str) -> str | None:
        from .text import head_lemma
        return head_lemma(name)

    @staticmethod
    def _unrecognized(nq) -> list[str]:
        return [t.text for t in nq.tokens if t.used_by is None and (t.significant or t.kind == "number")]

    @staticmethod
    def _feature_question(f: Feature, n: int):
        from .models import Question, QuestionOption
        opts = []
        for o in f.options:
            value = o.get("value", f.value)
            opts.append(QuestionOption(label=o["property_name"] + (f" = {value}" if "value" in o else ""),
                                       remaining=n, answer=Constraint(
                                           property=o["property_code"], op=f.op, value=value, value_to=f.value_to,
                                           min_inclusive=f.min_inclusive, max_inclusive=f.max_inclusive,
                                           unit=f.unit)))
        return Question(kind="property", text=f"К какому свойству относится «{f.evidence}»?",
                        worst_case_remaining=n, current_remaining=n, options=opts,
                        reason="значение из описания нельзя однозначно привязать к свойству")

    def _apply_constraints(self, features: list[Feature], cons: list[Constraint], source: str,
                           groups: dict[str, PropGroup], issues: list[Issue]) -> list[Feature]:
        for k, c in enumerate(cons):
            if c.property == TYPE_PROP:
                continue
            g = self._resolve_group(c.property, groups)
            for f in features:
                same = g is not None and f.property_name and " ".join(tokenize(f.property_name)) == g.key
                if same and f.status == "bound":
                    f.status = "removed" if c.remove else "overridden"
                    f.note = (f.note + "; " if f.note else "") + (
                        "удалено пользователем" if c.remove else
                        ("переопределено вручную" if source == "override" else "заменено ответом на уточнение"))
                # ответ на вопрос о неоднозначном признаке снимает неоднозначность
                if f.status == "ambiguous" and g is not None and any(o.get("property_name") == g.name
                                                                      for o in f.options) and \
                        (f.value or "").replace(",", ".") == (c.value or "").replace(",", "."):
                    f.status = "overridden"
                    f.note += "; привязано пользователем"
            if c.remove:
                continue
            if g is None:
                issues.append(Issue(level="warning", code="unknown_property",
                                    message=f"Свойство «{c.property}» отсутствует у позиций области поиска"))
                features.append(Feature(id=f"{source[0]}{k + 1}", source=source, status="unknown_property",
                                        property_name=c.property, op=c.op, value=c.value, value_to=c.value_to,
                                        unit=c.unit, note="свойство не найдено"))
                continue
            features.append(Feature(id=f"{source[0]}{k + 1}", source=source, status="bound",
                                    property_code=g.codes[0], property_name=g.name, op=c.op, value=c.value,
                                    value_to=c.value_to, min_inclusive=c.min_inclusive,
                                    max_inclusive=c.max_inclusive, unit=c.unit,
                                    note="ручное редактирование (приоритет над текстом)" if source == "override"
                                    else "ответ на уточняющий вопрос"))
        return features

    @staticmethod
    def _resolve_group(prop: str, groups: dict[str, PropGroup]) -> PropGroup | None:
        for g in groups.values():
            if prop in g.codes:
                return g
        key = " ".join(tokenize(prop))
        return groups.get(key)
