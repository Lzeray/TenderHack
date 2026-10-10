"""Выбор уточняющих вопросов при бюджете в два вопроса (docs/QUESTIONS_PLAN.md, Q2).

После двух вопросов система не спрашивает дальше, а показывает список характеристик, которые осталось заполнить.
Поэтому вопрос выбирается так, чтобы после оставшихся вопросов (2, затем 1) позиция определялась с наибольшей
вероятностью; второй вопрос зависит от ответа на первый, обе ступени перебираются полностью.

Модель.
* S — совместимые конечные позиции после всего, что уже известно (разобранный текст, ответы): вопрос выбирается
  по текущему состоянию, а не по частоте значений.
* Вопрос q — характеристика или наименование позиции. Ответ a — допустимое значение КТРУ. Позиция попадает в ветку a,
  если допускает a (для чисел — пересечение интервалов) или у неё нет этой характеристики (unknown ≠ invalid).
* Пользователю нужна одна из позиций S, все равновероятны. Позиция с k допустимыми значениями даёт каждое с
  вероятностью 1/k; позиция без характеристики — одно из значений, при которых она остаётся в ветке, ∝ w(a),
  w(a) = 1 + β·доля a среди товаров этого типа в выгрузках СТЕ (β = 1: выгрузки — слабая поправка; они же
  упорядочивают варианты ответа). Если таких значений нет (текстовое значение отсутствует у позиции во всех
  характеристиках — ядро её исключит), правдивого ответа нет: её вероятность — неудача.
* Ценность состояния T при бюджете b — пара (P(определена), −E[log2 |T_конец|]):
      b = 0 или |T| ≤ 1:  (1, 0), если |T| = 1, иначе (0, −log2 |T|);
      b > 0:              max_q Σ_a P(a|T)·V(T_a, b−1)  (покомпонентно; сравнение лексикографическое).
  Вопрос, который не делит T, не рассматривается; вопрос, на который пользователь части позиций T не может ответить
  так, чтобы его позиция осталась (варианта «Не знаю» нет), — тоже; если таких нет — ручной выбор.
* При равной ценности: обязательная характеристика, меньше вариантов ответа, код — детерминированно.

Множества — битовые маски (int): пересечение и размер ветки — одна операция; без внешних зависимостей.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

BETA = 1.0
BUDGET = 2
EPS = 1e-9


@dataclass
class Q:
    key: str
    members: dict = field(default_factory=dict)     # ответ → frozenset кодов, совместимых с ответом
    own: dict = field(default_factory=dict)         # код → frozenset ответов, которые есть у позиции (пусто — нет)
    weight: dict = field(default_factory=dict)      # ответ → w(a) ≥ 1
    required: bool = False
    tie: tuple = ()


class _M:
    """Вопрос над битовыми масками позиций."""

    def __init__(self, q: Q, index: dict[str, int]):
        self.q = q
        self.answers = sorted(q.members, key=repr)
        self.member = [0] * len(self.answers)
        # владельцы ответа, разложенные по числу значений k у позиции: вклад владельца в P(a) — 1/k
        self.owners: list[dict[int, int]] = [{} for _ in self.answers]
        self.w = [q.weight.get(a, 1.0) for a in self.answers]
        self.lack = 0                                 # позиции без характеристики
        pos = {a: i for i, a in enumerate(self.answers)}
        for a, i in pos.items():
            for c in q.members[a]:
                if c in index:
                    self.member[i] |= 1 << index[c]
        for c, j in index.items():
            mine = [pos[a] for a in q.own.get(c, ()) if a in pos]
            if not mine:
                self.lack |= 1 << j
                continue
            k = len(mine)
            for i in mine:
                self.owners[i][k] = self.owners[i].get(k, 0) | (1 << j)

    def split(self, t: int):
        """[(P(a|T), размер T_a, маска T_a)] для ответов, которые есть у позиций T."""
        n = t.bit_count()
        own = []
        for i in range(len(self.answers)):
            mass = sum((m & t).bit_count() / k for k, m in self.owners[i].items())
            own.append(mass)
        present = [i for i, m in enumerate(own) if m > 0]
        if not present:
            return []
        # позиция без характеристики отвечает одним из значений, при которых она остаётся (∝ w); если таких нет —
        # правдивого ответа нет, её вероятность в ветки не попадает (неудача для этой позиции)
        lack_t = self.lack & t
        extra = dict.fromkeys(present, 0.0)
        if lack_t:
            in_all = all(not (lack_t & ~self.member[i]) for i in present)
            if in_all:
                wsum = sum(self.w[i] for i in present)
                cnt = lack_t.bit_count()
                for i in present:
                    extra[i] = cnt * self.w[i] / wsum
            else:
                x = lack_t
                while x:
                    bit = x & -x
                    x ^= bit
                    mine = [i for i in present if self.member[i] & bit]
                    ws = sum(self.w[i] for i in mine)
                    for i in mine:
                        extra[i] += self.w[i] / ws
        out = []
        for i in present:
            p = (own[i] + extra[i]) / n
            b = self.member[i] & t
            out.append((p, b.bit_count(), b))
        return out


def _leaf(size: int) -> tuple[float, float]:
    return (1.0, 0.0) if size == 1 else (0.0, -math.log2(size) if size > 1 else 0.0)


class Planner:
    def __init__(self, questions: list[Q], codes):
        self.codes = sorted(codes)
        self.index = {c: i for i, c in enumerate(self.codes)}
        self.ms = [_M(q, self.index) for q in questions]
        self.memo: dict[tuple[int, int], tuple[float, float]] = {}

    def mask(self, codes) -> int:
        t = 0
        for c in codes:
            t |= 1 << self.index[c]
        return t

    def value(self, t: int, budget: int) -> tuple[float, float]:
        n = t.bit_count()
        if budget == 0 or n <= 1:
            return _leaf(n)
        key = (t, budget)
        if key not in self.memo:
            best = None
            for m in self.ms:
                v = self._value_of(m, t, budget)
                if v is not None and (best is None or v > best):
                    best = v
            self.memo[key] = best if best is not None else _leaf(n)
        return self.memo[key]

    def _value_of(self, m: _M, t: int, budget: int):
        br = m.split(t)
        n = t.bit_count()
        if not br or all(size >= n for _, size, _ in br):
            return None                       # вопрос не делит множество
        union = 0
        for _, _, b in br:
            union |= b
        if union != t:
            return None                       # у части позиций нет ответа, при котором они остаются: тупик
        if budget == 1:
            uniq = sum(p for p, size, _ in br if size == 1)
            logs = -sum(p * math.log2(size) for p, size, _ in br if size > 1)
            return (round(uniq, 9), round(logs, 9))
        u = l = 0.0
        for p, _, b in br:
            vu, vl = self.value(b, budget - 1)
            u += p * vu
            l += p * vl
        return (round(u, 9), round(l, 9))

    def choose(self, codes, budget: int = BUDGET):
        """Лучший вопрос, его ценность (P(определена), −E log2 остатка) и ценности всех вопросов."""
        t = self.mask(codes)
        scored = {}
        for m in self.ms:
            v = self._value_of(m, t, budget)
            if v is not None:
                scored[m.q.key] = v
        if not scored:
            return None, None, {}
        best = max((m for m in self.ms if m.q.key in scored),
                   key=lambda m: (scored[m.q.key], m.q.required,
                                  tuple(-x for x in m.q.tie if isinstance(x, (int, float))), m.q.key))
        return best.q, scored[best.q.key], scored


def branches(q: Q, T: frozenset) -> list[tuple[object, float, frozenset]]:
    """(ответ, P(ответ | T), ветка T_a) — для объяснений и тестов."""
    p = Planner([q], T)
    m = p.ms[0]
    t = p.mask(T)
    out = []
    owned = [i for i in range(len(m.answers)) if any(o & t for o in m.owners[i].values())]
    for (pr, _, b), i in zip(m.split(t), owned):
        out.append((m.answers[i], pr, frozenset(c for c, j in p.index.items() if b >> j & 1)))
    return out


__all__ = ["Q", "Planner", "branches", "BETA", "BUDGET"]
