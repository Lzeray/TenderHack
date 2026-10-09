"use strict";
// Состояние сеанса: текст, ручные правки, ответы, исправления опечаток, отклонённые предложения,
// подтверждённые предупреждения. Версии запросов и правила применения ответов — в state.js.
const S = window.KtruState;
const sess = S.newSession();
const state = { text: "", overrides: [], answers: [], answersHash: null, corrections: {}, rejected: [], confirmed: [],
  last: null, lastReq: null, latency: { draft: null, submitted: null }, resetNote: "" };
const DEBOUNCE_MS = 120;   // настраиваемый параметр (план: 100–150 мс), а не гарантированный оптимум
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STATUS_TEXT = {
  matched: "Определён конечный код КТРУ", clarification_needed: "Нужно уточнение", conflict: "Противоречие",
  not_found: "Ничего не найдено", manual_choice: "Нужен ручной выбор", error: "Ошибка",
};
const UI_TEXT = {
  editing: ["Черновик", "предварительный разбор правилами; Enter — полный разбор"],
  submitted: ["Обработка", "запрос зафиксирован, выполняется полный разбор"],
  resolved: ["Полный разбор", ""],
  stale: ["Устарело", "описание изменилось — результат ниже относится к прежней версии"],
  provider_error: ["Расширенный разбор недоступен", "показан результат по правилам; уточните вручную"],
};
const EXAMPLES = [
  "пассатижи слесарные 180 мм",
  "стул на металлическом каркасе с мягким сиденьем и мягкой спинкой",
  "шуруповерт сетевой",
  "молоток кровельный 0,5 кг",
  "куртка зимняя из кожи мужская размер 52",
  "дрель ручная электрическая мощность 500 в",
];

let timer = null;

function changed(kind) {
  // любое изменение ввода — новая версия; прежние вычисления устаревают
  S.bump(sess, performance.now());
  if (kind !== "silent") renderUiState();
}

function schedule() { clearTimeout(timer); timer = setTimeout(() => run("draft"), DEBOUNCE_MS); }

async function run(stage) {
  const text = $("desc").value.trim();
  if (!text) { renderIdle(); return; }
  const rev = sess.revision;
  const req = { text, session_id: sess.sessionId, revision: rev, stage, overrides: state.overrides,
    answers: state.answers, corrections: state.corrections, rejected: state.rejected, confirmed: state.confirmed };
  if (state.answersHash) req.answers_query_hash = state.answersHash;
  if (stage === "submitted") sess.pending.submitted = rev;
  renderUiState();
  const t0 = sess.lastInputAt ?? performance.now();
  const tSend = performance.now();
  try {
    const r = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const data = await r.json();
    if (stage === "submitted" && sess.pending.submitted === rev) sess.pending.submitted = null;
    if (!S.shouldApply(sess, data)) { renderUiState(); return; }  // устаревший ответ: в UI не применяется
    S.markShown(sess, data);
    state.last = data; state.lastReq = req;
    render(data);
    // задержка: от последнего изменения ввода до отрисовки (включая debounce, сеть и рендер)
    requestAnimationFrame(() => {
      const ms = Math.round(performance.now() - (stage === "draft" ? t0 : tSend));
      state.latency[stage] = { ms, server: data.timings?.end_to_end, rev };
      renderLatency(data);
    });
  } catch (e) {
    if (stage === "submitted") sess.pending.submitted = null;
    if (rev !== sess.revision) return;
    $("status").className = "status status--error";
    $("status").textContent = "Ошибка запроса: " + e.message;
  }
}

function renderUiState() {
  const ui = S.uiState(sess, state.last);
  const [t, note] = UI_TEXT[ui];
  $("uiState").className = "ui-state ui-state--" + ui;
  $("uiState").innerHTML = (ui === "submitted" ? '<span class="spinner"></span>' : "") + `<b>${esc(t)}</b> ${esc(note)}`
    + ` <span class="muted">· версия ${sess.revision}</span>`;
}

function renderIdle() {
  $("status").className = "status status--idle"; $("status").textContent = "Ожидание описания";
  for (const id of ["final", "question", "stages", "candidates", "corrections", "unrecognized", "completeness",
    "proposals", "resolution", "changes", "providers", "latency"]) $(id).innerHTML = "";
  $("features").innerHTML = '<tr><td colspan="5" class="muted">Введите описание</td></tr>';
  $("issuesCard").hidden = true; $("historyBox").hidden = true; $("exportBtn").disabled = true; $("addRowBtn").disabled = true;
  state.last = null; renderUiState();
}

function render(d) {
  $("status").className = "status status--" + d.status;
  const pre = d.preliminary ? '<span class="tag tag--muted">черновик</span> ' : '<span class="tag tag--answer">полный разбор</span> ';
  $("status").innerHTML = `${pre}${esc(STATUS_TEXT[d.status] || d.status)}<small>${esc(d.message)}</small>`;
  $("exportBtn").disabled = false;
  $("addRowBtn").disabled = !d.properties.length;
  renderUiState();
  renderCorrections(d); renderHistory(d); renderFeatures(d); renderProposals(d); renderResolution(d); renderFinal(d);
  renderQuestion(d); renderChanges(d); renderIssues(d); renderStages(d); renderCandidates(d); renderProps(d);
  renderProviders(d);
  $("versions").textContent = "Версии: " + Object.entries(d.versions).map(([k, v]) => `${k} ${v}`).join(" · ");
}

function renderLatency(d) {
  const l = state.latency;
  const part = (name, x) => x ? `${name}: <b>${x.ms} мс</b> <span class="muted">(сервер ${x.server ?? "—"} мс, версия ${x.rev})</span>` : "";
  const t = d.timings || {};
  const stages = ["normalize", "retrieval", "extract", "validate", "decide", "semantic", "llm"].filter((k) => t[k] !== undefined)
    .map((k) => `${k} ${t[k]}`).join(" · ");
  $("latency").innerHTML = [part("Черновик (ввод → отрисовка)", l.draft), part("Полный разбор (Enter → отрисовка)", l.submitted)]
    .filter(Boolean).join("<br>") + (stages ? `<div class="muted">этапы, мс: ${esc(stages)}</div>` : "");
}

function renderCorrections(d) {
  const box = $("corrections"); box.innerHTML = state.resetNote ? `<div class="small tag--warn reset">${esc(state.resetNote)}</div>` : "";
  for (const c of d.corrections) {
    if (c.status === "corrected" || c.status === "user_choice") {
      box.insertAdjacentHTML("beforeend", `<div class="small" style="margin-top:8px">Исправлено: <span class="chip chip--ok">${esc(c.original)} → ${esc(c.corrected)}</span> <span class="muted">${esc(c.note)}</span></div>`);
    } else {
      const opts = c.options.map((o) => `<button class="chip chip--warn" data-orig="${esc(c.original)}" data-opt="${esc(o)}">${esc(o)}</button>`).join(" ");
      box.insertAdjacentHTML("beforeend", `<div class="small" style="margin-top:8px">«${esc(c.original)}» — выберите вариант: ${opts} <button class="chip" data-orig="${esc(c.original)}" data-opt="${esc(c.original)}">оставить как есть</button></div>`);
    }
  }
  box.querySelectorAll("button[data-orig]").forEach((b) => b.onclick = () => {
    state.corrections[b.dataset.orig] = b.dataset.opt; changed(); run("draft");
  });
}

function renderHistory(d) {
  const h = d.query.history || [];
  $("historyBox").hidden = !h.length;
  $("history").innerHTML = h.map((s) => `<li><b>${esc(s.step)}</b>: ${esc(s.note)}<br><span class="muted">${esc(s.before)} → ${esc(s.after)}</span></li>`).join("");
}

const SRC = { text: ["из текста", "tag--text"], override: ["вручную", "tag--override"], answer: ["ответ", "tag--answer"],
  model: ["предложено", "tag--warn"] };
const FST = {
  bound: ["", ""], ambiguous: ["неоднозначно", "tag--warn"], unknown_property: ["нет такого свойства", "tag--bad"],
  overridden: ["переопределено", "tag--muted"], removed: ["удалено", "tag--muted"], proposed: ["не применено", "tag--muted"],
};

function featureValue(f) {
  const ops = { eq: "", ne: "≠ ", ge: "≥ ", gt: "> ", le: "≤ ", lt: "< " };
  if (f.op === "between") return `${f.value}–${f.value_to}`;
  return (ops[f.op] || "") + (f.value ?? "");
}

function checkStatus(d, f) {
  // статус проверки по КТРУ у лидирующего кандидата — отдельно от источника признака
  const c = d.candidates.find((c) => c.compatible && !c.is_template) || d.candidates[0];
  const k = c?.checks.find((k) => k.feature_id === f.id);
  return k ? `<span class="st st--${k.status}" title="${esc(k.reason)}">${k.status}</span>` : "";
}

function renderFeatures(d) {
  const tb = $("features");
  if (!d.features.length) { tb.innerHTML = '<tr><td colspan="5" class="muted">Характеристики не извлечены</td></tr>'; }
  else {
    tb.innerHTML = d.features.map((f, i) => {
      const [srcT, srcC] = SRC[f.source] || [f.source, ""]; const [stT, stC] = FST[f.status] || [f.status, ""];
      const dim = f.status === "overridden" || f.status === "removed" || f.status === "proposed";
      let prop = f.property_name ? esc(f.property_name) : '<span class="muted">—</span>';
      if (f.component) prop += ` <span class="tag tag--muted" title="часть товара">${esc(f.component)}</span>`;
      if (f.status === "ambiguous" && f.options.length) {
        prop = `<select data-amb="${i}"><option value="">выберите свойство…</option>${f.options.map((o, k) => `<option value="${k}">${esc(o.property_name)}${o.value ? " = " + esc(o.value) : ""}</option>`).join("")}</select>`;
      }
      const editable = f.status === "bound" && f.property_name && f.source !== "model";
      const val = editable ? `<input data-edit="${i}" value="${esc(featureValue(f))}" size="10">` : `<span class="${dim ? "strike" : ""}">${esc(featureValue(f))}</span>`;
      const ev = f.evidence ? `<div class="ev">«${esc(f.evidence)}»</div>` : "";
      const note = f.note ? `<div class="ev">${esc(f.note)}</div>` : "";
      const conf = f.source === "model" ? (f.confirmation === "tentative" ? ' <span class="tag tag--warn">не подтверждено</span>' : "")
        : (f.source !== "text" ? ' <span class="tag tag--answer">подтверждено</span>' : "");
      const sup = f.supported_by?.length ? ` <span class="tag tag--muted" title="источники, согласные с трактовкой">+ ${esc(f.supported_by.join(", "))}</span>` : "";
      const intent = f.intent === "requirement" ? ' <span class="tag tag--muted">требование</span>' : f.intent === "preference" ? ' <span class="tag tag--muted">предпочтение</span>' : "";
      const del = f.property_name && f.status === "bound" && f.source !== "model" ? `<button class="btn btn--danger btn--small" data-del="${i}" title="удалить">✕</button>` : "";
      return `<tr><td>${prop}${ev}</td><td>${val}${note}</td><td>${esc(f.unit || "")}</td>
        <td><span class="tag ${srcC}">${srcT}${f.source === "model" ? " (" + esc(f.origin) + ")" : ""}</span>${conf}${sup}${intent} ${stT ? `<span class="tag ${stC}">${stT}</span>` : ""} ${f.status === "bound" ? checkStatus(d, f) : ""}</td><td>${del}</td></tr>`;
    }).join("");
  }
  tb.querySelectorAll("input[data-edit]").forEach((inp) => inp.onchange = () => {
    const f = d.features[+inp.dataset.edit];
    upsertOverride(parseConstraint(f.property_code || f.property_name, inp.value, f.unit));
  });
  tb.querySelectorAll("button[data-del]").forEach((b) => b.onclick = () => {
    const f = d.features[+b.dataset.del];
    const key = f.property_code || f.property_name;
    state.overrides = state.overrides.filter((o) => o.property !== key);
    if (f.source === "text") state.overrides.push({ property: key, remove: true });
    if (f.source === "answer") state.answers = state.answers.filter((a) => a.property !== key);
    changed(); run("draft");
  });
  tb.querySelectorAll("select[data-amb]").forEach((s) => s.onchange = () => {
    if (s.value === "") return;
    const f = d.features[+s.dataset.amb]; const o = f.options[+s.value];
    upsertOverride({ property: o.property_code, op: f.op, value: o.value ?? f.value, value_to: f.value_to, unit: f.unit,
      min_inclusive: f.min_inclusive, max_inclusive: f.max_inclusive });
  });
  $("unrecognized").innerHTML = d.unrecognized.length
    ? `<div class="small" style="margin-top:8px">Не распознано: ${d.unrecognized.map((u) => `<span class="tag tag--warn">${esc(u)}</span>`).join(" ")}</div>` : "";
}

function renderProposals(d) {
  const ps = (d.proposals || []).filter((p) => !state.rejected.includes(p.key));
  if (!ps.length) { $("proposals").innerHTML = ""; return; }
  $("proposals").innerHTML = `<div class="card proposals"><h2>Предложения моделей <span class="muted small">не применяются без вашего подтверждения</span></h2>
    <ul class="plist">${ps.map((p, i) => `<li><span class="tag tag--warn">${esc(p.origin)}</span> ${esc(p.label)}
      <span class="muted small">${esc(p.reason)}</span>
      ${p.answer ? `<button class="btn btn--small" data-acc="${i}">принять</button>` : ""}
      <button class="btn btn--ghost btn--small" data-rej="${i}">отклонить</button></li>`).join("")}</ul></div>`;
  $("proposals").querySelectorAll("button[data-acc]").forEach((b) => b.onclick = () => answer(ps[+b.dataset.acc].answer, d.query_hash));
  $("proposals").querySelectorAll("button[data-rej]").forEach((b) => b.onclick = () => {
    state.rejected.push(ps[+b.dataset.rej].key); changed(); run(state.last?.stage || "draft");
  });
}

function renderResolution(d) {
  const cr = d.code_resolution; const cc = d.characteristics_completion; const sc = d.scope;
  if (!cr) { $("resolution").innerHTML = ""; return; }
  const CR = { resolved: ["код определён однозначно", "tag--answer"], unconfirmed: ["код не подтверждён", "tag--warn"],
    multiple: ["несколько позиций", "tag--warn"], none: ["нет позиции", "tag--muted"], conflict: ["противоречие", "tag--bad"] };
  const [t, c] = CR[cr.status] || [cr.status, ""];
  const draftNote = d.preliminary || !sc?.confirmed_scope
    ? `<div class="small muted">При текущей предварительной трактовке осталось ${cr.remaining || 0} поз.${sc?.confirmed_scope ? "" : " Тип не подтверждён — это не окончательное количество подходящих товаров."}</div>` : "";
  $("resolution").innerHTML = `<div class="card resolution"><div class="res-row"><span class="tag ${c}">${t}</span> ${cr.code ? `<b>${esc(cr.code)}</b>` : ""} <span class="small muted">${esc(cr.reason)}</span></div>
    ${cc ? `<div class="res-row small">Заполнение СТЕ: ${cc.complete ? '<span class="tag tag--answer">обязательные заполнены</span>' : `<span class="tag tag--warn">не завершено</span> обязательных ${cc.required_filled}/${cc.required_total}`}
      ${cc.missing.length ? ` · не указано: ${cc.missing.map(esc).join(", ")}` : ""}${cc.unchecked.length ? ` · не проверено: ${cc.unchecked.map(esc).join(", ")}` : ""}</div>` : ""}
    ${sc ? `<div class="res-row small muted">Область: ${sc.confirmed_scope ? esc(sc.confirmed_scope) : "тип не подтверждён"} · ${sc.scope_complete ? "проверена полностью" : "полнота не подтверждена"}${sc.type_basis.length ? " · основание: " + esc(sc.type_basis.join("; ")) : ""}</div>` : ""}
    ${draftNote}</div>`;
}

function parseConstraint(prop, raw, unit) {
  let s = String(raw).trim().replace(",", ".");
  let op = "eq", value = s, value_to = null;
  const m2 = s.match(/^(-?\d+(?:\.\d+)?)\s*[–-]\s*(-?\d+(?:\.\d+)?)$/);
  if (m2) { op = "between"; value = m2[1]; value_to = m2[2]; }
  else if (/^(≥|>=)/.test(s)) { op = "ge"; value = s.replace(/^(≥|>=)\s*/, ""); }
  else if (/^(≤|<=)/.test(s)) { op = "le"; value = s.replace(/^(≤|<=)\s*/, ""); }
  else if (/^>/.test(s)) { op = "gt"; value = s.slice(1).trim(); }
  else if (/^</.test(s)) { op = "lt"; value = s.slice(1).trim(); }
  else if (/^(≠|!=|не )/.test(s)) { op = "ne"; value = s.replace(/^(≠|!=|не )\s*/, ""); }
  else if (!/^-?\d+(\.\d+)?$/.test(s)) value = String(raw).trim();
  return { property: prop, op, value, value_to, unit: unit || null };
}

function upsertOverride(c) {
  state.overrides = state.overrides.filter((o) => o.property !== c.property);
  state.overrides.push(c); changed(); run("draft");
}

function renderFinal(d) {
  $("final").innerHTML = d.final_code ? `<div class="card final"><div class="muted small">Конечная позиция КТРУ</div>
    <div class="final__code">${esc(d.final_code)}</div><div>${esc(d.final_name)}</div>
    <div class="small muted" style="margin-top:6px">Все условия проверены в полной области типа; обязательные свойства заполнены.</div></div>` : "";
}

function renderQuestion(d) {
  const q = d.question; const box = $("question");
  if (!q) { box.innerHTML = ""; return; }
  const opts = q.options.map((o, i) => `<button class="opt" data-q="${i}">${esc(o.label)}${q.kind !== "confirm" ? `<small>→ ${o.remaining}</small>` : ""}</button>`).join("");
  const num = q.allows_number ? `<div class="num-answer"><input id="qNum" placeholder="число"><span>${esc(q.unit || "")}</span><button class="btn btn--small" id="qNumBtn">Ответить</button></div>` : "";
  const head = q.kind === "confirm" ? `<div class="small" style="margin-bottom:8px">${esc(q.reason)}</div>`
    : `<div class="small muted" style="margin-bottom:8px">Сейчас ${q.current_remaining} поз.; в худшем случае останется ${q.worst_case_remaining}. ${esc(q.reason)}</div>`;
  box.innerHTML = `<div class="card question"><div class="question__text">${esc(q.text)}</div>${head}
    <div class="options">${opts}</div>${num}</div>`;
  box.querySelectorAll("button[data-q]").forEach((b) => b.onclick = () => chooseOption(q.options[+b.dataset.q], d));
  if (q.allows_number) $("qNumBtn").onclick = () => {
    const v = $("qNum").value.trim(); if (!v) return;
    answer(parseConstraint(q.property_code, v, q.unit), d.query_hash);
  };
}

function chooseOption(o, d) {
  const many = o.answers && o.answers.length ? o.answers : (o.answer ? [o.answer] : []);
  for (const c of many) {
    if (c.property === "__type__") state.overrides = state.overrides.filter((x) => x.property !== "__type__");
    state.answers = state.answers.filter((a) => a.property !== c.property);
    state.answers.push(c);
  }
  if (many.length) state.answersHash = d.query_hash;
  for (const k of o.reject || []) if (!state.rejected.includes(k)) state.rejected.push(k);
  for (const k of o.confirm || []) if (!state.confirmed.includes(k)) state.confirmed.push(k);
  changed();
  run(d.stage === "submitted" ? "submitted" : "draft");
}

function answer(c, hash) {
  if (c.property === "__type__") state.overrides = state.overrides.filter((o) => o.property !== "__type__");
  state.answers = state.answers.filter((a) => a.property !== c.property);
  state.answers.push(c); state.answersHash = hash; changed(); run(state.last?.stage || "draft");
}

function renderChanges(d) {
  $("changes").innerHTML = d.changes?.length ? `<div class="card"><h2>Что изменил полный разбор</h2><ul class="issues">${d.changes.map((c) => `<li class="info">${esc(c)}</li>`).join("")}</ul></div>` : "";
}

function renderIssues(d) {
  $("issuesCard").hidden = !d.issues.length;
  $("issues").innerHTML = d.issues.map((i) => `<li class="${i.level}">${esc(i.message)}</li>`).join("");
}

function renderProviders(d) {
  const ST = { off: "выключен", ok: "выполнен", skipped: "не нужен", timeout: "таймаут", error: "ошибка", invalid: "ответ отклонён",
    cached: "из кэша", stale: "устарел" };
  $("providers").innerHTML = (d.providers || []).map((p) => `<span class="tag ${p.status === "ok" || p.status === "cached" ? "tag--answer" : p.status === "off" || p.status === "skipped" ? "tag--muted" : "tag--warn"}" title="${esc(p.detail)}">${esc(p.name)}: ${ST[p.status] || p.status}${p.elapsed_ms != null ? " · " + p.elapsed_ms + " мс" : ""}</span>`).join(" ");
}

function renderStages(d) {
  $("stages").innerHTML = d.stages.map((s) => `<li>${esc(s.stage)}: <b>${s.remaining}</b>${s.removed ? ` <span class="muted">(−${s.removed})</span>` : ""}<div class="small muted">${esc(s.note)}</div></li>`).join("");
  const c = d.completeness;
  $("completeness").innerHTML = `Бэкенд: ${esc(c.backend)}. Поиск: ${c.retrieval_returned} из ${c.retrieval_total_hits}${c.retrieval_complete ? "" : " (top-K)"}.
    Область типа: ${c.type_domain_returned} из ${c.type_domain_total} — ${c.type_domain_complete ? "проверена полностью" : "проверена НЕ полностью"}.
    Тип ${c.type_confirmed ? "подтверждён" : "не подтверждён"}. ${esc(c.note)}${d.effective_at ? ` Дата проверки активности: ${esc(d.effective_at)}.` : ""}`;
}

function renderCandidates(d) {
  $("candCount").textContent = `(в области ${d.candidates_total}, показано ${d.candidates.length})`;
  $("candidates").innerHTML = d.candidates.map((c) => {
    const rc = c.rank_components;
    const badges = [c.is_template ? '<span class="tag tag--muted">шаблон (укрупнённая)</span>' : "",
      !c.compatible ? '<span class="tag tag--bad">несовместима</span>' : "",
      c.code === d.final_code ? '<span class="tag tag--answer">конечный код</span>' : ""].join(" ");
    const rank = rc ? `тип/название: ${rc.name_tier} (${rc.name_coverage}) · покрытие терминов: ${rc.term_coverage} · проверено: ${rc.valid_conditions} · не проверено: ${rc.unknown_conditions}` : "";
    const checks = c.checks.map((k) => `<li><span class="st st--${k.status}">${k.status}</span> <b>${esc(k.property_name)}</b>${k.required ? " *" : ""}: ${esc(k.reason)}</li>`).join("");
    return `<div class="cand ${c.compatible ? "" : "cand--bad"}"><div class="cand__top"><span class="cand__code">${c.rank ? c.rank + ". " : ""}${esc(c.code)}</span><span>${badges}</span></div>
      <div class="cand__name">${esc(c.name)} <span class="muted small">v${c.version}</span></div>
      <div class="cand__rank">${rank}</div>${c.excluded_reason ? `<div class="small" style="color:var(--red)">${esc(c.excluded_reason)}</div>` : ""}
      ${checks ? `<details><summary class="small">Проверки свойств (${c.checks.length})</summary><ul class="checks">${checks}</ul></details>` : ""}</div>`;
  }).join("") || '<div class="muted">Нет кандидатов</div>';
}

function renderProps(d) {
  $("addProp").innerHTML = d.properties.map((p, i) => `<option value="${i}">${esc(p.name)}${p.required ? " *" : ""}${p.units.length ? " (" + esc(p.units.join(", ")) + ")" : ""}</option>`).join("");
  const fill = () => {
    const p = d.properties[+$("addProp").value]; if (!p) return;
    $("addValues").innerHTML = p.values.map((v) => `<option value="${esc(v)}">`).join("");
    $("addUnit").value = p.units[0] || "";
  };
  $("addProp").onchange = fill; fill();
}

function resetForNewText() {
  // новое описание: прежние ответы, исправления и отказы больше к нему не относятся (сброс показывается)
  const had = state.answers.length + Object.keys(state.corrections).length + state.rejected.length + state.confirmed.length;
  state.answers = []; state.answersHash = null; state.corrections = {}; state.rejected = []; state.confirmed = [];
  state.resetNote = had ? "Описание изменилось: прежние ответы на уточнения и подтверждения сброшены." : "";
}

$("addRowBtn").onclick = () => { $("addRow").hidden = !$("addRow").hidden; };
$("addApply").onclick = () => {
  const p = state.last?.properties[+$("addProp").value]; const v = $("addValue").value.trim();
  if (!p || !v) return;
  const c = parseConstraint(p.code, v, $("addUnit").value.trim());
  if ($("addOp").value !== "eq" && c.op === "eq") c.op = $("addOp").value;
  $("addValue").value = ""; upsertOverride(c);
};
$("exportBtn").onclick = () => {
  const blob = new Blob([JSON.stringify({ request: state.lastReq, response: state.last }, null, 2)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "ktru-result.json"; a.click();
  URL.revokeObjectURL(a.href);
};
$("desc").addEventListener("input", () => {
  if ($("desc").value.trim() !== state.text) resetForNewText();
  state.text = $("desc").value.trim();
  changed();
  schedule();
});
$("desc").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); clearTimeout(timer); changed("silent"); run("submitted"); }
});
$("submitBtn").onclick = () => { clearTimeout(timer); changed("silent"); run("submitted"); };
$("examples").innerHTML = EXAMPLES.map((e) => `<button class="chip" type="button">${esc(e)}</button>`).join("");
$("examples").querySelectorAll("button").forEach((b) => b.onclick = () => {
  $("desc").value = b.textContent; state.overrides = []; resetForNewText(); state.resetNote = "";
  state.text = b.textContent; changed(); run("draft");
});
fetch("/api/catalog").then((r) => r.json()).then((c) => {
  const cov = Object.values(c.coverage || {}).map((x) => `${x.title}: ${x.active_final} кон. / ${x.active_templates} шабл.`).join(" · ");
  $("catalogInfo").innerHTML = `Снимок КТРУ: ${esc(c.snapshot)} · на дату ${esc(c.as_of)} · поиск: ${esc(c.search_backend)}<br>${esc(cov)}`;
}).catch(() => { $("catalogInfo").textContent = "каталог недоступен"; });
renderUiState();
