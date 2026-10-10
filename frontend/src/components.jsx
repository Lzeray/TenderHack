import React, { useEffect, useRef, useState } from "react";
import { featureValue, parseConstraint } from "./state.js";

export function Icon({ name, size = 20, ...props }) {
  const paths = {
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    arrow: <path d="m9 5 7 7-7 7" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    check: <path d="m5 12 4 4L19 6" />,
    alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3v.1" /></>,
    sparkle: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" /><path d="M21 2v4m-2-2h4" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    filter: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="8" cy="6" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="10" cy="18" r="2" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    box: <><path d="m12 3 9 5v8l-9 5-9-5V8l9-5Zm0 10v8M3 8l9 5 9-5M7.5 5.5l9 5" /></>,
    copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V3H3v13h5" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.box}</svg>;
}

export function categoryOf(item) {
  if (item.category) return item.category;
  const name = item.name.toLowerCase();
  if (/стул|стол|кресл|шкаф|диван|табурет|полк|мебел/.test(name)) return "furniture";
  if (/куртк|брюк|перчат|рубаш|костюм|футбол|одежд|жилет|халат|пальто/.test(name)) return "clothes";
  return "tools";
}

export function ProductArt({ category, name = "" }) {
  const shirt = category === "clothes";
  const furniture = category === "furniture";
  const table = /стол/i.test(name) && !/стул/i.test(name);
  return <div className={`product-art art-${category}`}>
    <span className="art-orbit" /><span className="art-dot" />
    <svg viewBox="0 0 240 180" role="img" aria-label="Иллюстрация категории товара">
      <ellipse cx="121" cy="155" rx="68" ry="9" fill="currentColor" opacity=".09" />
      {shirt ? <g stroke="#6171b8" strokeWidth="2.5" strokeLinejoin="round">
        <path d="m88 32-28 15-27 36 30 18 14-18v66h88V83l14 18 30-18-27-36-28-15c-8 21-28 21-37 0Z" fill="#e2e7ff" />
        <path d="M88 32c9 22 29 22 37 0m-5 23v94m-41-67 9-31m76 31-9-31" fill="none" />
        <path d="M88 109h21v22H88z" fill="#bac6ff" /><path d="M138 109h18v22h-18z" fill="#bac6ff" />
        <path d="M114 72h12m-12 16h12m-12 16h12" />
      </g> : furniture ? table ? <g stroke="#8a6b4e" strokeWidth="3" strokeLinejoin="round">
        <path d="m40 69 122-22 41 31-123 25Z" fill="#eed7be" /><path d="M40 69v11l40 32 123-25V78L80 103Z" fill="#d4b08b" />
        <path d="M53 90v58h9V97M177 94v51h9V92M87 111v45h9v-47" fill="#84766a" />
      </g> : <g stroke="#8a6b4e" strokeWidth="3" strokeLinejoin="round">
        <path d="M81 31h74a9 9 0 0 1 9 9v50H72V40a9 9 0 0 1 9-9Z" fill="#dbc4ad" />
        <path d="m71 91 91-1 17 26H56l15-25Z" fill="#ead8c6" />
        <path d="M65 116v39m104-39v39M81 117l-9 30m81-30 11 30" stroke="#6b7285" strokeWidth="8" />
        <path d="M73 83V42m91 40V42" fill="none" />
      </g> : <g transform="rotate(-29 120 90)" stroke="#52677f" strokeWidth="2.5" strokeLinejoin="round">
        <path d="M111 52h19v90a9 9 0 0 1-19 0V52Z" fill="#dfad67" />
        <path d="M82 31h67l17 15-17 17H82V31Z" fill="#9aadc3" /><path d="M82 31h16v32H82Z" fill="#c8d5e5" />
        <path d="M109 103h23v39a11 11 0 0 1-23 0v-39Z" fill="#3155e7" stroke="#2945b8" />
        <path d="m114 113 13 7m-13 6 13 7m-13 6 13 7" stroke="#8da4ff" />
      </g>}
    </svg>
  </div>;
}

export function SearchBox({ search }) {
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const root = useRef(null);
  useEffect(() => {
    setOptions([]);
    const q = search.text.trim().split(/\s+/)[0];
    if (!q || q.length < 2) { setOptions([]); return; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/catalog/types?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        if (!response.ok) return;
        const types = await response.json();
        setOptions(types.sort((a, b) => a.name.length - b.name.length || a.name.localeCompare(b.name, "ru")).slice(0, 6));
        setActive(-1);
      } catch { /* A suggestion failure must not prevent ordinary search. */ }
    }, 120);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [search.text]);
  const choose = name => { search.changeText(name); setOpen(false); };
  const expanded = open && options.length > 0;
  return <div className="search-area" ref={root} onBlur={event => { if (!root.current.contains(event.relatedTarget)) setOpen(false); }}>
    <form className={`search-box ${expanded ? "search-open" : ""}`} onSubmit={event => { event.preventDefault(); setOpen(false); search.submit(); }}>
      <Icon name="search" size={23} />
      <input id="desc" aria-label="Описание товара" role="combobox" aria-autocomplete="list" aria-expanded={expanded}
        aria-controls="search-suggestions" aria-activedescendant={expanded && active >= 0 ? `suggestion-${active}` : undefined}
        placeholder="Название товара, характеристики или описание" value={search.text} maxLength={2000}
        onFocus={() => setOpen(true)} onChange={event => { search.changeText(event.target.value); setOpen(true); }}
        onKeyDown={event => {
          if (event.key === "Escape") setOpen(false);
          if (expanded && ["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault(); setActive(previous => previous < 0 ? (event.key === "ArrowDown" ? 0 : options.length - 1)
              : (previous + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length);
          }
          if (event.key === "Enter" && expanded && active >= 0) { event.preventDefault(); choose(options[active].name); }
        }} />
      {search.text && <button className="icon-button clear-search" type="button" aria-label="Очистить поиск" onClick={() => search.changeText("")}><Icon name="close" size={18} /></button>}
      <button className="button search-submit" type="submit"><span>Найти</span><Icon name="search" size={19} /></button>
    </form>
    {expanded && <ul id="search-suggestions" className="suggestions" role="listbox" aria-label="Подсказки каталога">
      <li className="suggestions-label" role="presentation">Наименования из каталога КТРУ</li>
      {options.map((option, i) => <li key={option.ref} id={`suggestion-${i}`} role="option" aria-selected={active === i}>
        <button type="button" className={active === i ? "suggestion-active" : ""} onMouseDown={event => event.preventDefault()} onClick={() => choose(option.name)}>
          <Icon name="search" size={17} /><span>{option.name}</span><small>{option.positions} поз.</small><Icon name="arrow" size={15} />
        </button>
      </li>)}
    </ul>}
    <div className="search-caption"><Icon name="sparkle" size={15} /><span>Опишите своими словами — найдём характеристики и подходящий КТРУ</span>
      {(search.busy.fast || search.busy.model) && <span className="search-progress" role="status"><span className="spinner" />{search.busy.fast ? "Ищем товары" : "Уточняем описание"}</span>}
    </div>
  </div>;
}

export function Feedback({ search }) {
  const data = search.result;
  if (!data && !search.error) return null;
  const conflict = !search.stale && data?.status === "conflict";
  const issues = search.stale ? [] : (data?.issues || []);
  const providerFailure = !search.stale && data?.providers?.some(p => ["error", "timeout", "invalid"].includes(p.status));
  const messages = [...new Set(issues.map(i => i.message))];
  return <div className="feedback-stack" aria-live="polite">
    {search.error && <div className="notice notice-error"><Icon name="alert" /><div><strong>Не удалось завершить запрос</strong><p>{search.error}</p><button className="text-button" onClick={search.submit}>Повторить</button></div></div>}
    {conflict && <div className="notice notice-error" role="alert"><Icon name="alert" /><div><strong>В описании есть противоречие</strong><p>{data.message}</p><span className="notice-hint">Исправьте указанную характеристику — поиск обновится автоматически.</span></div></div>}
    {!search.stale && data?.corrections?.map(c => <div className="notice notice-subtle" key={c.original}><Icon name="sparkle" /><div>
      <strong>{c.corrected ? "Распознали опечатку" : "Уточните слово"}</strong>
      <p>{c.corrected ? <><s>{c.original}</s> <span className="correction-arrow">→</span> <b>{c.corrected}</b></> : `«${c.original}» может означать несколько слов.`}</p>
      {c.corrected ? <button className="text-button" onClick={() => {
        const pattern = c.original.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        search.changeText(search.text.replace(new RegExp(pattern, "gi"), c.corrected));
      }}>Исправить в поиске</button> : c.options.map(value => <button className="choice" key={value} onClick={() => search.correct(c.original, value)}>{value}</button>)}
    </div></div>)}
    {providerFailure && <div className="notice notice-subtle"><Icon name="alert" /><div><strong>Дополнительный разбор недоступен</strong><p>Быстрый поиск работает. Проверьте параметры или добавьте их вручную.</p></div></div>}
    {messages.length > 0 && <details className="issue-details"><summary>Проверка описания <span>{messages.length}</span></summary><ul>{messages.map(message => <li key={message}>{message}</li>)}</ul></details>}
    {!search.stale && data?.unrecognized?.length > 0 && <div className="notice notice-subtle"><Icon name="alert" /><p>Не удалось проверить: {data.unrecognized.join(", ")}. Добавьте эти свойства в параметры товара.</p></div>}
  </div>;
}

function FeatureEditor({ feature, search }) {
  const [value, setValue] = useState(featureValue(feature));
  const key = feature.characteristic_ref || feature.property_code || feature.property_name;
  useEffect(() => setValue(featureValue(feature)), [feature.value, feature.value_to, feature.op]);
  const normalized = search.result.query_profile?.attributes?.find(a => a.name === feature.property_name && a.raw_value === feature.value);
  const conversion = normalized && (normalized.value !== normalized.raw_value || normalized.unit !== normalized.raw_unit);
  const editable = ["bound", "proposed"].includes(feature.status) && feature.property_name;
  const save = () => { if (value.trim() && value !== featureValue(feature)) search.override(parseConstraint(key, value, feature.unit)); };
  return <div className="feature-row" data-feature-name={feature.property_name}>
    <div className="feature-label"><label htmlFor={`feature-${feature.id}`}>{feature.property_name || "Уточните характеристику"}</label>
      {feature.confirmation === "tentative" && <span className="mini-tag amber">Предложение модели</span>}
    </div>
    {feature.status === "ambiguous" && feature.options?.length > 0 && <select aria-label="Выбрать характеристику" defaultValue="" disabled={search.stale} onChange={event => {
      const option = feature.options[Number(event.target.value)];
      search.override({ property: option.property_code, value: option.value ?? feature.value, value_to: feature.value_to, op: feature.op, unit: feature.unit });
    }}><option value="" disabled>Выберите свойство</option>{feature.options.map((o, i) => <option key={i} value={i}>{o.property_name}</option>)}</select>}
    <div className="feature-control"><input id={`feature-${feature.id}`} value={value} disabled={!editable || search.stale}
      onChange={event => setValue(event.target.value)} onBlur={save} onKeyDown={event => {
        if (event.key === "Enter") event.target.blur();
        if (event.key === "Escape") setValue(featureValue(feature));
      }} /><span>{feature.unit}</span>
      {editable && <button className="icon-button" title="Убрать характеристику" aria-label={`Удалить ${feature.property_name}`} disabled={search.stale} onClick={() => search.override({ property: key, remove: true })}><Icon name="close" size={15} /></button>}
    </div>
    {conversion && <small className="converted"><Icon name="check" size={13} />{String(normalized.value).replace(".", ",")} {normalized.unit}</small>}
    {feature.evidence && <small className="feature-evidence">Из описания: «{feature.evidence}»</small>}
  </div>;
}

export function Parameters({ search }) {
  const data = search.result;
  // Обязательные характеристики КТРУ — в таблице внизу; здесь неоднозначные и необязательные.
  const ambiguous = (data?.features || []).filter(f => f.status === "ambiguous");
  const optional = data?.optional_characteristics || [];
  const empty = !ambiguous.length && !optional.length && !(data?.additional || []).length;
  return <aside className="parameters panel">
    <div className="panel-heading"><Icon name="filter" /><h2>Распознанные характеристики</h2></div>
    <p className="panel-caption">Названия и значения приведены к виду КТРУ. Обязательные характеристики — в таблице внизу.</p>
    {ambiguous.length > 0 && <div className="parameter-group"><h3>Нужно уточнить</h3>{ambiguous.map(f => <FeatureEditor key={`${f.id}-amb`} feature={f} search={search} />)}</div>}
    {optional.length > 0 && <div className="parameter-group"><h3>Необязательные характеристики КТРУ</h3>{optional.map(f => <FeatureEditor key={`${f.id}-${f.property_code}`} feature={f} search={search} />)}</div>}
    <Additional data={data} />
    {empty && <div className="parameter-empty"><Icon name="sparkle" size={28} /><p>Необязательные и дополнительные характеристики появятся здесь после поиска</p></div>}
    <div className="parameter-tip"><Icon name="alert" size={16} /><p>Неизвестное значение не считается подтверждённым. КТРУ проверяем по справочнику.</p></div>
  </aside>;
}

const SOURCE_LABELS = { ste: "Есть в выгрузках СТЕ", session: "Запомнена в сессии", new: "Новая, запомнена в сессии", rejected: "Не принята" };

export function Additional({ data, compact = false }) {
  const items = (data?.additional || []).filter(a => !compact || a.accepted);
  if (!items.length) return null;
  return <div className={`parameter-group additional ${compact ? "additional-compact" : ""}`}>
    <h3>Дополнительные характеристики <small>(нет в КТРУ, на код не влияют)</small></h3>
    {items.map((a, i) => <div className={`feature-row ${a.accepted ? "" : "feature-rejected"}`} key={`${a.name}-${i}`}>
      <div className="feature-label">{a.name}<span className={`mini-tag ${a.accepted ? (a.source === "ste" ? "green" : "blue") : "amber"}`}>{SOURCE_LABELS[a.source]}</span></div>
      {a.value && <b>{a.value} {a.unit || ""}</b>}
      {!compact && <small className="feature-evidence">{a.reason}</small>}
    </div>)}
  </div>;
}

function RequiredInput({ row, search }) {
  const [value, setValue] = useState(row.value || "");
  const [unit, setUnit] = useState(row.unit || row.units?.[0] || "");
  useEffect(() => { setValue(row.value || ""); setUnit(row.unit || row.units?.[0] || ""); }, [row.value, row.unit, row.property_code]);
  const listId = `req-values-${row.property_code}`;
  const save = () => {
    const text = value.trim();
    if (!text || text === (row.value || "")) return;
    // по названию: у позиций КТРУ одна характеристика бывает под разными кодами
    search.override(parseConstraint(row.name, text, row.numeric ? unit : null));
  };
  const options = row.values || [];
  return <div className="required-input">
    {options.length > 0 && options.length <= 12 && !row.numeric
      ? <select aria-label={row.name} value={value} disabled={search.stale} onChange={event => {
          setValue(event.target.value);
          if (event.target.value) search.override(parseConstraint(row.name, event.target.value, null));
        }}><option value="">Выберите значение</option>{options.map(v => <option key={v} value={v}>{v}</option>)}{value && !options.includes(value) && <option value={value}>{value}</option>}</select>
      : <><input aria-label={row.name} placeholder={row.numeric ? "Число" : "Значение"} list={listId} value={value} disabled={search.stale}
          onChange={event => setValue(event.target.value)} onBlur={save} onKeyDown={event => {
            if (event.key === "Enter") event.target.blur();
            if (event.key === "Escape") setValue(row.value || "");
          }} /><datalist id={listId}>{options.slice(0, 50).map(v => <option key={v} value={v} />)}</datalist>
        {row.numeric && (row.units?.length > 1
          ? <select aria-label="Единица измерения" value={unit} onChange={event => setUnit(event.target.value)}>{row.units.map(u => <option key={u}>{u}</option>)}</select>
          : <span className="required-unit">{unit}</span>)}</>}
    {row.status !== "missing" && <button className="icon-button" title="Очистить" aria-label={`Очистить ${row.name}`} disabled={search.stale}
      onClick={() => search.override({ property: row.name, remove: true })}><Icon name="close" size={15} /></button>}
  </div>;
}

const SOURCE_TAGS = { ste: ["Доп. · есть в СТЕ", "green"], session: ["Доп. · из сессии", "blue"], new: ["Доп. · новая", "blue"], rejected: ["Не характеристика", "amber"] };

function FeatureValueInput({ feature, search }) {
  const [value, setValue] = useState(featureValue(feature));
  useEffect(() => setValue(featureValue(feature)), [feature.value, feature.value_to, feature.op]);
  const key = feature.property_name || feature.characteristic_ref || feature.property_code;
  const save = () => { if (value.trim() && value !== featureValue(feature)) search.override(parseConstraint(key, value, feature.unit)); };
  return <div className="required-input">
    <input aria-label={feature.property_name} value={value} disabled={search.stale} onChange={event => setValue(event.target.value)} onBlur={save}
      onKeyDown={event => { if (event.key === "Enter") event.target.blur(); if (event.key === "Escape") setValue(featureValue(feature)); }} />
    {feature.unit && <span className="required-unit">{feature.unit}</span>}
    <button className="icon-button" title="Убрать" aria-label={`Убрать ${feature.property_name}`} disabled={search.stale}
      onClick={() => search.override({ property: key, remove: true })}><Icon name="close" size={15} /></button>
  </div>;
}

function CharRow({ name, tag, tagClass, hint, evidence, children }) {
  return <div className="char-row">
    <div className="char-name"><b>{name}</b>{tag && <span className={`mini-tag ${tagClass}`}>{tag}</span>}
      {evidence && <small>Из описания: «{evidence}»</small>}{hint && <small className="char-hint">{hint}</small>}</div>
    <div className="char-value">{children}</div>
  </div>;
}

export function CharacteristicsPanel({ search }) {
  const data = search.result;
  const [showAll, setShowAll] = useState(false);
  useEffect(() => setShowAll(false), [data?.query?.original]);
  if (!data || data.status === "not_found") return null;
  const rows = data.required_characteristics || [];
  const features = data.features || [];
  const byId = Object.fromEntries(features.map(f => [f.id, f]));
  const filledRequired = rows.filter(r => r.status !== "missing");
  const requiredIds = new Set(filledRequired.map(r => r.feature_id));
  const optional = data.optional_characteristics || [];
  const optionalIds = new Set(optional.map(f => f.id));
  // распознанные признаки, не попавшие ни в обязательные, ни в необязательные (например, при противоречии)
  const otherBound = features.filter(f => ["bound", "proposed"].includes(f.status) && f.property_name && !requiredIds.has(f.id) && !optionalIds.has(f.id));
  const ambiguous = features.filter(f => f.status === "ambiguous");
  const extra = data.additional || [];
  const missing = rows.filter(r => r.status === "missing");
  const commonMissing = missing.filter(r => r.common);
  const partialMissing = missing.filter(r => !r.common);
  const partialShown = showAll ? partialMissing : partialMissing.filter(r => r.narrows).slice(0, commonMissing.length ? 4 : 8);
  const entered = filledRequired.length + optional.length + otherBound.length + ambiguous.length + extra.length;
  const statusTag = { filled: ["Обязательная · проверена", "green"], invalid: ["Обязательная · не подходит", "amber"], unchecked: ["Обязательная · не проверена", "amber"] };
  return <section className={`chars-panel panel ${search.stale ? "chars-stale" : ""}`} aria-label="Характеристики товара">
    <div className="chars-column">
      <div className="panel-heading"><Icon name="check" /><h2>Введённые характеристики <span className="chars-count">{entered}</span></h2></div>
      <p className="panel-caption">Приведены к виду КТРУ. Значение можно исправить.</p>
      {entered === 0 && <p className="chars-empty">Пока не распознано ни одной характеристики. Добавьте их в описание или заполните справа.</p>}
      {filledRequired.map(r => <CharRow key={`r-${r.property_code}`} name={r.name} tag={statusTag[r.status][0]} tagClass={statusTag[r.status][1]}
        evidence={byId[r.feature_id]?.evidence} hint={r.status !== "filled" ? r.reason : null}><RequiredInput row={r} search={search} /></CharRow>)}
      {[...optional, ...otherBound].map(f => <CharRow key={`o-${f.id}`} name={f.property_name} tag={optionalIds.has(f.id) ? "Необязательная" : "КТРУ"} tagClass="blue"
        evidence={f.evidence}><FeatureValueInput feature={f} search={search} /></CharRow>)}
      {ambiguous.map(f => <CharRow key={`a-${f.id}`} name={`«${f.evidence || f.value}»`} tag="Уточните свойство" tagClass="amber" hint={f.note}>
        <select className="char-select" defaultValue="" disabled={search.stale} onChange={event => {
          const option = f.options[Number(event.target.value)];
          search.override({ property: option.property_code, value: option.value ?? f.value, value_to: f.value_to, op: f.op, unit: f.unit });
        }}><option value="" disabled>К какому свойству относится?</option>{f.options.map((o, i) => <option key={i} value={i}>{o.property_name}{o.value ? ` = ${o.value}` : ""}</option>)}</select>
      </CharRow>)}
      {extra.map((a, i) => <CharRow key={`e-${i}`} name={a.name} tag={SOURCE_TAGS[a.source][0]} tagClass={SOURCE_TAGS[a.source][1]} hint={a.reason}>
        <b className="char-static">{a.value} {a.unit || ""}</b>
      </CharRow>)}
    </div>
    <div className="chars-column">
      <div className="panel-heading"><Icon name="filter" /><h2>Осталось ввести <span className="chars-count">{missing.length}</span></h2></div>
      <p className="panel-caption">{missing.length ? "Обязательные характеристики КТРУ оставшихся позиций. Сначала общие для всех." : rows.length ? "Все обязательные характеристики КТРУ указаны." : "Обязательные характеристики появятся, когда будет понятен товар."}</p>
      {commonMissing.map(r => <CharRow key={`m-${r.property_code}`} name={r.name} tag={r.narrows ? "Сузит выбор" : "Общая"} tagClass="blue"
        hint={r.positions < r.total ? `обязательна у ${r.positions} из ${r.total}` : null}><RequiredInput row={r} search={search} /></CharRow>)}
      {partialShown.length > 0 && <h3 className="chars-subtitle">Есть только у части позиций</h3>}
      {partialShown.map(r => <CharRow key={`p-${r.property_code}`} name={r.name} tag={r.narrows ? "Сузит выбор" : null} tagClass="blue"
        hint={`обязательна у ${r.positions} из ${r.total} позиций`}><RequiredInput row={r} search={search} /></CharRow>)}
      {partialMissing.length > partialShown.length && <button className="text-button" onClick={() => setShowAll(true)}>Показать все ({partialMissing.length})</button>}
    </div>
  </section>;
}

export function Question({ search }) {
  const question = search.result?.question;
  const [number, setNumber] = useState("");
  if (!question || search.result.status === "matched" || search.result.status === "conflict") return null;
  return <section className="question-panel panel" id="question">
    <div className="question-symbol"><Icon name="sparkle" size={22} /></div><div className="question-content">
      <span className="eyebrow">Поможем сузить поиск</span><h3>{question.text}</h3>
      {question.reason && <p className="question-reason">{question.reason}</p>}
      <fieldset disabled={search.stale}><div className="question-choices">{question.options.map((option, i) => <button className="choice" key={i} onClick={() => search.answer(option)}>{option.label}<Icon name="arrow" size={14} /></button>)}</div>
        {question.allows_number && <form className="numeric-answer" onSubmit={event => { event.preventDefault(); if (!number.trim()) return;
          search.override(parseConstraint(question.property_code, number, question.unit)); setNumber("");
        }}><input aria-label="Ответ на уточняющий вопрос" placeholder="Укажите значение" value={number} onChange={event => setNumber(event.target.value)} required /><span>{question.unit}</span><button className="button button-soft">Применить</button></form>}
      </fieldset>
    </div>
  </section>;
}

export function ProductCard({ item, kind, onDetails }) {
  const category = categoryOf(item);
  const description = kind === "ste" ? (item.characteristics || "").split("|").map(s => s.trim())
    .filter(s => s && !/упаков|штрихкод|не задано|неизвест/i.test(s)).slice(0, 3)
    : item.checks.filter(c => c.user_value).slice(0, 3).map(c => `${c.property_name}: ${c.user_value}`);
  const clean = value => value && !["-", "неизвестно", "неизвестен"].includes(value.toLowerCase());
  return <article className="product-card" data-product-id={kind === "ste" ? item.id : undefined} data-catalog-code={kind === "ktru" ? item.code : undefined}>
    <div className="card-visual"><ProductArt category={category} name={item.name} /><span className={`card-source source-${kind}`}>{kind === "ktru" ? "КТРУ" : "СТЕ"}</span></div>
    <div className="card-content"><div className="card-category">{{ furniture: "Мебель", clothes: "Одежда", tools: "Инструменты" }[category]}</div>
      <button className="card-name" onClick={() => onDetails({ item, kind })}>{item.name}</button>
      <div className="card-description">{description.length ? description.map((line, i) => <p key={i}>{line}</p>) : <p>{kind === "ktru" ? "Нормативная позиция каталога. Откройте карточку, чтобы проверить характеристики." : "Товар из предоставленной выгрузки. Подробнее — в карточке."}</p>}</div>
      <div className="card-bottom"><span>{kind === "ktru" ? `${item.checks.filter(c => c.status === "valid").length} условий проверено` : clean(item.manufacturer) ? item.manufacturer : clean(item.country) ? item.country : "Из выгрузки товаров"}</span>
        <button className="card-details" onClick={() => onDetails({ item, kind })} aria-label={`Подробнее: ${item.name}`}><Icon name="arrow" size={17} /></button>
      </div>
    </div>
  </article>;
}

export function ProductDialog({ selected, onClose, onUse }) {
  const dialog = useRef(null);
  const [details, setDetails] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!selected) return;
    dialog.current.showModal(); setDetails(null); setError("");
    const controller = new AbortController();
    if (selected.kind === "ktru") fetch(`/api/positions/${encodeURIComponent(selected.item.code)}`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); }).then(setDetails)
      .catch(failure => { if (failure.name !== "AbortError") setError("Полную карточку загрузить не удалось. Проверки подбора доступны ниже."); });
    return () => { controller.abort(); dialog.current?.close(); };
  }, [selected]);
  if (!selected) return null;
  const { item, kind } = selected;
  const labels = { valid: "Соответствует", invalid: "Противоречит", unknown: "Не проверено" };
  return <dialog ref={dialog} className="product-dialog" onCancel={onClose} onClick={event => { if (event.target === dialog.current) onClose(); }} aria-labelledby="dialog-title">
    <div className="dialog-body"><button className="icon-button dialog-close" aria-label="Закрыть карточку" onClick={onClose}><Icon name="close" /></button>
      <div className="dialog-top"><ProductArt category={categoryOf(item)} name={item.name} /><div><span className={`mini-tag ${kind === "ktru" ? "blue" : "green"}`}>{kind === "ktru" ? "Позиция каталога КТРУ" : "Товар СТЕ из выгрузки"}</span>
        <h2 id="dialog-title">{item.name}</h2>{kind === "ktru" ? <p className="dialog-code">Код КТРУ: {item.code}</p> : <p className="dialog-code">СТЕ № {item.ste_id || item.id}</p>}
        <button className="button button-soft" onClick={() => { onUse(item.name); onClose(); }}>Использовать название в поиске<Icon name="arrow" size={16} /></button>
      </div></div>
      {error && <p className="inline-warning">{error}</p>}
      {kind === "ste" ? <><div className="dialog-metadata">{[["Производитель", item.manufacturer], ["Модель", item.model], ["Страна", item.country]].filter(([, v]) => v && v !== "-").map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}</div>
        <h3>Характеристики из выгрузки</h3><ul className="raw-characteristics">{(item.characteristics || "Характеристики не указаны").split("|").filter(s => s.trim()).map((s, i) => <li key={i}>{s.trim()}</li>)}</ul>
        <p className="source-note">Это фактическая запись из выгрузки. Связь товара с конкретным кодом КТРУ не подтверждена.</p>
      </> : <><h3>Результат проверки описания</h3><ul className="check-list">{item.checks.map((check, i) => <li key={i}><span className={`check-state check-${check.status}`}>{labels[check.status]}</span><div><b>{check.property_name}{check.user_value ? `: ${check.user_value}` : ""}</b><p>{check.reason}</p></div></li>)}</ul>
        {details && <><h3>Характеристики позиции КТРУ</h3><dl className="catalog-characteristics">{details.characteristics.map((c, i) => <div key={i}><dt>{c.name}{c.required && <span className="required-dot" title="Обязательная характеристика"> *</span>}</dt><dd>{c.values.join("; ") || "Допустимые значения не заданы"}</dd></div>)}</dl></>}
      </>}
    </div>
  </dialog>;
}
