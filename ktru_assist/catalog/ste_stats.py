"""Сборка статистики выгрузок СТЕ для уровня 2 (эмпирика): data/ste_stats.sqlite.

Потоком читает XLSX (разбор строк — ste_importer), большую базу выгрузок не строит. Решения и замеры —
docs/LEVELS_PLAN.md (шаг B1).

1. Тип карточки — тем же реестром типов, что и тип запроса (`TypeRegistry.detect` по наименованию).
   Ключ типа — отсортированные главные слова через «|» («дрель|шуруповерт»), поэтому запрос и карточка
   с одинаковой формулировкой получают один ключ. Карточка привязывается, только если тип найден по слову
   до предлога, неоднозначного алиаса нет, а направление типа совпадает с файлом выгрузки.
   Значения свойств в привязке не участвуют.
2. Сегменты характеристик разбираются `ste_importer.annotate`. Флаги: заглушка («не задано», 0 у положительной
   величины), повтор с разными значениями в карточке, единица не определена, диапазон.
3. Единица счёта — модель (производитель + модель; без модели — карточка). Значение модели — значение
   большинства её карточек; без большинства модель в статистику этого свойства не входит.
4. Для каждой пары (тип, свойство[, размерность]): число моделей и производителей, доля заглушек и повторов,
   квантили, зоны типичных значений (логарифмическая шкала), точные частоты значений (Decimal в базовой
   единице размерности). Для текстовых свойств — частоты нормализованных значений.
5. Манифест: снимок КТРУ, SHA-256 файлов выгрузки, версия сборщика, пороги, хэш содержимого.

python -m ktru_assist.catalog.ste_stats --src "Примеры выгрузок" --db data/ktru.sqlite --out data/ste_stats.sqlite
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path

from ..config import ROOT
from ..nlp.normalize import normalize
from ..registry import TypeRegistry
from ..units import lookup
from .repository import Catalog
from .ste_importer import HEADERS, MISSING, SEED_NAMES, VALUE_START, annotate, key, xlsx_rows

VERSION = "1.1"   # 1.1 axis_order, pair_le (совместные закономерности по моделям)
FILE_CATEGORY = {"Инструменты": "tools", "Мебель": "furniture", "Одежда": "clothes"}
POSITIVE = {"length", "area", "mass", "volume", "power", "voltage", "current", "charge", "torque", "frequency",
            "rotation", "time", "flow"}
PACKAGING = ("упаков", "брутто", "транспорт", "коробк")
COUNT_PREFIX = ("количество", "кол-во", "число ")
QUANTILES = (1, 5, 25, 50, 75, 95, 99)
BINS_PER_DECADE = 10           # зоны: интервалы шкалы ×10^(1/10) ≈ ×1,26
BIN_MIN_SHARE = 0.005             # интервал шкалы «занят», если в нём не меньше 0,5 % моделей
ZONE_MIN_SHARE = Decimal("0.05")  # зона с долей моделей меньше 5 % — «эхо» (подтип или ошибки единиц в выгрузке)
CONFIG = {"bins_per_decade": BINS_PER_DECADE, "bin_min_share": BIN_MIN_SHARE, "zone_min_share": str(ZONE_MIN_SHARE),
          "quantiles": QUANTILES}

SCHEMA = """
CREATE TABLE manifest(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE types(type_key TEXT PRIMARY KEY, category TEXT, n_cards INTEGER, n_models INTEGER,
                   n_manufacturers INTEGER);
CREATE TABLE props(prop_id INTEGER PRIMARY KEY, type_key TEXT, prop_key TEXT, display_name TEXT, kind TEXT,
                   dimension TEXT, n_models INTEGER, n_manufacturers INTEGER, n_cards INTEGER, prevalence TEXT,
                   placeholder_share TEXT, multi_value_share TEXT, is_packaging INTEGER, quantiles TEXT,
                   min_value TEXT, max_value TEXT, n_distinct INTEGER);
CREATE UNIQUE INDEX props_key ON props(type_key, prop_key, kind, dimension);
CREATE TABLE zones(prop_id INTEGER, zone_no INTEGER, lo TEXT, hi TEXT, n_models INTEGER, is_echo INTEGER,
                   PRIMARY KEY(prop_id, zone_no));
CREATE TABLE value_freq(prop_id INTEGER, value TEXT, n_models INTEGER, PRIMARY KEY(prop_id, value));
CREATE TABLE text_freq(prop_id INTEGER, value_norm TEXT, display TEXT, n_models INTEGER,
                       PRIMARY KEY(prop_id, value_norm));
CREATE TABLE axis_order(type_key TEXT, axes TEXT, order_desc TEXT, n_models INTEGER,
                        PRIMARY KEY(type_key, axes, order_desc));
CREATE TABLE pair_le(type_key TEXT, a_key TEXT, b_key TEXT, dimension TEXT, n_models INTEGER, holds TEXT,
                     PRIMARY KEY(type_key, a_key, b_key));
"""


def prop_key(name: str) -> str:
    """Ключ названия свойства: регистр, ё, пробелы, двоеточие в конце. Совпадает для КТРУ и СТЕ."""
    return key(name).rstrip(":").strip()


def dec_str(x: Decimal) -> str:
    s = format(x.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def type_key_of(registry: TypeRegistry, name: str, category: str) -> tuple[str | None, str]:
    """(ключ типа | None, причина). Тот же код, что для запроса пользователя."""
    det = registry.detect(normalize(name).tokens)
    if not det.heads:
        return None, "type_not_found"
    if det.ambiguous_aliases and len(det.heads) == 1:
        return None, "ambiguous_alias"
    cats = set().union(*(registry.heads.get(h, {}).get("categories", set()) for h in det.heads))
    if category not in cats:
        return None, "other_category"
    return "|".join(sorted(det.heads)), "bound"


def quantile(sorted_vals: list[Decimal], q: int) -> Decimal:
    """Ближайший ранг (без интерполяции — значения остаются наблюдёнными, Decimal без округления)."""
    k = max(0, math.ceil(q / 100 * len(sorted_vals)) - 1)
    return sorted_vals[k]


def zones(model_vals: list[Decimal]) -> list[tuple[Decimal, Decimal, int, bool]]:
    """Зоны типичных значений по моделям (см. zones_from_freq)."""
    return zones_from_freq(sorted(collections.Counter(model_vals).items()))


def zones_from_freq(freq: list[tuple[Decimal, int]]) -> list[tuple[Decimal, Decimal, int, bool]]:
    """Зоны по частотам значений: логарифмическая шкала, BINS_PER_DECADE интервалов на порядок.

    Интервал «занят», если в нём не меньше BIN_MIN_SHARE моделей (иначе шум одной-двух моделей склеивает
    всё в одну зону от 5 см до 18 м). Занятые интервалы с разрывом не больше одного сливаются в зону;
    зона с долей меньше ZONE_MIN_SHARE — «эхо» (не типично). Значения в незанятых интервалах в зоны не входят.
    Нули и отрицательные значения — одна зона без шкалы."""
    n = sum(c for _, c in freq)
    if not n:
        return []
    if any(v <= 0 for v, _ in freq):
        return [(freq[0][0], freq[-1][0], n, False)]
    bins: dict[int, list] = collections.defaultdict(list)
    for v, c in freq:
        bins[math.floor(math.log10(float(v)) * BINS_PER_DECADE + 1e-9)].append((v, c))
    dense = sorted(b for b, vs in bins.items() if sum(c for _, c in vs) >= max(2, BIN_MIN_SHARE * n))
    runs, cur = [], []
    for b in dense:
        if cur and b - cur[-1] > 2:
            runs.append(cur)
            cur = []
        cur.append(b)
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        vs = [x for b in r for x in bins[b]]
        k = sum(c for _, c in vs)
        out.append((min(v for v, _ in vs), max(v for v, _ in vs), k, Decimal(k) / n < ZONE_MIN_SHARE))
    return out


def holdout_of(manufacturer: str, folds: int) -> int:
    """Блок производителя для оценки без утечки (детерминированный хэш)."""
    return int(hashlib.sha1(manufacturer.encode("utf-8")).hexdigest(), 16) % folds


def build(src: Path, db: Path, out: Path, report: Path | None = None, holdout: tuple[int, int] | None = None,
          holdout_out: Path | None = None) -> dict:
    """holdout=(блок, число блоков): модели производителей этого блока не входят в статистику, а их числовые
    значения пишутся в holdout_out (JSONL) для оценки уровня 2 без утечки."""
    held = []
    t0 = time.perf_counter()
    cat = Catalog(db)
    registry = TypeRegistry(cat.search_documents())
    names = {key(n): n for n in SEED_NAMES}
    with sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True) as con:
        for (n,) in con.execute("SELECT DISTINCT name FROM characteristics"):
            names[key(n)] = n
    paths = sorted(p for p in Path(src).glob("*.xlsx") if not p.name.startswith("~$"))
    # проход 1: границы «название — значение» по числовым сегментам и названия второго листа (как ste_importer)
    for path in paths:
        kinds = {}
        for sheet, _, cells in xlsx_rows(path):
            if sheet not in kinds:
                kinds[sheet] = "products" if [cells.get(c, "").strip() for c in "ABCDEF"] == HEADERS else "reference"
                continue
            if kinds[sheet] == "reference":
                for col in ("D", "J"):
                    n = cells.get(col, "").strip()
                    if n:
                        names[key(n)] = n
                continue
            for raw in cells.get("F", "").split("|"):
                m = VALUE_START.search(raw.strip())
                if m and raw.strip()[:m.start()].strip():
                    n = raw.strip()[:m.start()].strip()
                    names[key(n)] = n
    # проход 2: привязка и сбор значений по моделям
    type_cache: dict[tuple[str, str], tuple[str | None, str]] = {}
    num = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))   # (t,p,dim) → model → Counter
    txt = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))   # (t,p) → model → Counter
    display = collections.defaultdict(collections.Counter)   # (t,p,value_norm) → raw forms
    pname = collections.defaultdict(collections.Counter)     # (t,p) → raw names
    flags = collections.defaultdict(collections.Counter)     # (t,p) → флаги
    models_of_type = collections.defaultdict(set)
    manuf_of_model: dict[tuple, str] = {}
    cards_of_type = collections.Counter()
    stats = collections.Counter()
    unbound = collections.defaultdict(collections.Counter)    # причина → первое слово наименования
    sha = {}
    for path in paths:
        category = FILE_CATEGORY.get(path.stem)
        with path.open("rb") as fh:
            sha[path.name] = hashlib.file_digest(fh, "sha256").hexdigest()
        kinds = {}
        for sheet, row, cells in xlsx_rows(path):
            if sheet not in kinds:
                kinds[sheet] = "products" if [cells.get(c, "").strip() for c in "ABCDEF"] == HEADERS else "reference"
                continue
            if kinds[sheet] != "products" or not any(cells.values()):
                continue
            stats["cards"] += 1
            name = cells.get("B", "")
            ck = (key(name), category)
            if ck not in type_cache:
                type_cache[ck] = type_key_of(registry, name, category)
            tkey, why = type_cache[ck]
            if tkey is None:
                stats[f"unbound_{why}"] += 1
                w = key(name).split()
                unbound[why][w[0] if w else ""] += 1
                continue
            stats["bound"] += 1
            man, model = key(cells.get("D", "")), key(cells.get("C", ""))
            is_held = holdout is not None and holdout_of(man, holdout[1]) == holdout[0]
            mkey = (tkey, man, model) if model not in MISSING else (tkey, "card", f"{path.stem}:{row}")
            if is_held:
                stats["held_cards"] += 1
            else:
                models_of_type[tkey].add(mkey)
            manuf_of_model[mkey] = man
            cards_of_type[tkey] += 1
            card_num = collections.defaultdict(set)
            card_txt = collections.defaultdict(set)
            for raw in cells.get("F", "").split("|"):
                raw = raw.strip()
                if not raw:
                    continue
                a = annotate(raw, names)
                if a["name"] is None:
                    stats["seg_unresolved"] += 1
                    continue
                pk = prop_key(a["name"])
                tp = (tkey, pk)
                pname[tp][a["name"].strip().rstrip(":")] += 1
                flags[tp]["segments"] += 1
                if a["kind"] == "missing":
                    flags[tp]["placeholder"] += 1
                    continue
                if a["kind"] in ("number",):
                    dim, base = a["dimension"], a["base_numbers"]
                    paren = None
                    if dim is None:
                        paren = a["name"].rsplit("(", 1)[-1].rstrip(")").strip() if "(" in a["name"] else ""
                        u = lookup(paren) if paren else None
                        if u is not None and a["numbers"]:
                            dim, base = u.dimension, [str(Decimal(a["numbers"][0]) * u.factor)]
                        elif pk.startswith(COUNT_PREFIX) and a["numbers"]:
                            dim, base = "count", a["numbers"][:1]
                    if dim is None or not base:
                        flags[tp]["unit_missing"] += 1
                        continue
                    v = Decimal(base[0]).normalize()
                    if v == 0 and dim in POSITIVE:
                        flags[tp]["placeholder"] += 1
                        continue
                    if is_held:
                        held.append({"type": tkey, "property": a["name"].strip().rstrip(":"), "value": a["numbers"][0],
                                     "unit": a["unit_raw"] or (paren if a["dimension"] is None else None),
                                     "dimension": dim, "manufacturer": man, "model": model, "name": name})
                        continue
                    card_num[(tp, dim)].add(v)
                elif a["kind"] == "text":
                    if is_held:
                        continue
                    vn = key(a["value"])
                    if vn and vn not in MISSING:
                        card_txt[tp].add(vn)
                        display[(tkey, pk, vn)][a["value"].strip()] += 1
                else:
                    flags[tp][a["kind"]] += 1          # range, dimensions — в первой версии не оцениваются
            for (tp, dim), vals in card_num.items():
                if len(vals) > 1:
                    flags[tp]["multi_value"] += 1
                    continue
                num[(tp[0], tp[1], dim)][mkey][next(iter(vals))] += 1
            for tp, vals in card_txt.items():
                if len(vals) > 1:
                    flags[tp]["multi_value"] += 1
                    continue
                txt[tp][mkey][next(iter(vals))] += 1
    stats["build_parse_s"] = round(time.perf_counter() - t0, 1)
    if holdout_out is not None:
        holdout_out.parent.mkdir(parents=True, exist_ok=True)
        with holdout_out.open("w", encoding="utf-8") as fh:
            for h in held:
                fh.write(json.dumps(h, ensure_ascii=False) + chr(10))
        stats["held_values"] = len(held)

    # агрегация в файл
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)

    def majority(counter: collections.Counter):
        (v, n), *rest = counter.most_common(2) + [(None, 0)]
        return v if n > rest[0][1] else None

    for tkey in sorted(models_of_type):
        ms = models_of_type[tkey]
        con.execute("INSERT INTO types VALUES(?,?,?,?,?)", (tkey, _category_of(registry, tkey), cards_of_type[tkey],
                                                           len(ms), len({manuf_of_model[m] for m in ms})))
    pid = 0
    for (tkey, pk, dim) in sorted(num):
        per_model = num[(tkey, pk, dim)]
        vals = {m: majority(c) for m, c in per_model.items()}
        vals = {m: v for m, v in vals.items() if v is not None}
        if not vals:
            continue
        pid += 1
        sv = sorted(vals.values())
        n_types = len(models_of_type[tkey])
        fl = flags[(tkey, pk)]
        con.execute("INSERT INTO props VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            pid, tkey, pk, pname[(tkey, pk)].most_common(1)[0][0], "number", dim, len(vals),
            len({manuf_of_model[m] for m in vals}), sum(sum(c.values()) for c in per_model.values()),
            dec_str(Decimal(len(vals)) / n_types), dec_str(Decimal(fl["placeholder"]) / max(1, fl["segments"])),
            dec_str(Decimal(fl["multi_value"]) / max(1, fl["segments"])), int(any(w in pk for w in PACKAGING)),
            json.dumps({f"p{q:02d}": dec_str(quantile(sv, q)) for q in QUANTILES}), dec_str(sv[0]), dec_str(sv[-1]),
            len(set(sv))))
        for i, (lo, hi, n, echo) in enumerate(zones(sv)):
            con.execute("INSERT INTO zones VALUES(?,?,?,?,?,?)", (pid, i, dec_str(lo), dec_str(hi), n, int(echo)))
        freq = collections.Counter(dec_str(v) for v in vals.values())
        con.executemany("INSERT INTO value_freq VALUES(?,?,?)", [(pid, v, n) for v, n in sorted(freq.items())])
    for (tkey, pk) in sorted(txt):
        per_model = txt[(tkey, pk)]
        vals = {m: majority(c) for m, c in per_model.items()}
        vals = {m: v for m, v in vals.items() if v is not None}
        if not vals:
            continue
        pid += 1
        n_types = len(models_of_type[tkey])
        fl = flags[(tkey, pk)]
        freq = collections.Counter(vals.values())
        con.execute("INSERT INTO props VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            pid, tkey, pk, pname[(tkey, pk)].most_common(1)[0][0], "text", None, len(vals),
            len({manuf_of_model[m] for m in vals}), sum(sum(c.values()) for c in per_model.values()),
            dec_str(Decimal(len(vals)) / n_types), dec_str(Decimal(fl["placeholder"]) / max(1, fl["segments"])),
            dec_str(Decimal(fl["multi_value"]) / max(1, fl["segments"])), int(any(w in pk for w in PACKAGING)),
            None, None, None, len(freq)))
        con.executemany("INSERT INTO text_freq VALUES(?,?,?,?)", [
            (pid, v, display[(tkey, pk, v)].most_common(1)[0][0], n) for v, n in sorted(freq.items())])
    _joint_tables(con, num, models_of_type)
    con.commit()
    # хэш содержимого: логический дамп в фиксированном порядке
    h = hashlib.sha256()
    for table, order in (("types", "type_key"), ("props", "prop_id"), ("zones", "prop_id, zone_no"),
                         ("value_freq", "prop_id, value"), ("text_freq", "prop_id, value_norm"),
                         ("axis_order", "type_key, axes, order_desc"), ("pair_le", "type_key, a_key, b_key")):
        for r in con.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            h.update(json.dumps(r, ensure_ascii=False).encode())
    meta = cat.meta
    manifest = {"schema_version": VERSION, "holdout": list(holdout) if holdout else None, "ktru_snapshot": meta.get("snapshot"), "ktru_as_of": meta.get("as_of"),
                "ktru_morph": meta.get("morph", "pymorphy"), "ste_files": sha, "config": CONFIG,
                "content_hash": h.hexdigest(), "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "stats": dict(stats)}
    con.executemany("INSERT INTO manifest VALUES(?,?)", [(k, json.dumps(v, ensure_ascii=False))
                                                         for k, v in manifest.items()])
    con.commit()
    con.close()
    tmp.replace(out)
    if report is not None:
        rep = {"stats": dict(stats), "types": len(models_of_type),
               "unbound_top": {why: c.most_common(40) for why, c in unbound.items()},
               "types_top": sorted(((len(m), t) for t, m in models_of_type.items()), reverse=True)[:60],
               "elapsed_s": round(time.perf_counter() - t0, 1)}
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


AXIS_KEYS = ("длина", "ширина", "глубина", "высота", "диаметр")
PAIR_MIN_MODELS = 30           # пара свойств встречается вместе хотя бы у стольких моделей
PAIR_MIN_HOLDS = Decimal("0.99")  # «A ≤ B» выполняется не меньше чем у 99 % из них


def _joint_tables(con, num, models_of_type) -> None:
    """Совместные закономерности по моделям (docs/UNITS_PLAN.md, U3–U4):
    axis_order — порядок общих осей по величине у моделей, где указаны хотя бы две оси;
    pair_le — пары числовых свойств одной размерности, где «A ≤ B» выполняется у ≥ 99 % моделей (≥ 30 моделей)."""
    def majority(counter):
        (v, n), *rest = counter.most_common(2) + [(None, 0)]
        return v if n > rest[0][1] else None

    by_type: dict[str, dict] = collections.defaultdict(lambda: collections.defaultdict(dict))
    support: dict[tuple, int] = {}
    for (tkey, pk, dim), per_model in num.items():
        vals = {m: majority(c) for m, c in per_model.items()}
        vals = {m: v for m, v in vals.items() if v is not None}
        support[(tkey, pk, dim)] = len(vals)
        if len(vals) < PAIR_MIN_MODELS or dim in ("count", None):
            continue
        for m, v in vals.items():
            by_type[tkey][m][(pk, dim)] = v
    orders = collections.Counter()
    pairs_n = collections.Counter()
    pairs_le = collections.Counter()
    for tkey in sorted(by_type):
        for m, pv in by_type[tkey].items():
            axes = [(pk, v) for (pk, dim), v in pv.items() if dim == "length" and pk in AXIS_KEYS]
            if len(axes) >= 2:
                order = tuple(k for k, _ in sorted(axes, key=lambda x: (-x[1], x[0])))
                orders[(tkey, ",".join(sorted(k for k, _ in axes)), ",".join(order))] += 1
            items = sorted(pv.items())
            for i, ((a, da), va) in enumerate(items):
                for (b, db), vb in items[i + 1:]:
                    if da != db:
                        continue
                    pairs_n[(tkey, a, b, da)] += 1
                    pairs_le[(tkey, a, b, da)] += va <= vb
    con.executemany("INSERT INTO axis_order VALUES(?,?,?,?)", [(t, a, o, n) for (t, a, o), n in sorted(orders.items())])
    rows = []
    for (t, a, b, d), n in sorted(pairs_n.items()):
        if n < PAIR_MIN_MODELS:
            continue
        le = Decimal(pairs_le[(t, a, b, d)]) / n
        if le >= PAIR_MIN_HOLDS:
            rows.append((t, a, b, d, n, dec_str(le)))
        elif 1 - le >= PAIR_MIN_HOLDS:          # «B ≤ A»
            rows.append((t, b, a, d, n, dec_str(1 - le)))
    con.executemany("INSERT OR IGNORE INTO pair_le VALUES(?,?,?,?,?,?)", rows)


def _category_of(registry: TypeRegistry, tkey: str) -> str:
    cats = sorted(set().union(*(registry.heads.get(h, {}).get("categories", set()) for h in tkey.split("|"))))
    return ",".join(cats)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "Примеры выгрузок"))
    ap.add_argument("--db", default=str(ROOT / "data" / "ktru.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "data" / "ste_stats.sqlite"))
    ap.add_argument("--report", default=str(ROOT / "reports" / "ste_stats_report.json"))
    ap.add_argument("--holdout", default=None, help="блок/число блоков, например 0/5 — для оценки без утечки")
    ap.add_argument("--holdout-out", default=None)
    args = ap.parse_args()
    ho = tuple(int(x) for x in args.holdout.split("/")) if args.holdout else None
    m = build(Path(args.src), Path(args.db), Path(args.out), Path(args.report) if args.report else None,
              holdout=ho, holdout_out=Path(args.holdout_out) if args.holdout_out else None)
    print(json.dumps({k: m[k] for k in ("content_hash", "stats")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
