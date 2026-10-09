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


class SearchRequest(BaseModel):
    text: str = Field(max_length=2000)
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


class Feature(BaseModel):
    id: str
    source: Literal["text", "override", "answer"]
    status: Literal["bound", "ambiguous", "unknown_property", "overridden", "removed"]
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
    answer: Constraint


class Question(BaseModel):
    kind: Literal["property", "type", "manual_choice"]
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
