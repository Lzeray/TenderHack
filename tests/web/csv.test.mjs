import { test } from "node:test";
import assert from "node:assert/strict";
import { decodeCsv, encodeCsv, exportCsv, importCsv, parseCsv, projectCsvRows } from "../../frontend/src/csv.js";

test("CSV: BOM, точка с запятой, кавычки, переносы и пустые строки", () => {
  const text = '\uFEFFОписание;Материал\r\n"стол; \"\"Прямой\"\"";"массив\nдерева"\r\n\r\n';
  assert.deepEqual(parseCsv(text), [["Описание", "Материал"], ['стол; "Прямой"', "массив\nдерева"]]);
});

test("CSV: запятая, табуляция и директива Excel sep", () => {
  assert.deepEqual(parseCsv('Описание,Масса\n"молоток, слесарный","0,5 кг"'), [["Описание", "Масса"], ["молоток, слесарный", "0,5 кг"]]);
  assert.deepEqual(parseCsv("Описание\tМатериал\nстол\tдерево"), [["Описание", "Материал"], ["стол", "дерево"]]);
  assert.deepEqual(parseCsv("sep=,\nОписание,Масса\nмолоток,500 г"), [["Описание", "Масса"], ["молоток", "500 г"]]);
});

test("CSV: незакрытые кавычки и текст после кавычек не принимаются", () => {
  assert.throws(() => parseCsv('Описание\n"молоток'), /не закрыта кавычка/);
  assert.throws(() => parseCsv('Описание\n"молоток"лишнее'), /после закрывающей кавычки/);
});

test("CSV: описания и именованные параметры, идентификаторы не участвуют в поиске", () => {
  const imported = importCsv("ID;Наименование;Описание;Масса\n12;Молоток;слесарный;500 г");
  assert.equal(imported.rows[0].query, "Молоток, слесарный, Масса: 500 г");
  assert.deepEqual(imported.rows[0].fields, ["12", "Молоток", "слесарный", "500 г"]);
  assert.equal(imported.rows[0].rowNumber, 2);
});

test("CSV: файл без заголовка не теряет первую строку", () => {
  const imported = importCsv("молоток слесарный 500 г\nстол письменный\n");
  assert.equal(imported.rows.length, 2);
  assert.equal(imported.rows[0].query, "молоток слесарный 500 г");
  assert.equal(imported.rows[0].rowNumber, 1);
});

test("CSV: пустой файл, только заголовок и несовпадающие столбцы", () => {
  assert.throws(() => importCsv("\n\r\n"), /пуст/);
  assert.throws(() => importCsv("Описание\n"), /только заголовок/);
  assert.throws(() => importCsv("Описание;Масса\nмолоток;500;г"), /больше столбцов/);
  assert.match(importCsv("Описание;Масса\n;500 г").rows[0].error, /нет описания/);
});

test("CSV: UTF-8 и Windows-1251 для русских описаний", () => {
  assert.equal(decodeCsv(new TextEncoder().encode("молоток")), "молоток");
  assert.equal(decodeCsv(new Uint8Array([0xec, 0xee, 0xeb, 0xee, 0xf2, 0xee, 0xea])), "молоток");
});

const response = (code, missing = []) => ({
  status: "matched", preliminary: false, compatible_codes: [code],
  candidates: [{ code, name: `Товар ${code}`, compatible: true, is_template: false }],
  required_characteristics: missing.map(name => ({ name, status: "missing" })),
  features: [{ property_name: "Масса", status: "bound", value: "500", unit: "г", op: "eq" }],
  additional: [{ name: "Материал ручки", value: "Дерево", accepted: true }],
});
const row = (id, data) => ({ id, rowNumber: id + 2, fields: [`описание ${id}`], query: `описание ${id}`, done: true, response: data });

test("CSV: по умолчанию строгий режим, неполный товар скрыт, строка остаётся", () => {
  const projected = projectCsvRows([row(0, response("1")), row(1, response("2", ["Диаметр"]))]);
  assert.equal(projected[0].item.code, "1");
  assert.equal(projected[1].item, null);
  assert.equal(projected[1].status, "incomplete");
  assert.deepEqual(projected[1].missing, ["Диаметр"]);
});

test("CSV: мягкий режим возвращает тот же товар с предупреждением без повторного поиска", () => {
  const input = [row(0, response("2", ["Диаметр"]))];
  assert.equal(projectCsvRows(input)[0].item, null);
  const projected = projectCsvRows(input, false);
  assert.equal(projected[0].item.code, "2");
  assert.equal(projected[0].status, "warning");
  assert.match(projected[0].message, /не все обязательные/);
  assert.equal(input[0].response.candidates[0].code, "2");
});

test("CSV: несколько, ноль, устаревшие и неподтверждённые КТРУ не становятся товаром", () => {
  const many = { ...response("1", ["Диаметр"]), compatible_codes: ["1", "2"] };
  const none = { ...response("1"), status: "not_found", compatible_codes: [] };
  const stale = { ...response("1"), stale: true };
  const preview = { ...response("1"), preliminary: true };
  for (const data of [many, none, stale, preview]) {
    const projected = projectCsvRows([row(0, data)], false)[0];
    assert.equal(projected.item, null);
    assert.deepEqual(projected.missing, [], "Без одного КТРУ нельзя утверждать его обязательные поля");
    assert.equal(projected.message, "КТРУ не может быть однозначно определен");
  }
});

test("CSV: экспорт и карточки используют одни и те же коды, все исходные строки сохранены", () => {
  const rows = [row(0, response("1")), row(1, response("2", ["Диаметр"])),
    row(2, { ...response("3"), compatible_codes: ["3", "4"] })];
  const strict = parseCsv(exportCsv(["Описание"], projectCsvRows(rows)));
  const soft = parseCsv(exportCsv(["Описание"], projectCsvRows(rows, false)));
  assert.equal(strict.length, 4);
  assert.deepEqual(strict.slice(1).map(r => r[1]), ["1", "", ""]);
  assert.deepEqual(soft.slice(1).map(r => r[1]), ["1", "2", ""]);
  assert.match(strict[3][3], /не может быть однозначно/);
  assert.equal(strict[1][6], "Масса: 500 г\nМатериал ручки: Дерево");
  assert.deepEqual(importCsv(exportCsv(["Описание"], projectCsvRows(rows))).rows.map(r => r.query), rows.map(r => r.query));
});

test("CSV: выгрузка корректно экранирует значения и сохраняет десятичную запятую", () => {
  const rows = [['молоток; "красный"', "0,5 кг", "строка\nдва"]];
  assert.deepEqual(parseCsv(encodeCsv(["Описание", "Масса", "Примечание"], rows)).slice(1), rows);
});
