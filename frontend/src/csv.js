import { featureValue } from "./state.js";

const headerKey = value => value.trim().toLowerCase().replaceAll("ё", "е").replace(/[_-]+/g, " ").replace(/\s+/g, " ");
const descriptions = new Set(["описание", "описание товара", "наименование", "наименование товара", "название", "название товара", "товар", "запрос", "текст", "description", "name", "product", "product name"]);
const metadata = new Set(["id", "№", "номер", "артикул", "код ктру", "ктру"]);

export function decodeCsv(bytes) {
  if (bytes[0] === 255 && bytes[1] === 254) return new TextDecoder("utf-16le").decode(bytes);
  if (bytes[0] === 254 && bytes[1] === 255) return new TextDecoder("utf-16be").decode(bytes);
  try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch { return new TextDecoder("windows-1251").decode(bytes); }
}

export function parseCsv(source) {
  let text = source.replace(/^\uFEFF/, "");
  const separatorLine = text.match(/^sep=([;,\t])\r?\n/i);
  if (separatorLine) text = text.slice(separatorLine[0].length);
  const counts = { ";": 0, ",": 0, "\t": 0 };
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '"') {
      if (quoted && text[i + 1] === '"') i++;
      else quoted = !quoted;
    } else if (!quoted) {
      if (text[i] === "\n" || text[i] === "\r") break;
      if (text[i] in counts) counts[text[i]]++;
    }
  }
  const delimiter = separatorLine?.[1] || Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
  const rows = [];
  let row = [], value = "", inQuotes = false, closedQuote = false;
  const field = () => { row.push(value); value = ""; closedQuote = false; };
  const record = () => { field(); if (row.some(cell => cell.trim())) rows.push(row); row = []; };
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') { value += '"'; i++; }
        else { inQuotes = false; closedQuote = true; }
      } else value += char;
    } else if (char === delimiter) field();
    else if (char === "\n" || char === "\r") { record(); if (char === "\r" && text[i + 1] === "\n") i++; }
    else if (char === '"' && !value && !closedQuote) inQuotes = true;
    else if (closedQuote) { if (!/\s/.test(char)) throw new Error("Некорректный CSV: текст после закрывающей кавычки."); }
    else value += char;
  }
  if (inQuotes) throw new Error("Некорректный CSV: не закрыта кавычка.");
  if (value || row.length || closedQuote) record();
  return rows;
}

export function importCsv(source) {
  const records = parseCsv(source);
  if (!records.length) throw new Error("CSV пуст. Добавьте строки с описаниями товаров.");
  const hasHeader = records[0].some(cell => descriptions.has(headerKey(cell)));
  const headers = hasHeader ? records.shift() : Array.from({ length: records.reduce((width, r) => Math.max(width, r.length), 0) }, (_, i) => i ? `Поле ${i + 1}` : "Описание");
  if (!records.length) throw new Error("В CSV есть только заголовок. Добавьте описания товаров.");
  const keys = headers.map(headerKey);
  const descriptionIndices = hasHeader ? keys.flatMap((key, i) => descriptions.has(key) ? [i] : []) : [0];
  const rows = records.map((cells, index) => {
    if (cells.length > headers.length) throw new Error(`В строке ${index + 2} больше столбцов, чем в заголовке CSV.`);
    const fields = headers.map((_, i) => cells[i] || "");
    const base = descriptionIndices.map(i => fields[i].trim()).filter(Boolean);
    const attributes = fields.flatMap((cell, i) => {
      if (!cell.trim() || descriptionIndices.includes(i) || metadata.has(keys[i]) || keys[i].startsWith("результат:")) return [];
      return [hasHeader ? `${headers[i].trim()}: ${cell.trim()}` : cell.trim()];
    });
    return { id: index, rowNumber: index + (hasHeader ? 2 : 1), fields, query: [...base, ...attributes].join(", "),
      error: base.length ? null : "В строке нет описания товара.", done: false, response: null };
  });
  return { headers, rows };
}

export function recognizedParameters(response) {
  if (!response) return [];
  const values = (response.features || []).filter(f => f.status === "bound" && f.property_name && (f.value != null || f.values?.length))
    .map(f => ({ name: f.property_name, value: `${featureValue(f)}${f.unit ? ` ${f.unit}` : ""}` }));
  values.push(...(response.additional || []).filter(a => a.accepted && a.value != null)
    .map(a => ({ name: a.name, value: `${a.value}${a.unit ? ` ${a.unit}` : ""}` })));
  return values.filter((item, index) => values.findIndex(v => v.name === item.name && v.value === item.value) === index);
}

// Карточки и выгрузка используют одну проекцию: переключатель не запускает поиск заново.
export function projectCsvRows(rows, requireAll = true) {
  return rows.map(row => {
    const data = row.response;
    const missing = (data?.required_characteristics || []).filter(r => r.status !== "filled").map(r => r.name);
    const parameters = recognizedParameters(data);
    const base = { ...row, item: null, missing, parameters };
    if (!row.done) return { ...base, status: "pending", message: "Ожидает обработки" };
    if (row.error || data?.status === "error") return { ...base, status: "error", message: row.error || "Не удалось обработать строку." };
    const codes = [...new Set(data?.compatible_codes || [])];
    const candidate = codes.length === 1 && data?.candidates?.find(c => c.code === codes[0] && c.compatible && !c.is_template);
    if (!candidate || data.stale || data.preliminary || ["not_found", "conflict"].includes(data.status)
        || (data.recognition_mode === "semantic" && !data.scope?.confirmed_scope)) {
      return { ...base, missing: [], status: "unresolved", message: "КТРУ не может быть однозначно определен" };
    }
    if (requireAll && missing.length) return { ...base, status: "incomplete", message: "Не заполнены все обязательные параметры. Товар скрыт." };
    return { ...base, item: candidate, status: missing.length ? "warning" : "matched",
      message: missing.length ? "Найден только один КТРУ, но заполнены не все обязательные характеристики." : "КТРУ однозначно определен" };
  });
}

export function encodeCsv(headers, records) {
  const cell = value => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return "\uFEFF" + [headers, ...records].map(row => row.map(cell).join(";")).join("\r\n") + "\r\n";
}

export function exportCsv(headers, projectedRows) {
  return encodeCsv([...headers, "Результат: код КТРУ", "Результат: наименование КТРУ", "Результат: статус",
    "Результат: обязательные параметры заполнены", "Результат: недостающие параметры", "Результат: распознанные характеристики"],
  projectedRows.map(row => [...row.fields, row.item?.code || "", row.item?.name || "", row.message,
    row.status === "unresolved" ? "Не определено" : ["error", "pending"].includes(row.status) ? "Не проверено" : row.missing.length ? "Нет" : "Да", row.missing.join("; "),
    row.parameters.map(p => `${p.name}: ${p.value}`).join("\n")]));
}
