"""Pydantic-модели запроса и ответа API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Op = Literal["eq", "ne", "ge", "gt", "le", "lt", "between"]


class Constraint(BaseModel):
    """Ограничение на свойство: ручная правка или ответ на уточняющий вопрос."""
    property: str = Field(description="код характеристики КТРУ или её наименование; '__type__' — тип товара")
    op: Op = "eq"
    value: Optional[str] = Field(None, description="текстовое значение или число строкой")
    value_to: Optional[str] = Field(None, description="верхняя граница для op=between")
    min_inclusive: bool = True
    max_inclusive: bool = True
    unit: Optional[str] = None
    remove: bool = Field(False, description="удалить извлечённое из текста значение этого свойства")


RunStage = Literal["draft", "submitted"]


class SearchRequest(BaseModel):
    text: str = Field(max_length=2000)
    session_id: Optional[str] = Field(None, max_length=64, description="идентификатор сеанса интерфейса")
    revision: Optional[int] = Field(None, ge=0, description="версия состояния: растёт при любом изменении ввода")
    stage: RunStage = Field("draft", description="draft — черновик A при вводе; submitted — Enter, допускает разбор B")
    rejected: list[str] = Field(default_factory=list, description="ключи отклонённых пользователем предложений")
    confirmed: list[str] = Field(default_factory=list,
                                 description="ключи подтверждённых предупреждений правдоподобия")
    overrides: list[Constraint] = Field(default_factory=list, description="ручное редактирование")
    answers: list[Constraint] = Field(default_factory=list, description="ответы на уточнения")
    answers_query_hash: Optional[str] = Field(None, description="хеш нормализованного текста, к которому даны ответы")
    corrections: dict[str, str] = Field(default_factory=dict, description="выбор исправления опечатки: слово → вариант")
    top_k: Optional[int] = Field(None, ge=1, le=500)


class Step(BaseModel):
    step: str
    before: str
    after: str
    note: str = ""


class Correction(BaseModel):
    original: str
    status: Literal["corrected", "ambiguous", "user_choice"]
    corrected: Optional[str] = None
    options: list[str] = Field(default_factory=list)
    distance: Optional[int] = None
    note: str = ""


Origin = Literal["rule", "semantic", "llm", "manual"]


class Feature(BaseModel):
    """Разрешённый признак (ResolvedAssertion): привязка к свойству КТРУ области поиска."""
    id: str
    source: Literal["text", "override", "answer", "model"]
    status: Literal["bound", "ambiguous", "unknown_property", "overridden", "removed", "proposed"]
    property_code: Optional[str] = None
    property_name: Optional[str] = None
    op: Op = "eq"
    value: Optional[str] = None
    value_to: Optional[str] = None
    min_inclusive: bool = True
    max_inclusive: bool = True
    unit: Optional[str] = None
    evidence: Optional[str] = None
    span: Optional[tuple[int, int]] = None
    negated: bool = False
    options: list[dict[str, Any]] = Field(default_factory=list, description="варианты свойства при неоднозначности")
    note: str = ""
    origin: Origin = "rule"
    confirmation: Literal["confirmed", "tentative"] = "confirmed"
    component: Optional[str] = Field(None, description="часть товара: каркас, сиденье, рукоятка …")
    canonical_key: Optional[str] = Field(None, description="компонент.свойство, напр. frame.color; внутренний ключ")
    intent: Literal["fact", "requirement", "preference", "unknown"] = "fact"
    raw_span: Optional[tuple[int, int]] = Field(None, description="координаты в исходном тексте (code points)")
    supported_by: list[str] = Field(default_factory=list, description="источники, согласные с трактовкой")
    proposal_key: Optional[str] = Field(None, description="ключ предложения модели (для подтверждения/отказа)")
    char_source: Optional[Literal["ktru", "portal", "new"]] = Field(
        None, description="источник характеристики: КТРУ, характеристика портала или новая")
    ktru_value: Optional[str] = Field(None, description="значение в единице характеристики КТРУ")
    ktru_unit: Optional[str] = None


class Span(BaseModel):
    start: int = Field(description="начало, Unicode code point, включительно")
    end: int = Field(description="конец, не включается")
    quote: str


class Predicate(BaseModel):
    kind: Literal["enum", "number", "bool", "range", "text"]
    operator: Op = "eq"


class RawAssertion(BaseModel):
    """Исходный признак: что и где написано, до привязки к схеме КТРУ."""
    assertion_id: str
    source: Origin
    span: Optional[Span] = None
    component_raw: Optional[str] = None
    property_raw: Optional[str] = None
    raw_value: Optional[str] = None
    raw_value_to: Optional[str] = None
    raw_unit: Optional[str] = None
    predicate: Predicate
    negated: bool = False
    intent: Literal["fact", "requirement", "preference", "unknown"] = "fact"
    proposed_property_ref: Optional[str] = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = Field(None, description="вспомогательный сигнал модели, не вероятность")
    confirmation: Literal["confirmed", "tentative", "rejected"] = "tentative"
    feature_id: Optional[str] = None
    status: str = Field("", description="результат согласования: accepted / proposed / rejected:<причина>")


class Proposal(BaseModel):
    """Предложение модели (A-semantic или B-llm). Не применяется без подтверждения пользователя."""
    key: str
    origin: Literal["semantic", "llm"]
    kind: Literal["type", "value", "correction"]
    quote: Optional[str] = None
    span: Optional[Span] = None
    label: str
    answer: Optional[Constraint] = Field(None, description="что отправить в answers при подтверждении")
    score: Optional[float] = Field(None, description="косинусная близость/сигнал модели — не вероятность")
    reason: str = ""


class CodeResolution(BaseModel):
    status: Literal["resolved", "unconfirmed", "multiple", "none", "conflict"]
    code: Optional[str] = None
    remaining: int = 0
    reason: str = ""


class CharacteristicsCompletion(BaseModel):
    """Полнота заполнения СТЕ — отдельно от однозначности кода."""
    complete: bool
    required_total: int = 0
    required_filled: int = 0
    missing: list[str] = Field(default_factory=list)
    unchecked: list[str] = Field(default_factory=list, description="указанные, но не проверенные (unknown)")


class Scope(BaseModel):
    detected_types: list[str] = Field(default_factory=list, description="предложенные типы (главные слова)")
    type_basis: list[str] = Field(default_factory=list, description="на чём основан выбор типа")
    confirmed_scope: Optional[str] = Field(None, description="подтверждённая область: наименование или тип")
    scope_complete: bool = False
    registry_complete: bool = Field(True, description="все позиции области покрыты реестром типов")
    note: str = ""


class ProviderStatus(BaseModel):
    name: str
    enabled: bool
    used: bool = False
    status: Literal["off", "ok", "skipped", "timeout", "error", "invalid", "cached", "stale"] = "off"
    detail: str = ""
    elapsed_ms: Optional[float] = None


class PropertyCheck(BaseModel):
    property_code: str
    property_name: str
    required: bool
    kind: Optional[int]
    status: Literal["valid", "invalid", "unknown"]
    reason: str
    allowed: list[str] = Field(default_factory=list)
    user_value: Optional[str] = None
    feature_id: Optional[str] = None


class RankComponents(BaseModel):
    name_tier: int
    name_coverage: str
    term_coverage: str
    valid_conditions: int
    unknown_conditions: int
    code: str
    search_score: Optional[float] = None


class Candidate(BaseModel):
    code: str
    name: str
    version: int
    okpd2: Optional[str]
    category: Optional[str]
    is_template: bool
    active: bool
    parent_code: Optional[str]
    no_new_features: Optional[bool]
    compatible: bool
    excluded_reason: Optional[str] = None
    rank: Optional[int] = None
    rank_components: Optional[RankComponents] = None
    checks: list[PropertyCheck] = Field(default_factory=list)


class Stage(BaseModel):
    stage: str
    remaining: int
    removed: int = 0
    note: str = ""


class QuestionOption(BaseModel):
    label: str
    remaining: int
    answer: Optional[Constraint] = None
    answers: list[Constraint] = Field(default_factory=list, description="несколько ответов сразу (подтверждение)")
    reject: list[str] = Field(default_factory=list, description="ключи предложений, отклоняемых этим вариантом")
    confirm: list[str] = Field(default_factory=list, description="ключи предупреждений, подтверждаемых вариантом")


class Question(BaseModel):
    kind: Literal["property", "type", "manual_choice", "confirm"]
    property_code: Optional[str] = None
    property_name: Optional[str] = None
    text: str
    required: bool = False
    worst_case_remaining: int
    current_remaining: int
    options: list[QuestionOption] = Field(default_factory=list)
    allows_number: bool = False
    unit: Optional[str] = None
    reason: str = ""


class Completeness(BaseModel):
    backend: str
    retrieval_total_hits: int
    retrieval_returned: int
    retrieval_complete: bool
    type_domain_total: int
    type_domain_returned: int
    type_domain_complete: bool
    type_confirmed: bool
    note: str = ""


class Issue(BaseModel):
    level: Literal["error", "warning", "info"]
    code: str
    message: str


class DomainProperty(BaseModel):
    code: str
    codes: list[str]
    name: str
    required: bool
    numeric: bool
    boolean: bool
    units: list[str]
    values: list[str] = Field(default_factory=list, description="качественные значения (до 50)")
    positions: int


class SearchResponse(BaseModel):
    status: Literal["matched", "clarification_needed", "conflict", "not_found", "manual_choice", "error"]
    session_id: Optional[str] = None
    revision: Optional[int] = None
    run_id: str = ""
    stage: RunStage = "draft"
    preliminary: bool = Field(True, description="черновик: результат не окончательный")
    stale: bool = Field(False, description="пришла более новая версия запроса — ответ не применять")
    message: str
    query: dict[str, Any]
    query_hash: str
    corrections: list[Correction]
    features: list[Feature]
    unrecognized: list[str]
    detected_types: list[str]
    candidates: list[Candidate]
    candidates_total: int
    stages: list[Stage]
    properties: list[DomainProperty] = Field(default_factory=list, description="свойства позиций области поиска")
    question: Optional[Question] = None
    final_code: Optional[str] = None
    final_name: Optional[str] = None
    issues: list[Issue]
    completeness: Completeness
    versions: dict[str, str]
    elapsed_ms: float
    assertions: list[RawAssertion] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    code_resolution: Optional[CodeResolution] = None
    characteristics_completion: Optional[CharacteristicsCompletion] = None
    scope: Optional[Scope] = None
    providers: list[ProviderStatus] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list, description="что изменилось после расширенного разбора")
    timings: dict[str, float] = Field(default_factory=dict, description="мс по этапам")
    effective_at: Optional[str] = Field(None, description="дата проверки активности позиций (снимок)")
