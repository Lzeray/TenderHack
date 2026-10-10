"""Download bounded public evidence once; product serving remains entirely offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


def download(url, *, data=None):
    # Use the existing environment's CA bundle when available; never disable TLS verification.
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": "TenderHack-reference-research/1.0",
        "Content-Type": "application/json" if data else "text/plain",
    })
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            body = response.read()
            return {"url": url, "status": response.status,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "body": body.decode(response.headers.get_content_charset() or "utf-8")}
    except (urllib.error.URLError, TimeoutError) as error:
        return {"url": url, "status": getattr(error, "code", "unavailable"), "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/exp_reference_sources.json"))
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"Reuse the existing evidence snapshot: {args.out}")
    result = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "sources": [], "spgz": []}
    for url, body in [
        ("https://ac.mos.ru/standards/", None),
        ("https://base.garant.ru/407033232/53f89421bbdaf741eb2d1ecc4ddb4c33/", None),
        ("https://eaist.mos.ru/api/kpgz/list", b'{"start":0,"page":2,"params":{}}'),
        ("https://zakupki.mos.ru/", None),
    ]:
        evidence = download(url, data=body)
        result["sources"].append(evidence)
        print(url, evidence["status"], flush=True)
    # A third-party mirror, not normative ground truth. Keep every returned page and provenance.
    blocked = False
    for query in ("молоток", "стул", "перчатки"):
        entry = {"query": query, "pages": [], "complete": False}
        result["spgz"].append(entry)
        if blocked:
            entry["error"] = "Stopped after access/quota failure; no bypass or retries"
            continue
        offset = 0
        for _ in range(args.max_pages):
            url = "https://kuplushki.ru/tools/api/spgz/search/?" + urllib.parse.urlencode({"q": query, "offset": offset})
            evidence = download(url)
            entry["pages"].append(evidence)
            print(query, offset, evidence["status"], flush=True)
            if evidence["status"] != 200:
                blocked = True
                break
            try:
                payload = json.loads(evidence["body"])
            except ValueError:
                entry["error"] = "Non-JSON response"
                break
            evidence["payload"] = payload
            rows = payload.get("results", [])
            if not payload.get("has_more"):
                entry["complete"] = True
                break
            if not rows:
                entry["error"] = "Empty page with has_more=true"
                break
            offset += len(rows)
            time.sleep(1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
