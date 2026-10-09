"""Сводки по импортированной базе (для исследования, не для продукта)."""
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "data/ktru.sqlite")
q = lambda s, *a: con.execute(s, a).fetchall()  # noqa: E731
print("OKEI в значениях MVP:")
for r in q("""SELECT v.okei_code, v.okei_name, count(*) FROM char_values v JOIN positions p ON p.code=v.position_code
             WHERE p.category IS NOT NULL AND p.active=1 GROUP BY 1,2 ORDER BY 3 DESC"""):
    print("  ", r)
print("Числовые без ОКЕИ (имена характеристик):")
for r in q("""SELECT c.name, count(*) FROM char_values v JOIN characteristics c USING(position_code,char_code)
             JOIN positions p ON p.code=v.position_code
             WHERE p.category IS NOT NULL AND p.active=1 AND v.value_kind IN ('range','concrete') AND v.okei_code IS NULL
             GROUP BY 1 ORDER BY 2 DESC LIMIT 40"""):
    print("  ", r)
print("Самые частые характеристики:")
for r in q("""SELECT p.category, c.name, count(*) FROM characteristics c JOIN positions p ON p.code=c.position_code
             WHERE p.category IS NOT NULL AND p.active=1 GROUP BY 1,2 ORDER BY 3 DESC LIMIT 60"""):
    print("  ", r)
print("Головные слова:")
for r in q("""SELECT category, head, count(*) FROM positions WHERE category IS NOT NULL AND active=1
             GROUP BY 1,2 ORDER BY 3 DESC LIMIT 80"""):
    print("  ", r)
