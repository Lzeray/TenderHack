"""HTTP API (FastAPI) и раздача веб-интерфейса."""
from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .catalog.repository import Catalog
from .config import Settings
from .engine import Engine
from .models import SearchRequest, SearchResponse

WEB = Path(__file__).resolve().parent / "web"
_lock = threading.Lock()


def make_backend(settings: Settings, catalog: Catalog):
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


app = FastAPI(title="Подбор КТРУ", version="1.0",
              description="Автозаполнение характеристик и подбор конечной позиции КТРУ (MVP, без LLM).")


@app.get("/health")
def health():
    try:
        eng = get_engine()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "catalog_snapshot": eng.catalog.meta.get("snapshot"),
            "catalog_as_of": eng.catalog.meta.get("as_of"), "search_backend": eng.backend.name,
            "versions": eng.versions()}


@app.post("/api/search", response_model=SearchResponse)
def api_search(req: SearchRequest) -> SearchResponse:
    return get_engine().search(req)


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


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
