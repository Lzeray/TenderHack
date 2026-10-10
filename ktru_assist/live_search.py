"""Live description -> two extraction branches -> catalogue validation -> complete results."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import time

from . import canon, extras
from .catalog.scope import ref
from .engine import Engine
from .models import Constraint, Feature, Issue, ProviderStatus, SearchRequest, Stage
from .nlp.extract import build_groups
from .nlp.normalize import normalize
from .registry import TypeRegistry
from .resolver import same_value
from .search.local_backend import LocalBM25Backend
from .text import content_lemmas, norm
from .units import BY_KEY, convert, lookup
from .validate import conflicting_conditions


class LiveSearch:
    def __init__(self, orchestrator):
        self.o = orchestrator
        self.core = orchestrator.engine
        self.catalog = self.core.catalog
        docs = self.catalog.search_documents()
        self.rules = Engine(self.catalog, LocalBM25Backend(docs), replace(self.core.settings, recognition_mode="rules"))
        # Catalogue nouns/word forms are sufficient for the deterministic path; synonyms are optional.
        self.rules.registry = TypeRegistry(docs, aliases=[])
        self.colors = set()
        for p in self.core.catalog_scope.positions():
            for pr in p.props.values():
                if "цвет" in norm(pr.name):
                    for v in pr.values:
                        if v.kind == "quality" and v.text:
                            words = content_lemmas(v.text)
                            if len(words) == 1:
                                self.colors.add(words[0])
        self.ste = None
        ste_path = self.core.settings.db_path.parent / "ste_search.sqlite"
        if ste_path.exists():
            from .catalog.ste_search import SteSearch
            self.ste = SteSearch(ste_path)
            self.colors.update(self.ste.color_terms())

    def _domain(self, response):
        heads = response.detected_types
        if not heads:
            return []
        result = self.rules.backend.by_heads(heads, len(self.core.catalog_scope.codes) + 1)
        positions = self.catalog.get_many([h.code for h in result.hits])
        return [positions[h.code] for h in result.hits]

    def _resolve_numbers(self, features, positions, item_terms):
        groups = build_groups(positions)
        out = []
        for f in features:
            f = f.model_copy(deep=True)
            if f.status == "ambiguous" and f.property_name is None and not f.unit and set(content_lemmas(f.value or "")) <= set(item_terms):
                continue  # the catalogue object name is not a separate product attribute
            u = lookup(f.unit or "")
            if f.status == "ambiguous" and u is not None:
                possible = [g for g in groups.values() if g.numeric and u.dimension in g.dims]
                # A bare quantity refers to the item itself, not a named component.
                owners = [g for g in possible if g.component is None and set(content_lemmas(g.name)) & set(item_terms)]
                if len(owners) == 1:
                    g = owners[0]
                    f.status, f.property_name, f.property_code = "bound", g.name, g.codes[0]
                    f.options = []
                    f.note += "; величина относится к самому предмету по названию характеристики КТРУ"
            # вариант разложенного неоднозначного значения («мужские» → по свойству каждой позиции) не переносится
            taken = {x.property_name for x in features if x is not f and x.status == "bound"}
            if f.status == "bound" and f.unit is None and f.property_name and f.value and "." not in f.id \
                    and not any(g.name == f.property_name for g in groups.values()):
                # свойства нет у позиций выбранного наименования: то же значение под другим названием
                # («угловой»: «Тип конструкции стола» → «Конфигурация стола: Угловой»)
                same = canon.groups_with_value(f.value, groups)
                if len(same) == 1 and same[0].name not in taken:
                    g = same[0]
                    f.property_name, f.property_code = g.name, g.codes[0]
                    f.value = canon.match_value(f.value, g.quality) or f.value
                    f.note += f"; у выбранных позиций значение относится к «{g.name}»"
            out.append(f)
        return out

    def _fallback(self, req, response):
        text = req.text.strip()
        types = self.core.catalog_scope.types
        # Incomplete words are queried against catalogue names; no hand-written synonym list.
        prefix = norm(text)
        hits = [t for t in types.values() if len(prefix) >= 2 and norm(t.name).startswith(prefix)] if " " not in text else []
        if not hits and self.o.semantic is not None:
            proposals = self.o.semantic.propose(response, req.text, set(req.rejected))
            if proposals:
                best = max(p.score or 0 for p in proposals)
                hits = [types[p.answer.value] for p in proposals if p.answer and (p.score or 0) >= best - .025]
        codes = sorted({c for t in hits for c in t.codes})
        ps = self.catalog.get_many(codes)
        return [ps[c] for c in codes], False

    def fast(self, req):
        started = time.perf_counter()
        with self.o.core_lock:
            # без session_id: дополнительные характеристики запоминаются один раз — в _additional
            rule_response = self.rules.search(req.model_copy(update={"overrides": [], "answers": [], "session_id": None}))
            positions = self._domain(rule_response)
            if positions:
                # Retain all catalogue names not ruled out by explicit name terms.
                if rule_response.scope and rule_response.scope.confirmed_scope:
                    name = rule_response.scope.confirmed_scope
                    # названное наименование и его более частные разновидности («Халат» → «Халат детский», …):
                    # между ними выбирает вопрос о наименовании
                    base = next((set(p.name_lemmas) for p in positions if p.name == name), None)
                    narrowed = [p for p in positions if p.name == name or p.code == name
                                or (base and base <= set(p.name_lemmas))]
                    if narrowed:
                        positions = narrowed
                verified = rule_response.completeness.type_confirmed
            else:
                positions, verified = self._fallback(req, rule_response)
            type_choice = next((c for c in [*req.overrides, *req.answers] if c.property == "__type__" and not c.remove), None)
            selected = self.core.catalog_scope.selected(type_choice.value) if type_choice else None
            if selected:
                positions, verified = self.core.catalog_scope.positions(selected.ref), True
            features = self._resolve_numbers(rule_response.features, positions, rule_response.detected_types)
            response = self.core.search(req, candidate_codes=[p.code for p in positions],
                                        search_features=features, scope_verified=verified)
        response.corrections = rule_response.corrections
        response.query = rule_response.query
        response.query_hash = hashlib.sha256(req.text.encode()).hexdigest()[:16]
        response.query["original"] = req.text
        response.scope.type_basis = ["автоматический разбор описания"]
        response.scope.note = "Полная область распознанного предмета; выбор типа не является обязательным шагом."
        response.detected_types = sorted({p.name for p in positions})
        response.results_total = len(response.candidates)
        response.preview_candidates = []
        response.preview_total = 0
        response.recognition_mode = "hybrid"
        response.preliminary = False
        response.providers = [ProviderStatus(name="rules", enabled=True, used=True, status="ok", detail="тип и характеристики извлечены автоматически")]
        response.timings["fast_total"] = round((time.perf_counter() - started) * 1000, 2)
        response.query_profile = self._profile(response, positions)
        known_colors = any("цвет" in norm(a["name"]) for a in response.query_profile["attributes"])
        if not known_colors:
            for token in normalize(req.text).tokens:
                if token.kind == "word" and token.lemma in self.colors:
                    response.query_profile["attributes"].append({"name": "Цвет", "raw_value": token.text,
                        "value": token.text, "raw_unit": None, "unit": None, "source": "rule",
                        "status": "outside_catalogue", "quote": token.text, "op": "eq"})
        response.query_profile["item_terms"] = rule_response.detected_types
        response.query_profile["unrecognized"] = rule_response.unrecognized
        # Поиск идёт только по КТРУ; выгрузки СТЕ лишь подтверждают дополнительные характеристики.
        self._additional(req, response, rule_response.detected_types,
                         [a for a in response.query_profile["attributes"] if a["status"] == "outside_catalogue"])
        conflicts = conflicting_conditions(response.features, positions, req.text)
        if conflicts:
            self._set_conflict(response, conflicts)
        response.stages[0] = Stage(stage="распознан предмет", remaining=len(positions), note=", ".join(response.detected_types))
        response.model_pending = not conflicts and self.o.llm is not None and self.o.cfg.b_mode != "off" and not req.manual_only
        return response, positions, features, verified

    def _additional(self, req, response, heads, extra_attrs):
        """Характеристики вне КТРУ: смысл → выгрузки СТЕ → память сессии. Товары СТЕ не выдаются."""
        response.additional = extras.classify(response.features, extra_attrs, list(heads or []),
                                              self.rules.ste_stats, req.session_id)
        response.ste_results = {}
        for w in extras.subjective_words(response.query_profile.get("unrecognized", [])):
            response.issues.append(Issue(level="warning", code="not_a_characteristic",
                message=f"«{w}» — оценочное слово, а не характеристика товара: оно не влияет на подбор. "
                        "Укажите конкретное свойство (материал, цвет, размер …)"))
        for a in response.additional:
            if not a.accepted and not any(i.code == "not_a_characteristic" and a.name in i.message for i in response.issues):
                response.issues.append(Issue(level="warning", code="not_a_characteristic",
                    message=f"«{a.name}{': ' + a.value if a.value else ''}» не принята как характеристика: {a.reason}"))

    @staticmethod
    def _set_conflict(response, conflicts):
        response.status = "conflict"
        response.message = conflicts[0].message
        response.issues.extend(conflicts)
        response.query_profile["conflicts"] = [i.message for i in conflicts]
        response.candidates, response.compatible_codes, response.preview_candidates = [], [], []
        response.results_total, response.preview_total = 0, 0
        response.final_code = response.final_name = response.question = None
        response.model_pending = False
        response.ste_results = {"total": 0, "items": [], "offset": 0, "limit": 25}
        if response.code_resolution:
            response.code_resolution.status, response.code_resolution.code = "conflict", None
            response.code_resolution.remaining, response.code_resolution.reason = 0, response.message

    def _profile(self, response, positions):
        groups = build_groups(positions)
        attrs = []
        for f in response.features:
            if f.status in ("overridden", "removed"):
                continue
            value, unit = f.value, f.unit
            try:
                number = Decimal((value or "").replace(",", "."))
            except InvalidOperation:
                number = None
            g = next((g for g in groups.values() if g.name == f.property_name), None)
            source_unit = lookup(unit or "")
            if number is not None and number.is_finite() and source_unit and g:
                target = next((BY_KEY[k] for k in sorted(g.unit_keys) if BY_KEY[k].dimension == source_unit.dimension), None)
                if target:
                    converted = convert(number, source_unit, target)
                    value, unit = format(converted.normalize(), "f"), target.title
            if g is not None and g.quality and unit is None:
                value = canon.match_value(value, g.quality) or value
            elif value and unit is None and not any(ch.isdigit() for ch in value):
                value = canon.display(value)
            attrs.append({"name": f.property_name or "Неоднозначная характеристика", "raw_value": f.value,
                          "raw_unit": f.unit, "value": value, "unit": unit, "source": f.origin,
                          "status": f.status, "quote": f.evidence, "op": f.op})
        return {"categories": sorted({p.category for p in positions if p.category}),
                "items": sorted({p.name for p in positions}), "attributes": attrs}

    def full(self, req, fast, positions, facts, verified):
        from .llm import description as extractor
        if fast.status == "conflict":
            return fast  # an LLM must not undo contradictory user-supplied conditions
        if req.manual_only or self.o.llm is None or self.o.cfg.b_mode == "off":
            fast.model_pending = False
            fast.providers.append(ProviderStatus(name="qwen", enabled=False, status="off"))
            return fast
        groups = build_groups(positions)
        hints = [{"name": g.name, "values": sorted(g.quality.values())[:8],
                  "units": [BY_KEY[k].title for k in sorted(g.unit_keys)]} for g in sorted(groups.values(), key=lambda g: (-g.positions, g.key))[:30]]
        type_names = sorted({p.name for p in positions})
        # Extraction is independent of catalogue definitions: passing them here encouraged
        # a small model to invent every listed property. Binding happens after extraction.
        key = extractor.cache_key(req.text, [], [], self.o.native_digest, getattr(self.o.llm, "options", {}))
        reply = self.o.b_cache.get(key)
        elapsed, cached = 0.0, reply is not None
        if reply is None:
            with self.o.llm_lock:
                if self.o.is_stale(req):
                    fast.stale, fast.model_pending = True, False
                    return fast
                reply = self.o.b_cache.get(key)
                if reply is None:
                    result = self.o.llm.complete(extractor.messages(req.text, [], []), extractor.SCHEMA)
                    elapsed = result.elapsed_ms
                    if not result.ok or result.meta.get("done_reason") == "length":
                        fast.model_pending = False
                        fast.providers.append(ProviderStatus(name="qwen", enabled=True, used=True,
                            status="timeout" if result.kind == "timeout" else "error", detail=result.error or "ответ обрезан", elapsed_ms=elapsed))
                        return fast
                    reply = result.text
        try:
            parsed, attrs, rejected = extractor.validate(req.text, reply)
        except Exception as e:
            fast.model_pending = False
            fast.providers.append(ProviderStatus(name="qwen", enabled=True, used=True, status="invalid", detail=str(e)))
            return fast
        self.o.b_cache.put(key, reply)
        if self.o.is_stale(req):
            fast.stale, fast.model_pending = True, False
            return fast
        # The model can resolve a type not understood by rules; source is still shown explicitly.
        if parsed.catalogue_type and not verified:
            selected = self.core.catalog_scope.selected(parsed.catalogue_type)
            if selected:
                positions = self.core.catalog_scope.positions(selected.ref)
                groups = build_groups(positions)
        all_facts = self._resolve_numbers(facts, positions, list(content_lemmas(parsed.item)))
        extra_attrs = []
        model_only = False
        for i, (attr, span) in enumerate(attrs):
            item_words = set(fast.query_profile.get("item_terms") or content_lemmas(parsed.item))
            if set(content_lemmas(attr.value)) & item_words and any(w in norm(attr.name) for w in ("назван", "предмет", "вид/назначение")):
                continue
            g = self._bind(attr, groups)
            if g is None:
                extra_attrs.append({"name": canon.display(attr.name), "raw_value": attr.value, "raw_unit": attr.unit,
                    "value": canon.display(attr.canonical_value or attr.value), "unit": attr.unit, "source": "llm",
                    "status": "outside_catalogue", "quote": req.text[span[0]:span[1]], "op": attr.op})
                continue
            value = attr.canonical_value or attr.value
            if g.numeric:
                value = attr.value
            else:
                # единый формат: значение в написании КТРУ («угловой» → «Угловой»)
                value = canon.match_value(value, g.quality) or canon.match_value(attr.value, g.quality)
                if value is None:
                    continue
            f = Feature(id=f"qwen-{i}", source="model", origin="llm", status="bound", confirmation="confirmed",
                        property_code=g.codes[0], property_name=g.name, value=value, value_to=attr.value_to,
                        unit=attr.unit, op=attr.op, evidence=req.text[span[0]:span[1]], raw_span=span,
                        note="Извлечено Qwen; значение проверяется алгоритмом по КТРУ")
            previous = [f0 for f0 in all_facts if f0.property_name == f.property_name and f0.status == "bound"]
            if previous:
                if any(same_value(f0, f) for f0 in previous):
                    for f0 in previous:
                        f0.supported_by = list(set(f0.supported_by + ["llm"]))
                continue  # a model cannot overwrite independently extracted numbers/negations
            for old in all_facts:
                if old.status == "ambiguous" and old.evidence and f.evidence and (old.evidence in f.evidence or f.evidence in old.evidence):
                    old.status = "overridden"
            all_facts.append(f)
            model_only = True
        with self.o.core_lock:
            response = self.core.search(req, candidate_codes=[p.code for p in positions],
                                        search_features=all_facts, scope_verified=verified)
        # These are search results under the displayed interpretation, not an unproved unique code.
        if model_only and response.status == "matched":
            response.status, response.final_code, response.final_name = "clarification_needed", None, None
            response.message = "Найдена одна позиция по разбору модели; проверьте распознанные характеристики."
        response.query_profile = self._profile(response, positions)
        response.query_profile["attributes"] += extra_attrs
        model_names = {norm(a["name"]) for a in response.query_profile["attributes"]}
        response.query_profile["attributes"] += [a for a in fast.query_profile["attributes"] if norm(a["name"]) not in model_names]
        response.query_profile["item_terms"] = fast.query_profile.get("item_terms") or content_lemmas(parsed.item)
        response.query_profile["unrecognized"] = fast.query_profile.get("unrecognized", [])
        self._additional(req, response, response.query_profile["item_terms"],
                         [a for a in response.query_profile["attributes"] if a["status"] == "outside_catalogue"])
        conflicts = conflicting_conditions(response.features, positions, req.text)
        if conflicts:
            self._set_conflict(response, conflicts)
        response.detected_types = sorted({p.name for p in positions})
        response.results_total = len(response.candidates)
        response.recognition_mode = "hybrid"
        response.preliminary = model_only
        response.model_pending = False
        response.providers = fast.providers + [ProviderStatus(name="qwen", enabled=True, used=True,
            status="cached" if cached else "ok", elapsed_ms=elapsed, detail="независимый разбор предмета и характеристик")]
        response.timings["llm"] = elapsed
        for reason in rejected:
            response.issues.append(Issue(level="info", code="model_fragment_rejected", message=reason))
        response.query["model_description"] = parsed.model_dump()
        return response

    @staticmethod
    def _bind(attr, groups):
        name = tuple(content_lemmas(attr.name))
        exact = [g for g in groups.values() if tuple(content_lemmas(g.name)) == name]
        if len(exact) == 1:
            return exact[0]
        matching = [g for g in groups.values() if set(name) <= set(content_lemmas(g.name))]
        if len(matching) == 1:
            return matching[0]
        # «Тип: угловой» — общее слово названия подходит к нескольким свойствам: выбрать по значению КТРУ
        value = attr.canonical_value or attr.value
        for pool in ([exact, matching] if exact or matching else [None]):
            if pool is not None and not pool:
                continue
            by_value = canon.groups_with_value(value, groups, pool) or canon.groups_with_value(attr.value, groups, pool)
            if len(by_value) == 1:
                return by_value[0]
        u = lookup(attr.unit or "")
        if u:
            matching = [g for g in groups.values() if g.numeric and u.dimension in g.dims]
            if len(matching) == 1:
                return matching[0]
        return None
