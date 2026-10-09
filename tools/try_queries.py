"""Прогон запросов через движок с кратким выводом в UTF-8 файл (для отладки)."""
import json
import sys
import time

sys.path.insert(0, ".")
from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402

out = open(sys.argv[1], "w", encoding="utf-8")
queries = [l.strip() for l in open(sys.argv[2], encoding="utf-8") if l.strip() and not l.startswith("#")]
t0 = time.perf_counter()
eng = get_engine()
out.write(f"init {time.perf_counter() - t0:.2f}s\n")
for q in queries:
    req = SearchRequest(**json.loads(q)) if q.startswith("{") else SearchRequest(text=q)
    r = eng.search(req)
    out.write(f"\n=== {req.text}  [{r.status}] {r.elapsed_ms}ms\n{r.message}\n")
    out.write(f"types={r.detected_types} corr={[(c.original, c.status, c.corrected, c.options) for c in r.corrections]}\n")
    for f in r.features:
        out.write(f"  F {f.id} {f.status} {f.property_name} {f.op} {f.value} {f.value_to or ''} {f.unit or ''} "
                  f"«{f.evidence}» {[o.get('property_name') for o in f.options]} {f.note}\n")
    out.write(f"  unrecognized={r.unrecognized}\n")
    for s in r.stages:
        out.write(f"  S {s.stage}: {s.remaining} (-{s.removed}) {s.note}\n")
    for i in r.issues:
        out.write(f"  I {i.level} {i.message}\n")
    for c in r.candidates[:6]:
        rc = c.rank_components
        out.write(f"  C {c.rank} {c.code} {c.name} tpl={c.is_template} ok={c.compatible} "
                  f"{rc.name_tier if rc else ''} {rc.name_coverage if rc else ''} {rc.term_coverage if rc else ''} "
                  f"v{rc.valid_conditions if rc else ''} u{rc.unknown_conditions if rc else ''} {c.excluded_reason or ''}\n")
        for ch in c.checks[:8]:
            out.write(f"      {ch.status} {ch.property_name}: {ch.reason}\n")
    if r.question:
        q = r.question
        out.write(f"  Q {q.kind} {q.text} worst={q.worst_case_remaining}/{q.current_remaining} "
                  f"{[(o.label, o.remaining) for o in q.options[:10]]}\n")
    out.write(f"  final={r.final_code} completeness={r.completeness.model_dump()}\n")
