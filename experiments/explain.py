"""Подробный разбор одного запроса ядром: признаки, этапы, кандидаты с проверками.
python -m experiments.explain OUT.txt "текст" ["текст2" ...]"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if os.environ.get("STEMMER"):  # STEMMER=snowball — бесловарный стеммер и его база
    from experiments.stemmers import install
    install(os.environ["STEMMER"])
    os.environ["KTRU_DB"] = str(ROOT / "data" / f"exp_{os.environ['STEMMER']}.sqlite")
from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.models import SearchRequest  # noqa: E402

eng = get_engine()
with open(sys.argv[1], "w", encoding="utf-8") as out:
    for text in sys.argv[2:]:
        r = eng.search(SearchRequest(text=text))
        out.write(f"=== {text}\n[{r.status}] {r.final_code} {r.message}\n")
        for f in r.features:
            out.write(f"  F {f.status} {f.property_name} {f.op} {f.value} {f.unit or ''} «{f.evidence}» {f.note}\n")
        out.write(f"  unrecognized={r.unrecognized}\n")
        for s in r.stages:
            out.write(f"  S {s.stage}: {s.remaining} (-{s.removed}) {s.note[:150]}\n")
        for c in r.candidates[:12]:
            out.write(f"  C {c.code} {c.name} ok={c.compatible} tpl={c.is_template}\n")
            for k in c.checks:
                if k.feature_id or k.status != "unknown":
                    out.write(f"      {k.status} {k.property_name}: {k.reason[:160]}\n")
