"""Exact cosine search over snapshot documents, independent of lexical recognizers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading

import numpy as np

from ..catalog.scope import identity_groups, ref
from ..clarify import TYPE_PROP
from ..models import Constraint, Proposal

DOCUMENT_VERSION = "catalog-docs-1.2"


class CatalogIndex:
    def __init__(self, encoder, scope, cache_dir: Path):
        self.enc, self.scope = encoder, scope
        self.revision = encoder.revision + "/" + DOCUMENT_VERSION + "/query-prefixes-1.0"
        self.lock = threading.Lock()
        self.docs = list(scope.documents)
        self.type_refs = sorted(scope.types)
        positions = scope.positions()
        self.groups = identity_groups(positions)
        self.property_docs = []
        self.value_docs = []
        for k, g in sorted(self.groups.items()):
            names = sorted({p.name for p in positions if g.codes[0] in p.props and p.props[g.codes[0]].name == g.name})
            self.property_docs.append({"id": k, "text": g.name + " · " + " · ".join(names[:3])})
            values = {}
            for p in positions:
                pr = p.props.get(g.codes[0])
                if pr is not None and pr.name == g.name:
                    for v in pr.values:
                        vr = ref("value", k, v.value_code, v.label)
                        values[vr] = {"id": vr, "characteristic_ref": k, "text": g.name + " · " + v.label}
            self.value_docs.extend(values[r] for r in sorted(values))
        fingerprint = [self.revision, scope.catalog.meta, self.docs, self.property_docs, self.value_docs]
        self.cache_key = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"catalog_{self.cache_key}.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as z:
                self.vectors, self.property_vectors, self.type_vectors = z["positions"], z["properties"], z["types"]
                self.value_vectors = z["values"]
                for label, docs in (("position_ids", self.docs), ("property_ids", self.property_docs), ("value_ids", self.value_docs)):
                    if list(z[label]) != [d["id"] for d in docs]:
                        raise ValueError("Semantic index identity mapping mismatch")
        else:
            self.vectors = encoder.encode([d["text"] for d in self.docs])
            self.property_vectors = encoder.encode([d["text"] for d in self.property_docs])
            self.type_vectors = encoder.encode([scope.types[r].name for r in self.type_refs])
            self.value_vectors = encoder.encode([d["text"] for d in self.value_docs])
            np.savez_compressed(path, positions=self.vectors, properties=self.property_vectors, types=self.type_vectors,
                                values=self.value_vectors, position_ids=[d["id"] for d in self.docs],
                                property_ids=[d["id"] for d in self.property_docs], value_ids=[d["id"] for d in self.value_docs])
            path.with_suffix(".json").write_text(json.dumps({"revision": self.revision, "snapshot": scope.catalog.meta,
                "positions": self.docs, "properties": self.property_docs, "values": self.value_docs}, ensure_ascii=False), encoding="utf-8")
        for a in (self.vectors, self.property_vectors, self.type_vectors, self.value_vectors):
            if not np.isfinite(a).all():
                raise ValueError("Semantic index contains non-finite vectors")
            if len(a) and not np.allclose(np.linalg.norm(a, axis=1), 1, atol=1e-4):
                raise ValueError("Semantic vectors are not normalized")

    def query_vector(self, text):
        with self.lock:
            return self.enc.encode([text])[0]

    def propose(self, resp, text: str, rejected: set[str]):
        import re
        ends = [m.end() for m in re.finditer(r"\S+", text)][:4]
        queries = list(dict.fromkeys([text, *[text[:end] for end in ends]]))
        # Prefixes reduce domination by long measurement suffixes in tiny embeddings.
        # They are only retrieval hypotheses, never facts or confirmed filters.
        with self.lock:
            qs = self.enc.encode(queries)
        sims = (self.vectors @ qs.T).max(axis=1)
        scores = {}
        for doc, score in zip(self.docs, sims):
            scores[doc["type_ref"]] = max(scores.get(doc["type_ref"], -1.0), float(score))
        # Long generic OKPD descriptions must not drown out the actual designation.
        for r, score in zip(self.type_refs, (self.type_vectors @ qs.T).max(axis=1)):
            scores[r] = 0.8 * float(score) + 0.2 * scores[r]
        ordered = sorted(scores, key=lambda r: (-scores[r], r))[:8]
        return [Proposal(key="sem:" + r, origin="semantic", kind="type", label=self.scope.types[r].name,
                         answer=Constraint(property=TYPE_PROP, value=r), score=round(scores[r], 4),
                         reason="предложение по косинусной близости; подтвердите обозначение каталога")
                for r in ordered if "sem:" + r not in rejected]

    def rank_properties(self, text: str, refs: list[str]):
        q = self.query_vector(text)
        scores = {d["id"]: float(s) for d, s in zip(self.property_docs, self.property_vectors @ q)}
        return sorted(refs, key=lambda r: (-scores.get(r, -1.0), r))


def main():
    import argparse
    from ..catalog.repository import Catalog
    from ..catalog.scope import CatalogScope
    from ..config import Settings
    from .encoder import TransformersEncoder
    ap = argparse.ArgumentParser(description="Build the offline snapshot semantic index")
    ap.parse_args()
    settings = Settings.from_env()
    index = CatalogIndex(TransformersEncoder(settings.encoder_path), CatalogScope(Catalog(settings.db_path)), settings.cache_dir)
    print(json.dumps({"index": index.cache_key, "positions": len(index.docs), "properties": len(index.property_docs),
                      "values": len(index.value_docs),
                      "revision": index.revision}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
