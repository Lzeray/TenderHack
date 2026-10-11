"""HTTP API (FastAPI) и раздача веб-интерфейса."""
from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .catalog.repository import Catalog
from .config import Settings
from .engine import Engine
from .models import SearchRequest, SearchResponse
from .orchestrator import Orchestrator, OrchestratorConfig

WEB = Path(__file__).resolve().parent / "web"
log = logging.getLogger("ktru_assist")
_lock = threading.Lock()


def make_backend(settings: Settings, catalog: Catalog):
    if settings.recognition_mode in ("semantic", "hybrid"):
        from .search.base import SearchResult
        class CatalogOnlyBackend:
            name = "catalogue-scope"
            def search(self, terms, size):
                return SearchResult([], 0, self.name)
            def by_heads(self, heads, size):
                raise AssertionError("Head-word lookup is not part of semantic recognition")
        return CatalogOnlyBackend()
    from .search.local_backend import LocalBM25Backend
    if settings.search_backend == "opensearch":
        from .search.opensearch_backend import OpenSearchBackend
        be = OpenSearchBackend(settings.opensearch_url, settings.opensearch_index)
        if not be.ping():
            raise RuntimeError(f"OpenSearch недоступен по адресу {settings.opensearch_url}. "
                               "Запустите его или задайте SEARCH_BACKEND=local.")
        return be
    return LocalBM25Backend(catalog.search_documents())


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    with _lock:
        settings = Settings.from_env()
        catalog = Catalog(settings.db_path)
        return Engine(catalog, make_backend(settings, catalog), settings)


def build_orchestrator(engine: Engine, cfg: OrchestratorConfig | None = None) -> Orchestrator:
    """Модели подключаются только по флагам (SEMANTIC=1, LLM_MODE=escalate|always); при ошибке загрузки —
    работа без них с явным статусом в ответе."""
    cfg = cfg or OrchestratorConfig.from_env()
    s = engine.settings
    semantic = llm = None
    if cfg.semantic:
        try:
            from .semantic.encoder import RubertTiny2
            if engine.native:
                from .semantic.catalog_index import CatalogIndex
                from .semantic.encoder import TransformersEncoder
                semantic = CatalogIndex(TransformersEncoder(s.encoder_path), engine.catalog_scope, s.cache_dir)
            else:
                from .semantic.proposer import SemanticProposer
                semantic = SemanticProposer(RubertTiny2(s.encoder_path), engine.catalog, engine.registry, s.cache_dir)
        except Exception as e:  # noqa: BLE001
            log.warning("семантический слой не загружен: %s", e)
    if cfg.b_mode != "off":
        from .llm.provider import OllamaProvider
        llm = OllamaProvider(s.ollama_url, s.llm_model, timeout_s=cfg.b_timeout_s,
                             num_ctx=4096 if s.recognition_mode == "hybrid" else 16384 if engine.native else 8192,
                             num_predict=768 if s.recognition_mode == "hybrid" else 2048 if engine.native else 1024)
    orchestrator = Orchestrator(engine, cfg, semantic=semantic, llm=llm)
    if s.recognition_mode == "hybrid":
        from .live_search import LiveSearch
        orchestrator.live = LiveSearch(orchestrator)
    return orchestrator


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    eng = get_engine()
    with _lock:
        return build_orchestrator(eng)


@asynccontextmanager
async def lifespan(_app):
    # Initialization/index loading is measured separately, before accepting typing requests.
    await run_in_threadpool(get_orchestrator)
    yield


app = FastAPI(title="Подбор КТРУ", version="3.1", lifespan=lifespan,
              description="Автозаполнение характеристик и подбор конечной позиции КТРУ. Детерминированное ядро; "
                          "локальные модели — только предложения, по флагам.")


@app.get("/health")
def health():
    try:
        eng = get_engine()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "catalog_snapshot": eng.catalog.meta.get("snapshot"),
            "catalog_as_of": eng.catalog.meta.get("as_of"), "search_backend": eng.backend.name,
            "versions": get_orchestrator().versions()}


@app.post("/api/search", response_model=SearchResponse)
def api_search(req: SearchRequest) -> SearchResponse:
    o = get_orchestrator()
    core = getattr(getattr(o, "live", None), "rules", None) or get_engine()
    if get_engine().native and (req.session_id is None or req.revision is None):
        raise HTTPException(422, "session_id и revision обязательны для семантического пути")
    if req.canonical is not None:
        # скрытая строка «тип; ключ: значение» (docs/PARSE_INPUT_PLAN.md, P4)
        from .canonical import process
        o = get_orchestrator()
        # разбор видимого текста — правилами: в гибридном режиме основной движок сам текст не разбирает
        core = getattr(getattr(o, "live", None), "rules", None) or get_engine()
        response = process(req, core, o.run, lock=o.core_lock)
    else:
        response = o.run(req)
    # Run only after Enter / the existing 1000 ms idle timer, on original visible text.
    # This separate provider cannot alter the primary recognizer or catalogue codes.
    # модели по умолчанию выключены (CLAUDE.md): Qwen для доп. характеристик включается EXTRAS_LLM=on (docker-compose)
    if os.environ.get("EXTRAS_LLM", "off") == "on":
        from .llm.extra_characteristics import enrich
        core = getattr(getattr(o, "live", None), "rules", None) or core
        response = enrich(req, response, core, get_extras_provider(), o.is_stale)
    response.stale = response.stale or o.is_stale(req)
    return response


@lru_cache(maxsize=1)
def get_extras_provider():
    from .llm.provider import OllamaProvider
    settings = Settings.from_env()
    return OllamaProvider(settings.ollama_url,
                          os.environ.get("EXTRAS_LLM_MODEL", "qwen3.5:4b"),
                          timeout_s=float(os.environ.get("EXTRAS_LLM_TIMEOUT", "20")),
                          num_ctx=16384, num_predict=1536, think=False)


@app.post("/api/revision")
def api_revision(req: SearchRequest):
    o = get_orchestrator()
    o._register(req)
    return {"session_id": req.session_id, "revision": req.revision, "stale": o.is_stale(req)}


@app.get("/api/catalog/types")
def api_types(q: str = ""):
    # Exact catalogue names, complete result list; not a synonym recognizer.
    scope = get_engine().catalog_scope
    return [{"ref": t.ref, "name": t.name, "category": t.category, "positions": len(t.codes)}
            for t in scope.types.values() if q.casefold() in t.name.casefold()]


@lru_cache(maxsize=1)
def get_value_scorer():
    if os.environ.get("VALUE_SCORER", "off") != "cross_encoder":
        return None
    from .semantic.value_scorer import LocalCrossEncoder
    return LocalCrossEncoder(Path(os.environ["CROSS_ENCODER_PATH"]))


@app.get("/api/catalog/values")
def api_values(type_ref: str, characteristic_ref: str, text: str = ""):
    from .clarify import _interval_constraint
    from .models import Constraint
    from .llm.catalog_extractor import build_context
    from .semantic.value_scorer import RecommendationPolicy
    scope = get_engine().catalog_scope
    selected = scope.selected(type_ref)
    if selected is None:
        raise HTTPException(404, "Неизвестный тип каталога")
    ctx = build_context(scope, type_ref, text, max_props=100000, max_values=100000)
    if characteristic_ref not in ctx.groups:
        raise HTTPException(404, "Характеристика не принадлежит выбранной области")
    g = ctx.groups[characteristic_ref]
    options = [{"value_id": r, "label": v.label,
                "answer": (Constraint(property=g.key, value=v.text).model_dump() if v.kind == "quality" else
                           _interval_constraint(g.key, v.interval, v.unit).model_dump() if v.interval else None),
                "context": selected.name + " · " + g.name + " · " + v.label}
               for r, (pr, v) in sorted(ctx.values.items()) if pr == characteristic_ref]
    result = None
    try:
        scorer = get_value_scorer()
        if scorer is not None:
            result = scorer.score(text, characteristic_ref, options)
    except Exception as e:
        result = {"error": str(e)}
    # Explicit experimental thresholds, outside the model; no automatic constraints.
    return RecommendationPolicy(min_score=float(os.environ.get("VALUE_MIN_SCORE", "0")),
        margin=float(os.environ.get("VALUE_MARGIN", "0.1"))).apply(options, result)


@app.get("/api/providers")
def api_providers():
    o = get_orchestrator()
    llm = None
    if o.llm is not None:
        llm = {"model": o.llm.model, "digest": o.llm.digest(), "available": o.llm.available(),
               "mode": o.cfg.b_mode, "timeout_s": o.cfg.b_timeout_s}
    return {"semantic": {"enabled": o.semantic is not None and o.cfg.semantic,
                         "encoder": o.semantic.revision if o.semantic else None},
             "llm": llm or {"mode": "off"}, "versions": o.versions()}


class ProductSearch(BaseModel):
    profile: dict
    offset: int = Field(0, ge=0)
    limit: int = Field(25, ge=1, le=100)


@app.post("/api/products")
def api_products(req: ProductSearch):
    # Подбор идёт только по КТРУ; товары СТЕ не выдаются (выгрузки подтверждают доп. характеристики).
    if os.environ.get("STE_PRODUCTS", "off") != "on" or req.profile.get("conflicts"):
        return {"total": 0, "items": [], "offset": req.offset, "limit": req.limit}
    o = get_orchestrator()
    service = getattr(o, "live", None)
    if service is None or service.ste is None:
        return {"total": 0, "items": [], "offset": req.offset, "limit": req.limit, "available": False}
    return service.ste.search(req.profile.get("item_terms", []), req.profile.get("attributes", []), req.offset, req.limit)


@app.get("/api/catalog")
def api_catalog():
    eng = get_engine()
    summary = eng.catalog.catalog_summary()
    summary["search_backend"] = eng.backend.name
    return summary


@app.get("/api/positions/{code}")
def api_position(code: str):
    p = get_engine().catalog.get(code)
    if p is None:
        raise HTTPException(404, f"Позиция {code} не найдена в импортированном снимке")
    return {
        "code": p.code, "name": p.name, "version": p.version, "okpd2": {"code": p.okpd2_code, "name": p.okpd2_name},
        "status": p.status, "active": p.active, "inactive_reason": p.inactive_reason, "is_template": p.is_template,
        "parent": {"code": p.parent_code, "version": p.parent_version} if p.parent_code else None,
        "no_new_features": p.no_new_features, "application_start": p.application_start,
        "application_end": p.application_end, "category": p.category, "rubrics": p.rubrics, "okeis": p.okeis,
        "characteristics": [{
            "code": pr.code, "name": pr.name, "type": pr.char_type, "kind": pr.kind, "required": pr.required,
            "values": [v.label for v in pr.values]} for pr in p.props.values()],
    }


@app.middleware("http")
async def no_cache_ui(request, call_next):
    """Интерфейс без кэша браузера: после обновления кода страница и скрипты сразу новые."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
