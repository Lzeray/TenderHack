"""Snapshot-local identities and full domains. No head-word or synonym lookup."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from functools import cached_property

from .repository import Position
from ..nlp.extract import PropGroup
from ..text import norm


def ref(kind: str, *parts) -> str:
    return kind + ":" + hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class CatalogType:
    ref: str
    name: str
    category: str
    codes: tuple[str, ...]


class CatalogScope:
    """A type is an explicit exact catalogue designation within an organizer group.

    This is not an inferred taxonomy: membership is stored/replayable as position IDs.
    Choosing a type never means choosing the first retrieved position.
    """
    def __init__(self, catalog):
        self.catalog = catalog
        rows = catalog.con.execute("SELECT code,name,category,version,is_template,parent_code,okpd2_name FROM positions WHERE active=1 AND category IS NOT NULL ORDER BY code").fetchall()
        members = {}
        self.documents = []
        for r in rows:
            members.setdefault((r["category"], r["name"]), []).append(r["code"])
            self.documents.append({"id": ref("position", r["code"], r["version"]), "code": r["code"],
                                   "name": r["name"],
                                   "type_ref": ref("type", r["category"], r["name"]),
                                   "text": " · ".join(x for x in [r["name"], r["okpd2_name"], r["parent_code"]] if x)})
        self.types = {ref("type", cat, name): CatalogType(ref("type", cat, name), name, cat, tuple(codes))
                      for (cat, name), codes in sorted(members.items())}
        self.codes = tuple(r["code"] for r in rows)

    def selected(self, value: str | None):
        if value in self.types:
            return self.types[value]
        direct = next((d for d in self.documents if value in (d["id"], d["code"])), None)
        if direct:
            parent_type = self.types[direct["type_ref"]]
            return CatalogType(direct["id"], direct["name"], parent_type.category, (direct["code"],))
        # Explicit manual name selection is allowed only if unambiguous in the snapshot.
        matches = [t for t in self.types.values() if t.name == value]
        return matches[0] if len(matches) == 1 else None

    def positions(self, type_ref: str | None = None) -> list[Position]:
        selected = self.selected(type_ref) if type_ref else None
        codes = selected.codes if selected else self.codes
        ps = self.catalog.get_many(list(codes))
        return [ps[c] for c in codes]

    @cached_property
    def context_ids(self):
        """Short technical IDs, stable for this snapshot; not word/synonym aliases."""
        properties, values = set(), set()
        for p in self.positions():
            for pr in p.props.values():
                r = ref("characteristic", pr.code, pr.name)
                properties.add(r)
                values.update(ref("value", r, v.value_code, v.label) for v in pr.values)
        return ({f"P{i + 1}": r for i, r in enumerate(sorted(properties))},
                {f"V{i + 1}": r for i, r in enumerate(sorted(values))})


def identity_groups(positions: list[Position]) -> dict[str, PropGroup]:
    """Shared catalogue characteristic code/name, never merely a matching name."""
    groups = {}
    for p in positions:
        for pr in p.props.values():
            k = ref("characteristic", pr.code, pr.name)
            if k not in groups:
                groups[k] = PropGroup(k, pr.name, [pr.code], pr.is_numeric, pr.is_boolean,
                                      set(), set(), {}, {}, [], pr.required)
            g = groups[k]
            g.positions += 1
            g.required |= pr.required
            for u in pr.units:
                g.dims.add(u.dimension)
                g.unit_keys.add(u.key)
            for v in pr.values:
                if v.kind == "quality" and v.text:
                    g.quality[norm(v.text)] = v.text
    return groups
