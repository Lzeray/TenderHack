"""Энкодер rubert-tiny2 (cointegrated/rubert-tiny2, MIT) на numpy.

Прямой проход BERT (3 слоя, 312 признаков, 12 голов), пулинг по [CLS] и L2-нормализация —
как в конфигурации sentence-transformers модели (1_Pooling: pooling_mode_cls_token=true, 2_Normalize).
Зависимости: numpy, safetensors, tokenizers (requirements-ml.txt), без torch.
Совпадение с эталонной реализацией проверяется tools/check_encoder.py.

Файлы модели: data/models/rubert-tiny2/ (model.safetensors, tokenizer.json, config.json),
ревизия закрепляется в ENCODER_REVISION и проверяется по sha256 весов.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ENCODER_NAME = "cointegrated/rubert-tiny2"
ENCODER_REVISION = "e8ed3b0c8bbf4fb6984c3de043bf7d2f4e5969ae"
WEIGHTS_SHA256 = "26ebb6db2a68593c54c74902d7a74f332da66297693f965cc9f1b0af4abf3894"
POOLING = "cls+l2"


def _erf(x: np.ndarray) -> np.ndarray:
    # Абрамовиц–Стиган 7.1.26, погрешность < 1.5e-7
    s = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t \
        * np.exp(-a * a)
    return s * y


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + _erf(x / math.sqrt(2.0)))


def _layer_norm(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float) -> np.ndarray:
    mu = x.mean(-1, keepdims=True)
    var = ((x - mu) ** 2).mean(-1, keepdims=True)
    return (x - mu) / np.sqrt(var + eps) * w + b


class RubertTiny2:
    def __init__(self, path: Path | str, max_len: int = 64, verify: bool = True):
        from safetensors.numpy import load_file
        from tokenizers import Tokenizer
        path = Path(path)
        wfile = path / "model.safetensors"
        if verify:
            h = hashlib.sha256(wfile.read_bytes()).hexdigest()
            if h != WEIGHTS_SHA256:
                raise ValueError(f"веса энкодера не совпадают с закреплённой ревизией {ENCODER_REVISION}: {h}")
        self.cfg = json.loads((path / "config.json").read_text(encoding="utf-8"))
        self.w = {k: v.astype(np.float32) for k, v in load_file(str(wfile)).items()}
        self.tok = Tokenizer.from_file(str(path / "tokenizer.json"))
        self.tok.enable_truncation(max_len)
        self.tok.enable_padding(pad_id=self.cfg.get("pad_token_id", 0))
        self.n_layers = self.cfg["num_hidden_layers"]
        self.n_heads = self.cfg["num_attention_heads"]
        self.eps = self.cfg.get("layer_norm_eps", 1e-12)
        self.dim = self.cfg["hidden_size"]

    @property
    def revision(self) -> str:
        return f"{ENCODER_NAME}@{ENCODER_REVISION[:12]}/{POOLING}"

    def _lin(self, x: np.ndarray, name: str) -> np.ndarray:
        return x @ self.w[name + ".weight"].T + self.w[name + ".bias"]

    def encode(self, texts: list[str], batch: int = 64) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch):
            out.append(self._encode_batch(texts[i:i + batch]))
        return np.concatenate(out) if out else np.zeros((0, self.dim), np.float32)

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        enc = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.float32)
        types = np.array([e.type_ids for e in enc], dtype=np.int64)
        B, T = ids.shape
        p = "bert.embeddings."
        x = self.w[p + "word_embeddings.weight"][ids] + self.w[p + "position_embeddings.weight"][np.arange(T)][None] \
            + self.w[p + "token_type_embeddings.weight"][types]
        x = _layer_norm(x, self.w[p + "LayerNorm.weight"], self.w[p + "LayerNorm.bias"], self.eps)
        H = self.n_heads
        d = self.dim // H
        bias = (1.0 - mask)[:, None, None, :] * np.float32(-1e9)
        for li in range(self.n_layers):
            p = f"bert.encoder.layer.{li}."
            q = self._lin(x, p + "attention.self.query").reshape(B, T, H, d).transpose(0, 2, 1, 3)
            k = self._lin(x, p + "attention.self.key").reshape(B, T, H, d).transpose(0, 2, 1, 3)
            v = self._lin(x, p + "attention.self.value").reshape(B, T, H, d).transpose(0, 2, 1, 3)
            att = q @ k.transpose(0, 1, 3, 2) / np.float32(math.sqrt(d)) + bias
            att = np.exp(att - att.max(-1, keepdims=True))
            att = att / att.sum(-1, keepdims=True)
            ctx = (att @ v).transpose(0, 2, 1, 3).reshape(B, T, self.dim)
            x = _layer_norm(self._lin(ctx, p + "attention.output.dense") + x,
                            self.w[p + "attention.output.LayerNorm.weight"],
                            self.w[p + "attention.output.LayerNorm.bias"], self.eps)
            h = _gelu(self._lin(x, p + "intermediate.dense"))
            x = _layer_norm(self._lin(h, p + "output.dense") + x, self.w[p + "output.LayerNorm.weight"],
                            self.w[p + "output.LayerNorm.bias"], self.eps)
        cls = x[:, 0, :]
        return cls / np.linalg.norm(cls, axis=1, keepdims=True).clip(1e-12)
