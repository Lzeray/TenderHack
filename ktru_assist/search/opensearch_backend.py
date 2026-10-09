"""OpenSearch-бэкенд: индекс позиций MVP с предварительно лемматизированными полями.

Те же поля, что и у локального BM25: name_lemmas (вес 2), head_parts (3), okpd2_lemmas (0.5),
плюс поле name с встроенным анализатором russian. Сортировка: _score, затем code.
"""
from __future__ import annotations

from .base import Hit, SearchResult

MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {"properties": {
        "code": {"type": "keyword"},
        "name": {"type": "text", "analyzer": "russian"},
        "name_lemmas": {"type": "text", "analyzer": "whitespace"},
        "head_parts": {"type": "keyword"},
        "okpd2_lemmas": {"type": "text", "analyzer": "whitespace"},
        "category": {"type": "keyword"},
        "active": {"type": "boolean"},
        "is_template": {"type": "boolean"},
    }},
}


class OpenSearchBackend:
    name = "opensearch"

    def __init__(self, url: str, index: str):
        from opensearchpy import OpenSearch
        self.client = OpenSearch(hosts=[url], timeout=10)
        self.index = index

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:  # noqa: BLE001
            return False

    def rebuild(self, docs: list[dict]) -> int:
        from opensearchpy import helpers
        if self.client.indices.exists(index=self.index):
            self.client.indices.delete(index=self.index)
        self.client.indices.create(index=self.index, body=MAPPING)
        actions = ({"_index": self.index, "_id": d["code"], "_source": {
            "code": d["code"], "name": d["name"], "name_lemmas": " ".join(d["name_lemmas"]),
            "head_parts": d["head_parts"], "okpd2_lemmas": " ".join(d["okpd2_lemmas"]),
            "category": d["category"], "active": d["active"], "is_template": d["is_template"],
        }} for d in docs)
        ok, _ = helpers.bulk(self.client, actions)
        self.client.indices.refresh(index=self.index)
        return ok

    def search(self, terms: list[str], size: int) -> SearchResult:
        q = " ".join(sorted(set(terms)))
        body = {
            "size": size, "track_total_hits": True,
            "sort": [{"_score": "desc"}, {"code": "asc"}],
            "query": {"bool": {
                "filter": [{"term": {"active": True}}],
                "should": [
                    {"match": {"name_lemmas": {"query": q, "boost": 2.0}}},
                    {"terms": {"head_parts": sorted(set(terms)), "boost": 3.0}},
                    {"match": {"okpd2_lemmas": {"query": q, "boost": 0.5}}},
                    {"match": {"name": {"query": q, "boost": 1.0}}},
                ],
                "minimum_should_match": 1,
            }},
        }
        r = self.client.search(index=self.index, body=body)
        hits = [Hit(h["_source"]["code"], round(float(h["_score"] or 0), 6)) for h in r["hits"]["hits"]]
        return SearchResult(hits, int(r["hits"]["total"]["value"]), self.name)

    def by_heads(self, heads: list[str], size: int) -> SearchResult:
        body = {"size": size, "track_total_hits": True, "sort": [{"code": "asc"}],
                "query": {"bool": {"filter": [{"term": {"active": True}}, {"terms": {"head_parts": heads}}]}}}
        r = self.client.search(index=self.index, body=body)
        hits = [Hit(h["_source"]["code"], 0.0) for h in r["hits"]["hits"]]
        return SearchResult(hits, int(r["hits"]["total"]["value"]), self.name)
