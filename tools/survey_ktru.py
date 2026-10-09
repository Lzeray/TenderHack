"""Обзор структуры выгрузки КТРУ: пути элементов, перечисления, имена вложенных файлов.

Использование: python tools/survey_ktru.py "КТРУ/КТРУ xml/КТРУ" > reports/survey.txt
Не меняет исходные данные.
"""
import collections
import glob
import json
import os
import sys
import zipfile
from xml.etree.ElementTree import iterparse

ENUM = {"status", "type", "kind", "choiceType", "valueFormat", "minMathNotation",
        "maxMathNotation", "isTemplate", "actual", "isRequired", "noNewFeatures"}


def loc(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def main(src: str) -> None:
    paths = collections.Counter()
    enums = collections.defaultdict(collections.Counter)
    inner_kinds = collections.Counter()
    not_actual = []
    codes = collections.Counter()
    npos = 0
    for zp in sorted(glob.glob(os.path.join(src, "*.zip"))):
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                kind = "not_actual" if "not_actual" in name.lower().replace("-", "_") else "actual"
                inner_kinds[kind] += 1
                if kind == "not_actual":
                    not_actual.append((os.path.basename(zp), name))
                    continue
                stack = []
                with z.open(name) as f:
                    for ev, el in iterparse(f, events=("start", "end")):
                        if ev == "start":
                            stack.append(loc(el.tag))
                            continue
                        p = "/".join(stack)
                        paths[p] += 1
                        last = stack[-1]
                        if last in ENUM and el.text:
                            enums[p][el.text.strip()] += 1
                        if p.endswith("position/data/code"):
                            codes[el.text] += 1
                        stack.pop()
                        if last == "position":
                            npos += 1
                            el.clear()
    print("inner files:", dict(inner_kinds))
    print("not_actual entries:", not_actual)
    print("positions:", npos, "unique codes:", len(codes),
          "codes with >1 record:", sum(1 for c in codes.values() if c > 1))
    for p, c in sorted(paths.items()):
        print(c, p)
    print(json.dumps({k: dict(v.most_common(10)) for k, v in enums.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
