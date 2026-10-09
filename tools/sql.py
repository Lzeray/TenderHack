"""Выполнить SQL-запрос к базе каталога и записать результат в UTF-8 файл: sql.py OUT "SELECT ..."."""
import sqlite3
import sys

con = sqlite3.connect("data/ktru.sqlite")
with open(sys.argv[1], "w", encoding="utf-8") as out:
    for q in sys.argv[2:]:
        out.write(f"-- {q}\n")
        for r in con.execute(q):
            out.write(" | ".join("" if x is None else str(x) for x in r) + "\n")
