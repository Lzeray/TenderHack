"""Командная строка: импорт каталога, индексация в OpenSearch, запуск сервера, поиск.

  python -m ktru_assist.cli import --src "КТРУ/КТРУ xml/КТРУ" --db data/ktru.sqlite --as-of 2026-10-09
  python -m ktru_assist.cli index  --db data/ktru.sqlite --opensearch http://localhost:9200
  python -m ktru_assist.cli serve  --port 8000
  python -m ktru_assist.cli search "стул на металлическом каркасе с мягким сиденьем"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="ktru_assist")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import", help="импорт XML КТРУ в SQLite")
    p.add_argument("--src", required=True, type=Path)
    p.add_argument("--db", default="data/ktru.sqlite", type=Path)
    p.add_argument("--as-of", default=dt.date.today().isoformat(),
                   help="дата проверки применимости позиций (YYYY-MM-DD)")
    p.add_argument("--all-characteristics", action="store_true")
    p = sub.add_parser("index", help="загрузить позиции MVP в OpenSearch")
    p.add_argument("--db", default="data/ktru.sqlite", type=Path)
    p.add_argument("--opensearch", default="http://localhost:9200")
    p.add_argument("--index", default="ktru_positions")
    p = sub.add_parser("serve", help="запустить API и веб-интерфейс")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", default=8000, type=int)
    p = sub.add_parser("portal", help="индекс характеристик портала из выгрузок (лист 2)")
    p.add_argument("--src", default="Примеры выгрузок", type=Path)
    p = sub.add_parser("search", help="разовый поиск из командной строки")
    p.add_argument("text")
    args = ap.parse_args(argv)

    if args.cmd == "import":
        from .catalog.importer import run_import
        t0 = time.perf_counter()
        meta = run_import(args.src, args.db, dt.date.fromisoformat(args.as_of), args.all_characteristics)
        meta["seconds"] = round(time.perf_counter() - t0, 1)
        print(json.dumps(meta, ensure_ascii=False, indent=1))
    elif args.cmd == "index":
        from .catalog.repository import Catalog
        from .search.opensearch_backend import OpenSearchBackend
        cat = Catalog(args.db)
        be = OpenSearchBackend(args.opensearch, args.index)
        n = be.rebuild(cat.search_documents())
        print(f"проиндексировано документов: {n}")
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("ktru_assist.api:app", host=args.host, port=args.port)
    elif args.cmd == "portal":
        from .portal.characteristics import build
        print(json.dumps(build(args.src), ensure_ascii=False, indent=1))
    elif args.cmd == "search":
        from .api import get_engine
        from .models import SearchRequest
        res = get_engine().search(SearchRequest(text=args.text))
        print(json.dumps(res.model_dump(mode="json"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
