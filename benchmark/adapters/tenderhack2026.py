"""Адаптер решения команды MrDragar/TenderHack2026 (для сравнения на общем наборе тестов).

Их репозиторий клонируется отдельно (не в наш проект), справочник собирается их же скриптом:
  git clone https://github.com/MrDragar/TenderHack2026 ../competitors/TenderHack2026
  python3.14 scripts/build_ktru_actual.py --input "<наш КТРУ/КТРУ xml/КТРУ>" --as-of 2026-10-09
Запуск:
  python -m benchmark.run --adapter "benchmark.adapters.tenderhack2026:TenderHack2026=<путь к их репозиторию>" ...

Перевод их результата в общий формат:
  code есть → matched; есть вопрос → clarification; кандидатов не было → not_found;
  кандидаты были, но все отсеяны → conflict. Списка совместимых кодов они не отдают (None),
  признаки — их chars, предупреждения — их remarks.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .base import Adapter


class TenderHack2026(Adapter):
    name = "tenderhack2026"

    def __init__(self, repo: str = "../competitors/TenderHack2026"):
        self.repo = Path(repo).resolve()
        sys.path.insert(0, str(self.repo))
        from pipeline.candidates import find
        from pipeline.chars import extract
        from pipeline.narrow import narrow
        from scripts.dataloader import load_data
        self._find, self._extract, self._narrow = find, extract, narrow
        self.ref = load_data(self.repo / "data" / "processed" / "ktru.json")

    def info(self):
        rev = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True).stdout.strip()
        return {"adapter": self.name, "repo": "https://github.com/MrDragar/TenderHack2026", "commit": rev,
                "positions": len(self.ref)}

    def predict(self, text: str) -> dict:
        cands = self._find(text, self.ref)
        res = self._narrow(cands, self._extract(text, cands, self.ref, {}), self.ref)
        if res["code"]:
            status = "matched"
        elif res["question"]:
            status = "clarification"
        elif not cands["candidates"]:
            status = "not_found"
        else:
            status = "conflict"
        return {
            "status": status, "final_code": res["code"], "compatible_codes": None,
            "features": [{"property": c["name"], "value": str(c["value"]),
                          "unit": (c["unit"] or {}).get("name") if c["unit"] else None, "op": "eq"}
                         for c in res["chars"]],
            "warnings": [r["why"] for r in res["remarks"]],
        }
