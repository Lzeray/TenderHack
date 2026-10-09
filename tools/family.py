"""Показать семейство позиций по точному наименованию: коды, статус, шаблон и значения
характеристик kind=1 (различающих позиции). Используется для ручной разметки eval-кейсов.

python tools/family.py OUT "Наименование 1" "Наименование 2" ...
"""
import sqlite3
import sys

con = sqlite3.connect("data/ktru.sqlite")
with open(sys.argv[1], "w", encoding="utf-8") as out:
    for name in sys.argv[2:]:
        out.write(f"\n##### {name}\n")
        rows = con.execute("SELECT code, version, status, active, is_template, no_new_features FROM positions "
                           "WHERE name=? AND category IS NOT NULL ORDER BY code", (name,)).fetchall()
        for code, ver, st, act, tpl, nnf in rows:
            out.write(f"{code} v{ver} {st} active={act} tpl={tpl} nnf={nnf}\n")
            for cname, kind, req, vals in con.execute(
                    "SELECT c.name, c.kind, c.is_required, group_concat(coalesce(v.text, "
                    "coalesce(v.min_value,'')||'..'||coalesce(v.max_value,'')||' '||coalesce(v.okei_name,'')), ' | ') "
                    "FROM characteristics c JOIN char_values v USING(position_code, char_code) "
                    "WHERE c.position_code=? GROUP BY c.char_code ORDER BY c.ord", (code,)):
                out.write(f"    [{'R' if req else ' '}k{kind}] {cname}: {vals[:200]}\n")
