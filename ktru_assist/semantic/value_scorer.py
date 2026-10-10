"""Optional closed-set scorer. Scores never become catalogue validity decisions."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import time
from typing import Protocol


class ValueScorer(Protocol):
    revision: str
    def score(self, context: str, characteristic_ref: str, options: list[dict]) -> dict: ...


@dataclass(frozen=True)
class RecommendationPolicy:
    min_score: float = 0.0
    margin: float = 0.1
    limit: int = 3

    def apply(self, options: list[dict], result: dict | None):
        full = [dict(o, score=None, recommended=False) for o in options]
        if not result or result.get("error"):
            return {"options": full, "ambiguous": True, "error": (result or {}).get("error")}
        scores = result.get("scores_by_option_id", {})
        if set(scores) != {o["value_id"] for o in options}:
            return {"options": full, "ambiguous": True, "error": "скорер не оценил полный набор"}
        import math
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in scores.values()):
            return {"options": full, "ambiguous": True, "error": "некорректные оценки"}
        for o in full:
            o["score"] = scores[o["value_id"]]
        full.sort(key=lambda o: (-o["score"], o["value_id"]))
        nearby = [o for o in full if o["score"] >= self.min_score and full[0]["score"] - o["score"] <= self.margin]
        ambiguous = len(nearby) != 1 or len(nearby) > self.limit
        for o in nearby[:self.limit]:
            o["recommended"] = True
        return {"options": full, "ambiguous": ambiguous, "recommendations_truncated": len(nearby) > self.limit,
                "model_revision": result.get("model_revision"), "score_kind": result.get("score_kind"),
                "latency_ms": result.get("latency_ms"), "error": None}


class LocalCrossEncoder:
    """Experimental local DiTy-compatible backend; never downloaded implicitly."""
    def __init__(self, path: Path):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.model = AutoModelForSequenceClassification.from_pretrained(str(path), local_files_only=True).eval()
        self.tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        weights = sorted(path.glob("*.safetensors"))
        h = hashlib.sha256()
        for p in weights:
            with p.open("rb") as f:
                h.update(hashlib.file_digest(f, "sha256").digest())
        self.revision = "local-cross-encoder@" + h.hexdigest()

    def score(self, context, characteristic_ref, options):
        t0 = time.perf_counter()
        scores = {}
        with self.torch.inference_mode():
            for i in range(0, len(options), 16):
                batch = options[i:i + 16]
                inputs = self.tokenizer([context] * len(batch), [o["context"] for o in batch],
                                        padding=True, truncation=True, max_length=512, return_tensors="pt")
                logits = self.model(**inputs).logits
                if logits.shape[-1] != 1:
                    raise ValueError("Expected a single ranking logit, not class probabilities")
                scores.update({o["value_id"]: float(s) for o, s in zip(batch, logits[:, 0])})
        return {"model_revision": self.revision, "score_kind": "ranking_logit", "scores_by_option_id": scores,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "error": None}
