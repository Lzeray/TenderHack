"""Вывести непройденные кейсы отчёта run_exp: python -m experiments.show_fail REPORT.json SUITE OUT.txt"""
import json
import sys

rep = json.load(open(sys.argv[1], encoding="utf-8"))
suite = sys.argv[2]
with open(sys.argv[3], "w", encoding="utf-8") as out:
    for r in rep["suites"][suite]["cases"]:
        if not r["pass"] or r["auto_incorrect"]:
            out.write(f"{'WRONG ' if r['auto_incorrect'] else ''}{r['id']} [{r['status']}] final={r['final_code']} "
                      f"acc={r['acceptable']} recall={r['compatible_recall']}\n    {r['text']}\n")
