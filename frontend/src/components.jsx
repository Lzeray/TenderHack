import React, { useEffect, useId, useRef, useState } from "react";
import { featureValue, parseConstraint, phraseFor } from "./state.js";

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
      {shirt ? <g stroke="#b86165" strokeWidth="2.5" strokeLinejoin="round">
        <path d="m88 32-28 15-27 36 30 18 14-18v66h88V83l14 18 30-18-27-36-28-15c-8 21-28 21-37 0Z" fill="#fcebec" />
        <path d="M88 32c9 22 29 22 37 0m-5 23v94m-41-67 9-31m76 31-9-31" fill="none" />
        <path d="M88 109h21v22H88z" fill="#ffbabd" /><path d="M138 109h18v22h-18z" fill="#ffbabd" />
        <path d="M114 72h12m-12 16h12m-12 16h12" />
      </g> : furniture ? table ? <g stroke="#8a6b4e" strokeWidth="3" strokeLinejoin="round">
        <path d="m40 69 122-22 41 31-123 25Z" fill="#eed7be" /><path d="M40 69v11l40 32 123-25V78L80 103Z" fill="#d4b08b" />
        <path d="M53 90v58h9V97M177 94v51h9V92M87 111v45h9v-47" fill="#84766a" />
      </g> : <g stroke="#8a6b4e" strokeWidth="3" strokeLinejoin="round">
        <path d="M81 31h74a9 9 0 0 1 9 9v50H72V40a9 9 0 0 1 9-9Z" fill="#dbc4ad" />
        <path d="m71 91 91-1 17 26H56l15-25Z" fill="#ead8c6" />
        <path d="M65 116v39m104-39v39M81 117l-9 30m81-30 11 30" stroke="#6b7285" strokeWidth="8" />
        <path d="M73 83V42m91 40V42" fill="none" />
      </g> : <g transform="rotate(-29 120 90)" stroke="#6d6464" strokeWidth="2.5" strokeLinejoin="round">
        <path d="M111 52h19v90a9 9 0 0 1-19 0V52Z" fill="#dfad67" />
        <path d="M82 31h67l17 15-17 17H82V31Z" fill="#b2abab" /><path d="M82 31h16v32H82Z" fill="#e5c8c9" />
        <path d="M109 103h23v39a11 11 0 0 1-23 0v-39Z" fill="#e7313a" stroke="#b82930" />
        <path d="m114 113 13 7m-13 6 13 7m-13 6 13 7" stroke="#ff8d93" />
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
    {(search.busy.fast || search.busy.model) && <div className="search-caption">
      <span className="search-progress" role="status"><span className="spinner" />{search.busy.fast ? "Ищем товары" : "Уточняем описание"}</span>
    </div>}
  </div>;
}

export function Feedback({ search }) {
  const data = search.result;
  if (!data && !search.error) return null;
  const conflict = !search.stale && data?.status === "conflict";
  const issues = search.stale ? [] : (data?.issues || []);
  const providerFailure = !search.stale && data?.providers?.some(p => ["error", "timeout", "invalid"].includes(p.status));
  const messages = [...new Set(issues.map(i => i.message))];
  const corrections = search.stale ? [] : data?.corrections || [];
  const unrecognized = search.stale ? [] : data?.unrecognized || [];
  const detailCount = corrections.length + messages.length + Number(!!providerFailure) + Number(unrecognized.length > 0);
  return <div className="feedback-stack" aria-live="polite">
    {search.error && <div className="notice notice-error"><Icon name="alert" /><div><strong>Не удалось завершить запрос</strong><p>{search.error}</p><button className="text-button" onClick={search.submit}>Повторить</button></div></div>}
    {conflict && <div className="notice notice-error" role="alert"><Icon name="alert" /><div><strong>В описании есть противоречие</strong><p>{data.message}</p><span className="notice-hint">Исправьте указанную характеристику — поиск обновится автоматически.</span></div></div>}
    {detailCount > 0 && <details className="feedback-details"><summary><Icon name="alert" size={16} />Замечания к запросу<span className="chars-count">{detailCount}</span></summary><div className="feedback-details-body">
    {corrections.map(c => <div className="notice notice-subtle" key={c.original}><Icon name="sparkle" /><div>
      <strong>{c.corrected ? "Распознали опечатку" : "Уточните слово"}</strong>
      <p>{c.corrected ? <><s>{c.original}</s> <span className="correction-arrow">→</span> <b>{c.corrected}</b></> : `«${c.original}» может означать несколько слов.`}</p>
      {c.corrected ? <button className="text-button" onClick={() => {
        const pattern = c.original.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        search.changeText(search.text.replace(new RegExp(pattern, "gi"), c.corrected));
      }}>Исправить в поиске</button> : c.options.map(value => <button className="choice" key={value} onClick={() => search.correct(c.original, value)}>{value}</button>)}
    </div></div>)}
    {providerFailure && <div className="notice notice-subtle"><Icon name="alert" /><div><strong>Дополнительный разбор недоступен</strong><p>Быстрый поиск работает. Проверьте параметры или добавьте их вручную.</p></div></div>}
    {messages.length > 0 && <ul className="feedback-messages">{messages.map(message => <li key={message}>{message}</li>)}</ul>}
    {unrecognized.length > 0 && <div className="notice notice-subtle"><Icon name="alert" /><p>Не удалось проверить: {unrecognized.join(", ")}. Добавьте эти свойства в параметры товара.</p></div>}
    </div></details>}
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

// Ввод значения: результат записывается в строку поиска (и дублируется ручным условием).
function applyValue(search, { name, fragment, constraint }) {
  search.putInText({ name, fragment, phrase: phraseFor(name, constraint) });
}
function removeValue(search, { name, fragment, value }) {
  search.putInText({ name, fragment, phrase: "", value });
}

function ValueInput({ name, values = [], numeric = false, units = [], initial = "", initialUnit = "", fragment = null, removable = false, search }) {
  // initial — текущее значение: им же ищется фрагмент строки при удалении, если сервер фрагмент не вернул
  const [value, setValue] = useState(initial);
  const [unit, setUnit] = useState(initialUnit || units[0] || "");
  useEffect(() => { setValue(initial); setUnit(initialUnit || units[0] || ""); }, [initial, initialUnit, name]);
  const commit = text => {
    const v = (text ?? value).trim();
    if (!v || v === initial) return;
    applyValue(search, { name, fragment, constraint: parseConstraint(name, v, numeric ? unit : null) });
  };
  const listId = useId();
  const select = values.length > 0 && values.length <= 12 && !numeric;
  return <div className="value-input">
    {select
      ? <select aria-label={name} value={value} disabled={search.stale} onChange={event => { setValue(event.target.value); if (event.target.value) commit(event.target.value); }}>
          <option value="">Выберите значение</option>{values.map(v => <option key={v} value={v}>{v}</option>)}
          {value && !values.includes(value) && <option value={value}>{value}</option>}
        </select>
      : <><input aria-label={name} placeholder={numeric ? "Число" : "Значение"} list={listId} value={value} disabled={search.stale}
          onChange={event => setValue(event.target.value)} onBlur={() => commit()}
          onKeyDown={event => { if (event.key === "Enter") event.target.blur(); if (event.key === "Escape") setValue(initial); }} />
        <datalist id={listId}>{values.slice(0, 50).map(v => <option key={v} value={v} />)}</datalist>
        {numeric && (units.length > 1
          ? <select className="unit-select" aria-label="Единица измерения" value={unit} onChange={event => setUnit(event.target.value)}>{units.map(u => <option key={u}>{u}</option>)}</select>
          : unit && <span className="value-unit">{unit}</span>)}</>}
    {removable && <button className="icon-button" title="Убрать" aria-label={`Убрать ${name}`} disabled={search.stale}
      onClick={() => removeValue(search, { name, fragment, value: initial })}><Icon name="close" size={14} /></button>}
  </div>;
}

function CharItem({ name, tag, tagClass, hint, evidence, children, kind = "" }) {
  return <li className={`char-item ${kind ? `char-${kind}` : ""}`}>
    <div className="char-head"><b>{name}</b>{tag && <span className={`mini-tag ${tagClass}`}>{tag}</span>}</div>
    {children}
    {hint && <small className="char-note">{hint}</small>}
    {evidence && <details className="char-evidence"><summary>Из описания</summary><small>«{evidence}»</small></details>}
  </li>;
}

const SOURCE_TAGS = { ste: ["Доп. · есть в СТЕ", "green"], session: ["Доп. · из сессии", "blue"], new: ["Доп. · новая", "blue"], rejected: ["Не характеристика", "amber"] };
const STATUS_TAGS = { filled: ["Обязательная", "green"], invalid: ["Не подходит", "amber"], unchecked: ["Не проверена", "amber"] };

function SidePanel({ icon, title, count, empty, children, className = "", collapsible = false }) {
  const Container = collapsible ? "details" : "section";
  const Heading = collapsible ? "summary" : "div";
  return <Container className={`side-panel panel ${className}`}>
    <Heading className="side-panel-head"><Icon name={icon} size={18} /><h2>{title}</h2><span className="chars-count">{count}</span>{collapsible && <Icon name="arrow" size={15} />}</Heading>
    <div className="side-panel-body">{count ? <ul className="char-list">{children}</ul> : <p className="chars-empty">{empty}</p>}</div>
  </Container>;
}

// фрагмент описания, где задано свойство: правка заменяет его на месте, а не дописывает второй раз
function fragmentFor(name, features, feature) {
  if (feature?.evidence) return feature.evidence;
  return features.find(x => x.property_name === name && x.source === "text" && x.evidence)?.evidence || null;
}

export function SelectedChars({ search }) {
  const data = search.result;
  if (!data) return null;
  const rows = (data.required_characteristics || []).filter(r => r.status !== "missing");
  const features = data.features || [];
  const byId = Object.fromEntries(features.map(f => [f.id, f]));
  const requiredIds = new Set(rows.map(r => r.feature_id));
  const optional = data.optional_characteristics || [];
  const optionalIds = new Set(optional.map(f => f.id));
  const other = features.filter(f => ["bound", "proposed"].includes(f.status) && f.property_name && !requiredIds.has(f.id) && !optionalIds.has(f.id));
  const ambiguous = features.filter(f => f.status === "ambiguous");
  const extra = data.additional || [];
  // «Вид товара: Стол» из слова типа — это сам товар, а не характеристика: показывается без удаления
  const typeWord = features.filter(f => f.status === "bound" && f.from_type_name && !requiredIds.has(f.id));
  const optionalShown = [...optional, ...other].filter(f => !f.from_type_name);
  const total = rows.length + optionalShown.length + typeWord.length + ambiguous.length + extra.length;
  if (!total) return null;
  return <SidePanel icon="check" title="Выбранные характеристики" count={total} className="side-selected" collapsible
    empty="Пока ничего не распознано. Опишите товар подробнее или заполните характеристики ниже.">
    {rows.length > 0 && <li className="char-group char-group-required">Обязательные характеристики КТРУ</li>}
    {rows.map(r => { const f = byId[r.feature_id]; const fixed = f?.from_type_name; return <CharItem key={`r-${r.property_code}`} name={r.name} tag={STATUS_TAGS[r.status][0]} tagClass={STATUS_TAGS[r.status][1]}
      evidence={f?.evidence} hint={fixed ? "задано наименованием товара" : r.status !== "filled" ? r.reason : null} kind="required">
      {fixed ? <b className="char-static">{r.value}</b>
        : <ValueInput search={search} name={r.name} values={r.values} numeric={r.numeric} units={r.units} initial={r.value || ""} initialUnit={r.unit || ""} fragment={fragmentFor(r.name, features, f)} removable />}
    </CharItem>; })}
    {optionalShown.length > 0 && <li className="char-group char-group-optional">Необязательные характеристики КТРУ</li>}
    {optionalShown.map(f => <CharItem key={`o-${f.id}`} name={f.property_name} tag={optionalIds.has(f.id) ? "Необязательная" : "КТРУ"} tagClass="blue" evidence={f.evidence} kind="optional">
      <ValueInput search={search} name={f.property_name} initial={featureValue(f)} initialUnit={f.unit || ""} numeric={!!f.unit} units={f.unit ? [f.unit] : []} fragment={fragmentFor(f.property_name, features, f)} removable />
    </CharItem>)}
    {typeWord.map(f => <CharItem key={`t-${f.id}`} name={f.property_name} tag="Тип товара" tagClass="blue" hint="задано наименованием товара" kind="optional">
      <b className="char-static">{f.value}</b>
    </CharItem>)}
    {ambiguous.length > 0 && <li className="char-group char-group-ambiguous">Уточните, к чему относится</li>}
    {ambiguous.map(f => <CharItem key={`a-${f.id}`} name={`«${f.evidence || f.value}»`} tag="Уточните свойство" tagClass="amber" kind="ambiguous">
      <select className="value-select" defaultValue="" disabled={search.stale} onChange={event => {
        const option = f.options[Number(event.target.value)];
        search.override({ property: option.property_code, value: option.value ?? f.value, value_to: f.value_to, op: f.op, unit: f.unit });
      }}><option value="" disabled>К какому свойству относится?</option>{f.options.map((o, i) => <option key={i} value={i}>{o.property_name}{o.value ? ` = ${o.value}` : ""}</option>)}</select>
    </CharItem>)}
    {extra.length > 0 && <li className="char-group char-group-extra">Дополнительные (нет в КТРУ, на код не влияют)</li>}
    {extra.map((a, i) => <CharItem key={`e-${i}`} name={a.name} tag={SOURCE_TAGS[a.source][0]} tagClass={SOURCE_TAGS[a.source][1]} hint={a.reason} kind="extra">
      <b className="char-static">{a.value} {a.unit || ""}</b>
    </CharItem>)}
  </SidePanel>;
}

export function MissingChars({ search }) {
  const data = search.result;
  if (!data) return null;
  const missing = (data.required_characteristics || []).filter(r => r.status === "missing");
  const common = missing.filter(r => r.common);
  const partial = missing.filter(r => !r.common);
  const empty = (data.required_characteristics || []).length ? "Все обязательные характеристики КТРУ указаны." : "Появятся, когда станет понятен товар.";
  return <SidePanel icon="filter" title="Осталось заполнить (обязательные)" count={missing.length} className="side-missing" empty={empty}>
    {common.length > 0 && partial.length > 0 && <li className="char-group">Общие для всех позиций</li>}
    {common.map(r => <CharItem key={`m-${r.property_code}`} name={r.name}>
      <ValueInput search={search} name={r.name} values={r.values} numeric={r.numeric} units={r.units} />
    </CharItem>)}
    {partial.length > 0 && <li className="char-group">Есть только у части позиций</li>}
    {partial.map(r => <CharItem key={`p-${r.property_code}`} name={r.name} hint={`обязательна у ${r.positions} из ${r.total}`}>
      <ValueInput search={search} name={r.name} values={r.values} numeric={r.numeric} units={r.units} />
    </CharItem>)}
  </SidePanel>;
}

export function Question({ search }) {
  const question = search.result?.question;
  const [number, setNumber] = useState("");
  // после ответа уточнение сразу скрывается: до нового ответа сервера показывать нечего
  if (!question || search.stale || search.busy.fast || search.result.status === "matched" || search.result.status === "conflict") return null;
  const choose = option => {
    const answers = option.answers?.length ? option.answers : option.answer ? [option.answer] : [];
    const property = answers.length === 1 && question.kind === "property" && question.property_name && answers[0].property !== "__type__";
    if (property && !option.reject?.length && !option.confirm?.length) applyValue(search, { name: question.property_name, constraint: { ...answers[0], property: question.property_name } });
    else search.answer(option);
  };
  return <details className="question-panel panel" id="question">
    <summary className="question-head"><Icon name="sparkle" size={17} /><span><b>Уточнить поиск</b><small>{question.text}</small></span><Icon name="arrow" size={15} /></summary>
    <div className="question-body">
    {question.reason && <p className="question-reason">{question.reason}</p>}
    <div className="question-choices">{question.options.map((option, i) => <button className="choice" key={i} onClick={() => choose(option)}>{option.label}<Icon name="arrow" size={13} /></button>)}</div>
    {question.allows_number && <form className="numeric-answer" onSubmit={event => { event.preventDefault(); if (!number.trim()) return;
      applyValue(search, { name: question.property_name, constraint: parseConstraint(question.property_name, number, question.unit) }); setNumber("");
    }}><input aria-label="Ответ на уточняющий вопрос" placeholder="Укажите значение" value={number} onChange={event => setNumber(event.target.value)} required /><span>{question.unit}</span><button className="button button-soft">Ок</button></form>}
    </div>
  </details>;
}

export function ProductCard({ item, kind, onDetails }) {
  const category = categoryOf(item);
  const description = kind === "ste" ? (item.characteristics || "").split("|").map(s => s.trim())
    .filter(s => s && !/упаков|штрихкод|не задано|неизвест/i.test(s)).slice(0, 3)
    : [];
  const clean = value => value && !["-", "неизвестно", "неизвестен"].includes(value.toLowerCase());
  return <article className="product-card" data-product-id={kind === "ste" ? item.id : undefined} data-catalog-code={kind === "ktru" ? item.code : undefined}>
    <div className="card-visual"><ProductArt category={category} name={item.name} /><span className={`card-source source-${kind}`}>{kind === "ktru" ? "КТРУ" : "СТЕ"}</span></div>
    {kind === "ktru" && <div className="catalog-card-top"><code>{item.code}</code></div>}
    <div className="card-content"><div className="card-category">{{ furniture: "Мебель", clothes: "Одежда", tools: "Инструменты" }[category]}</div>
      <button className="card-name" onClick={() => onDetails({ item, kind })}>{item.name}</button>
      {kind === "ste" && <div className="card-description">{description.length ? description.map((line, i) => <p key={i}>{line}</p>) : <p>Товар из предоставленной выгрузки. Подробнее — в карточке.</p>}</div>}
      <div className="card-bottom">{kind === "ste" && <span>{clean(item.manufacturer) ? item.manufacturer : clean(item.country) ? item.country : "Из выгрузки товаров"}</span>}
        <button className={`card-details ${kind === "ktru" ? "catalog-card-details" : ""}`} onClick={() => onDetails({ item, kind })} aria-label={`Подробнее: ${item.name}`}>{kind === "ktru" && "Характеристики"}<Icon name="arrow" size={17} /></button>
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
      .catch(failure => { if (failure.name !== "AbortError") setError("Полную карточку загрузить не удалось. Попробуйте открыть её снова."); });
    return () => { controller.abort(); dialog.current?.close(); };
  }, [selected]);
  if (!selected) return null;
  const { item, kind } = selected;
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
      </> : <>
        {details && <><h3>Характеристики позиции КТРУ</h3><dl className="catalog-characteristics">{details.characteristics.map((c, i) => <div key={i}><dt>{c.name}{c.required && <span className="required-dot" title="Обязательная характеристика"> *</span>}</dt><dd>{c.values.join("; ") || "Допустимые значения не заданы"}</dd></div>)}</dl></>}
      </>}
    </div>
  </dialog>;
}
