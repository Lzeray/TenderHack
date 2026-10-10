"""Контракт адаптера: как подключить любое решение к общему набору тестов.

Решение команды/участника оборачивается в класс с методом `predict(text) -> dict` (и, по желанию,
`dialog`). Формат ответа одинаков для всех решений — так метрики сравнимы.

predict(text) возвращает словарь:
  status            — "matched" | "clarification" | "conflict" | "not_found" | "manual_choice" | "error";
                      "matched" = решение выдало конечный код автоматически, без вопросов пользователю;
  final_code        — код КТРУ при matched, иначе None;
  compatible_codes  — список кодов, которые решение считает совместимыми (необязательно, None — не умеет);
  ranked_codes      — список, который пользователь видит первым, лучший кандидат первым (необязательно; если нет —
                      final_code, затем compatible_codes в их порядке). По нему считаются hit@1/@3/@5, mrr, ndcg@3;
  features          — [{"property": str, "value": str, "unit": str|None, "op": str}] (необязательно);
  warnings          — список строк: предупреждения/ошибки, показанные пользователю (необязательно).

dialog(text, acceptable_codes, max_steps) — необязательно: симуляция уточнений, где «пользователь»
выбирает вариант, совместимый с эталоном. Возвращает {"resolved": bool, "steps": int, "final_code": str|None}
и, по желанию, "trace": [{"ranked": [...], "status": str}, …] — что видел пользователь после 0, 1, 2… ответов
(по нему считается дальность эталона от вершины на каждом шаге), и "reason": matched | no_question | max_steps |
no_option (ни один вариант ответа не сохранял эталон).
Если метод не реализован, метрики диалога помечаются как not_supported.
"""
from __future__ import annotations

STATUSES = {"matched", "clarification", "conflict", "not_found", "manual_choice", "error"}


class Adapter:
    name = "base"

    def info(self) -> dict:
        """Версии и настройки решения — попадают в отчёт."""
        return {}

    def predict(self, text: str) -> dict:
        raise NotImplementedError

    def dialog(self, text: str, acceptable_codes: set[str], max_steps: int = 6) -> dict | None:
        return None
