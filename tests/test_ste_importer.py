"""Quality labels are proposals; raw exports and unknown fragments are preserved."""
import json
import sqlite3
import zipfile

from ktru_assist.catalog.ste_importer import HEADERS, REFERENCE_HEADERS, SEED_NAMES, annotate, key, run


NAMES = {key(n): n for n in [*SEED_NAMES, "Масса", "Длина", "Размеры"]}


def test_quantities_dimensions_and_unknown():
    mass = annotate("Масса 500 г", NAMES)
    assert mass["base_numbers"] == ["0.500"] and mass["dimension"] == "mass"
    interval = annotate("Длина до 50 см", NAMES)
    assert interval["operator"] == "до" and interval["numbers"] == ["50"]
    dims = annotate("Размеры 450 х 285 х 150 см", NAMES)
    assert dims["kind"] == "dimensions" and len(dims["numbers"]) == 3
    assert "dimension_axes_unassigned" in dims["issues"]
    unknown = annotate("Неизученное свойство интересное", NAMES)
    assert unknown["name"] is None and unknown["value"] == "Неизученное свойство интересное"
    assert annotate("Масса (не задано) кг", NAMES)["kind"] == "missing"


def test_import_preserves_rows_labels_conflicts_and_does_not_invent_codes(tmp_path):
    from xml.sax.saxutils import escape
    path = tmp_path / "Мебель.xlsx"
    rows = [HEADERS, ["001", "Шкаф", "-", "Завод", "Россия", "Масса 500 г | Масса 0,5 кг | Масса 2 кг | Тип шкаф"],
            ["001", "Шкаф", "-", "Завод", "Россия", "Непонятное свойство неизвестное"]]
    body = []
    for n, values in enumerate(rows, 1):
        cells = "".join(f'<c r="{col}{n}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for col, v in zip("ABCDEF", values))
        body.append(f'<row r="{n}">{cells}</row>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Лист1" r:id="rId1"/><sheet name="Лист2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(body) + '</sheetData></worksheet>')
        refs = [REFERENCE_HEADERS, ["Шкафы", "001.02", "Мебель", "Материал корпуса", "базовая", "текст", "Сталь", "", "123", "Материал", "Металл"]]
        ref_body = "".join('<row r="%s">%s</row>' % (n, "".join(f'<c r="{col}{n}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for col, v in zip("ABCDEFGHIJK", values))) for n, values in enumerate(refs, 1))
        z.writestr("xl/worksheets/sheet2.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ref_body + '</sheetData></worksheet>')
    db = tmp_path / "ste.sqlite"
    summary = run(path, db, tmp_path / "report.json", tmp_path / "review.csv")
    assert summary["products"] == 2 and summary["features"] == 5
    assert summary["category_properties"] == 1
    assert summary["issue_counts"]["duplicate_feature"] == 1
    assert summary["issue_counts"]["conflicting_feature_values"] == 1
    assert summary["issue_counts"]["duplicate_ste_id"] == 1
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT kpgz_code,property_name,spgz_id FROM category_properties").fetchone() == ("001.02", "Материал корпуса", "123")
        assert c.execute("SELECT ste_id,row_number,ktru_code,annotation_status FROM products ORDER BY id").fetchall() == [
            ("001", 2, None, "unreviewed"), ("001", 3, None, "unreviewed")]
        assert json.loads(c.execute("SELECT raw_cells FROM products ORDER BY id").fetchone()[0])["F"] == rows[1][5]
