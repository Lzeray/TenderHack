"""Настройки из переменных окружения. Все значения имеют явные значения по умолчанию."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Версии правил: меняются вручную при изменении соответствующего модуля.
VERSIONS = {
    "api": "2.0",
    "importer": "1.0",
    "normalizer": "1.1",      # карта координат исходного текста, отрицательные числа
    "typos": "1.0",
    "extractor": "1.1",       # алиасы значений, части товара, «не менее» = ≥ (ошибка 1.0: было <)
    "validator": "1.1",       # семантика требования (intent=requirement)
    "ranking": "1.0",
    "clarifier": "1.1",       # сначала тип при неоднозначном алиасе
    "engine": "2.0",          # реестр типов, защита завершения, code_resolution / completion
    "type_registry": "1.0",
    "resolver": "1.0",
    "plausibility": "1.0",
}

# Направления MVP. Критерий — префикс ОКПД2 (см. docs/DATA.md, почему не рубрикатор).
CATEGORIES = {
    "clothes": {"title": "Одежда", "okpd2_prefixes": ["14."]},
    "furniture": {"title": "Мебель", "okpd2_prefixes": ["31."]},
    "tools": {"title": "Инструменты", "okpd2_prefixes": ["25.73", "28.24"]},
}


def category_for_okpd2(code: str | None) -> str | None:
    if not code:
        return None
    for key, cat in CATEGORIES.items():
        if any(code.startswith(p) for p in cat["okpd2_prefixes"]):
            return key
    return None


@dataclass(frozen=True)
class Settings:
    db_path: Path
    search_backend: str
    opensearch_url: str
    opensearch_index: str
    top_k: int
    type_fetch_limit: int
    encoder_path: Path = ROOT / "data" / "models" / "rubert-tiny2"
    cache_dir: Path = ROOT / "data" / "cache"
    ollama_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:4b-instruct-2507-q4_K_M"

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            db_path=Path(os.environ.get("KTRU_DB", str(ROOT / "data" / "ktru.sqlite"))),
            search_backend=os.environ.get("SEARCH_BACKEND", "local"),
            opensearch_url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
            opensearch_index=os.environ.get("OPENSEARCH_INDEX", "ktru_positions"),
            top_k=int(os.environ.get("TOP_K", "50")),
            type_fetch_limit=int(os.environ.get("TYPE_FETCH_LIMIT", "1000")),
            encoder_path=Path(os.environ.get("ENCODER_PATH", str(ROOT / "data" / "models" / "rubert-tiny2"))),
            cache_dir=Path(os.environ.get("CACHE_DIR", str(ROOT / "data" / "cache"))),
            ollama_url=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
            llm_model=os.environ.get("LLM_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
        )
