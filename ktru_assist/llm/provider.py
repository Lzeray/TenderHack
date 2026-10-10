"""Провайдеры LLM для разбора B. Только локальные: Ollama на этой же машине.

Провайдер изолирован интерфейсом `complete(messages, schema) -> ProviderResult`: замена модели
или рантайма не меняет ядро и правила соответствия КТРУ. Внешние API не используются.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    ok: bool
    text: str = ""
    error: str = ""
    kind: str = ""            # "" | timeout | http | connection | invalid
    elapsed_ms: float = 0.0
    attempts: int = 1
    meta: dict = field(default_factory=dict)


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str, model: str, timeout_s: float = 20.0, num_ctx: int = 12288, num_predict: int = 1536,
                 seed: int = 0, think: bool | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.think = think
        self.options = {"temperature": 0, "seed": seed, "num_ctx": num_ctx, "num_predict": num_predict}
        self._digest: str | None = None
        self._digest_failed_at = 0.0
        self.expected_digest: str | None = None

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def digest(self) -> str:
        """Закреплённая ревизия модели (digest из Ollama), а не тег «latest»."""
        if self._digest is None:
            if time.monotonic() - self._digest_failed_at < 30:   # не опрашивать недоступный сервер на каждый запрос
                return "unavailable"
            try:
                with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r:
                    tags = json.loads(r.read().decode())
                m = next((m for m in tags.get("models", []) if m.get("name") == self.model or
                          m.get("model") == self.model), None)
                if m is None:
                    self._digest_failed_at = time.monotonic()
                    return "unknown"
                self._digest = m.get("digest", "") or "unknown"
            except Exception:  # noqa: BLE001
                self._digest_failed_at = time.monotonic()
                return "unavailable"
        return self._digest

    def available(self) -> bool:
        return self.digest() not in ("unavailable", "unknown")

    def complete(self, messages: list[dict], schema: dict) -> ProviderResult:
        if self.expected_digest is not None:
            try:
                with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r:
                    tags = json.loads(r.read().decode())
                current = next((m.get("digest") for m in tags.get("models", []) if m.get("name") == self.model or m.get("model") == self.model), None)
                if current != self.expected_digest:
                    return ProviderResult(ok=False, kind="invalid", error="ревизия модели изменилась; перезапустите сессию сервиса")
            except Exception as e:
                return ProviderResult(ok=False, kind="connection", error=str(e))
        body = {"model": self.model, "messages": messages, "format": schema, "stream": False,
                "options": self.options, "keep_alive": "30m"}
        if self.think is not None:
            body["think"] = self.think
        t0 = time.perf_counter()
        last = ProviderResult(ok=False)
        for attempt in (1, 2):   # один ограниченный повтор — только при техническом сбое
            try:
                data = self._post("/api/chat", body, self.timeout_s)
                text = data.get("message", {}).get("content", "")
                meta = {k: data.get(k) for k in ("eval_count", "prompt_eval_count", "total_duration",
                                                 "load_duration", "done_reason")}
                return ProviderResult(ok=True, text=text, elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
                                      attempts=attempt, meta=meta)
            except TimeoutError as e:
                return ProviderResult(ok=False, error=f"таймаут {self.timeout_s} с: {e}", kind="timeout",
                                      elapsed_ms=round((time.perf_counter() - t0) * 1000, 1), attempts=attempt)
            except urllib.error.HTTPError as e:
                last = ProviderResult(ok=False, error=f"HTTP {e.code}: {e.read()[:200]!r}", kind="http",
                                      attempts=attempt)
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                if "timed out" in str(e):
                    return ProviderResult(ok=False, error=f"таймаут {self.timeout_s} с", kind="timeout",
                                          elapsed_ms=round((time.perf_counter() - t0) * 1000, 1), attempts=attempt)
                last = ProviderResult(ok=False, error=f"нет соединения: {e}", kind="connection", attempts=attempt)
        last.elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        return last


class FakeProvider:
    """Провайдер для тестов: возвращает заранее заданный ответ. Не является моделью."""
    name = "fake"
    model = "fake"

    def __init__(self, reply=None, error: str = "", kind: str = ""):
        self.reply, self.error, self.kind = reply, error, kind
        self.calls: list[list[dict]] = []

    def digest(self) -> str:
        return "fake"

    def available(self) -> bool:
        return True

    def complete(self, messages, schema) -> ProviderResult:
        self.calls.append(messages)
        if self.error:
            return ProviderResult(ok=False, error=self.error, kind=self.kind or "connection")
        reply = self.reply(messages) if callable(self.reply) else self.reply
        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return ProviderResult(ok=True, text=text, elapsed_ms=1.0)
