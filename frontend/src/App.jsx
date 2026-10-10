import React, { useEffect, useState } from "react";
import { useSearch } from "./useSearch.js";
import { Additional, Feedback, Icon, MissingChars, ProductArt, ProductCard, ProductDialog, Question, SearchBox, SelectedChars } from "./components.jsx";

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
        : <p>{data.completeness?.type_confirmed ? "Заполните обязательные характеристики внизу или ответьте на уточнение." : "Уточните описание, чтобы подтвердить область товара."}</p>}
      {matched && <Additional data={data} compact />}
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
  const [selected, setSelected] = useState(null);
  const [help, setHelp] = useState(false);
  const data = search.result;
  const current = data && !search.stale;
  const matched = current && data.status === "matched" && data.final_code;
  // Подбор только по КТРУ: список оставшихся конечных позиций, в конце — одна позиция.
  const candidates = current ? (data.recognition_mode === "semantic" && !data.scope?.confirmed_scope ? data.preview_candidates : data.candidates)?.filter(c => c.compatible && !c.is_template) || [] : [];
  const items = matched ? candidates.filter(c => c.code === data.final_code) : candidates;
  const searching = search.busy.fast || search.stale;

  return <>
    <header className="site-header"><div className="container header-inner">
      <button className="brand" onClick={() => search.changeText("")} aria-label="Портал поставщиков — на главную"><span className="brand-mark"><Icon name="box" size={24} /></span><span>Портал <span className="brand-accent">поставщиков</span><small>Помощник подбора КТРУ</small></span></button>
      <nav aria-label="Навигация"><span className="nav-current">Каталог</span><button onClick={() => setHelp(value => !value)}>Как это работает</button></nav>
      <div className="header-badge"><span className="status-dot" />КТРУ — источник истины</div>
    </div></header>
    <main className="container">
      <section className={`hero ${search.text ? "hero-compact" : ""}`}>
        <div className="hero-eyebrow"><span className="mini-tag blue"><Icon name="sparkle" size={14} />Умный подбор</span><span>Для работы с характеристиками СТЕ</span></div>
        <h1>Опишите товар.<br className="desktop-break" /><span> Код КТРУ подберём вместе.</span></h1>
        <p className="hero-description">Характеристики приводим к виду КТРУ, сужаем список позиций и подсказываем, что ещё указать.</p>
        <SearchBox search={search} />
        {!search.text.trim() && <div className="example-row"><span>Например:</span>{examples.map(example => <button key={example} onClick={() => search.changeText(example)}>{example}<Icon name="arrow" size={13} /></button>)}</div>}
      </section>
      {help && <section className="help-panel panel"><button className="icon-button" aria-label="Закрыть подсказку" onClick={() => setHelp(false)}><Icon name="close" /></button><h2>Поиск, который объясняет свой результат</h2><p>Поиск идёт только по справочнику КТРУ. Характеристики, которые есть в КТРУ, сужают список позиций; те, которых в КТРУ нет, сохраняются как дополнительные (с проверкой по выгрузкам СТЕ) и на код не влияют.</p><p>Слева — выбранные характеристики и те, что осталось ввести (сначала общие для всех позиций); выбранное значение дописывается в строку поиска. Справа — подходящие позиции КТРУ. Когда остаётся одна позиция, показываем её код.</p></section>}
      <Feedback search={search} />
      {!search.text.trim() ? <Welcome onChoose={search.changeText} /> : <>
        <div className="catalog-layout"><aside className="catalog-sidebar side" aria-label="Подбор и характеристики">
          <CodeSummary search={search} />
          <Question search={search} />
          <SelectedChars search={search} />
          <MissingChars search={search} />
        </aside><section className="catalog-main" aria-label="Результаты подбора" data-query={current ? data.query.original : ""}>
          <div className="results-header"><div><span className="eyebrow">Справочник КТРУ</span><h2>{matched ? "Подобранная позиция" : "Подходящие позиции КТРУ"}</h2></div><span className="view-label"><Icon name="grid" size={17} />{searching ? "…" : count(items.length)}</span></div>
          <div id="result-panel">
            <p className="results-note">{matched ? "Позиция определена однозначно. Дополнительные характеристики сохранены." : "Совместимые конечные позиции. Список сужается по мере ввода характеристик."}</p>
            {searching ? <div className="product-grid" aria-label="Загрузка позиций">{Array.from({ length: 6 }, (_, i) => <div className="skeleton-card" key={i}><div /><span /><span /><span /></div>)}</div>
              : items.length > 0 ? <div className="product-grid">{items.map(item => <ProductCard key={`ktru-${item.code}`} item={item} kind="ktru" onDetails={setSelected} />)}</div>
              : <div className="empty-results"><span className="empty-symbol"><Icon name={data?.status === "conflict" ? "alert" : "search"} size={35} /></span><h3>{data?.status === "conflict" ? "Сначала уточним описание" : search.busy.model ? "Уточняем ваш запрос" : "Подходящих позиций пока нет"}</h3><p>{data?.status === "conflict" ? "Причина указана выше. После исправления покажем подходящие позиции." : "Попробуйте другое название, добавьте характеристику или ответьте на вопрос."}</p><button className="button button-soft" onClick={() => search.changeText("")}>Начать новый поиск</button></div>}
          </div>
        </section></div>
      </>}
    </main>
    <footer className="site-footer container"><span>Портал поставщиков <span className="footer-divider">/</span> TenderHack</span><span>Подбор по справочнику КТРУ; выгрузки СТЕ — для дополнительных характеристик</span></footer>
    <ProductDialog selected={selected} onClose={() => setSelected(null)} onUse={search.changeText} />
  </>;
}
