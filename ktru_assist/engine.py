"""Сквозной конвейер: описание → характеристики → кандидаты → уточнение → конечный код.

Ядро детерминированное. Признаки моделей (A-semantic, B-llm) приходят снаружи через
`model_features` / `model_type` как гипотезы: они участвуют в пересчёте, но автоматическое
завершение с ними невозможно без подтверждения пользователя (см. resolver.py).
"""
from __future__ import annotations

import hashlib
import time
from fractions import Fraction

from . import __version__
from .catalog.repository import Catalog, Position
from .catalog.scope import CatalogScope, identity_groups
from .clarify import TYPE_PROP, choose_question
from .components import components_version
from .config import VERSIONS, Settings
from .models import (Candidate, CharacteristicsCompletion, CodeResolution, Completeness, Constraint,
                     DomainProperty, Feature, Issue, Predicate, Question, QuestionOption, RawAssertion,
                     Scope, SearchRequest, SearchResponse, Span, Stage, Step)
from .nlp.extract import Extractor, PropGroup, build_groups, value_aliases_version
from .nlp.normalize import NormalizedQuery, normalize
from .nlp.typos import TypoCorrector
from .plausibility import check as plausibility_check, rules_version as plausibility_version
from . import empirical, suspicious
from .rank import components, name_match, term_coverage
from .registry import TypeDetection, TypeRegistry
from .resolver import describe, merge_model_features
from .search.base import Hit, SearchBackend, SearchResult
from .text import MORPH_MODE, fuzzy_equal, lemma, norm, tokenize
from .units import BY_KEY
from .validate import check_feature, evaluate

MAX_CANDIDATES_OUT = 100
PREFERENCE_WORDS = {"желательно", "предпочтительно", "желательный", "предпочтительный"}
REQUIREMENT_WORDS = {"нужный", "нужно", "нужен", "требоваться", "требуется", "должный", "должен", "необходимый"}


class Engine:
    def __init__(self, catalog: Catalog, backend: SearchBackend, settings: Settings):
        self.catalog = catalog
        self.backend = backend
        self.settings = settings
        self.native = settings.recognition_mode in ("semantic", "hybrid")
        # уровень 2: статистика выгрузок; без файла или с другим снимком КТРУ — not_assessed с причиной
        self.ste_stats = None if self.native else empirical.SteStats(settings.ste_stats_path,
                                                                     catalog.meta.get("snapshot"))
        self.catalog_scope = CatalogScope(catalog)
        self.typos = None if self.native else TypoCorrector(catalog.vocabulary_texts())
        self.registry = None if self.native else TypeRegistry(catalog.search_documents())
        self.head_vocab = [] if self.native else self.registry.head_vocab
        self._head_set = frozenset(self.head_vocab)
        self.known_terms = set() if self.native else catalog.property_core_terms()

    # ------------------------------------------------------------------
    def versions(self) -> dict[str, str]:
        v = dict(VERSIONS)
        v["package"] = __version__
        v["catalog_snapshot"] = str(self.catalog.meta.get("snapshot"))
        v["catalog_as_of"] = str(self.catalog.meta.get("as_of"))
        v["search_backend"] = self.backend.name
        v["recognition_mode"] = self.settings.recognition_mode
        v["morph"] = MORPH_MODE
        v["suspicious"] = suspicious.VERSION
        v["ste_stats"] = (self.ste_stats.version or "—") if self.ste_stats and self.ste_stats.available else             f"off: {self.ste_stats.reason if self.ste_stats else 'native'}"
        if not self.native:
            v["components_lexicon"] = components_version()
            v["value_aliases"] = value_aliases_version()
            v["plausibility_rules"] = plausibility_version()
        return v

    @property
    def effective_at(self) -> str | None:
        a = self.catalog.meta.get("as_of")
        return str(a) if a else None

    # ------------------------------------------------------------------
    def search(self, req: SearchRequest, model_features: list[Feature] | None = None,
               model_type: str | None = None, candidate_codes: list[str] | None = None,
               search_features: list[Feature] | None = None, scope_verified: bool = False) -> SearchResponse:
        t0 = time.perf_counter()
        tm: dict[str, float] = {}

        def lap(name: str, since: float) -> float:
            now = time.perf_counter()
            tm[name] = round((now - since) * 1000, 2)
            return now

        issues: list[Issue] = []
        stages: list[Stage] = []
        nq = NormalizedQuery(req.text, req.text, [], offsets=[(i, i + 1) for i in range(len(req.text))]) if self.native else normalize(req.text)
        corrections = [] if self.native else self.typos.correct(nq.tokens, req.corrections, type_heads=self._head_set)
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
        det = TypeDetection(["catalog"], []) if self.native else self.registry.detect(nq.tokens)
        alias_terms = det.alias_terms
        for b in det.basis:
            if b.startswith("алиас"):
                nq.history.append(Step(step="алиас", before=b.split("«")[1].split("»")[0],
                                       after=b.split("→ ")[-1], note="проверенный алиас из data/aliases.json"))
        for a in det.ambiguous_aliases:
            issues.append(Issue(level="warning", code="type_alias_ambiguous",
                                message=f"«{a}» допускает несколько типов товара — тип нужно подтвердить"))
        terms = nq.lemmas() + alias_terms
        qhash = hashlib.sha256((req.text if self.native else " ".join(t.lemma for t in nq.tokens)).encode()).hexdigest()[:16]
        answers = list(req.answers)
        if answers and req.answers_query_hash and req.answers_query_hash != qhash:
            issues.append(Issue(level="warning", code="stale_answers",
                                message="Описание изменилось — прежние ответы на уточнения не применены"))
            answers = []
        t = lap("normalize", t0)

        top_k = req.top_k or self.settings.top_k
        res_a = SearchResult([], 0, "semantic") if self.native else self.backend.search(terms, top_k)
        stages.append(Stage(stage="поиск по названию и словоформам", remaining=len(res_a.hits),
                            note=f"{self.backend.name}: найдено {res_a.total}, показано top-{top_k}"))
        heads, modifiers = det.heads, det.modifiers
        type_basis = list(det.basis)
        # тип, выбранный вручную, задаёт главное слово
        type_choice = next((c for c in [*req.overrides, *answers] if c.property == TYPE_PROP and not c.remove), None)
        type_tentative = False
        if not self.native and type_choice is None and model_type:
            type_choice = Constraint(property=TYPE_PROP, value=model_type)
            type_tentative = True
        if type_choice is not None:
            chosen = None if self.native else self.catalog.get(type_choice.value or "")
            h = "catalog" if self.native else (chosen.head if chosen is not None and chosen.head else self._head_of_name(type_choice.value or ""))
            if h:
                heads = [h]
                type_basis.append(("предложен моделью: " if type_tentative else "выбран пользователем: ")
                                  + (type_choice.value or ""))
        if modifiers:
            issues.append(Issue(level="info", code="modifier_heads",
                                message=f"Слова после предлога не считаются типом товара: {', '.join(modifiers)}"))
        base = dict(query={"original": req.text, "normalized": nq.text, "history": [h.model_dump() for h in nq.history],
                           "terms": terms}, query_hash=qhash, corrections=corrections, versions=self.versions(),
                    session_id=req.session_id, revision=req.revision, stage=req.stage,
                    effective_at=self.effective_at)
        if not heads:
            sugg = self.catalog.get_many([h.code for h in res_a.hits[:5]])
            names = sorted({p.name for p in sugg.values()})
            msg = "Тип товара не распознан среди направлений MVP (одежда, мебель, инструменты)."
            if names:
                msg += " Ближайшие по словам наименования: " + "; ".join(names)
            lap("retrieval", t)
            tm["total"] = round((time.perf_counter() - t0) * 1000, 2)
            return SearchResponse(status="not_found", message=msg, features=[], unrecognized=self._unrecognized(nq),
                                  detected_types=[], candidates=[], candidates_total=0, stages=stages,
                                  issues=issues, completeness=Completeness(
                                      backend=self.backend.name, retrieval_total_hits=res_a.total,
                                      retrieval_returned=len(res_a.hits), retrieval_complete=res_a.complete,
                                      type_domain_total=0, type_domain_returned=0, type_domain_complete=False,
                                      type_confirmed=False, note="тип товара не определён"),
                                  code_resolution=CodeResolution(status="none", reason="тип товара не определён"),
                                  characteristics_completion=CharacteristicsCompletion(complete=False),
                                  scope=Scope(note="тип товара не определён; область не выбрана"),
                                  timings=tm, elapsed_ms=tm["total"], **base)

        selected_type = self.catalog_scope.selected(type_choice.value) if self.native and type_choice else None
        if self.native:
            codes = candidate_codes if candidate_codes is not None else selected_type.codes if selected_type else self.catalog_scope.codes
            res_b = SearchResult([Hit(c, 0.0) for c in codes], len(codes), "catalogue-scope")
        else:
            res_b = self.backend.by_heads(heads, self.settings.type_fetch_limit)
        domain = self.catalog.get_many([h.code for h in res_b.hits])
        scores = {h.code: h.score for h in res_a.hits}
        positions = [domain[c] for c in sorted(domain)]
        inactive = 0 if self.native else self.catalog.inactive_count_by_heads(heads)
        stages.append(Stage(stage=f"все активные позиции типа «{', '.join(heads)}»", remaining=len(positions),
                            note=f"исчерпывающая выборка по главному слову ({res_b.total} в индексе); "
                                 f"неактивных/вне срока исключено: {inactive}"))
        if not res_b.complete:
            issues.append(Issue(level="warning", code="domain_truncated",
                                message=f"Позиций типа больше лимита {self.settings.type_fetch_limit}: "
                                        "проверена не вся область"))

        # --- тип по наименованию ---------------------------------------------
        type_confirmed = False
        weak_single_name = False
        confirmed_scope = None
        # цели неоднозначного алиаса («сидушка» → кресло | табурет) не подтверждают наименование
        q_lemmas = [t.lemma for t in nq.tokens if t.kind in ("word", "code")] + det.unique_alias_terms
        if type_choice is not None:
            v = type_choice.value or ""
            sel = positions if selected_type else ([] if self.native else [p for p in positions if p.code == v or norm(p.name) == norm(v)])
            if sel:
                stages.append(Stage(stage="тип предложен моделью" if type_tentative else "тип выбран пользователем",
                                    remaining=len(sel), removed=len(positions) - len(sel), note=v))
                positions, type_confirmed = sel, True
                confirmed_scope = v if not type_tentative else None
            else:
                issues.append(Issue(level="warning", code="type_choice_unknown",
                                    message=f"Выбранный тип «{v}» не найден в области поиска"))
                type_tentative = False
        if not type_confirmed and not self.native:
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
                # Одно наименование в области подтверждает тип, только если описание его подкрепляет:
                # наименование из одного слова или в описании есть ещё слово наименования кроме главного.
                # «кресло-качалка» не подтверждает единственное «Кресло компьютерное детское».
                only = next(iter(by_name.values()))[0]
                tier, _, matched = name_match(only, q_lemmas)
                type_confirmed = len(set(only.name_lemmas)) == 1 or len(matched) >= 2
                weak_single_name = not type_confirmed
            if det.ambiguous_aliases and type_confirmed:
                # разговорное слово с несколькими трактовками: тип подтверждает только пользователь
                type_confirmed = False
                issues.append(Issue(level="info", code="type_needs_confirmation",
                                    message="Тип определён по слову с несколькими трактовками — нужно подтверждение"))
            if type_confirmed:
                confirmed_scope = positions[0].name if positions else None
                type_basis.append(f"наименование позиции: {confirmed_scope}")
        if candidate_codes is not None:
            type_confirmed = scope_verified
            confirmed_scope = "область, распознанная из описания" if scope_verified else None
        t = lap("retrieval", t)

        groups = identity_groups(positions) if self.native else build_groups(positions)
        domain_name_lemmas = {l for p in positions for l in p.name_lemmas}
        extractor = None if self.native else Extractor(
            groups, self.known_terms - domain_name_lemmas,
            name_tokens=self._name_tokens(nq.tokens, positions) | det.type_token_idx)
        features = list(search_features) if search_features is not None else [] if self.native else extractor.extract(nq)
        self._mark_intent(nq, features)
        features = self._apply_constraints(features, [a for a in answers if a.property != TYPE_PROP], "answer",
                                           groups, issues)
        features = self._apply_constraints(features, req.overrides, "override", groups, issues)
        group_names = {c: g.key for g in groups.values() for c in g.codes}
        if self.native:
            from .resolver import MergeResult
            # Model suggestions are visible but NEVER evaluated as constraints before confirmation.
            manual_codes = {(f.property_code, f.property_name) for f in features if f.status in ("bound", "proposed")}
            manual_evidence = {f.proposal_key for f in features if f.source in ("answer", "override")}
            suggestions = []
            for f in model_features or []:
                if f.proposal_key in manual_evidence or "ignore:" + (f.proposal_key or "") in req.rejected:
                    continue
                if (f.property_code, f.property_name) in manual_codes:
                    continue
                changes = {"status": "unknown_property" if f.status == "unknown_property" else "proposed",
                           "confirmation": "tentative", "strict_ref": True}
                if f.proposal_key in req.rejected:
                    changes.update(status="unknown_property", property_code=None, property_name=None,
                                   characteristic_ref=None, note="Привязка отклонена; исходный фрагмент сохранён для ручного ввода")
                suggestions.append(f.model_copy(update=changes))
            merge = MergeResult(features + suggestions)
        else:
            merge = merge_model_features(features, model_features or [], group_names, set(req.rejected), issues)
        features = merge.features
        for f in features:
            if f.status == "ambiguous":
                issues.append(Issue(level="warning", code="feature_ambiguous",
                                    message=f"«{f.evidence}»: {f.note}"))
            elif f.status == "unknown_property" and f.source == "text":
                issues.append(Issue(level="warning", code="unknown_property",
                                    message=f"«{f.evidence}»: {f.note}"))
        # слова наименований области считаются объяснёнными типом
        name_lemmas = {l for p in positions for l in p.name_lemmas}
        for tok in nq.tokens:
            if tok.used_by is None and tok.kind in ("word", "code") and any(fuzzy_equal(tok.lemma, n)
                                                                              for n in name_lemmas):
                tok.used_by = "type"
            if tok.used_by is None and tok.i in det.alias_token_idx:
                tok.used_by = "type"
        # гипотеза модели, противоречащая всем конечным позициям области, не становится фильтром:
        # это сигнал об ошибке в описании (несуществующее значение), а не повод исключить всех кандидатов
        domain_finals = [p for p in positions if not p.is_template]
        for f in features:
            if f.source == "model" and f.status == "bound" and domain_finals:
                sts = {check_feature(p, f)[0] for p in domain_finals}
                if sts == {"invalid"}:
                    f.status = "proposed"
                    f.note += "; противоречит всем позициям области — не применено как условие"
                    issues.append(Issue(level="warning", code="model_value_not_in_ktru",
                                        message=f"«{f.evidence}»: предложено {describe(f)}, но такого значения нет "
                                                "ни у одной позиции области КТРУ. Проверьте описание."))
        # правдоподобие: предупреждения, не исключения
        categories = {p.category for p in positions if p.category}
        findings = [] if self.native else plausibility_check(features, categories)
        plaus_block = []
        for fd in findings:
            confirmed = fd.key in req.confirmed
            issues.append(Issue(level="info" if confirmed else "warning", code="implausible_value",
                                message=fd.message + (" Значение подтверждено пользователем." if confirmed else "")))
            if not confirmed:
                plaus_block.append(fd)
        t = lap("extract", t)

        # --- проверка кандидатов ------------------------------------------------
        evals = {p.code: evaluate(p, features) for p in positions}
        # уровень 3: сомнительные значения — только предложения, на отбор не влияют
        level3 = [] if self.native else suspicious.check(features, positions, req.text, set(req.confirmed),
                                                             heads=heads, stats=self.ste_stats)
        for sg in level3:
            issues.append(Issue(level="warning", code=f"suspect_{sg.rule}", message=sg.message))
        level2 = [] if self.native else [e for f in features
                                         for e in [empirical.assess(f, heads, self.ste_stats)
                                                   or empirical.presence(f, heads, self.ste_stats)] if e is not None]
        ranked = []
        for p in positions:
            ev = evals[p.code]
            tier, ncov, matched = (0, Fraction(0), set()) if self.native else name_match(p, q_lemmas)
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
        if self.settings.recognition_mode == "hybrid":
            out = [c for _, c, _ in finals]
        else:
            out = [c for _, c, _ in finals][:MAX_CANDIDATES_OUT]
            out += [c for _, c, p in compatible if p.is_template][:20]
            out += [c for _, c, _ in ranked if not c.compatible][:30]
        # ошибка размерности — отдельное предупреждение с обоснованием, а не только причина исключения
        for f in features:
            if f.status != "bound" or not f.unit:
                continue
            reasons = [k.reason for ev in evals.values() for k in ev.checks if k.feature_id == f.id
                       and k.status == "invalid" and k.reason.startswith("несовместимая размерность")]
            others = [k for ev in evals.values() for k in ev.checks if k.feature_id == f.id
                      and not k.reason.startswith("несовместимая размерность") and k.status != "unknown"]
            if reasons and not others:
                issues.append(Issue(level="error", code="dimension_mismatch",
                                    message=f"«{f.evidence or f.value}»: {reasons[0]}. Это разные физические величины — "
                                            f"проверьте единицу для «{f.property_name}»."))
        t = lap("validate", t)

        # --- решение ------------------------------------------------------------
        # Неоднозначная опечатка блокирует код, только если хотя бы один вариант — слово области поиска
        # (наименования, названия и значения свойств): «Китай» с несколькими вариантами исправления
        # не может изменить результат.
        domain_vocab = domain_name_lemmas | {t for g in groups.values() for t in g.terms} | \
            {l for g in groups.values() for lems in g.value_lemmas.values() for l in lems}
        blocking_feats = [f for f in features if f.status == "ambiguous"] + \
            [None for c in corrections if c.status == "ambiguous"
             and any(lemma(o) in domain_vocab for o in c.options)]
        contradictions = self._contradictions(features, positions)
        for key, fs in contradictions:
            vals = " и ".join(f"«{describe(f)}»" for f in fs)
            issues.append(Issue(level="error", code="contradictory_values",
                                message=f"Для свойства «{fs[0].property_name}» в описании указано несколько "
                                        f"несовместимых значений: {vals}. У товара одно значение этого свойства "
                                        "— укажите верное"))
            blocking_feats.append(None)
        constrained = {(f.characteristic_ref if self.native else " ".join(tokenize(f.property_name))) for f in features
                       if f.status == "bound" and f.property_name}
        tentative = [f for f in features if f.status in ("bound", "proposed", "unknown_property") and f.confirmation == "tentative"]
        final_code = final_name = None
        question = None
        completeness = Completeness(
            backend=self.backend.name, retrieval_total_hits=res_a.total, retrieval_returned=len(res_a.hits),
            retrieval_complete=res_a.complete, type_domain_total=res_b.total, type_domain_returned=len(res_b.hits),
            type_domain_complete=res_b.complete, type_confirmed=type_confirmed and not type_tentative,
            note=("область = все активные позиции подтверждённого обозначения каталога; без подтверждения — все три группы. Поисковый top-K не сужает область."
                  if self.native else "область = все активные позиции с тем же главным словом наименования; top-K поиска используется только для выбора типа"))
        finals_pos = [p for _, _, p in finals]
        # гарантии, которые модели и подозрительные значения не могут обойти
        gate: list[str] = []
        if tentative:
            gate.append("трактовки моделей не подтверждены: " + "; ".join(describe(f) for f in tentative))
        if type_tentative:
            gate.append(f"тип предложен моделью и не подтверждён: {type_choice.value}")
        if plaus_block:
            gate.append("подозрительные значения не подтверждены")
        if merge.disagreements:
            gate.append("расхождение разбора правилами и модели")
        if self.native and any(f.status == "unknown_property" for f in features):
            gate.append("есть признаки без подтверждённой привязки к полной схеме")
        code_res: CodeResolution
        ev0 = evals[finals_pos[0].code] if finals else None
        if not finals:
            if positions and n_invalid:
                reasons = sorted({r for _, c, _ in ranked if c.excluded_reason for r in [c.excluded_reason]})[:5]
                status, message = "conflict", ("Все позиции типа противоречат описанию. Причины: " + " | ".join(reasons))
                code_res = CodeResolution(status="conflict", reason="все позиции области противоречат описанию")
            elif templates:
                status, message = "conflict", "Совместимы только укрупнённые позиции (шаблоны) — конечного кода нет"
                code_res = CodeResolution(status="conflict", reason="совместимы только шаблоны")
            else:
                status, message = "not_found", "Подходящих позиций не найдено"
                code_res = CodeResolution(status="none", reason="в области нет конечных позиций")
        else:
            single = len(finals) == 1
            ev = ev0
            proven = single and type_confirmed and res_b.complete and not blocking_feats
            if proven and not gate:
                code_res = CodeResolution(status="resolved", code=finals_pos[0].code, remaining=1,
                                          reason="единственная конечная позиция в полностью проверенной области "
                                                 "подтверждённого типа")
            elif single:
                why = []
                if not type_confirmed:
                    why.append("тип не подтверждён")
                if not res_b.complete:
                    why.append("область проверена не полностью")
                if blocking_feats:
                    why.append("есть неоднозначности")
                why += gate
                code_res = CodeResolution(status="unconfirmed", code=finals_pos[0].code, remaining=1,
                                          reason="; ".join(why))
            else:
                code_res = CodeResolution(status="multiple", remaining=len(finals),
                                          reason=f"совместимых конечных позиций: {len(finals)}")
            ambiguous_feature = next((f for f in features if f.status == "ambiguous"), None)
            if proven and not gate and not ev.blocking:
                status = "matched"
                final_code, final_name = finals[0][2].code, finals[0][2].name
                message = (f"Определена конечная позиция {final_code}: все условия проверены в полной области "
                           f"типа ({len(positions)} поз.)")
            else:
                if (proven or self.native) and gate:
                    question = self._confirm_question(tentative, type_choice if type_tentative else None,
                                                      plaus_block, merge.disagreements, len(finals))
                elif det.ambiguous_aliases and not type_confirmed and len({p.name for p in finals_pos}) > 1:
                    # тип от разговорного слова с несколькими трактовками — подтверждается первым
                    question = choose_question(finals_pos, constrained, False, type_first=True)
                elif ambiguous_feature is not None and ambiguous_feature.options:
                    question = self._feature_question(ambiguous_feature, len(finals))
                else:
                    req_unknown = []
                    if single:
                        p = finals_pos[0]
                        req_unknown = [p.props[c.property_code] for c in ev.checks
                                       if c.status == "unknown" and c.required and c.property_code in p.props]
                    question = None if self.native and not type_confirmed else choose_question(
                        finals_pos, constrained, type_confirmed, req_unknown,
                        type_first=bool(det.ambiguous_aliases) or weak_single_name, strict_refs=self.native)
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
                    if gate:
                        parts.append("нужно подтверждение: " + "; ".join(gate))
                    if single and ev.blocking:
                        parts.append("не проверено: " + "; ".join(ev.blocking[:3]))
                    message = ". ".join(parts)
        if contradictions:
            # переизбыток данных: несовместимые значения одного свойства — сначала выбрать верное
            key, fs = contradictions[0]
            status = "conflict"
            message = (f"Противоречие в описании: «{fs[0].property_name}» указано по-разному "
                       f"({', '.join(describe(f) for f in fs)}). Выберите верное значение")
            question = Question(kind="property", property_code=fs[0].property_code, property_name=fs[0].property_name,
                                text=f"Какое значение «{fs[0].property_name}» верное?", required=True,
                                worst_case_remaining=len(finals), current_remaining=len(finals),
                                options=[QuestionOption(label=describe(f), remaining=len(finals), answer=Constraint(
                                    property=f.property_code or f.property_name, op=f.op, value=f.value,
                                    value_to=f.value_to, min_inclusive=f.min_inclusive,
                                    max_inclusive=f.max_inclusive, unit=f.unit)) for f in fs],
                                reason="в описании несколько несовместимых значений одного свойства")
            code_res = CodeResolution(status="conflict", reason="противоречивые значения в описании")
        completion = self._completion(finals_pos[0], ev0) if len(finals) == 1 else \
            CharacteristicsCompletion(complete=False, missing=[], unchecked=[])
        if tentative and status == "matched":  # защита: недостижимо при корректной логике выше
            raise AssertionError("matched с неподтверждёнными трактовками моделей")
        scope = Scope(detected_types=heads, type_basis=type_basis,
                      confirmed_scope=confirmed_scope if type_confirmed and not type_tentative else None,
                      scope_complete=bool(res_b.complete and type_confirmed and not type_tentative),
                      registry_complete=True,
                       note="обозначения каталога: группа + точное название; членство хранится по кодам" if self.native else "реестр типов построен по всем активным позициям направлений MVP в снимке")
        if self.native:
            heads = [selected_type.ref] if selected_type else []
            scope.detected_types = heads
            stages[0].stage = "семантические предложения (отдельно от подтверждённой области)"
            stages[1].stage = "полная область каталога"
            stages[1].note = completeness.note
        lap("decide", t)
        tm["total"] = round((time.perf_counter() - t0) * 1000, 2)
        return SearchResponse(
            status=status, message=message, features=features, unrecognized=self._unrecognized(nq),
            detected_types=heads, candidates=out, candidates_total=len(ranked), stages=stages, question=question,
            properties=[DomainProperty(code=g.key if self.native else g.codes[0], codes=g.codes, ref=g.key if self.native else None, name=g.name, required=g.required,
                                       numeric=g.numeric, boolean=g.boolean,
                                       units=sorted(BY_KEY[k].title for k in g.unit_keys),
                                        values=sorted(g.quality.values()) if self.native else sorted(g.quality.values())[:50], positions=g.positions)
                        for g in sorted(groups.values(), key=lambda g: (-g.positions, g.key))],
            final_code=final_code, final_name=final_name, issues=issues, completeness=completeness,
            assertions=self._assertions(nq, features, merge), code_resolution=code_res,
            characteristics_completion=completion, scope=scope, timings=tm,
            elapsed_ms=tm["total"], recognition_mode=self.settings.recognition_mode,
            compatible_codes=[p.code for p in finals_pos], suggestions=level3, empirical=level2, **base)

    # ------------------------------------------------------------------
    @staticmethod
    def _mark_intent(nq: NormalizedQuery, features: list[Feature]) -> None:
        """Факт о товаре / требование / предпочтение. Предпочтение не становится жёстким условием."""
        lemmas = [t.lemma for t in nq.tokens]
        for f in features:
            if f.span is None:
                continue
            first = next((t.i for t in nq.tokens if t.start >= f.span[0]), 0)
            seg_start = first
            while seg_start > 0 and nq.tokens[seg_start - 1].lemma not in (",", ";", ":"):
                seg_start -= 1
            before = set(lemmas[seg_start:first])
            if before & PREFERENCE_WORDS:
                f.intent = "preference"
                if f.status == "bound":
                    f.status = "proposed"
                    f.note += "; предпочтение («желательно») — не жёсткое условие подбора"
            elif f.op in ("ge", "gt", "le", "lt", "between") or before & REQUIREMENT_WORDS:
                f.intent = "requirement"

    @staticmethod
    def _completion(p: Position, ev) -> CharacteristicsCompletion:
        req = [pr for pr in p.props.values() if pr.required]
        filled = {c.property_code for c in ev.checks if c.status == "valid" and c.required}
        missing = [c.property_name for c in ev.checks if c.reason == "обязательное свойство не заполнено"]
        unchecked = [c.property_name for c in ev.checks if c.status == "unknown"
                     and c.reason != "обязательное свойство не заполнено"]
        return CharacteristicsCompletion(complete=not missing and not unchecked, required_total=len(req),
                                         required_filled=len(filled), missing=missing, unchecked=unchecked)

    @staticmethod
    def _assertions(nq: NormalizedQuery, features: list[Feature], merge) -> list[RawAssertion]:
        out = []
        rejected = [(f, why) for f, why in merge.rejected]
        for f, extra_status in [(f, None) for f in features] + rejected:
            span = None
            if f.raw_span is not None:
                span = Span(start=f.raw_span[0], end=f.raw_span[1], quote=nq.original[f.raw_span[0]:f.raw_span[1]])
            origin = "manual" if f.source in ("override", "answer") else f.origin
            if f.op == "between":
                kind = "range"
            elif f.value is not None and f.value.replace(",", "").replace(".", "").lstrip("-").isdigit():
                kind = "number"
            elif norm(f.value or "") in ("да", "нет"):
                kind = "bool"
            else:
                kind = "enum"
            if extra_status:
                status, conf = "rejected:" + extra_status, "rejected"
            elif f.status == "bound":
                status = "accepted" if f.confirmation == "confirmed" else "proposed"
                conf = f.confirmation
            else:
                status, conf = f.status, ("confirmed" if origin == "manual" else "tentative")
            out.append(RawAssertion(
                assertion_id=f"a-{f.id}", source=origin, span=span, component_raw=f.component,
                property_raw=None, raw_value=f.value, raw_value_to=f.value_to, raw_unit=f.unit,
                predicate=Predicate(kind=kind, operator=f.op), negated=f.negated, intent=f.intent,
                proposed_property_ref=f.characteristic_ref or f.property_code, alternatives=f.options,
                confirmation=conf, feature_id=f.id, status=status))
        return out

    @staticmethod
    def _confirm_question(tentative: list[Feature], type_choice, plaus, disagreements, n: int) -> Question:
        answers = [Constraint(property=f.characteristic_ref or f.property_code or f.property_name or "", op=f.op, value=f.value, values=f.values,
                              value_to=f.value_to, min_inclusive=f.min_inclusive, max_inclusive=f.max_inclusive,
                              unit=f.unit) for f in tentative]
        if type_choice is not None:
            answers.append(Constraint(property=TYPE_PROP, value=type_choice.value))
        items = [f"«{f.evidence or f.value}» → {describe(f)} (предложено: {f.origin})" for f in tentative]
        if type_choice is not None:
            items.append(f"тип товара → {type_choice.value} (предложено моделью)")
        items += [p.message for p in plaus]
        items += [d.message for d in disagreements]
        opts = [QuestionOption(label="Да, всё верно", remaining=n, answer=answers[0] if answers else None,
                               answers=answers, confirm=[p.key for p in plaus])]
        for f in tentative:
            if f.proposal_key:
                opts.append(QuestionOption(label=f"Нет: «{f.evidence or f.value}» ≠ {describe(f)}", remaining=n,
                                           reject=[f.proposal_key]))
        for d in disagreements:
            mf = d.model_feature
            opts.append(QuestionOption(
                label=f"Заменить на {describe(mf)}", remaining=n,
                answer=Constraint(property=mf.property_code or "", op=mf.op, value=mf.value, value_to=mf.value_to,
                                  unit=mf.unit)))
        return Question(kind="confirm", text="Подтвердите трактовку описания перед выдачей кода",
                        worst_case_remaining=n, current_remaining=n, options=opts,
                        reason="; ".join(items))

    # ------------------------------------------------------------------
    def _head_of_name(self, name: str) -> str | None:
        from .text import head_lemma
        return head_lemma(name)

    @staticmethod
    def _contradictions(features: list[Feature], positions: list[Position]) -> list[tuple[str, list[Feature]]]:
        """Несовместимые значения одного свойства из текста (переизбыток данных).

        Учитываются признаки из описания со статусом bound. Свойства с выбором нескольких значений
        (kind=3 у какой-либо позиции области) не проверяются. Несовместимы: разные качественные
        значения; «X» и «не X»; числа, чьи интервалы не пересекаются после перевода единиц."""
        multi = {p_.norm_name for p in positions for p_ in p.props.values() if p_.kind == 3}
        by_key: dict[str, list[Feature]] = {}
        for f in features:
            if f.status == "bound" and f.source == "text" and f.property_name:
                key = " ".join(tokenize(f.property_name))
                if key not in multi:
                    by_key.setdefault(key, []).append(f)
        out = []
        for key, fs in sorted(by_key.items()):
            if len(fs) < 2:
                continue
            bad = []
            for i, a in enumerate(fs):
                for b in fs[i + 1:]:
                    if Engine._incompatible(a, b):
                        bad += [x for x in (a, b) if x not in bad]
            if bad:
                out.append((key, bad))
        return out

    @staticmethod
    def _incompatible(a: Feature, b: Feature) -> bool:
        from .validate import user_interval
        from .units import lookup
        ia, ib = user_interval(a) if a.op != "ne" else None, user_interval(b) if b.op != "ne" else None
        if ia is not None and ib is not None:
            ua, ub = lookup(a.unit) if a.unit else None, lookup(b.unit) if b.unit else None
            if (ua is None) != (ub is None) or (ua and ub and ua.dimension != ub.dimension):
                return False
            if ua and ub:
                ib = ib.scaled(ub.factor / ua.factor)
            return not ia.intersects(ib)
        va, vb = norm(a.value or "").strip(), norm(b.value or "").strip()
        if a.op == "eq" and b.op == "eq":
            return va != vb
        if {a.op, b.op} == {"eq", "ne"}:
            return va == vb
        return False

    @staticmethod
    def _name_tokens(tokens, positions: list[Position]) -> set[int]:
        """Токены, которыми записано наименование типа: наименование области с наибольшим числом
        найденных слов, каждое слово наименования — к первому свободному подходящему токену."""
        best: set[int] = set()
        for name_lemmas in sorted({tuple(dict.fromkeys(p.name_lemmas)) for p in positions}):
            used: set[int] = set()
            for l in name_lemmas:
                i = next((t.i for t in tokens if t.kind in ("word", "code") and t.i not in used
                          and fuzzy_equal(t.lemma, l)), None)
                if i is not None:
                    used.add(i)
            if len(used) > len(best):
                best = used
        return best

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
                same = g is not None and (f.characteristic_ref == g.key if self.native else f.property_name and " ".join(tokenize(f.property_name)) == g.key)
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
                                        origin="manual",
                                        property_name=c.property, op=c.op, value=c.value, value_to=c.value_to,
                                        unit=c.unit, note="свойство не найдено"))
                continue
            features.append(Feature(id=f"{source[0]}{k + 1}", source=source, status="proposed" if c.intent == "preference" else "bound",
                                    origin="manual",
                                    intent=c.intent,
                                    property_code=g.codes[0], property_name=g.name, op=c.op, value=c.value, values=c.values,
                                    value_to=c.value_to, min_inclusive=c.min_inclusive,
                                    max_inclusive=c.max_inclusive, unit=c.unit,
                                    strict_ref=self.native,
                                    characteristic_ref=g.key if self.native else None,
                                    proposal_key=c.evidence_key,
                                    note="ручное редактирование (приоритет над текстом)" if source == "override"
                                    else "ответ на уточняющий вопрос"))
        return features

    @staticmethod
    def _resolve_group(prop: str, groups: dict[str, PropGroup]) -> PropGroup | None:
        if prop in groups:
            return groups[prop]
        code_matches = [g for g in groups.values() if prop in g.codes]
        if code_matches:
            return code_matches[0] if len(code_matches) == 1 else None
        key = " ".join(tokenize(prop))
        matches = [g for g in groups.values() if " ".join(tokenize(g.name)) == key]
        return matches[0] if len(matches) == 1 else None
