"""Offline ablation: baseline STE search vs category facts and SPGZ/OKPD2 bridge.

Never assigns a KTRU code to a product and never changes the KTRU resolver.
Output contains full sets of product IDs, unknowns and counterexamples for review.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
import re
import sqlite3

from ktru_assist.catalog.repository import Catalog
from ktru_assist.catalog.ste_importer import key
from ktru_assist.catalog.ste_search import SteSearch
from ktru_assist.models import Feature
from ktru_assist.text import content_lemmas, tokenize
from ktru_assist.validate import check_feature

KPGZ_CODE = re.compile(r"01(?:\.\d{2})+")


@lru_cache(maxsize=30000)
def property_key(name):
    return tuple(content_lemmas(name))


@dataclass
class ReferenceCategory:
    source_id: int
    code: str
    name: str
    # PP feature -> names of explicitly linked SPGZ characteristics. IDs remain property IDs.
    aliases: dict = field(default_factory=lambda: defaultdict(set))
    defining: dict = field(default_factory=lambda: defaultdict(set))
    property_ids: set = field(default_factory=set)


def read_reference(connection):
    categories = {}
    invalid = 0
    for row in connection.execute("SELECT * FROM category_properties"):
        if not KPGZ_CODE.fullmatch(row["kpgz_code"] or "") or not row["category_name"]:
            invalid += 1
            continue
        identity = (row["source_id"], row["kpgz_code"], row["category_name"])
        category = categories.setdefault(identity, ReferenceCategory(*identity))
        if row["property_role"] == "Категореобразующая":
            category.defining[property_key(row["property_name"])].update(
                key(value) for value in row["allowed_values_raw"].split(";") if value.strip())
        if row["spgz_id"]:
            ids = [value.strip() for value in row["spgz_id"].split("|")]
            names = [value.strip() for value in row["spgz_name"].split("|")]
            # A malformed column alignment does not authorize guessing the association.
            if len(ids) == len(names):
                for identifier, name in zip(ids, names):
                    if identifier.isdigit() and name:
                        category.property_ids.add(identifier)
                        category.aliases[property_key(row["property_name"])].add(name)
    return categories, invalid


def classify(facts, all_categories, pair_index, known_properties, category_names):
    """Intersect provided category-forming facts, without names or Excel row-order guesses."""
    candidates = set(all_categories)
    used = False
    for name, value in facts:
        prop = property_key(name)
        if prop not in known_properties:
            continue
        values = pair_index.get((prop, key(value)))
        if values is None:
            return "unknown_value", set()
        used = True
        candidates.intersection_update(values)
        if not candidates:
            return "conflicting_facts", set()
    if not used:
        return "no_category_facts", set()
    if len(candidates) == 1:
        identity = next(iter(candidates))
        # Broad facts alone cannot prove a leaf in an incomplete category reference.
        if not any(property_key(name) in known_properties and key(value) == key(category_names[identity])
                   for name, value in facts):
            return "partial_facts", candidates
        return "unique", candidates
    return "ambiguous", candidates


def build_assignments(connection, categories):
    by_source, indices, properties = defaultdict(set), defaultdict(dict), defaultdict(set)
    for identity, category in categories.items():
        by_source[category.source_id].add(identity)
        for name, values in category.defining.items():
            properties[category.source_id].add(name)
            for value in values:
                indices[category.source_id].setdefault((name, value), set()).add(identity)
    # Use the original property spellings for SQLite; lower() in SQLite does not fold Cyrillic.
    raw_names = [r[0] for r in connection.execute(
        "SELECT DISTINCT property_name FROM category_properties WHERE property_role='Категореобразующая'")]
    facts = defaultdict(list)
    if raw_names:
        placeholders = ",".join("?" for _ in raw_names)
        for row in connection.execute(f"SELECT product_id,name,value FROM features WHERE name IN ({placeholders})", raw_names):
            facts[row[0]].append((row[1], row[2]))
    assignments, states, coverage = {}, {}, defaultdict(Counter)
    category_names = {identity: category.name for identity, category in categories.items()}
    for row in connection.execute("SELECT id,source_id FROM products ORDER BY id"):
        pid, source = row
        state, choices = classify(facts.get(pid, []), by_source[source], indices[source], properties[source],
                                  category_names)
        assignments[pid], states[pid] = choices, state
        coverage[source][state] += 1
    return assignments, states, {str(source): dict(counts) for source, counts in coverage.items()}


def mirror_records(snapshot):
    records = {}
    for query in snapshot.get("spgz", []):
        for page in query.get("pages", []):
            for row in page.get("payload", {}).get("results", []):
                records[row["global_id"]] = row
    return list(records.values())


def bridge(positions, categories, records):
    """Exact name + exact OKPD2 only. A category may legitimately have many KTRU positions."""
    targets, evidence = set(), []
    for position in positions:
        name = property_key(position.name)
        for row in records:
            if name != property_key(row["spgz_name"]) or position.okpd2_code != row["okpd2_code"]:
                continue
            matches = {identity for identity in categories if identity[1] == row["kpgz_code"]}
            if matches:
                targets.update(matches)
                evidence.append({"ktru_code": position.code, "kpgz_code": row["kpgz_code"],
                                 "spgz_global_id": row["global_id"], "okpd2": row["okpd2_code"],
                                 "basis": "third_party_exact_name_and_okpd2_hypothesis"})
    return targets, evidence


OPERATORS = {None: "eq", "eq": "eq", "от": "ge", "до": "le", "не менее": "ge",
             "не более": "le", ">=": "ge", "<=": "le", "≥": "ge", "≤": "le",
             ">": "gt", "<": "lt", "between": "between"}


def product_check(rows, position, categories):
    """Reuse KTRU validator; check every mapped supplied fact, and every required property.

    Missing, ambiguous aliases, conflicting duplicates and unsupported formats remain unknown.
    No normalization of categorical values beyond the existing validator is invented here.
    """
    checked, unknown, invalid, valid_codes = [], [], [], set()
    supplied = defaultdict(set)
    for row in rows:
        names = {row["name"]} if row["name"] else set()
        for category in categories:
            names.update(category.aliases.get(property_key(row["name"] or ""), set()))
        normalized = {" ".join(tokenize(name)) for name in names}
        props = [prop for prop in position.props.values() if prop.norm_name in normalized]
        if len(props) > 1:
            unknown.extend(prop.name for prop in props)
            continue
        if not props:
            continue
        prop = props[0]
        supplied[prop.code].add((row["kind"], row["numbers"], row["operator"],
                                 row["unit_raw"], key(row["value"])))
        if row["kind"] == "missing":
            unknown.append(prop.name)
            continue
        numbers = json.loads(row["numbers"])
        operator = OPERATORS.get(row["operator"])
        if row["kind"] in ("number", "range") and numbers and operator:
            value = numbers[0]
            upper = numbers[1] if len(numbers) == 2 else None
        elif row["kind"] == "text":
            value, upper, operator = row["value"], None, "eq"
        else:
            unknown.append(prop.name)
            continue
        feature = Feature(id=f"ste-{row['id']}", source="text", status="bound", property_code=prop.code,
                          property_name=prop.name, strict_ref=True, value=value, value_to=upper,
                          op=operator, unit=row["unit_raw"], intent="fact", confirmation="confirmed")
        status, reason, _ = check_feature(position, feature)
        checked.append({"property": prop.name, "value": row["value"], "status": status, "reason": reason})
        if status == "valid":
            valid_codes.add(prop.code)
        elif status == "invalid":
            invalid.append(prop.name)
        else:
            unknown.append(prop.name)
    unknown.extend(position.props[code].name for code, values in supplied.items() if len(values) > 1)
    missing = [prop.name for prop in position.props.values() if prop.required and prop.code not in valid_codes]
    if invalid:
        state = "contradicted"
    elif missing or unknown or not checked:
        state = "unknown"
    else:
        state = "checked"
    return {"state": state, "missing_required": missing, "unknown": unknown, "checks": checked}


CASES = [
    ("Молоток", []),
    ("Молоток", [{"name": "Тип", "value": "Слесарный"}]),
    ("Молоток", [{"name": "Тип", "value": "Слесарный"}, {"name": "Масса молотка", "value": "500", "unit": "г"}]),
    ("Стул на металлическом каркасе", []),
    ("Стул на деревянном каркасе", []),
    ("Стул на металлическом каркасе", [{"name": "Тип сиденья", "value": "Мягкое"}]),
    ("Перчатки трикотажные для защиты от внешних воздействий", []),
    ("Перчатки швейные для защиты от внешних воздействий", []),
    ("Перчатки из полимерных материалов для защиты от внешних воздействий", []),
]


def run(source_path, search_path, catalog_path, snapshot_path, out):
    source = sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    categories, invalid_reference_rows = read_reference(source)
    assignments, states, coverage = build_assignments(source, categories)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    records = mirror_records(snapshot)
    catalog, search = Catalog(catalog_path), SteSearch(search_path)
    positions = catalog.get_many([row[0] for row in catalog.con.execute(
        "SELECT code FROM positions WHERE active=1 AND is_template=0 AND category IS NOT NULL")])
    report = {"version": "1.0", "annotation": "Hypothesis ablation, not precision/recall or verified product KTRU labels",
              "external_snapshot": str(snapshot_path), "retrieved_at": snapshot.get("retrieved_at"),
              "external_queries": [{"query": q["query"], "complete": q["complete"],
                                    "pages": len(q["pages"])} for q in snapshot.get("spgz", [])],
              "snapshot": catalog.meta, "sources": [dict(row) for row in source.execute("SELECT * FROM sources")],
              "reference_categories": len(categories), "invalid_reference_rows": invalid_reference_rows,
              "spgz_characteristic_ids": len(set().union(*(category.property_ids for category in categories.values()))),
              "mirror_positions": len(records), "category_coverage": coverage, "cases": []}
    feature_cache = {}
    for name, attributes in CASES:
        selected = [p for p in positions.values() if property_key(p.name) == property_key(name)]
        query_facts = [Feature(id=f"query-{i}", source="text", status="bound", property_name=a["name"],
                              value=a["value"], unit=a.get("unit"), op=a.get("op", "eq"))
                       for i, a in enumerate(attributes)]
        selected = [p for p in selected if all(check_feature(p, f)[0] != "invalid" for f in query_facts)]
        # The candidate set is held constant for the ablation. This is a supplied KTRU selection,
        # not a replacement description recognizer.
        targets, evidence = bridge(selected, categories, records)
        baseline = search.search(content_lemmas(name), attributes, limit=300000)
        before = {row["id"] for row in baseline["items"]}
        known_in, known_out, unknown = set(), set(), set()
        for pid in before:
            choices = assignments[pid]
            if not targets or not choices or states[pid] != "unique":
                unknown.add(pid)
            elif choices <= targets:
                known_in.add(pid)
            else:
                known_out.add(pid)
        bins = defaultdict(set)
        direct_bins = defaultdict(set)
        samples = defaultdict(list)
        for pid in sorted(known_in):
            if pid not in feature_cache:
                feature_cache[pid] = source.execute("SELECT * FROM features WHERE product_id=? ORDER BY ordinal", (pid,)).fetchall()
            product_categories = [categories[identity] for identity in assignments[pid]]
            checks = [product_check(feature_cache[pid], position, product_categories) for position in selected]
            direct = [product_check(feature_cache[pid], position, []) for position in selected]
            direct_state = ("checked" if any(check["state"] == "checked" for check in direct) else
                            "unknown" if any(check["state"] == "unknown" for check in direct) else "contradicted")
            direct_bins[direct_state].add(pid)
            state = ("checked" if any(check["state"] == "checked" for check in checks) else
                     "unknown" if any(check["state"] == "unknown" for check in checks) else "contradicted")
            bins[state].add(pid)
            if len(samples[state]) < 5:
                product = source.execute("SELECT ste_id,name,raw_characteristics FROM products WHERE id=?", (pid,)).fetchone()
                samples[state].append({"id": pid, **dict(product), "checks": checks})
        for label, ids in (("category_excluded", known_out), ("category_unknown", unknown)):
            for pid in sorted(ids)[:5]:
                product = source.execute("SELECT ste_id,name FROM products WHERE id=?", (pid,)).fetchone()
                samples[label].append({"id": pid, **dict(product), "category_state": states[pid],
                                       "categories": [categories[identity].name for identity in sorted(assignments[pid])]})
        sets = {"baseline": sorted(before), "category_selected": sorted(known_in),
                "category_excluded": sorted(known_out), "category_unknown": sorted(unknown),
                "category_soft": sorted(before - known_out),
                "characteristics_checked": sorted(bins["checked"]),
                "characteristics_unknown": sorted(bins["unknown"]),
                "characteristics_contradicted": sorted(bins["contradicted"]),
                "direct_characteristics_checked": sorted(direct_bins["checked"]),
                "direct_characteristics_unknown": sorted(direct_bins["unknown"]),
                "direct_characteristics_contradicted": sorted(direct_bins["contradicted"])}
        report["cases"].append({"name": name, "attributes": attributes,
                                "ktru_codes_held_constant": [p.code for p in selected],
                                "target_categories": sorted({categories[identity].name for identity in targets}),
                                "bridge_evidence": evidence, "bridge_available": bool(targets),
                                "counts": {label: len(ids) for label, ids in sets.items()},
                                "sets": sets, "samples": dict(samples)})
        print(name, attributes, report["cases"][-1]["counts"], flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Portable, small evidence artifact. Raw HTTP bodies stay in ignored data/exp_*.
    portable = {"retrieved_at": snapshot.get("retrieved_at"),
                "sources": [{k: v for k, v in evidence.items() if k != "body"}
                            for evidence in snapshot.get("sources", [])],
                "spgz": [{**query, "pages": [{k: v for k, v in page.items() if k != "body"}
                                            for page in query["pages"]]} for query in snapshot.get("spgz", [])]}
    out.with_name(out.name + "_sources").with_suffix(".json").write_text(
        json.dumps(portable, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Аблация товарного отбора через КПГЗ/СПГЗ", "",
             "Это сравнение множеств, не оценка точности: эталонных кодов КТРУ для СТЕ нет.", "",
             f"Категорий: {len(categories)}; строк без валидного КПГЗ: {invalid_reference_rows}; "
             f"ID характеристик СПГЗ: {report['spgz_characteristic_ids']}; позиций стороннего зеркала: {len(records)}.", "",
             "## Покрытие фактических категорий", "", "```json", json.dumps(coverage, ensure_ascii=False, indent=2), "```", "",
             "## Сравнение полных наборов", "",
             "| Кейс | Без связи | Категория подходит | Категория исключена | Категория неизвестна | Характеристики проверены | Не хватает характеристик | Противоречие КТРУ |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for case in report["cases"]:
        count = case["counts"]
        label = case["name"] + ("; " + ", ".join(f"{a['name']}={a['value']} {a.get('unit', '')}" for a in case["attributes"]) if case["attributes"] else "")
        lines.append("| " + label + " | " + " | ".join(str(count[k]) for k in
                     ("baseline", "category_selected", "category_excluded", "category_unknown", "characteristics_checked", "characteristics_unknown", "characteristics_contradicted")) + " |")
    lines += ["", "Полные ID всех наборов, основания связи и реальные примеры: соседний JSON.", "",
              "`category_selected` означает только соответствие категории. `characteristics_checked` — "
              "все распознанные факты совместимы и обязательные свойства присутствуют; это не официальная привязка СТЕ к КТРУ.",
              "Непроверенные товары сохранены отдельным набором. Строгий отбор потеряет их; мягкий оставит неопределённость."]
    lines += ["", "## Добавочный эффект связей характеристик СПГЗ", "",
              "На уже отобранной категории: тот же валидатор КТРУ, сначала только прямые названия, затем явные связи характеристик СПГЗ.", "",
              "| Кейс | Прямые названия: проверены | Связи СПГЗ: проверены |", "|---|---:|---:|"]
    for case in report["cases"]:
        lines.append(f"| {case['name']} ({len(case['attributes'])} фильтров) | "
                     f"{case['counts']['direct_characteristics_checked']} | {case['counts']['characteristics_checked']} |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/ste.sqlite"))
    parser.add_argument("--search", type=Path, default=Path("data/ste_search.sqlite"))
    parser.add_argument("--catalog", type=Path, default=Path("data/ktru.sqlite"))
    parser.add_argument("--snapshot", type=Path, default=Path("data/exp_reference_sources.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/ste_reference_ablation"))
    args = parser.parse_args()
    run(args.source, args.search, args.catalog, args.snapshot, args.out)


if __name__ == "__main__":
    main()
