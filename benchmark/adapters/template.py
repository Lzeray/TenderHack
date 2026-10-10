"""Шаблон адаптера для другого решения. Скопируйте файл, реализуйте predict и запустите:

  python -m benchmark.run --adapter benchmark.adapters.template:MyAdapter --suites all --out reports/bench/my.json

Строка после двоеточия передаётся в конструктор как аргумент (если указан класс — как в примере выше,
конструктор вызывается без аргументов).
"""
from __future__ import annotations

from .base import Adapter


class MyAdapter(Adapter):
    name = "my-solution"

    def info(self) -> dict:
        return {"adapter": self.name, "version": "0.1"}

    def predict(self, text: str) -> dict:
        # Пример для решения с HTTP API — замените своим вызовом и приведите ответ к общему формату.
        # r = requests.post("http://localhost:9000/match", json={"query": text}).json()
        # return {"status": "matched" if r["code"] else "clarification", "final_code": r["code"],
        #         "compatible_codes": r.get("candidates"), "ranked_codes": r.get("candidates"),  # лучший первым
        #         "features": None, "warnings": r.get("errors")}
        return {"status": "clarification", "final_code": None, "compatible_codes": None, "features": None,
                "warnings": None}
