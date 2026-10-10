"""Кандидаты исправления опечаток для слов: python -m experiments.typo_probe OUT.txt слово1 слово2 ..."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ktru_assist.api import get_engine  # noqa: E402
from ktru_assist.text import is_known_word, lemma  # noqa: E402

eng = get_engine()
with open(sys.argv[1], "w", encoding="utf-8") as out:
    for w in sys.argv[2:]:
        c = eng.typos.candidates(w)
        out.write(f"{w}: known_catalog={eng.typos.known(w)} known_dict={is_known_word(w)} lemma={lemma(w)}\n")
        out.write(f"   {[(d, x, lemma(x)) for d, x in c[:15]]}\n")
