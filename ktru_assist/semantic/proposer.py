"""SemanticProposer (этап A): смысловые предложения для фрагментов, которые правила не разобрали.

* Только предложения: ничего не привязывается без подтверждения пользователя (Proposal.answer
  отправляется в `answers` по нажатию «принять»). Ядро и его гарантии не меняются.
* Сравниваются заранее вычисленные векторы каталога (названия типов; пары «характеристика: значение»)
  с векторами неразобранных слов. Модель на каждого кандидата не запускается.
* Косинусная близость — вспомогательный сигнал, не вероятность. Порог и отрыв от следующего
  варианта задаются конфигурацией; ниже порога — отказ (предложений нет).
* Предложения значений ограничены свойствами типов, найденных правилами (область поиска).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..clarify import TYPE_PROP
from ..models import Constraint, Proposal, SearchResponse, Span


@dataclass
class SemanticConfig:
    min_score_value: float = 0.78
    min_score_type: float = 0.70
    margin: float = 0.02
    max_per_fragment: int = 3
    max_types: int = 5


class SemanticProposer:
    name = "semantic"

    def __init__(self, encoder, catalog, registry, cache_dir: Path, cfg: SemanticConfig | None = None):
        self.enc = encoder
        self.cfg = cfg or SemanticConfig()
        self.revision = encoder.revision
        snap = str(catalog.meta.get("snapshot"))
        # справочные строки
        self.type_names = registry.type_names()
        triples = catalog.quality_values()
        self.val_meta = triples
        val_texts = [v for _, _, v in triples]
        pair_texts = [f"{n}: {v}" for _, n, v in triples]
        key = hashlib.sha256(json.dumps([self.revision, snap, self.type_names, triples],
                                        ensure_ascii=False).encode()).hexdigest()[:16]
        cache_dir.mkdir(parents=True, exist_ok=True)
        f = cache_dir / f"semantic_{key}.npz"
        if f.exists():
            z = np.load(f)
            self.type_vecs, self.val_vecs, self.pair_vecs = z["types"], z["vals"], z["pairs"]
        else:
            self.type_vecs = encoder.encode(self.type_names)
            self.val_vecs = encoder.encode(val_texts)
            self.pair_vecs = encoder.encode(pair_texts)
            np.savez_compressed(f, types=self.type_vecs, vals=self.val_vecs, pairs=self.pair_vecs)
        self.cache_key = key
        self.heads = np.array([h for h, _, _ in triples], dtype=object)

    # ------------------------------------------------------------------
    def propose(self, resp: SearchResponse, text: str, rejected: set[str]) -> list[Proposal]:
        out: list[Proposal] = []
        frags = self._fragments(resp, text)
        if not frags:
            return out
        vecs = self.enc.encode([f for f, _ in frags])
        if not resp.detected_types:
            out += self._types(text, frags, vecs)
        else:
            out += self._values(resp, frags, vecs)
        return [p for p in out if p.key not in rejected]

    @staticmethod
    def _fragments(resp: SearchResponse, text: str) -> list[tuple[str, Span | None]]:
        """Неразобранные значимые слова с координатами в исходном тексте (если их удалось найти)."""
        out = []
        low = text.lower()
        for w in resp.unrecognized:
            if any(ch.isdigit() for ch in w) or len(w) < 3:
                continue
            i = low.find(w.lower())
            span = Span(start=i, end=i + len(w), quote=text[i:i + len(w)]) if i >= 0 else None
            out.append((w, span))
        return out

    def _types(self, text: str, frags, vecs) -> list[Proposal]:
        q = self.enc.encode([text])[0]
        sims = self.type_vecs @ q
        for v in vecs:
            sims = np.maximum(sims, self.type_vecs @ v)
        order = np.argsort(-sims, kind="stable")[: self.cfg.max_types]
        out = []
        for i in order:
            s = float(sims[i])
            if s < self.cfg.min_score_type:
                break
            name = self.type_names[i]
            out.append(Proposal(key=f"sem:type:{name}", origin="semantic", kind="type", quote=text, label=name,
                                answer=Constraint(property=TYPE_PROP, value=name), score=round(s, 4),
                                reason=f"близость описания к наименованию позиции {s:.2f} (не вероятность)"))
        return out

    def _values(self, resp: SearchResponse, frags, vecs) -> list[Proposal]:
        heads = set(resp.detected_types)
        idx = np.array([i for i, h in enumerate(self.heads) if h in heads], dtype=int)
        if idx.size == 0:
            return []
        known = {(p.name, v) for p in resp.properties for v in p.values} | \
            {(p.name, None) for p in resp.properties}
        bound = {f.property_name for f in resp.features if f.status == "bound" and f.property_name}
        out = []
        for (frag, span), v in zip(frags, vecs):
            sims = np.maximum(self.val_vecs[idx] @ v, self.pair_vecs[idx] @ v)
            order = np.argsort(-sims, kind="stable")
            seen: set[tuple[str, str]] = set()
            picked = []
            for j in order:
                s = float(sims[j])
                if s < self.cfg.min_score_value:
                    break
                _, prop, val = self.val_meta[idx[j]]
                if (prop, val) in seen or prop in bound or (prop, None) not in known:
                    continue
                seen.add((prop, val))
                picked.append((s, prop, val))
                if len(picked) >= self.cfg.max_per_fragment:
                    break
            if not picked:
                continue
            ambiguous = len(picked) > 1 and picked[0][0] - picked[1][0] < self.cfg.margin
            for s, prop, val in picked:
                out.append(Proposal(
                    key=f"sem:value:{frag}:{prop}={val}", origin="semantic", kind="value", quote=frag, span=span,
                    label=f"«{frag}» → {prop} = {val}", answer=Constraint(property=prop, value=val),
                    score=round(s, 4),
                    reason=f"близость {s:.2f} (не вероятность)" + ("; варианты близки — выберите" if ambiguous else "")))
        return out
