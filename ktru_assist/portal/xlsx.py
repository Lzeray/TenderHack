"""Потоковое чтение .xlsx без внешних пакетов (zipfile + iterparse).

Выгрузки портала большие (sharedStrings до 120 МБ), поэтому строки отдаются генератором,
а разделяемые строки читаются один раз.
"""
from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from xml.etree.ElementTree import iterparse

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_COL = re.compile(r"([A-Z]+)")


def _col_index(ref: str) -> int:
    letters = _COL.match(ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def shared_strings(z: zipfile.ZipFile) -> list[str]:
    out: list[str] = []
    if "xl/sharedStrings.xml" not in z.namelist():
        return out
    with z.open("xl/sharedStrings.xml") as fh:
        for _, el in iterparse(fh, events=("end",)):
            if el.tag == NS + "si":
                out.append("".join(t.text or "" for t in el.iter(NS + "t")))
                el.clear()
    return out


def rows(path, sheet: int = 1, strings: list[str] | None = None) -> Iterator[list[str | None]]:
    """Строки листа sheet (1 — первый) как списки значений."""
    with zipfile.ZipFile(path) as z:
        ss = strings if strings is not None else shared_strings(z)
        with z.open(f"xl/worksheets/sheet{sheet}.xml") as fh:
            for _, el in iterparse(fh, events=("end",)):
                if el.tag != NS + "row":
                    continue
                vals: list[str | None] = []
                for c in el.iter(NS + "c"):
                    i = _col_index(c.get("r", "A1"))
                    while len(vals) < i:
                        vals.append(None)
                    v = c.find(NS + "v")
                    if c.get("t") == "s" and v is not None:
                        vals.append(ss[int(v.text)])
                    elif c.get("t") == "inlineStr":
                        vals.append("".join(t.text or "" for t in c.iter(NS + "t")))
                    else:
                        vals.append(v.text if v is not None else None)
                yield vals
                el.clear()
