import React, { useState } from "react";
import { useSearch } from "./useSearch.js";
import { Feedback, Icon, MissingChars, ProductArt, ProductCard, ProductDialog, Question, SearchBox, SelectedChars } from "./components.jsx";

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
  return <section className={`code-summary ${matched ? "code-matched" : "code-progress"}`} aria-label="Результат подбора КТРУ">
    {matched && <><div className="code-summary-icon"><Icon name="check" size={22} /></div>
    <div className="code-summary-main"><span className="eyebrow">Конечная позиция найдена</span>
      <h3>{data.final_name}</h3>
      <div className="resolved-code"><code>{data.final_code}</code><button className="icon-button" aria-label="Скопировать код КТРУ" onClick={async () => {
        try { await navigator.clipboard.writeText(data.final_code); setCopied(true); } catch { setCopied(false); }
      }}><Icon name={copied ? "check" : "copy"} size={16} /></button>{copied && <small>Скопировано</small>}</div>
    </div></>}
    <details className="code-stages"><summary>История подбора</summary>
    {search.history.length > 1 && <div className="narrowing-history" aria-label="История сужения КТРУ">{search.history.map((item, i) => <React.Fragment key={i}>
      {i > 0 && <Icon name="arrow" size={14} />}<span className={i === search.history.length - 1 ? "history-current" : ""}>{item.count}</span>
    </React.Fragment>)}</div>}
    <ol>{data.stages.map((stage, i) => <li key={i}><b>{stage.stage} · {stage.remaining}</b><p>{stage.note}</p></li>)}</ol></details>
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
      <nav aria-label="Навигация"><span className="nav-current">Каталог</span></nav>
    </div></header>
    <main className="container">
      <section className={`hero ${search.text ? "hero-compact" : ""}`}>
        <h1>Опишите товар.<br className="desktop-break" /><span> Код КТРУ подберём вместе.</span></h1>
        <SearchBox search={search} />
      </section>
      <Feedback search={search} />
      {!search.text.trim() ? <Welcome onChoose={search.changeText} /> : <>
        <div className="catalog-layout"><aside className="catalog-sidebar side" aria-label="Подбор и характеристики" tabIndex={0}>
          <div className="secondary-panels"><Question search={search} /><SelectedChars search={search} /></div>
          <MissingChars search={search} />
        </aside><section className="catalog-main" aria-label="Результаты подбора" data-query={current ? data.query.original : ""}>
          <div className="results-header"><h2>{matched ? "Подобранный КТРУ" : "Подходящие КТРУ"}</h2><span className="view-label" aria-label="Количество подходящих позиций">{searching ? "…" : count(items.length)}</span></div>
          {matched && <CodeSummary search={search} />}
          <div id="result-panel">
            {searching ? <div className="product-grid" aria-label="Загрузка позиций">{Array.from({ length: 6 }, (_, i) => <div className="skeleton-card" key={i}><div /><span /><span /><span /></div>)}</div>
              : items.length > 0 ? <div className="product-grid">{items.map(item => <ProductCard key={`ktru-${item.code}`} item={item} kind="ktru" onDetails={setSelected} />)}</div>
              : <div className="empty-results"><span className="empty-symbol"><Icon name={data?.status === "conflict" ? "alert" : "search"} size={35} /></span><h3>{data?.status === "conflict" ? "Сначала уточним описание" : search.busy.model ? "Уточняем ваш запрос" : "Подходящих позиций пока нет"}</h3><p>{data?.status === "conflict" ? "Причина указана выше. После исправления покажем подходящие позиции." : "Попробуйте другое название, добавьте характеристику или ответьте на вопрос."}</p><button className="button button-soft" onClick={() => search.changeText("")}>Начать новый поиск</button></div>}
          </div>
          {!matched && <CodeSummary search={search} />}
        </section></div>
      </>}
    </main>
    <footer className="site-footer container"><span>Портал поставщиков <span className="footer-divider">/</span> TenderHack</span><span>Подбор по справочнику КТРУ; выгрузки СТЕ — для дополнительных характеристик</span></footer>
    <ProductDialog selected={selected} onClose={() => setSelected(null)} onUse={search.changeText} />
  </>;
}
