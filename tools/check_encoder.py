"""Проверка numpy-реализации rubert-tiny2 против эталона sentence-transformers.

Запускается один раз во временном окружении с torch и sentence-transformers (в проект не входят):
  python -m venv /tmp/ref && /tmp/ref/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
  /tmp/ref/bin/pip install sentence-transformers numpy safetensors tokenizers
  /tmp/ref/bin/python tools/check_encoder.py data/models/rubert-tiny2 reports/encoder_check.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ktru_assist.semantic.encoder import ENCODER_NAME, ENCODER_REVISION, RubertTiny2  # noqa: E402

TEXTS = ["шуруповерт сетевой", "От сети", "Тип питания: От аккумуляторных батарей", "стул на металлическом каркасе",
         "сидушка", "Подушка на сиденье", "куртка зимняя мужская", "молоток кровельный 0,5 кг",
         "очень длинный текст " * 20]


def main() -> int:
    path, out = sys.argv[1], sys.argv[2]
    from sentence_transformers import SentenceTransformer
    ref = SentenceTransformer(ENCODER_NAME, revision=ENCODER_REVISION, device="cpu")
    ref.max_seq_length = 64
    a = ref.encode(TEXTS, normalize_embeddings=True)
    b = RubertTiny2(path).encode(TEXTS)
    cos = (a * b).sum(1)
    res = {"model": ENCODER_NAME, "revision": ENCODER_REVISION, "texts": len(TEXTS),
           "min_cosine_numpy_vs_reference": float(cos.min()), "max_abs_diff": float(np.abs(a - b).max())}
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if cos.min() > 0.9999 else 1


if __name__ == "__main__":
    raise SystemExit(main())
