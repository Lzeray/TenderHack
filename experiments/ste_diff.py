"""Сравнить два прогона ste_run по каждому наименованию: python -m experiments.ste_diff A.json B.json OUT.txt"""
import json
import sys

a = json.load(open(sys.argv[1], encoding="utf-8"))["audit"]
b = json.load(open(sys.argv[2], encoding="utf-8"))["audit"]
with open(sys.argv[3], "w", encoding="utf-8") as out:
    n = 0
    for x, y in zip(a, b):
        if (x["status"], x["final"], x["types"], x["features"]) != (y["status"], y["final"], y["types"], y["features"]):
            n += 1
            out.write(f"{x['text']}\n   A: {x['status']} {x['types']} final={x['final']} F={x['features']}\n"
                      f"   B: {y['status']} {y['types']} final={y['final']} n={y['n']} F={y['features']} "
                      f"top={y['top'][:1]}\n")
    out.write(f"\nchanged={n}\n")
