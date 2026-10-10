"""Адаптеры нашего решения (ktru_assist): в процессе и по HTTP.

  --adapter ktru:core            ядро без моделей (в процессе)
  --adapter ktru:core_sem_b      ядро + rubert-tiny2 + LLM по эскалации
  --adapter ktru:core_b_always   ядро + LLM на каждый запрос
  --adapter ktru:core_b_nodraft  как core_sem_b, но LLM без черновика правил
  --adapter ktru_http:http://127.0.0.1:8000   запущенный сервер (настройки моделей — переменными сервера)
"""
from __future__ import annotations

import itertools
import json
import urllib.request

from .base import Adapter

STATUS = {"matched": "matched", "clarification_needed": "clarification", "conflict": "conflict",
          "not_found": "not_found", "manual_choice": "manual_choice", "error": "error"}
CONFIGS = {
    "core": dict(b_mode="off", semantic=False),
    "core_b_always": dict(b_mode="always", semantic=False),
    "core_sem_b": dict(b_mode="escalate", semantic=True),
    "core_b_nodraft": dict(b_mode="escalate", semantic=True, b_include_draft=False),
}
_session = itertools.count(1)


def _finals(r: dict) -> list[str]:
    """Совместимые конечные позиции в порядке ранга системы (первая — лучшая)."""
    fin = [c for c in r.get("candidates", []) if c["compatible"] and not c["is_template"]]
    return [c["code"] for c in sorted(fin, key=lambda c: (c.get("rank") is None, c.get("rank") or 0))]


def normalize(r: dict) -> dict:
    return {
        "status": STATUS.get(r["status"], "error"),
        "final_code": r.get("final_code"),
        "compatible_codes": _finals(r),
        "ranked_codes": _finals(r),
        "features": [{"property": f.get("property_name"), "value": f.get("value"), "unit": f.get("unit"),
                      "op": f.get("op")} for f in r.get("features", [])
                     if f.get("status") in ("bound", "overridden") and f.get("property_name")],
        "warnings": [i["message"] for i in r.get("issues", []) if i["level"] in ("warning", "error")],
    }


class _Dialog:
    """Симуляция: на каждый вопрос выбирается вариант, после которого эталон остаётся совместимым."""

    def _call(self, payload: dict) -> dict:
        raise NotImplementedError

    def dialog(self, text, acceptable_codes, max_steps=6):
        """trace[i] — что видел пользователь после i ответов (ранжированный список и статус); reason — почему
        диалог закончился: matched | no_question | max_steps | no_option (ни один вариант не сохраняет эталон)."""
        sid = f"bench-{next(_session)}"
        rev = 1
        state = {"answers": [], "rejected": [], "confirmed": []}
        r = self._call({"text": text, "stage": "submitted", "session_id": sid, "revision": rev, **state})
        trace = []
        for step in range(max_steps + 1):
            trace.append({"ranked": _finals(r), "status": STATUS.get(r["status"], "error")})
            if r["status"] == "matched":
                return {"resolved": r["final_code"] in acceptable_codes, "steps": step, "final_code": r["final_code"],
                        "trace": trace, "reason": "matched"}
            q = r.get("question")
            if not q or step == max_steps or not acceptable_codes:
                return {"resolved": False, "steps": step, "final_code": None, "trace": trace,
                        "reason": "no_question" if not q else "max_steps"}
            chosen = None
            for opt in q["options"]:
                many = opt.get("answers") or ([opt["answer"]] if opt.get("answer") else [])
                props = {m["property"] for m in many}
                trial = {"answers": [a for a in state["answers"] if a["property"] not in props] + many,
                         "rejected": state["rejected"] + opt.get("reject", []),
                         "confirmed": state["confirmed"] + opt.get("confirm", [])}
                rev += 1
                rr = self._call({"text": text, "stage": "submitted", "session_id": sid, "revision": rev,
                                 "answers_query_hash": r["query_hash"], **trial})
                if {c["code"] for c in rr["candidates"] if c["compatible"] and not c["is_template"]} & acceptable_codes:
                    chosen = (trial, rr)
                    break
            if chosen is None:
                return {"resolved": False, "steps": step, "final_code": None, "trace": trace, "reason": "no_option"}
            state, r = chosen
        return {"resolved": False, "steps": max_steps, "final_code": None, "trace": trace, "reason": "max_steps"}


class KtruInProcess(_Dialog, Adapter):
    def __init__(self, config: str = "core"):
        from ktru_assist.api import get_engine
        if config not in CONFIGS:
            raise ValueError(f"неизвестная конфигурация {config}; есть: {', '.join(CONFIGS)}")
        self.name = f"ktru:{config}"
        try:
            from ktru_assist.api import build_orchestrator
            from ktru_assist.orchestrator import OrchestratorConfig
        except ImportError:
            # MVP без оркестратора (ветка main до плана улучшений): только ядро
            if config != "core":
                raise ValueError("в этой версии ktru_assist нет моделей: доступна только конфигурация core")
            self.o, self.engine = None, get_engine()
        else:
            self.o = build_orchestrator(get_engine(), OrchestratorConfig(cache_size=512, **CONFIGS[config]))
            self.engine = self.o.engine

    def info(self):
        return {"adapter": self.name, "versions": self.o.versions() if self.o else self.engine.versions()}

    def _call(self, payload):
        from ktru_assist.models import SearchRequest
        if self.o is None:
            return self.engine.search(SearchRequest(**payload)).model_dump(mode="json")
        return self.o.run(SearchRequest(**payload)).model_dump(mode="json")

    def predict(self, text):
        return normalize(self._call({"text": text, "stage": "submitted", "session_id": f"bench-{next(_session)}",
                                     "revision": 1}))


class KtruHttp(_Dialog, Adapter):
    def __init__(self, base: str = "http://127.0.0.1:8000"):
        self.base = base.rstrip("/")
        self.name = f"ktru_http:{self.base}"

    def _call(self, payload):
        req = urllib.request.Request(self.base + "/api/search", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())

    def info(self):
        with urllib.request.urlopen(self.base + "/health", timeout=10) as r:
            return {"adapter": self.name, "health": json.loads(r.read().decode())}

    def predict(self, text):
        return normalize(self._call({"text": text, "stage": "submitted", "session_id": f"bench-{next(_session)}",
                                     "revision": 1}))
