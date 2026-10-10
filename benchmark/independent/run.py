"""Прогон решений на независимых наборах и метрики v2.

  python -m benchmark.independent.run --adapters ktru:core \\
      --suites natural contradictions out_of_scope --out reports/bench/independent/v2.json

Адаптеры загружаются через benchmark.run.load_adapter (тот же контракт, что у общего набора тестов).
Тривиальные базовые линии («всегда уточнение», «всегда не найдено») добавляются в отчёт всегда
(отключить: --no-baselines). Рядом с JSON пишется Markdown-таблица (тот же путь с расширением .md).

Правило заморозки: по test смотрим только агрегаты. Флаг --hide-test-cases убирает строки test-кейсов
из JSON (агрегаты остаются). Настраиваться — только на --split dev.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import sys
from pathlib import Path

from . import metrics as mt
from .generate import MANIFEST, SUITES, test_hash

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITES = ("natural", "contradictions", "out_of_scope")


def load_cases(name: str, split: str) -> list[dict]:
    path = Path(name) if name.endswith(".jsonl") else SUITES / f"{name}.jsonl"
    cases = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return cases if split == "all" else [c for c in cases if c.get("split") == split]


def _manifest(path: Path) -> dict[str, str]:
    """Хеши test-частей: манифест рядом с папкой набора (suites/../test_manifest.sha256), иначе манифест v2."""
    own = path.resolve().parent.parent / "test_manifest.sha256"
    m = own if own.exists() else MANIFEST
    frozen = {}
    if m.exists():
        for line in m.read_text(encoding="utf-8").splitlines():
            if line.strip():
                h, f = line.split()[:2]
                frozen[f] = h
    return frozen


def frozen_status(names) -> dict:
    """Совпадает ли test-часть каждого набора с замороженной (test_manifest.sha256)."""
    out = {}
    for n in names:
        path = Path(n) if n.endswith(".jsonl") else SUITES / f"{n}.jsonl"
        h, k = test_hash(path)
        frozen = _manifest(path)
        out[path.stem] = {"test_sha256": h, "test_cases": k, "frozen": frozen.get(path.name),
                          "ok": frozen.get(path.name) == h,
                          "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return out


def make_adapter(spec: str):
    for cls in mt.BASELINES:
        if spec == cls.name:
            return cls()
    sys.path.insert(0, str(ROOT))
    from benchmark.run import load_adapter
    return load_adapter(spec)


def evaluate(adapters, suites: dict[str, list[dict]], ks, use_dialog: bool, n_boot: int, hide_test: bool,
             progress=None) -> dict:
    report = {}
    for ad in adapters:
        try:
            info = ad.info()
        except Exception as e:  # noqa: BLE001
            info = {"error": f"{type(e).__name__}: {e}"}
        entry = {"info": info, "suites": {}}
        for sname, cases in suites.items():
            if progress:
                progress(f"{ad.name}: {sname} ({len(cases)} кейсов)")
            rows = mt.run_suite(ad, cases, ks, use_dialog)
            block = {"summary": mt.summarize(rows, ks, n_boot), "by_split": {}}
            for sp in ("dev", "test"):
                sub = [r for r in rows if r["split"] == sp]
                if sub:
                    block["by_split"][sp] = mt.summarize(sub, ks, n_boot)
            text = {c["id"]: c["text"] for c in cases}
            block["cases"] = [dict(r, text=text[r["id"]]) for r in rows if not (hide_test and r["split"] == "test")]
            entry["suites"][sname] = block
        report[ad.name] = entry
    return report


def _ci(ci: dict | None) -> str:
    return f" [{ci['lo']:.3f}–{ci['hi']:.3f}]" if ci else ""


def _f(x) -> str:
    return "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))


def to_markdown(rep: dict) -> str:
    meta = rep["meta"]
    lines = [f"# Независимые наборы v2 — метрики", "",
             f"Дата: {meta['generated_at']}. Сплит: **{meta['split']}**. Уточнений в диалоге: k ≤ {max(meta['ks'])}. "
             f"Бутстреп: {meta['bootstrap']} повторов, seed {mt.BOOT_SEED}.", ""]
    bad = [n for n, s in meta["frozen"].items() if not s["ok"]]
    lines.append("Заморозка test: " + ("совпадает с test_manifest.sha256" if not bad
                                       else f"**НЕ совпадает** для {', '.join(bad)}"))
    lines.append("")
    any_ad = next(iter(rep["adapters"].values()))
    for sname in any_ad["suites"]:
        s0 = any_ad["suites"][sname]["summary"]
        lines += [f"## {sname}", "",
                  f"Кейсов: {s0['cases']} (gold непуст: {s0['gold_nonempty']}, code_required: {s0['required_cases']}, "
                  f"no_code: {s0['no_code_cases']}).", "",
                  "| Решение | автокоды | wrong_auto | auto_precision [95% ДИ] | auto_coverage | @0 | @1 | @2 [95% ДИ] "
                  "| @3 | required_hit | no_code_respected [95% ДИ] | premature_auto | вопросов | p50 / p95, мс |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for aname, a in rep["adapters"].items():
            s = a["suites"][sname]["summary"]
            ci = s["ci95"]
            dl = "" if s["dialog_support"] in ("supported", "not_run") else f" ({s['dialog_support']})"
            wr = f"{s['wrong_auto']}" + (f" ({s['wrong_auto_rate']:.3f})" if s["wrong_auto_rate"] is not None else "")
            lines.append(
                f"| {aname} | {s['auto']} | {wr} | {_f(s['auto_precision'])}{_ci(ci['auto_precision'])} "
                f"| {_f(s['auto_coverage'])} | {_f(s['code_reached@0'])} | {_f(s.get('code_reached@1'))}{dl} "
                f"| {_f(s.get('code_reached@2'))}{_ci(ci.get('code_reached@2'))} | {_f(s.get('code_reached@3'))} "
                f"| {_f(s['required_hit'])} | {_f(s['no_code_respected'])}{_ci(ci['no_code_respected'])} "
                f"| {_f(s['premature_auto'])} | {_f(s['questions_mean'])} "
                f"| {_f(s['latency_ms_p50'])} / {_f(s['latency_ms_p95'])} |")
        if meta["split"] == "all":
            lines += ["", "По сплитам (только агрегаты):", "",
                      "| Решение | сплит | n | wrong_auto | auto_precision | @0 | @2 | required_hit | no_code_respected |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for aname, a in rep["adapters"].items():
                for sp, s in a["suites"][sname]["by_split"].items():
                    lines.append(f"| {aname} | {sp} | {s['cases']} | {s['wrong_auto']} | {_f(s['auto_precision'])} "
                                 f"| {_f(s['code_reached@0'])} | {_f(s.get('code_reached@2'))} "
                                 f"| {_f(s['required_hit'])} | {_f(s['no_code_respected'])} |")
        lines.append("")
    lines += ["Обозначения: @k — доля кейсов с непустым эталоном, где верный код получен не более чем за k уточнений; "
              "«not_supported» — решение не умеет диалог, @k = @0. При доле 1 (или 0) интервал — «правило трёх».", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapters", nargs="*", default=[], help="спецификации адаптеров, как в benchmark.run")
    ap.add_argument("--suites", nargs="+", default=list(DEFAULT_SUITES))
    ap.add_argument("--split", choices=("all", "dev", "test"), default="all")
    ap.add_argument("--ks", nargs="+", type=int, default=list(mt.KS), help="шаги диалога для code_reached@k")
    ap.add_argument("--no-dialog", action="store_true", help="не вызывать dialog (@k = @0)")
    ap.add_argument("--bootstrap", type=int, default=mt.BOOT_N)
    ap.add_argument("--no-baselines", action="store_true")
    ap.add_argument("--hide-test-cases", action="store_true", help="не писать строки test-кейсов в JSON")
    ap.add_argument("--limit", type=int, default=0, help="первые N кейсов каждого набора (отладка)")
    ap.add_argument("--out", default="reports/bench/independent/v2.json")
    a = ap.parse_args(argv)
    if a.bootstrap < 1000:
        ap.error("--bootstrap должен быть не меньше 1000")

    suites = {Path(n).stem: load_cases(n, a.split) for n in a.suites}
    if a.limit:
        suites = {k: v[:a.limit] for k, v in suites.items()}
    specs = list(a.adapters) + ([] if a.no_baselines else [c.name for c in mt.BASELINES])
    adapters = [make_adapter(s) for s in specs]
    ks = tuple(sorted(set(a.ks)))
    frozen = frozen_status(a.suites)
    for n, st in frozen.items():
        if not st["ok"]:
            print(f"ВНИМАНИЕ: test-часть {n} не совпадает с test_manifest.sha256", file=sys.stderr)
    adapters_report = evaluate(adapters, suites, ks, not a.no_dialog, a.bootstrap, a.hide_test_cases,
                               progress=lambda m: print(m, file=sys.stderr))
    rep = {"meta": {"generated_at": dt.datetime.now().isoformat(timespec="seconds"), "split": a.split,
                    "ks": list(ks), "dialog": not a.no_dialog, "bootstrap": a.bootstrap,
                    "bootstrap_seed": mt.BOOT_SEED, "suites": {k: len(v) for k, v in suites.items()},
                    "frozen": frozen, "python": sys.version.split()[0], "platform": platform.platform(),
                    "hide_test_cases": a.hide_test_cases},
           "adapters": adapters_report}
    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    md = to_markdown(rep)
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    print(f"JSON: {out}\nMarkdown: {out.with_suffix('.md')}", file=sys.stderr)


if __name__ == "__main__":
    main()
