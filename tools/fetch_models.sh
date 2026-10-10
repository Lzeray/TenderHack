#!/usr/bin/env bash
# Загрузка локальных моделей с закреплёнными ревизиями (нужны только при SEMANTIC=1 / LLM_MODE≠off).
set -euo pipefail
cd "$(dirname "$0")/.."
REV=e8ed3b0c8bbf4fb6984c3de043bf7d2f4e5969ae          # cointegrated/rubert-tiny2, MIT
DST=data/models/rubert-tiny2
mkdir -p "$DST/1_Pooling"
for f in config.json tokenizer.json tokenizer_config.json special_tokens_map.json vocab.txt model.safetensors \
         1_Pooling/config.json; do
  curl -fsSL -o "$DST/$f" "https://huggingface.co/cointegrated/rubert-tiny2/resolve/$REV/$f"
done
"${PYTHON:-python3}" -c 'import hashlib; from pathlib import Path; p=Path("data/models/rubert-tiny2/model.safetensors"); assert hashlib.sha256(p.read_bytes()).hexdigest()=="26ebb6db2a68593c54c74902d7a74f332da66297693f965cc9f1b0af4abf3894", "Unexpected encoder weights"'
# Qwen3-4B-Instruct-2507 (Apache 2.0), квантизация Q4_K_M, через локальный Ollama.
# Закреплённый digest проверяется в ответе API (versions.llm_model).
ollama pull qwen3:4b-instruct-2507-q4_K_M
