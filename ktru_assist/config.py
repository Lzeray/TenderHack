"""Настройки из переменных окружения. Все значения имеют явные значения по умолчанию."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Версии правил: меняются вручную при изменении соответствующего модуля.
VERSIONS = {
    "api": "3.1",
    "importer": "1.0",
    "normalizer": "1.5",
    "typos": "1.1",
    "extractor": "2.0",
    "validator": "1.7",       # 1.7 дискретный диапазон «48-50»; 1.6 одна ось — разные названия; 1.5 диапазон против ступеней КТРУ; 1.4 unknown_reason; 1.3 конфликтующие условия запроса по всей области каталога (aydar)
    "ranking": "1.0",
    "clarifier": "1.3",       # 1.3 слияние: полные списки вариантов, свойства по идентичности (aydar) + подтверждение наименования
    "engine": "2.7",          # 2.7 слияние с aydar: живой поиск, двухветочный структурный поиск
    "type_registry": "1.4",   # 1.4 кэш нечёткого сравнения главных слов
    "resolver": "1.0",
    "plausibility": "1.1",
    "live_search": "1.1",
    "ste_search": "1.0",
    "suspicious": "1.1",      # уровень 3: scale (КТРУ и выгрузки), unit_missing, placeholder (docs/LEVELS_PLAN.md)
    "empirical": "1.4",
    "dims": "1.1",            # 1.1 доля моделей под условием, близость границы
    "unit_infer": "1.0",      # подстановка единиц (docs/UNITS_PLAN.md)            # габариты: раскладка по общим осям (docs/DIMENSIONS_PLAN.md)       # уровень 2: typical/rare/unseen по выгрузкам СТЕ (docs/LEVELS_PLAN.md)
}
# История изменений правил (подробности и замеры — docs/EXPERIMENTS.md):
# normalizer 1.1 карта координат исходного текста, отрицательные числа; 1.2 режим KTRU_MORPH (pymorphy | snowball),
#   служебные слова через lemma_set; 1.3 обозначение размера одежды «р.66», «размер 48/170».
# normalizer 1.4 тире в диапазоне, разряды «1 200 мм», допуск «±», «~».
# extractor 1.8 «около/примерно X» = ±5 % у измеряемых величин; 1.9 общая ось важнее размера части («глубина 40 см»);
#   2.0 габариты целиком, упаковка, дискретный диапазон, число без названия не бывает толщиной.
# normalizer 1.5 «120 на 60 на 75», «120 см x 60 см».
# typos 1.1 из равноудалённых вариантов — единственный тип товара.
# extractor 1.1 алиасы значений, части, «не менее» = ≥; 1.2 часть — свободное слово; 1.3 «Без X» только целиком;
#   1.4 частичное совпадение без слов наименования, поглощение вложенных значений; 1.5 слово найденного значения
#   не указывает на часть товара; 1.6 все упоминания логических свойств, привязка чисел (занятые слова,
#   счётные/измеряемые, габариты), значение только из наименования уступает; 1.7 явно заданное свойство
#   не получает значение из слов наименования.
# validator 1.1 семантика требования (intent=requirement).
# clarifier 1.1 сначала тип при неоднозначном алиасе; 1.2 вопрос-подтверждение единственного наименования.
# engine 2.0 реестр типов, защита завершения, code_resolution; 2.1 dimension_mismatch; 2.2–2.3 токены наименования
#   и составного типа передаются экстрактору; 2.4 одно наименование подтверждает тип только при поддержке текста;
#   2.5 неоднозначная опечатка блокирует код, только если вариант — слово области; 2.6 противоречивые значения
#   одного свойства → conflict с вопросом.
# type_registry 1.1 тип по составу слова (дефис, сложные слова); 1.2 слова после предлога не повышаются до типа;
#   1.3 предлог ищется через числа и обрывки.
# plausibility 1.1 ядра названий свойств сравниваются через lemma().

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
    recognition_mode: str = "rules"
    ste_stats_path: Path = ROOT / "data" / "ste_stats.sqlite"   # уровень 2: статистика выгрузок СТЕ

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
            recognition_mode=os.environ.get("RECOGNITION_MODE", "rules"),
            ste_stats_path=Path(os.environ.get("STE_STATS", str(ROOT / "data" / "ste_stats.sqlite"))),
        )
