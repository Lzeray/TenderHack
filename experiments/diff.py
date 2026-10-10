"""Сравнить два отчёта run_exp по кейсам: python -m experiments.diff A.json B.json SUITE OUT.txt"""
import json
import sys

a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
suite = sys.argv[3]
ra = {r["id"]: r for r in a["suites"][suite]["cases"]}
rb = {r["id"]: r for r in b["suites"][suite]["cases"]}
better = worse = 0
with open(sys.argv[4], "w", encoding="utf-8") as out:
    for i, x in ra.items():
        y = rb.get(i)
        if y is None:
            continue
        key = lambda r: (r["pass"], r["status"], r["final_code"], r["compatible_recall"])  # noqa: E731
        if key(x) != key(y):
            tag = "BETTER" if (y["pass"] and not x["pass"]) or (y["status"] == "matched" and not y["auto_incorrect"]
                                                                and x["status"] != "matched") else \
                  "WORSE" if (x["pass"] and not y["pass"]) or y["auto_incorrect"] else "CHANGE"
            better += tag == "BETTER"
            worse += tag == "WORSE"
            out.write(f"{tag} {i}: {x['status']}/{x['final_code']}/{x['compatible_recall']} -> "
                      f"{y['status']}/{y['final_code']}/{y['compatible_recall']}\n    {x['text']}\n")
    out.write(f"\nbetter={better} worse={worse}\n")
print(f"better={better} worse={worse}")
