"""Токены запроса и ключевые слова свойств области (отладка): STEMMER=snowball python -m experiments.debug_tokens OUT "текст" "подстрока свойства" """
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if os.environ.get("STEMMER"):
    from experiments.stemmers import install
    install(os.environ["STEMMER"])
    os.environ["KTRU_DB"] = str(ROOT / "data" / f"exp_{os.environ['STEMMER']}.sqlite")
from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.nlp.extract import build_groups  # noqa: E402
from ktru_assist.nlp.normalize import normalize  # noqa: E402

eng = get_engine()
text, sub = sys.argv[2], sys.argv[3].lower()
nq = normalize(text)
det = eng.registry.detect(nq.tokens)
res = eng.backend.by_heads(det.heads, 1000)
pos = list(eng.catalog.get_many([h.code for h in res.hits]).values())
with open(sys.argv[1], "w", encoding="utf-8") as out:
    out.write(f"heads={det.heads}\n")
    for t in nq.tokens:
        out.write(f"  {t.i} {t.text!r} kind={t.kind} lemma={t.lemma!r} unit={t.unit_key}\n")
    for g in build_groups(pos).values():
        if sub in g.name.lower():
            out.write(f"GROUP {g.name}: core={g.core} terms={g.terms} numeric={g.numeric} dims={g.dims} "
                      f"quality={list(g.quality)[:8]}\n")
