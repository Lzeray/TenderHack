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
from .models import Issue, ProviderStatus, Question, QuestionOption, SearchRequest, SearchResponse
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
            event_log=os.environ.get("EVENT_LOG") or None,
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
        self.log_lock = threading.Lock()

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
        v["orchestrator"] = "1.0"
        v["llm_mode"] = self.cfg.b_mode
        if self.semantic is not None:
            v["semantic_encoder"] = self.semantic.revision
        if self.llm is not None and self.cfg.b_mode != "off":
            from .llm.extractor import PROMPT_VERSION, SCHEMA_HASH
            v["llm_model"] = f"{self.llm.model}@{self.llm.digest()[:19]}"
            v["llm_prompt"] = PROMPT_VERSION
            v["llm_schema"] = SCHEMA_HASH
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
    def _log(self, req: SearchRequest, resp: SearchResponse) -> None:
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
        p = Path(self.cfg.event_log)
        p.parent.mkdir(parents=True, exist_ok=True)
        with self.log_lock, p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
