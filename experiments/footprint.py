"""Ресурсы ядра: время инициализации, пиковая память процесса, задержка запроса.
python -m experiments.footprint [--stemmer snowball]  (Windows: память через psutil, если есть, иначе tracemalloc)"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def rss_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 2**20, 1)
    except ImportError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stemmer", default=None)
    args = ap.parse_args()
    base = rss_mb()
    tracemalloc.start()
    t0 = time.perf_counter()
    if args.stemmer:
        from experiments.stemmers import install
        install(args.stemmer)
        os.environ["KTRU_DB"] = str(ROOT / "data" / f"exp_{args.stemmer}.sqlite")
    from ktru_assist.api import get_engine
    from ktru_assist.models import SearchRequest
    eng = get_engine()
    init = time.perf_counter() - t0
    cases = [json.loads(l)["text"] for l in (ROOT / "benchmark" / "suites" / "manual_dev.jsonl")
             .read_text(encoding="utf-8").splitlines()]
    for c in cases:
        eng.search(SearchRequest(text=c))
    lat = []
    for _ in range(5):
        for c in cases:
            t = time.perf_counter()
            eng.search(SearchRequest(text=c))
            lat.append((time.perf_counter() - t) * 1000)
    cur, peak = tracemalloc.get_traced_memory()
    lat.sort()
    print(json.dumps({"stemmer": args.stemmer or "pymorphy3", "init_s": round(init, 2),
                      "python_heap_peak_mb": round(peak / 2**20, 1), "rss_mb": rss_mb(), "rss_before_mb": base,
                      "latency_ms_p50": round(lat[len(lat) // 2], 2), "latency_ms_p95": round(lat[int(len(lat) * .95)], 2),
                      "latency_ms_mean": round(statistics.mean(lat), 2)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
