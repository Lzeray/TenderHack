"""SearchOrchestrator: пути A (черновик при вводе) и B (расширенный разбор по Enter).

A: правила ядра → (если включено) смысловые предложения для неразобранных фрагментов → ответ.
B: только для отправленной версии (stage=submitted) и только по эскалации: контекст из снимка КТРУ →
   один вызов локальной LLM → строгая проверка → согласование → полный пересчёт ядром с начала.

Версии и гонки:
* ответ несёт session_id и revision; сервер помнит последнюю revision сеанса и помечает
  ответы на старые версии как stale (клиент их не применяет);
* перед вызовом LLM и после него проверяется актуальность; устаревшее задание не выполняется;
* отмена на клиенте не считается остановкой инференса — проверка версии обязательна.

Кэш: A — по тексту, ручным полям и версиям; B — по полному входу модели, схеме, контексту и
ревизии модели. В кэш попадают только валидные ответы; при выдаче из кэша создаётся новая
служебная оболочка (run_id, revision).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .clarify import TYPE_PROP
from .models import Candidate, Issue, ProviderStatus, Question, QuestionOption, SearchRequest, SearchResponse
from .resolver import describe


@dataclass
class OrchestratorConfig:
    b_mode: str = "off"              # off | escalate | always
    b_timeout_s: float = 20.0
    b_include_draft: bool = True
    semantic: bool = False
    event_log: str | None = None
    cache_size: int = 256

    @staticmethod
    def from_env() -> "OrchestratorConfig":
        return OrchestratorConfig(
            b_mode=os.environ.get("LLM_MODE", "off"),
            b_timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "20")),
            b_include_draft=os.environ.get("LLM_INCLUDE_DRAFT", "1") == "1",
            semantic=os.environ.get("SEMANTIC", "0") == "1",
            event_log=os.environ.get("EVENT_LOG") or ("data/cache/semantic-events.jsonl" if os.environ.get("RECOGNITION_MODE") == "semantic" else None),
        )


class LRU:
    def __init__(self, size: int):
        self.size, self.d, self.lock = size, OrderedDict(), threading.Lock()

    def get(self, k):
        with self.lock:
            if k in self.d:
                self.d.move_to_end(k)
                return self.d[k]
        return None

    def put(self, k, v):
        with self.lock:
            self.d[k] = v
            self.d.move_to_end(k)
            while len(self.d) > self.size:
                self.d.popitem(last=False)


def escalation_reasons(resp: SearchResponse) -> list[str]:
    """Когда нужен разбор B (план, п. 6.2). Не вызывается ради понятной ошибки размерности
    или незаполненного значения."""
    why = []
    sig = [u for u in resp.unrecognized if not any(ch.isdigit() for ch in u)]
    if sig:
        why.append("неразобранные фрагменты: " + ", ".join(sig[:5]))
    if any(f.status == "ambiguous" for f in resp.features):
        why.append("неоднозначная привязка значения")
    if any(f.status == "unknown_property" and f.source == "text" for f in resp.features):
        why.append("свойство не найдено у типа")
    if resp.status == "not_found":
        why.append("тип товара не определён правилами")
    elif resp.completeness and not resp.completeness.type_confirmed:
        why.append("тип товара не подтверждён")
    if resp.status == "conflict":
        # конфликт объясняется понятной ошибкой единицы, если хотя бы одна позиция исключена только из-за неё
        dim_explained = any(c.excluded_reason and all("несовместимая размерность" in part
                                                      for part in c.excluded_reason.split("; "))
                            for c in resp.candidates if not c.compatible)
        if not dim_explained:
            why.append("конфликт, возможна ошибка разбора")
    if any(c.status == "ambiguous" for c in resp.corrections):
        why.append("неоднозначная опечатка")
    return why


class Orchestrator:
    def __init__(self, engine, cfg: OrchestratorConfig | None = None, semantic=None, llm=None):
        self.engine = engine
        self.cfg = cfg or OrchestratorConfig()
        self.semantic = semantic
        self.llm = llm
        self.core_lock = threading.Lock()
        self.llm_lock = threading.Lock()
        self.sessions: dict[str, int] = {}
        self.sess_lock = threading.Lock()
        self.a_cache = LRU(self.cfg.cache_size)
        self.b_cache = LRU(self.cfg.cache_size)
        self.validated_cache = LRU(self.cfg.cache_size)
        self.log_lock = threading.Lock()
        self.native_digest = self.llm.digest() if self.engine.native and self.llm is not None else None
        if self.engine.native and self.llm is not None and hasattr(self.llm, "expected_digest"):
            self.llm.expected_digest = self.native_digest
        self.extraction_log: dict[str, dict] = {}

    # --- версии запросов ---------------------------------------------------
    def _register(self, req: SearchRequest) -> None:
        if req.session_id is None or req.revision is None:
            return
        with self.sess_lock:
            if req.revision > self.sessions.get(req.session_id, -1):
                self.sessions[req.session_id] = req.revision

    def is_stale(self, req: SearchRequest) -> bool:
        if req.session_id is None or req.revision is None:
            return False
        with self.sess_lock:
            return self.sessions.get(req.session_id, -1) > req.revision

    def versions(self) -> dict[str, str]:
        v = self.engine.versions()
        v["orchestrator"] = "3.0"
        v["llm_mode"] = self.cfg.b_mode
        if self.semantic is not None:
            v["semantic_encoder"] = self.semantic.revision
        if self.llm is not None and self.cfg.b_mode != "off":
            if self.engine.settings.recognition_mode == "hybrid":
                from .llm.description import PROMPT_VERSION, SCHEMA
                SCHEMA_HASH = hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest()
            elif self.engine.native:
                from .llm.catalog_extractor import PROMPT_VERSION, SCHEMA_HASH
            else:
                from .llm.extractor import PROMPT_VERSION, SCHEMA_HASH
            v["llm_model"] = f"{self.llm.model}@{self.native_digest or self.llm.digest()}"
            v["llm_prompt"] = PROMPT_VERSION
            v["llm_schema"] = SCHEMA_HASH
            v["llm_options"] = json.dumps(getattr(self.llm, "options", {}), sort_keys=True)
        return v

    # --- ядро -----------------------------------------------------------------
    @staticmethod
    def _a_key(req: SearchRequest) -> str:
        d = req.model_dump(mode="json", exclude={"session_id", "revision", "stage"})
        return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def _core(self, req: SearchRequest, **kw) -> SearchResponse:
        with self.core_lock:
            return self.engine.search(req, **kw)

    # --- основной вход -----------------------------------------------------------
    def run(self, req: SearchRequest) -> SearchResponse:
        if self.engine.settings.recognition_mode == "hybrid":
            return self._run_live(req)
        if self.engine.native:
            return self._run_native(req)
        t0 = time.perf_counter()
        run_id = uuid.uuid4().hex[:12]
        self._register(req)
        providers: list[ProviderStatus] = []
        akey = self._a_key(req) + json.dumps(self.versions(), sort_keys=True)
        cached = self.a_cache.get(akey)
        if cached is not None:
            resp = cached.model_copy(deep=True)
            resp.timings = dict(resp.timings, a_cache_hit=1.0)
        else:
            resp = self._core(req)
            if self.semantic is not None and self.cfg.semantic:
                ts = time.perf_counter()
                try:
                    props = self.semantic.propose(resp, req.text, set(req.rejected))
                    resp.proposals += props
                    providers.append(ProviderStatus(name="semantic", enabled=True, used=True, status="ok",
                                                    detail=f"предложений: {len(props)}",
                                                    elapsed_ms=round((time.perf_counter() - ts) * 1000, 2)))
                    self._type_question_from_proposals(resp)
                except Exception as e:  # noqa: BLE001 — сбой модели не ломает ядро
                    providers.append(ProviderStatus(name="semantic", enabled=True, status="error", detail=str(e)))
                resp.timings["semantic"] = round((time.perf_counter() - ts) * 1000, 2)
            self.a_cache.put(akey, resp.model_copy(deep=True))
        if self.semantic is None or not self.cfg.semantic:
            providers.append(ProviderStatus(name="semantic", enabled=False, status="off"))
        draft = resp
        if req.stage == "submitted":
            resp = self._stage_b(req, draft, providers)
        else:
            providers.append(ProviderStatus(name="llm", enabled=self.cfg.b_mode != "off", status="skipped"
                                            if self.cfg.b_mode != "off" else "off",
                                            detail="черновик: разбор B выполняется только по Enter"))
        resp.run_id = run_id
        resp.session_id, resp.revision, resp.stage = req.session_id, req.revision, req.stage
        resp.preliminary = req.stage == "draft"
        resp.providers = providers
        resp.versions = self.versions()
        resp.stale = self.is_stale(req)
        resp.timings["end_to_end"] = round((time.perf_counter() - t0) * 1000, 2)
        self._log(req, resp)
        return resp

    def _run_live(self, req):
        from .live_search import LiveSearch
        self._register(req)
        if not hasattr(self, "live"):
            with self.core_lock:
                if not hasattr(self, "live"):
                    self.live = LiveSearch(self)
        expected = hashlib.sha256(req.text.encode()).hexdigest()[:16]
        # как в ядре: без хеша ответы не сверяются (скрытая строка сама держит их по фрагментам текста)
        if req.answers and req.answers_query_hash and req.answers_query_hash != expected:
            req = req.model_copy(update={"answers": []})
        t0 = time.perf_counter()
        key = "live:" + self._a_key(req) + json.dumps(self.versions(), sort_keys=True)
        hit = self.a_cache.get(key)
        if hit:
            fast, positions, facts, verified = hit[0].model_copy(deep=True), hit[1], hit[2], hit[3]
        else:
            fast, positions, facts, verified = self.live.fast(req)
            self.a_cache.put(key, (fast.model_copy(deep=True), positions, facts, verified))
        response = self.live.full(req, fast, positions, facts, verified) if req.stage == "submitted" else fast
        response.session_id, response.revision, response.stage = req.session_id, req.revision, req.stage
        response.run_id = uuid.uuid4().hex[:12]
        response.stale = self.is_stale(req)
        response.versions = self.versions()
        response.timings["end_to_end"] = round((time.perf_counter() - t0) * 1000, 2)
        self._log(req, response)
        return response

    def _run_native(self, req: SearchRequest) -> SearchResponse:
        """Reuse the real engine for confirmed constraints; lexical parsing is bypassed."""
        from .llm import catalog_extractor as extract
        t0 = time.perf_counter()
        self._register(req)
        providers = []
        bkey = None
        expected_hash = hashlib.sha256(req.text.encode()).hexdigest()[:16]
        if req.answers and req.answers_query_hash and req.answers_query_hash != expected_hash:
            req = req.model_copy(update={"answers": []})
        scope = self.engine.catalog_scope
        type_choice = next((c for c in [*req.overrides, *req.answers] if c.property == TYPE_PROP and not c.remove), None)
        selected = scope.selected(type_choice.value) if type_choice else None
        akey = self._a_key(req) + json.dumps(self.versions(), sort_keys=True)
        cached = self.a_cache.get(akey)
        if cached is None:
            resp = self._core(req)
            if self.semantic is not None and self.cfg.semantic and not self.is_stale(req):
                ts = time.perf_counter()
                try:
                    resp.proposals = self.semantic.propose(resp, req.text, set(req.rejected))
                    resp.completeness.retrieval_total_hits = len(scope.types)
                    resp.completeness.retrieval_returned = len(resp.proposals)
                    resp.completeness.retrieval_complete = len(resp.proposals) == len(scope.types)
                    resp.stages[0].remaining = len(resp.proposals)
                    resp.stages[0].note = "Предложения типов; не изменяют подтверждённую область каталога"
                    providers.append(ProviderStatus(name="semantic", enabled=True, used=True, status="ok"))
                except Exception as e:
                    providers.append(ProviderStatus(name="semantic", enabled=True, status="error", detail=str(e)))
                resp.timings["semantic"] = round((time.perf_counter() - ts) * 1000, 2)
            else:
                providers.append(ProviderStatus(name="semantic", enabled=self.cfg.semantic,
                                                status="error" if self.cfg.semantic else "off", detail="энкодер не загружен"))
            if not selected:
                seen_codes = set()
                previews = []
                for proposal in resp.proposals:
                    if proposal.kind != "type" or proposal.answer is None:
                        continue
                    for p in scope.positions(proposal.answer.value):
                        if p.is_template or p.code in seen_codes:
                            continue
                        seen_codes.add(p.code)
                        previews.append(Candidate(code=p.code, name=p.name, version=p.version,
                            okpd2=p.okpd2_code, category=p.category, is_template=False, active=p.active,
                            parent_code=p.parent_code, no_new_features=p.no_new_features, compatible=True,
                            rank=len(previews) + 1, checks=[]))
                resp.preview_candidates = previews[:50]
                resp.preview_total = len(previews)
                resp.question = Question(kind="type", text="Подтвердите обозначение товара из каталога",
                    current_remaining=len(scope.codes), worst_case_remaining=len(scope.codes),
                    options=[QuestionOption(label=p.label, remaining=len(scope.types[p.answer.value].codes), answer=p.answer)
                             for p in resp.proposals if p.kind == "type"],
                    reason="Предложения не сужают область; полный список доступен через поиск типа, также можно выбрать «ни один».")
                # The full catalogue schema remains in the server, not a giant draft payload.
                resp.properties = []
            self.a_cache.put(akey, (resp.model_copy(deep=True), list(providers)))
        else:
            resp, providers = cached[0].model_copy(deep=True), list(cached[1])
            resp.timings["a_cache_hit"] = 1.0
        llm_out = None
        validated_key = hashlib.sha256(json.dumps([req.text, selected.ref if selected else None, self.versions()], sort_keys=True).encode()).hexdigest()
        if req.stage == "submitted" and selected and self.llm is not None and self.cfg.b_mode != "off" and not req.manual_only:
            ctx = extract.build_context(scope, selected.ref, req.text, self.semantic,
                                        [c.model_dump() for c in [*req.answers, *req.overrides]])
            bkey = extract.cache_key(req.text, ctx, self.native_digest, getattr(self.llm, "options", {}))
            reply = self.b_cache.get(bkey)
            previous = self.validated_cache.get(validated_key) if req.action == "confirm" else None
            if previous:
                reply, ctx = previous
            status = "cached" if reply is not None else "ok"
            ms = 0.0
            if reply is None and req.action != "confirm":
                # Waiting old tasks never enter the model once a newer revision is registered.
                with self.llm_lock:
                    if not self.is_stale(req):
                        reply = self.b_cache.get(bkey)
                        if reply is not None:
                            status = "cached"
                        else:
                            llm_out = self.llm.complete(extract.messages_for(req.text, ctx), extract.schema_for(ctx))
                if llm_out is not None:
                    self.extraction_log[bkey] = {"context": ctx.payload, "reply": llm_out.text,
                                                "id_map": {"properties": ctx.property_ids, "values": ctx.value_ids},
                                                "meta": llm_out.meta, "error": llm_out.error}
                if llm_out is not None and llm_out.ok and llm_out.meta.get("done_reason") != "length":
                    reply, ms = llm_out.text, llm_out.elapsed_ms
                elif llm_out is not None:
                    providers.append(ProviderStatus(name="llm", enabled=True, used=True,
                        status="timeout" if llm_out.kind == "timeout" else "error", detail=llm_out.error or "обрезанный ответ",
                        elapsed_ms=llm_out.elapsed_ms))
                    resp.issues.append(Issue(level="warning", code="llm_unavailable", message="Разбор недоступен: введите характеристики вручную."))
                    if resp.status == "matched":
                        resp.status, resp.final_code, resp.final_name = "clarification_needed", None, None
            if reply is not None and not self.is_stale(req):
                result = extract.parse_and_validate(req.text, reply, ctx)
                providers.append(ProviderStatus(name="llm", enabled=True, used=True,
                    status=status if result.valid else "invalid", detail=result.error, elapsed_ms=ms))
                if result.valid:
                    self.validated_cache.put(validated_key, (reply, ctx))
                    if status != "cached":
                        self.b_cache.put(bkey, reply)
                    type_proposals = resp.proposals
                    if self.semantic is not None:
                        for feature in result.features:
                            if feature.property_code is None:
                                refs = self.semantic.rank_properties(feature.evidence or feature.value or "", list(ctx.all_groups))[:5]
                                feature.options = [{"property_code": r, "property_name": ctx.all_groups[r].name}
                                                   for r in refs]
                                feature.note += "; варианты найдены в полной схеме, привязку выбирает пользователь"
                    resp = self._core(req, model_features=result.features)
                    resp.completeness.retrieval_total_hits = len(scope.types)
                    resp.completeness.retrieval_returned = len(type_proposals)
                    resp.completeness.retrieval_complete = len(type_proposals) == len(scope.types)
                    for proposal in result.proposals:
                        for f in resp.features:
                            if f.source in ("answer", "override") and f.status == "bound" and f.characteristic_ref == proposal.characteristic_ref \
                                    and f.value == proposal.answer.value and f.values == proposal.answer.values:
                                f.evidence = proposal.quote
                                f.raw_span = (proposal.span.start, proposal.span.end) if proposal.span else None
                                f.supported_by = ["llm"]
                                raw = next((x for x in result.features if x.proposal_key == proposal.key), None)
                                for assertion in resp.assertions:
                                    if assertion.feature_id == f.id:
                                        assertion.span = proposal.span
                                        if raw:
                                            assertion.raw_value, assertion.raw_unit = raw.value, raw.unit
                    manual_codes = {f.characteristic_ref for f in resp.features if f.source in ("answer", "override") and f.status in ("bound", "proposed")}
                    pending = [p for p in result.proposals if p.key not in req.rejected and p.answer.property not in manual_codes]
                    resp.proposals = type_proposals + pending
                    if pending and len({p.answer.property for p in pending}) == len(pending):
                        resp.question = Question(kind="confirm", text="Подтвердите трактовки характеристик",
                            current_remaining=len(resp.compatible_codes),
                            worst_case_remaining=len(resp.compatible_codes),
                            options=[QuestionOption(label="Подтвердить все показанные трактовки", remaining=len(resp.compatible_codes),
                                answers=[p.answer for p in pending])], reason="; ".join(p.label for p in pending))
                    review_key = "parse-review:" + validated_key
                    if review_key not in req.confirmed:
                        if resp.question and resp.question.kind == "confirm" and pending:
                            resp.question.options[0].confirm.append(review_key)
                        else:
                            resp.question = Question(kind="confirm", text="Подтвердите результат разбора описания",
                                current_remaining=len(resp.compatible_codes), worst_case_remaining=len(resp.compatible_codes),
                                options=[QuestionOption(label="Разбор проверен, перейти к проверке КТРУ", remaining=len(resp.compatible_codes),
                                                        confirm=[review_key])],
                                reason="Проверьте извлечённые и пропущенные характеристики; пустой ответ модели не доказывает их отсутствие.")
                        if resp.status == "matched":
                            resp.status, resp.final_code, resp.final_name = "clarification_needed", None, None
                            if resp.code_resolution:
                                resp.code_resolution.status = "unconfirmed"
                    resp.unrecognized = list(dict.fromkeys(result.unresolved))
                    for reason in result.rejected:
                        resp.issues.append(Issue(level="warning", code="llm_item_rejected", message=reason))
                    if result.unresolved or result.rejected or result.ambiguities:
                        if resp.status == "matched":
                            resp.status, resp.final_code, resp.final_name = "clarification_needed", None, None
                            resp.message = "Остались неразобранные или неоднозначные фрагменты; уточните их вручную."
                            if resp.code_resolution:
                                resp.code_resolution.status = "unconfirmed"
                    if ctx.omitted:
                        resp.issues.append(Issue(level="info", code="llm_context_truncated",
                            message=f"Контекст обрезан ({len(ctx.omitted)} элементов); полная схема доступна для ручной привязки."))
                    self.extraction_log[bkey] = {"context": ctx.payload, "reply": reply, "rejected": result.rejected,
                                                "id_map": {"properties": ctx.property_ids, "values": ctx.value_ids},
                                                "meta": llm_out.meta if llm_out is not None else self.extraction_log.get(bkey, {}).get("meta", {})}
                    if len(self.extraction_log) > self.cfg.cache_size:
                        self.extraction_log.pop(next(iter(self.extraction_log)))
                    resp.timings["llm"] = ms
                else:
                    resp.issues.append(Issue(level="warning", code="llm_invalid", message=result.error))
                    if resp.status == "matched":
                        resp.status, resp.final_code, resp.final_name = "clarification_needed", None, None
        else:
            providers.append(ProviderStatus(name="llm", enabled=self.cfg.b_mode != "off", status="off" if self.cfg.b_mode == "off" else "skipped",
                detail="выбран явный ручной ввод" if req.manual_only else "LLM вызывается только после Enter и подтверждения типа"))
            if req.manual_only:
                resp.issues.append(Issue(level="info", code="manual_only", message="Проверены только явно введённые пользователем характеристики; модельный разбор не применяется."))
            elif req.stage == "submitted" and selected and (self.llm is None or self.cfg.b_mode == "off") and resp.status == "matched":
                resp.status, resp.final_code, resp.final_name = "clarification_needed", None, None
                resp.message = "Полный разбор недоступен: выберите явный ручной ввод и проверьте характеристики."
        if req.stage == "draft":
            # A draft cannot be a completed classification, including an exact manual scope.
            if resp.status == "matched":
                resp.status, resp.final_code, resp.final_name = "clarification_needed", None, None
                resp.message = "Предварительная проверка; нажмите Enter для завершения."
                if resp.code_resolution:
                    resp.code_resolution.status = "unconfirmed"
        resp.run_id = uuid.uuid4().hex[:12]
        resp.session_id, resp.revision, resp.stage = req.session_id, req.revision, req.stage
        resp.preliminary, resp.stale = req.stage == "draft", self.is_stale(req)
        resp.providers, resp.versions = providers, self.versions()
        resp.timings["end_to_end"] = round((time.perf_counter() - t0) * 1000, 2)
        self._log(req, resp, self.extraction_log.get(bkey))
        return resp

    # --- B ------------------------------------------------------------------------
    def _stage_b(self, req: SearchRequest, draft: SearchResponse, providers: list[ProviderStatus]) -> SearchResponse:
        if self.cfg.b_mode == "off" or self.llm is None:
            providers.append(ProviderStatus(name="llm", enabled=False, status="off",
                                            detail="расширенный разбор выключен (LLM_MODE=off)"))
            return draft
        reasons = escalation_reasons(draft)
        if self.cfg.b_mode == "escalate" and not reasons:
            providers.append(ProviderStatus(name="llm", enabled=True, status="skipped",
                                            detail="эскалация не нужна: правила разобрали описание"))
            return draft
        if self.is_stale(req):
            providers.append(ProviderStatus(name="llm", enabled=True, status="stale",
                                            detail="пришла новая версия запроса — вызов не выполнялся"))
            return draft
        from .llm.context import build_context
        from .llm.extractor import cache_key, messages_for, parse_and_validate, SCHEMA, type_proposal
        tb = time.perf_counter()
        heads = list(draft.detected_types)
        basis = {}
        if not heads:
            # тип не найден правилами: области из смысловых предложений и ближайших по словам позиций
            names = [p.label for p in draft.proposals if p.kind == "type"]
            for n in names:
                h = self.engine._head_of_name(n)
                if h and h not in heads:
                    heads.append(h)
                    basis[n] = "смысловое предложение A"
            if not heads:
                res = self.engine.backend.search(draft.query.get("terms", []), 20)
                pos = self.engine.catalog.get_many([h.code for h in res.hits])
                for c in sorted(pos, key=lambda c: [h.code for h in res.hits].index(c)):
                    h = pos[c].head
                    if h and h not in heads:
                        heads.append(h)
                        basis[pos[c].name] = "ближайшие по словам наименования"
        if not heads:
            providers.append(ProviderStatus(name="llm", enabled=True, status="skipped",
                                            detail="нет ни одной области каталога для контекста"))
            return draft
        dsum = None
        if self.cfg.b_include_draft:
            dsum = {"note": "гипотеза черновика (правила), может быть ошибочной",
                    "features": [{"quote": f.evidence, "property": f.property_name, "value": f.value,
                                  "unit": f.unit, "status": f.status} for f in draft.features if f.source == "text"],
                    "unrecognized": draft.unrecognized}
        snap = str(self.engine.catalog.meta.get("snapshot"))
        ctx = build_context(self.engine, heads, basis, snap, self.engine.effective_at, dsum)
        key = cache_key(req.text, ctx, self.llm.digest(), getattr(self.llm, "options", {}))
        hit = self.b_cache.get(key)
        status = "ok"
        if hit is not None:
            reply, meta, status = hit, {}, "cached"
            ms = 0.0
        else:
            with self.llm_lock:
                if self.is_stale(req):
                    providers.append(ProviderStatus(name="llm", enabled=True, status="stale",
                                                    detail="версия устарела в очереди — вызов отменён"))
                    return draft
                out = self.llm.complete(messages_for(req.text, ctx), SCHEMA)
            ms = out.elapsed_ms
            if not out.ok:
                st = "timeout" if out.kind == "timeout" else "error"
                providers.append(ProviderStatus(name="llm", enabled=True, used=True, status=st, detail=out.error,
                                                elapsed_ms=ms))
                draft.issues.append(Issue(level="warning", code="llm_unavailable",
                                          message="Расширенный разбор недоступен (" + out.error + "). Результат — "
                                                  "по правилам; уточните описание или выберите значения вручную."))
                draft.timings["llm"] = ms
                return draft
            reply, meta = out.text, out.meta
        b = parse_and_validate(req.text, reply, ctx, unexplained={w.lower() for w in draft.unrecognized})
        if not b.valid:
            providers.append(ProviderStatus(name="llm", enabled=True, used=True, status="invalid", detail=b.error,
                                            elapsed_ms=ms))
            draft.issues.append(Issue(level="warning", code="llm_invalid",
                                      message="Ответ расширенного разбора не прошёл проверку и не применён: " + b.error))
            draft.timings["llm"] = ms
            return draft
        if hit is None:
            self.b_cache.put(key, reply)
        if self.is_stale(req):
            providers.append(ProviderStatus(name="llm", enabled=True, used=True, status="stale",
                                            detail="ответ пришёл для устаревшей версии — не применён", elapsed_ms=ms))
            return draft
        model_type = b.model_type if not draft.completeness.type_confirmed else None
        final = self._core(req, model_features=b.features, model_type=model_type)
        final.proposals = list(draft.proposals) + b.proposals
        if b.model_type and model_type is None and draft.completeness.type_confirmed \
                and b.model_type not in {c.name for c in draft.candidates}:
            final.issues.append(Issue(level="warning", code="model_disagreement",
                                      message=f"Модель предлагает тип «{b.model_type}», правила — "
                                              f"{', '.join(draft.detected_types)}. Оставлен тип по правилам."))
        for r in b.rejected:
            final.issues.append(Issue(level="info", code="llm_item_rejected",
                                      message=f"Элемент ответа модели отклонён проверкой: {r['reason']} "
                                              f"({json.dumps(r['item'], ensure_ascii=False)[:160]})"))
        if b.ambiguities:
            final.issues.append(Issue(level="info", code="llm_ambiguities",
                                      message="Модель отметила неоднозначности: " + "; ".join(b.ambiguities)))
        final.changes = self._changes(draft, final)
        if ctx.omitted:
            final.issues.append(Issue(level="info", code="llm_context_truncated",
                                      message="Контекст модели обрезан: " + "; ".join(ctx.omitted[:3]) +
                                              ". Проверка ядром выполнена по всей области."))
        detail = (f"причины: {'; '.join(reasons) or 'режим always'}; принято признаков: {len(b.features)}, "
                  f"отклонено проверкой: {len(b.rejected)}, пустых: {b.ignored}; context_id={ctx.context_id}")
        providers.append(ProviderStatus(name="llm", enabled=True, used=True, status=status, detail=detail,
                                        elapsed_ms=ms))
        final.timings = dict(final.timings, llm=ms, stage_b=round((time.perf_counter() - tb) * 1000, 2),
                             draft_total=draft.timings.get("total", 0.0))
        if meta:
            final.timings["llm_eval_tokens"] = float(meta.get("eval_count") or 0)
        return final

    @staticmethod
    def _changes(draft: SearchResponse, final: SearchResponse) -> list[str]:
        out = []
        before = {f.property_name: f for f in draft.features if f.status == "bound" and f.property_name}
        for f in final.features:
            if f.source == "model" and f.status == "bound":
                old = before.get(f.property_name)
                if old is None:
                    out.append(f"Добавлено (предложено LLM, требует подтверждения): {describe(f)} по «{f.evidence}»")
                elif old.value != f.value:
                    out.append(f"«{f.property_name}» уточнено с «{old.value}» на «{f.value}» (предложено LLM)")
        if draft.status != final.status:
            out.append(f"Статус: {draft.status} → {final.status}")
        nd = sum(c.compatible and not c.is_template for c in draft.candidates)
        nf = sum(c.compatible and not c.is_template for c in final.candidates)
        if nd != nf:
            out.append(f"Совместимых конечных позиций: {nd} → {nf}")
        return out

    @staticmethod
    def _type_question_from_proposals(resp: SearchResponse) -> None:
        types = [p for p in resp.proposals if p.kind == "type"]
        if resp.status != "not_found" or not types or resp.question is not None:
            return
        resp.question = Question(
            kind="type", text="Тип товара не распознан правилами. Возможно, это одна из позиций:",
            worst_case_remaining=0, current_remaining=0,
            options=[QuestionOption(label=p.label + (f" ({p.score:.2f})" if p.score else ""), remaining=0,
                                    answer=p.answer) for p in types],
            reason="смысловые предложения (rubert-tiny2); близость — не вероятность; выберите или уточните описание")

    # --- журнал --------------------------------------------------------------------
    def _log(self, req: SearchRequest, resp: SearchResponse, extraction=None) -> None:
        if not self.cfg.event_log:
            return
        ev = {"ts": time.time(), "run_id": resp.run_id, "session": req.session_id, "revision": req.revision,
              "stage": req.stage, "stale": resp.stale, "status": resp.status, "final_code": resp.final_code,
              "code_resolution": resp.code_resolution.status if resp.code_resolution else None,
              "query_hash": resp.query_hash, "text": req.text,
              "providers": [p.model_dump() for p in resp.providers], "timings": resp.timings,
              "versions": resp.versions,
              "features": [{"property": f.property_name, "value": f.value, "unit": f.unit, "status": f.status,
                            "origin": f.origin, "confirmation": f.confirmation} for f in resp.features],
               "answers": [a.model_dump() for a in req.answers], "overrides": [o.model_dump() for o in req.overrides]}
        if self.engine.native:
            ev.update(request=req.model_dump(mode="json"), response=resp.model_dump(mode="json"), extraction=extraction)
        p = Path(self.cfg.event_log)
        p.parent.mkdir(parents=True, exist_ok=True)
        with self.log_lock, p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
