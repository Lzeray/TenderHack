import React, { useEffect, useState } from "react";
import { useSearch } from "./useSearch.js";
import { Feedback, Icon, Parameters, ProductArt, ProductCard, ProductDialog, Question, SearchBox } from "./components.jsx";
import { featureValue } from "./state.js";

const examples = ["Молоток слесарный 500 г", "Стул на металлическом каркасе", "Куртка утеплённая"];
const categories = [
  { key: "tools", name: "Инструменты", text: "Молотки, дрели и ручной инструмент", sample: "Молоток", label: "Начать с молотка" },
  { key: "furniture", name: "Мебель", text: "Стулья, столы и мебель для работы", sample: "Стул", label: "Начать со стула" },
  { key: "clothes", name: "Одежда", text: "Спецодежда, куртки и перчатки", sample: "Куртка", label: "Начать с куртки" },
];
const count = value => (value || 0).toLocaleString("ru-RU");

function CodeSummary({ search }) {
  const data = search.result;
  const [copied, setCopied] = useState(false);
  if (!data || search.stale) return null;
  const matched = data.status === "matched" && data.final_code;
  const remaining = data.compatible_codes?.length || 0;
  return <section className={`code-summary ${matched ? "code-matched" : ""}`} aria-label="Результат подбора КТРУ">
    <div className="code-summary-icon"><Icon name={matched ? "check" : "filter"} size={22} /></div>
    <div className="code-summary-main"><span className="eyebrow">{matched ? "Конечная позиция найдена" : "Подбор кода КТРУ"}</span>
      <h3>{matched ? data.final_name : remaining ? `Осталось позиций: ${count(remaining)}` : "Подходящий код пока не определён"}</h3>
      {matched ? <div className="resolved-code"><code>{data.final_code}</code><button className="icon-button" aria-label="Скопировать код КТРУ" onClick={async () => {
        try { await navigator.clipboard.writeText(data.final_code); setCopied(true); } catch { setCopied(false); }
      }}><Icon name={copied ? "check" : "copy"} size={16} /></button>{copied && <small>Скопировано</small>}</div>
        : <p>{data.completeness?.type_confirmed ? "Добавляйте характеристики или отвечайте на уточнения." : "Уточните описание, чтобы подтвердить область товара."}</p>}
    </div>
    {search.history.length > 1 && <div className="narrowing-history" aria-label="История сужения КТРУ">{search.history.map((item, i) => <React.Fragment key={i}>
      {i > 0 && <Icon name="arrow" size={14} />}<span className={i === search.history.length - 1 ? "history-current" : ""}>{item.count}</span>
    </React.Fragment>)}</div>}
    <details className="code-stages"><summary>Как подбирали код</summary><ol>{data.stages.map((stage, i) => <li key={i}><b>{stage.stage} · {stage.remaining}</b><p>{stage.note}</p></li>)}</ol></details>
  </section>;
}

function Welcome({ onChoose }) {
  return <section className="welcome">
    <div className="section-heading"><div><span className="eyebrow">Три направления каталога</span><h2>С чего начнём?</h2></div><span className="quiet-label">Реальные данные · проверка по КТРУ</span></div>
    <div className="category-grid">{categories.map(category => <button className="category-tile" key={category.key} onClick={() => onChoose(category.sample)}>
      <div><ProductArt category={category.key} name={category.sample} /></div><div className="category-copy"><h3>{category.name}</h3><p>{category.text}</p><span>{category.label}<Icon name="arrow" size={16} /></span></div>
    </button>)}</div>
    <div className="how-it-works"><div><span>01</span><h3>Опишите товар</h3><p>В привычных словах, с размерами и любыми известными свойствами.</p></div><div><span>02</span><h3>Уточните параметры</h3><p>Подскажем, чего не хватает, и заметим ошибки в характеристиках.</p></div><div><span>03</span><h3>Получите код КТРУ</h3><p>Проверим значения по справочнику и объясним результат подбора.</p></div></div>
  </section>;
}

export default function App() {
  const search = useSearch();
  const [tab, setTab] = useState("ste");
  const [selected, setSelected] = useState(null);
  const [help, setHelp] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 760px)").matches);
  const data = search.result;
  const current = data && !search.stale;
  const candidates = current ? (data.recognition_mode === "semantic" && !data.scope?.confirmed_scope ? data.preview_candidates : data.candidates)?.filter(c => c.compatible && !c.is_template) || [] : [];
  const totalProducts = current && data.status !== "conflict" ? data.ste_results?.total || 0 : 0;
  const source = tab;
  const items = source === "ktru" ? candidates : current ? search.products : [];
  const searching = search.busy.fast || search.stale;
  const filters = current ? data.ste_results?.applied || [] : [];
  const ignored = current ? data.ste_results?.ignored || [] : [];
  useEffect(() => {
    if (data) setTab(data.ste_results?.total ? "ste" : "ktru");
  }, [data?.query?.original]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const changed = () => setMobile(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);

  return <>
    <header className="site-header"><div className="container header-inner">
      <button className="brand" onClick={() => search.changeText("")} aria-label="Портал поставщиков — на главную"><span className="brand-mark"><Icon name="box" size={24} /></span><span>Портал <span className="brand-accent">поставщиков</span><small>Помощник подбора товаров</small></span></button>
      <nav aria-label="Навигация"><span className="nav-current">Каталог</span><button onClick={() => setHelp(value => !value)}>Как это работает</button></nav>
      <div className="header-badge"><span className="status-dot" />КТРУ — источник истины</div>
    </div></header>
    <main className="container">
      <section className={`hero ${search.text ? "hero-compact" : ""}`}>
        <div className="hero-eyebrow"><span className="mini-tag blue"><Icon name="sparkle" size={14} />Умный подбор</span><span>Для работы с характеристиками СТЕ</span></div>
        <h1>Найдите товар.<br className="desktop-break" /><span> Остальное уточним вместе.</span></h1>
        <p className="hero-description">Товары, понятные характеристики и подходящий код КТРУ — в одном поиске.</p>
        <SearchBox search={search} />
        <div className="example-row"><span>Например:</span>{examples.map(example => <button key={example} onClick={() => search.changeText(example)}>{example}<Icon name="arrow" size={13} /></button>)}</div>
      </section>
      {help && <section className="help-panel panel"><button className="icon-button" aria-label="Закрыть подсказку" onClick={() => setHelp(false)}><Icon name="close" /></button><h2>Поиск, который объясняет свой результат</h2><p>Введите один товар и его свойства. Карточки СТЕ показывают примеры из выгрузок, а позиции КТРУ — нормативные ограничения. Это разные источники: найденный товар не получает код автоматически.</p><p>Характеристики можно редактировать слева. При нехватке данных появится уточняющий вопрос; противоречия и опечатки показываем рядом с поиском. Предложения модели требуют подтверждения.</p></section>}
      <Feedback search={search} />
      {!search.text.trim() ? <Welcome onChoose={search.changeText} /> : <>
        <div className="catalog-layout"><div className="catalog-sidebar"><CodeSummary search={search} />
          <details className="mobile-parameters" open={!mobile}><summary><Icon name="filter" size={18} />Параметры и уточнения<Icon name="arrow" size={16} /></summary>
            <Parameters search={search} /><Question search={search} />
          </details>
        </div><section className="catalog-main" aria-label="Результаты поиска" data-query={current ? data.query.original : ""}>
          <div className="results-header"><div><span className="eyebrow">Каталог по вашему описанию</span><h2>Результаты поиска</h2></div><span className="view-label"><Icon name="grid" size={17} />Карточки</span></div>
          <div className="result-tabs" role="tablist" aria-label="Источник результатов">
            <button id="tab-ste" role="tab" aria-controls="result-panel" aria-selected={source === "ste"} className={source === "ste" ? "tab-active" : ""} onClick={() => setTab("ste")}>Товары СТЕ<span>{searching ? "…" : count(totalProducts)}</span></button>
            <button id="tab-ktru" role="tab" aria-controls="result-panel" aria-selected={source === "ktru"} className={source === "ktru" ? "tab-active" : ""} onClick={() => setTab("ktru")}>Позиции КТРУ<span>{searching ? "…" : count(candidates.length)}</span></button>
          </div>
          <div id="result-panel" role="tabpanel" aria-labelledby={`tab-${source}`}>
            <p className="results-note">{source === "ste" ? "Примеры из выгрузок товаров. Соответствие конкретному коду КТРУ не подтверждено." : "Совместимые конечные позиции. Непроверенные характеристики доступны в карточке."}</p>
            {source === "ste" && filters.length > 0 && <div className="applied-filters">{filters.map((filter, i) => <span key={i}><Icon name="check" size={13} />{filter.name}: {featureValue({ ...filter, value: filter.raw_value ?? filter.value })} {filter.raw_unit || filter.unit}</span>)}</div>}
            {source === "ste" && ignored.length > 0 && <details className="ignored-filters"><summary><Icon name="alert" size={15} />Не все условия проверены в СТЕ</summary><ul>{ignored.map((filter, i) => <li key={i}>{filter.name}: {filter.reason}</li>)}</ul></details>}
            {searching ? <div className="product-grid" aria-label="Загрузка товаров">{Array.from({ length: 6 }, (_, i) => <div className="skeleton-card" key={i}><div /><span /><span /><span /></div>)}</div>
              : items.length > 0 ? <div className="product-grid">{items.map(item => <ProductCard key={`${source}-${item.code || item.id}`} item={item} kind={source} onDetails={setSelected} />)}</div>
              : <div className="empty-results"><span className="empty-symbol"><Icon name={data?.status === "conflict" ? "alert" : "search"} size={35} /></span><h3>{data?.status === "conflict" ? "Сначала уточним описание" : search.busy.model ? "Уточняем ваш запрос" : "Подходящих карточек пока нет"}</h3><p>{data?.status === "conflict" ? "Причина указана выше. После исправления покажем подходящие товары." : "Попробуйте другое название, добавьте характеристику или ответьте на вопрос."}</p><button className="button button-soft" onClick={() => search.changeText("")}>Начать новый поиск</button></div>}
            {search.pageError && <p className="inline-warning" role="alert">{search.pageError}</p>}
            {!searching && source === "ste" && search.products.length < totalProducts && <div className="pagination"><button className="button button-outline" disabled={search.loadingMore} onClick={search.loadMore}>{search.loadingMore ? <><span className="spinner" />Загружаем</> : "Показать ещё товары"}</button><span>Показано {count(search.products.length)} из {count(totalProducts)}</span></div>}
          </div>
        </section></div>
      </>}
    </main>
    <footer className="site-footer container"><span>Портал поставщиков <span className="footer-divider">/</span> TenderHack</span><span>Подбор по данным КТРУ и предоставленным выгрузкам СТЕ</span></footer>
    <ProductDialog selected={selected} onClose={() => setSelected(null)} onUse={search.changeText} />
  </>;
}
