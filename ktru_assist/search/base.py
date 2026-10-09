"""Интерфейс поиска кандидатов. Поиск только находит позиции; совместимость проверяет validate.py."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Hit:
    code: str
    score: float


@dataclass
class SearchResult:
    hits: list[Hit]
    total: int            # сколько документов удовлетворяет запросу (до обрезки size)
    backend: str
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return len(self.hits) >= self.total


class SearchBackend(Protocol):
    name: str

    def search(self, terms: list[str], size: int) -> SearchResult:
        """Активные позиции MVP, где встречается хотя бы один терм (OR), по убыванию релевантности."""

    def by_heads(self, heads: list[str], size: int) -> SearchResult:
        """Все активные позиции MVP с указанным главным словом наименования (исчерпывающе до size)."""
