import React, { useEffect, useId, useRef, useState } from "react";
import { Icon, ProductCard } from "./components.jsx";
import { decodeCsv, exportCsv, importCsv, projectCsvRows } from "./csv.js";
import { newSession } from "./state.js";

export default function CsvBatch({ active, onActiveChange, onDetails }) {
  const input = useRef(null);
  const controller = useRef(null);
  const filterId = useId();
  const [filename, setFilename] = useState("");
  const [headers, setHeaders] = useState([]);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [requireAll, setRequireAll] = useState(true);
  useEffect(() => () => controller.current?.abort(), []);

  const projected = projectCsvRows(rows, requireAll);
  const processed = rows.filter(row => row.done).length;
  const found = projected.filter(row => row.item).length;
  const unresolved = projected.filter(row => row.status === "unresolved").length;
  const incomplete = projected.filter(row => row.status === "incomplete").length;

  async function upload(file) {
    if (!file) return;
    controller.current?.abort();
    const run = new AbortController();
    controller.current = run;
    onActiveChange(true);
    setFilename(file.name); setError(""); setRows([]); setHeaders([]); setBusy(true);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (run.signal.aborted) return;
      const parsed = importCsv(decodeCsv(bytes));
      setHeaders(parsed.headers); setRows(parsed.rows);
      // По одной строке: ядро и локальная модель не перегружаются параллельным CSV-потоком.
      for (const row of parsed.rows) {
        if (run.signal.aborted) return;
        let result = { ...row, done: true };
        if (!row.error) {
          try {
            const session = newSession();
            const response = await fetch("/api/search", {
              method: "POST", headers: { "Content-Type": "application/json" }, signal: run.signal,
              body: JSON.stringify({ text: row.query, canonical: { items: [] }, stage: "submitted",
                session_id: session.sessionId, revision: 1 }),
            });
            if (!response.ok) throw new Error("Не удалось обработать строку. Попробуйте загрузить файл ещё раз.");
            const data = await response.json();
            if (data.stale) throw new Error("Ответ поиска устарел. Загрузите файл ещё раз.");
            result = { ...result, response: data };
          } catch (failure) {
            if (run.signal.aborted) return;
            result = { ...result, error: failure.message };
          }
        }
        if (run.signal.aborted) return;
        setRows(previous => previous.map(value => value.id === row.id ? result : value));
      }
    } catch (failure) {
      if (!run.signal.aborted) setError(failure.message);
    } finally {
      if (controller.current === run && !run.signal.aborted) setBusy(false);
    }
  }

  function download() {
    const blob = new Blob([exportCsv(headers, projected)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filename.replace(/\.csv$/i, "") || "результат"}-КТРУ-${requireAll ? "полные" : "с-предупреждениями"}.csv`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className={`csv-section ${active ? "csv-active" : ""}`} aria-label="Поиск товаров по CSV">
    <div className="csv-toolbar">
      <input ref={input} type="file" accept=".csv,text/csv" hidden aria-label="Файл CSV" onChange={event => {
        const file = event.target.files?.[0]; event.target.value = ""; upload(file);
      }} />
      <button className="button button-soft" onClick={() => input.current.click()}><Icon name="plus" size={17} />Добавить CSV</button>
      {!active && rows.length > 0 && <button className="button button-soft" onClick={() => onActiveChange(true)}>Результаты CSV ({processed}/{rows.length})</button>}
      {active && <button className="csv-back" onClick={() => onActiveChange(false)}>К обычному поиску<Icon name="arrow" size={15} /></button>}
      {!active && <small>Колонка «Описание» или «Наименование»; остальные колонки — параметры товара.</small>}
    </div>
    {active && <div className="csv-results catalog-main">
      <div className="csv-heading"><div><h2>Товары из CSV</h2><p className="csv-filename">{filename}</p></div>
        <button className="button button-soft" disabled={busy || !rows.length} onClick={download}><Icon name="copy" size={17} />Выгрузить CSV</button>
      </div>
      <fieldset className="csv-required-filter"><legend>Обязательные параметры</legend>
        <label className={!requireAll ? "is-selected" : ""}><input type="radio" name={filterId} checked={!requireAll} onChange={() => setRequireAll(false)} />Показывать с предупреждением</label>
        <label className={requireAll ? "is-selected" : ""}><input type="radio" name={filterId} checked={requireAll} onChange={() => setRequireAll(true)} />Только полностью заполненные</label>
      </fieldset>
      <p className="csv-filter-hint">{requireAll
        ? "Товар и код показываются только при заполнении всех обязательных параметров. Остальные строки сохраняются в отчёте без кода КТРУ."
        : "Если найден один КТРУ, товар и код показываются даже с недостающими обязательными параметрами — с предупреждением."}</p>
      {error && <div className="notice notice-error" role="alert"><Icon name="alert" /><p>{error}</p></div>}
      {rows.length > 0 && <>
        <div className="csv-progress" role="status"><span>{busy ? "Обработка" : "Обработано"}: {processed} из {rows.length}</span>
          <span>Товаров: {found} · Неопределённых КТРУ: {unresolved}{incomplete > 0 && ` · Без обязательных параметров: ${incomplete}`}</span>
        </div>
        {busy && <progress className="csv-progress-bar" value={processed} max={rows.length} aria-label="Обработка строк CSV" />}
        <div className="product-grid csv-grid">{projected.map(row => <div className="csv-row" data-csv-row={row.rowNumber} data-csv-status={row.status} key={row.id}>
          {row.item ? <ProductCard item={row.item} kind="ktru" onDetails={onDetails}>
            <CsvRowContent row={row} />
          </ProductCard> : <article className={`csv-placeholder csv-${row.status}`}><CsvRowContent row={row} /></article>}
        </div>)}</div>
      </>}
    </div>}
  </section>;
}

function CsvRowContent({ row }) {
  return <div className="csv-row-content"><span className="csv-row-number">Строка {row.rowNumber}</span>
    <p className="csv-source-query">{row.query || "Описание не указано"}</p>
    {!row.item && <p className="csv-row-message">{row.message}</p>}
    {row.status === "warning" && <div className="notice notice-subtle csv-incomplete-note"><Icon name="filter" size={16} /><p>{row.message}</p></div>}
    {row.missing.length > 0 && <p className="csv-missing">Не заполнены: {row.missing.join(", ")}.</p>}
    {row.parameters.length > 0 && <details className="csv-parameters"><summary>Распознанные характеристики · {row.parameters.length}</summary>
      <dl>{row.parameters.map((p, i) => <div key={i}><dt>{p.name}</dt><dd>{p.value}</dd></div>)}</dl>
    </details>}
  </div>;
}
