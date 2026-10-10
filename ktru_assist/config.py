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
    "normalizer": "1.3",      # 1.3 обозначение размера одежды «р.66», «размер 48/170»; 1.2 режим KTRU_MORPH (pymorphy | snowball), служебные слова через lemma_set;      # карта координат исходного текста, отрицательные числа
    "typos": "1.1",           # 1.1 равноудалённые варианты: приоритет типа товара;
    "extractor": "1.6",       # 1.6 все упоминания логических свойств; числа: занятые слова, счётные/измеряемые, габариты; значение только из наименования уступает; 1.5 слово полностью найденного значения не указывает на часть товара; 1.4 частичное совпадение без слов наименования, поглощение вложенных значений; 1.1 алиасы значений, части, «не менее» = ≥; 1.2 часть — свободное слово; 1.3 «Без X» только целиком
    "validator": "1.1",       # семантика требования (intent=requirement)
    "ranking": "1.0",
    "clarifier": "1.2",       # 1.2 вопрос-подтверждение единственного наименования;       # сначала тип при неоднозначном алиасе
    "engine": "2.6",          # 2.6 противоречивые значения одного свойства → conflict с вопросом; 2.5 неоднозначная опечатка блокирует код, только если вариант — слово области; 2.4 одно наименование подтверждает тип только при поддержке текста; 2.3 слова составного типа считаются словами наименования; 2.2 токены наименования передаются экстрактору;          # 2.0 реестр типов, защита завершения, code_resolution; 2.1 dimension_mismatch
    "type_registry": "1.3",   # 1.3 предлог ищется через числа и обрывки; 1.2 слова после предлога не повышаются до типа; 1.1 тип по составу слова: дефис, сложные слова
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
