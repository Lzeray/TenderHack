"use strict";
const S = window.KtruState;
const sess = S.newSession();
const state = { text: "", overrides: [], answers: [], answersHash: null, corrections: {}, rejected: [], confirmed: [],
  last: null, lastReq: null, latency: {}, loadedProducts: [], productResult: null, productKey: null };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const DEBOUNCE_MS = Number(new URLSearchParams(location.search).get("debounce")) || 200;
const EXAMPLES = ["Молоток слесарный 500 г", "Стул на металлическом каркасе", "Стол белый"];
let timer = null, modelTimer = null;

function changed() {
  S.bump(sess, performance.now());
  fetch("/api/revision", {method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text:$("desc").value,session_id:sess.sessionId,revision:sess.revision})}).catch(() => {});
  renderUiState();
}
function schedule() {
  clearTimeout(timer); clearTimeout(modelTimer);
  timer = setTimeout(() => run("draft"), DEBOUNCE_MS);
  modelTimer = setTimeout(() => run("submitted"), 1000);
}
async function run(stage, action = "search") {
  const text = $("desc").value;
  if (!text.trim()) { renderIdle(); return; }
  const rev = sess.revision, inputAt = sess.lastInputAt ?? performance.now();
  const req = {text,session_id:sess.sessionId,revision:rev,stage,action,overrides:state.overrides,answers:state.answers,
    corrections:state.corrections,rejected:state.rejected,confirmed:state.confirmed};
  if (state.answersHash) req.answers_query_hash = state.answersHash;
  if (stage === "submitted") sess.pending.submitted = rev;
  renderUiState();
  try {
    const r = await fetch("/api/search", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(req)});
    if (!r.ok) throw new Error("request_failed");
    const d = await r.json();
    if (stage === "submitted" && sess.pending.submitted === rev) sess.pending.submitted = null;
    if (!S.shouldApply(sess,d)) { renderUiState(); return; }
    S.markShown(sess,d); state.last = d; state.lastReq = req;
    render(d);
    requestAnimationFrame(() => { state.latency[stage] = {ms:Math.round(performance.now()-inputAt),rev}; });
  } catch (_) {
    if (stage === "submitted" && sess.pending.submitted === rev) sess.pending.submitted = null;
    if (rev !== sess.revision) return;
    $("uiState").textContent = "";
    if (stage === "submitted" && state.last?.revision === rev) return; // keep the useful fast result
    $("status").className = "status status--error";
    $("status").textContent = "Не удалось выполнить поиск. Попробуйте ещё раз.";
  }
}
function renderUiState() {
  const loading = sess.pending.submitted === sess.revision || state.last?.revision !== sess.revision;
  $("uiState").innerHTML = loading && $("desc").value.trim() ? '<span class="spinner"></span>Ищем…' : "";
  if (state.last?.revision !== sess.revision) {
    for (const id of ["features","question","resultsPager","addRow"]) {
      $(id).querySelectorAll("button,input,select").forEach((el) => {el.disabled=true;});
    }
  }
}
function renderIdle() {
  state.last = null; state.loadedProducts = []; state.productKey = null;
  $("status").hidden = false; $("status").className = "status status--idle"; $("status").textContent = "Введите описание товара";
  for (const id of ["results","question","final","corrections","features","resultsPager","notes"]) $(id).innerHTML = "";
  $("notesCard").hidden = true;
  $("resultsCard").hidden = true; $("featuresCard").hidden = true; $("uiState").textContent = "";
}
function activeCandidates(d) {
  const candidates = d.recognition_mode === "semantic" && !d.scope?.confirmed_scope ? d.preview_candidates || [] : d.candidates || [];
  return candidates.filter((c) => c.compatible && !c.is_template);
}
function render(d) {
  renderCorrections(d); renderNotes(d); renderFeatures(d); renderQuestion(d); renderFinal(d); renderResults(d); renderStatus(d); renderProps(d);
  $("addRow").querySelectorAll("input,select,button").forEach((el) => {el.disabled=false;});
  renderUiState();
}
function renderStatus(d) {
  if (d.status === "conflict") {
    $("status").className = "status status--conflict";
    $("status").innerHTML = `<b>Уточните описание</b><small>${esc(d.message)}</small>`;
    return;
  }
  const total = activeCandidates(d).length + (d.ste_results?.total || 0);
  if (!total) {
    $("status").className = "status status--not_found";
    $("status").innerHTML = '<b>Товары не найдены</b><small>Попробуйте изменить название или убрать часть характеристик.</small>';
  } else {
    $("status").className = "status status--idle";
    $("status").textContent = "Результаты обновляются по вашему описанию";
    $("status").hidden = true; // the result heading already provides the useful count
  }
  if (!total || d.status === "conflict") $("status").hidden = false;
}
function renderCorrections(d) {
  $("corrections").innerHTML = (d.corrections || []).map((c) => c.corrected
    ? `<div class="small muted correction">Исправлено: ${esc(c.original)} → ${esc(c.corrected)}</div>`
    : `<div class="small correction">Уточните слово «${esc(c.original)}»: ${c.options.map((o) =>
      `<button class="chip" data-original="${esc(c.original)}" data-correction="${esc(o)}">${esc(o)}</button>`).join(" ")}</div>`).join("");
  $("corrections").querySelectorAll("[data-correction]").forEach((b) => b.onclick = () => {
    state.corrections[b.dataset.original] = b.dataset.correction; changed(); schedule();
  });
}
// Замечания: предложения уровня 3 (сомнительные значения) и предупреждения ядра.
// «Заменить» правит текст описания — это новый ввод, который заново проходит проверку по КТРУ.
// «Оставить» передаёт ключ в confirmed: в этом описании предложение больше не показывается.
function renderNotes(d) {
  const sugg = d.suggestions || [];
  const issues = (d.issues || []).filter((i) => !i.code.startsWith("suspect_") && i.level !== "info");
  $("notesCard").hidden = !sugg.length && !issues.length;
  const sHtml = sugg.map((s, k) => {
    const fix = s.replace_span && s.replacement_text != null
      ? `<button class="btn" data-fix="${k}" type="button">Заменить на «${esc(s.replacement_text)}»</button>` : "";
    return `<div class="note note--warn"><div class="small">${esc(s.message)}</div>
      <div class="note__actions">${fix}<button class="btn btn--ghost" data-keep="${k}" type="button">Оставить как есть</button></div></div>`;
  }).join("");
  const iHtml = issues.map((i) => `<div class="note note--${i.level === "error" ? "bad" : "warn"} small">${esc(i.message)}</div>`).join("");
  $("notes").innerHTML = sHtml + iHtml;
  $("notes").querySelectorAll("[data-fix]").forEach((b) => b.onclick = () => {
    const s = sugg[+b.dataset.fix], text = $("desc").value, [a, z] = s.replace_span;
    // текст мог измениться с момента ответа: заменяем, только если на месте прежний фрагмент
    if (state.last?.query?.original !== undefined && state.last.query.original !== text) return;
    const next = text.slice(0, a) + s.replacement_text + text.slice(z);
    resetForNewText(); $("desc").value = next; state.text = next; changed(); schedule();
  });
  $("notes").querySelectorAll("[data-keep]").forEach((b) => b.onclick = () => {
    const s = sugg[+b.dataset.keep];
    if (!state.confirmed.includes(s.id)) state.confirmed.push(s.id);
    changed(); schedule();
  });
}
function featureValue(f) {
  if (f.op === "in") return (f.values || []).join(" / ");
  if (f.op === "between") return `${f.value}–${f.value_to}`;
  return ({ne:"не ",ge:"≥ ",gt:"> ",le:"≤ ",lt:"< "}[f.op] || "") + (f.value ?? "");
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
      let val = editable ? `<input data-edit="${i}" value="${esc(featureValue(f))}" size="10">` : `<span class="${dim ? "strike" : ""}">${esc(featureValue(f))}</span>`;
      if (f.ktru_value && (f.ktru_value !== f.value || f.ktru_unit !== f.unit)) {
        val += `<div class="ev unified" title="значение в единице характеристики КТРУ">→ ${esc(f.ktru_value)} ${esc(f.ktru_unit)} (по КТРУ)</div>`;
      }
      const ev = f.evidence ? `<div class="ev">«${esc(f.evidence)}»</div>` : "";
      const note = f.note ? `<div class="ev">${esc(f.note)}</div>` : "";
      const conf = f.source === "model" ? (f.confirmation === "tentative" ? ' <span class="tag tag--warn">не подтверждено</span>' : "")
        : (f.source !== "text" ? ' <span class="tag tag--answer">подтверждено</span>' : "");
      const sup = f.supported_by?.length ? ` <span class="tag tag--muted" title="источники, согласные с трактовкой">+ ${esc(f.supported_by.join(", "))}</span>` : "";
      const SRCK = { ktru: ["КТРУ", "tag--text"], portal: ["портал", "tag--override"], new: ["новая", "tag--warn"] };
      const csrc = f.char_source ? ` <span class="tag ${SRCK[f.char_source][1]}" title="источник характеристики">${SRCK[f.char_source][0]}</span>` : "";
      const intent = f.intent === "requirement" ? ' <span class="tag tag--muted">требование</span>' : f.intent === "preference" ? ' <span class="tag tag--muted">предпочтение</span>' : "";
      const del = f.property_name && f.status === "bound" && f.source !== "model" ? `<button class="btn btn--danger btn--small" data-del="${i}" title="удалить">✕</button>` : "";
      return `<tr><td>${prop}${ev}</td><td>${val}${note}</td><td>${esc(f.unit || "")}</td>
        <td><span class="tag ${srcC}">${srcT}${f.source === "model" ? " (" + esc(f.origin) + ")" : ""}</span>${csrc}${conf}${sup}${intent} ${stT ? `<span class="tag ${stC}">${stT}</span>` : ""} ${f.status === "bound" ? checkStatus(d, f) : ""}</td><td>${del}</td></tr>`;
    }).join("");
  }
  tb.querySelectorAll("input[data-edit]").forEach((inp) => inp.onchange = () => {
    const f = d.features[+inp.dataset.edit];
    upsertOverride(parseConstraint(f.property_code || f.property_name, inp.value, f.unit));
  });
  for (const a of extras) rows.push(`<tr><td>${esc(a.name)}</td><td>${esc(a.value ?? a.raw_value)}${a.unit ? " " + esc(a.unit) : ""}</td><td></td></tr>`);
  $("features").innerHTML = rows.join("") || '<tr><td colspan="3" class="muted">Добавьте нужные свойства</td></tr>';
  $("features").querySelectorAll("[data-edit]").forEach((el) => el.onchange = () => {
    const f = d.features[+el.dataset.edit]; upsert(parseConstraint(f.characteristic_ref || f.property_code || f.property_name,el.value,f.unit));
  });
  $("features").querySelectorAll("[data-bind]").forEach((el) => el.onchange = () => {
    if (!el.value) return;
    const f=d.features[+el.dataset.bind], option=f.options[+el.value];
    upsert({property:option.property_code,op:f.op,value:option.value ?? f.value,value_to:f.value_to,unit:f.unit});
  });
  $("features").querySelectorAll("[data-delete]").forEach((el) => el.onclick = () => {
    const f=d.features[+el.dataset.delete], key=f.characteristic_ref || f.property_code || f.property_name;
    state.overrides=state.overrides.filter((x)=>x.property!==key);
    state.answers=state.answers.filter((x)=>x.property!==key);
    state.overrides.push({property:key,remove:true}); changed(); run("draft","confirm");
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
  if (d.final_code) {
    $("final").innerHTML = `<div class="card final"><div class="muted small">Конечная позиция КТРУ</div>
      <div class="final__code">${esc(d.final_code)}</div><div>${esc(d.final_name)}</div>
      <div class="small muted" style="margin-top:6px">Все условия проверены в полной области типа; обязательные свойства заполнены.</div></div>`;
    return;
  }
  // код уже однозначен, не хватает только обязательных характеристик СТЕ — показываем код сразу
  const cr = d.code_resolution, cc = d.characteristics_completion;
  if (cr && cr.status === "resolved" && cr.code) {
    const name = (d.candidates.find((c) => c.code === cr.code) || {}).name || "";
    const miss = cc && cc.missing.length ? `Для заполнения СТЕ укажите: <b>${cc.missing.map(esc).join(", ")}</b>` : "";
    const unch = cc && cc.unchecked.length ? ` Не проверено: ${cc.unchecked.map(esc).join(", ")}.` : "";
    $("final").innerHTML = `<div class="card final final--partial"><div class="muted small">Код КТРУ определён</div>
      <div class="final__code">${esc(cr.code)}</div><div>${esc(name)}</div>
      <div class="small" style="margin-top:6px">${miss}${unch}</div>
      <div class="small muted">Код однозначен в полной области типа; ответ на вопрос ниже дозаполнит характеристики.</div></div>`;
    return;
  }
  $("final").innerHTML = "";
}

function renderQuestion(d) {
  const q=d.question;
  if (!q || d.status === "conflict" || d.status === "matched") {$("question").innerHTML="";return;}
  $("question").innerHTML=`<div class="card question"><div class="question__text">${esc(q.text)}</div>
    <div class="options">${q.options.map((o,i)=>`<button class="opt" data-question="${i}">${esc(o.label)}</button>`).join("")}</div>
    ${q.allows_number ? `<div class="num-answer"><input id="qNum" placeholder="Значение" aria-label="Значение"><span>${esc(q.unit||"")}</span><button class="btn btn--small" id="qNumBtn">Применить</button></div>` : ""}</div>`;
  $("question").querySelectorAll("[data-question]").forEach((b)=>b.onclick=()=>{
    const o=q.options[+b.dataset.question], answers=o.answers?.length ? o.answers : o.answer ? [o.answer] : [];
    for (const a of answers) {state.answers=state.answers.filter((x)=>x.property!==a.property);state.answers.push(a);}
    state.answersHash=d.query_hash;state.rejected.push(...(o.reject||[]));state.confirmed.push(...(o.confirm||[]));
    changed();run("draft","confirm");
  });
  if(q.allows_number) $("qNumBtn").onclick=()=>{
    if(!$("qNum").value.trim())return;
    upsert(parseConstraint(q.property_code,$("qNum").value,q.unit));
  };
}
function renderFinal(d) {
  $("final").innerHTML=d.final_code && d.status!=="conflict" ? `<div class="card final"><div>${esc(d.final_name)}</div>
    <div class="small muted">Код каталога: <strong>${esc(d.final_code)}</strong></div></div>` : "";
}
function cleanInfo(...values) {
  return values.filter((v)=>v && !["-","неизвестен","неизвестно"].includes(String(v).toLowerCase())).map(esc).join(" · ");
}
function productCard(p) {
  return `<article class="cand" data-product-id="${esc(p.id)}"><div class="cand__name">${esc(p.name)}</div>
    ${cleanInfo(p.manufacturer,p.country) ? `<div class="small muted">${cleanInfo(p.manufacturer,p.country)}</div>` : ""}
    ${p.characteristics ? `<details><summary>Подробнее</summary><div class="small product-description">${esc(p.characteristics).replace(/\s*\|\s*/g,"<br>")}</div></details>` : ""}</article>`;
}
// Проверки по КТРУ: «не указано» и «не удалось проверить» — разные состояния (unknown_reason)
const CHECK_GROUPS = [
  ["ok", "Совпадает", (k) => k.status === "valid" && !k.wider],
  ["warn", "Подходит, но значение КТРУ шире запроса", (k) => k.status === "valid" && k.wider],
  ["bad", "Не подходит", (k) => k.status === "invalid"],
  ["warn", "Уточните в описании", (k) => k.unknown_reason === "ambiguous" || k.unknown_reason === "unconfirmed"],
  ["warn", "Не удалось проверить", (k) => k.unknown_reason === "not_comparable" || k.unknown_reason === "property_absent"],
  ["muted", "Не указано (обязательное)", (k) => k.unknown_reason === "not_specified"],
];
function checksBlock(checks) {
  return CHECK_GROUPS.map(([cls, title, pick]) => {
    const items = (checks || []).filter(pick);
    if (!items.length) return "";
    const lines = items.map((k) => {
      const val = k.user_value ? `: ${esc(k.user_value)}` : "";
      const why = (k.status === "valid" && !k.wider) || k.unknown_reason === "not_specified" ? "" : ` <span class="muted">— ${esc(k.reason)}</span>`;
      return `<div class="small">${esc(k.property_name)}${val}${why}</div>`;
    }).join("");
    return `<div class="checks-group checks-group--${cls}"><div class="small checks-group__title">${title} (${items.length})</div>${lines}</div>`;
  }).join("");
}
function catalogCard(c) {
  const checks = c.checks || [];
  const ok = checks.filter((k) => k.status === "valid").length, open = checks.filter((k) => k.status === "unknown").length;
  const summary = checks.length ? `Подробнее · совпадает ${ok}${open ? `, открыто ${open}` : ""}` : "Подробнее";
  return `<article class="cand" data-catalog-code="${esc(c.code)}"><div class="cand__name">${esc(c.name)}</div>
    <details><summary>${summary}</summary>${checksBlock(checks)}
      <div class="small muted">Код каталога: ${esc(c.code)}</div></details></article>`;
}
function renderResults(d) {
  if(d.status==="conflict") {
    $("status").hidden=false;$("resultsCard").hidden=true;$("results").innerHTML="";$("resultsPager").innerHTML="";
    state.loadedProducts=[];state.productKey=null;return;
  }
  const result=d.ste_results || {}, key=JSON.stringify([d.query?.original,d.query_profile]);
  if(key!==state.productKey) {state.productKey=key;state.loadedProducts=[...(result.items||[])];}
  state.productResult=result;
  paintResults(d);
}
function paintResults(d) {
  const cats=activeCandidates(d), products=state.loadedProducts, result=state.productResult || {};
  const total=cats.length+(result.total||0);
  $("resultsCard").hidden=!total;
  $("resultsCount").textContent=total ? `(${total.toLocaleString("ru-RU")})` : "";
  $("results").innerHTML=products.map(productCard).join("")+cats.map(catalogCard).join("");
  $("resultsPager").innerHTML=products.length<(result.total||0) ? '<button class="btn btn--ghost" id="loadMore">Показать ещё</button>' : "";
  if($("loadMore")) $("loadMore").onclick=async()=>{
    const revision=sess.revision, currentKey=state.productKey, button=$("loadMore");button.disabled=true;button.textContent="Загружаем…";
    try {
      const r=await fetch("/api/products",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({profile:d.query_profile,offset:products.length,limit:25})});
      if(!r.ok)throw new Error(); const page=await r.json();
      if(revision!==sess.revision || currentKey!==state.productKey)return;
      const ids=new Set(state.loadedProducts.map((p)=>p.id));
      state.loadedProducts.push(...page.items.filter((p)=>!ids.has(p.id)));paintResults(d);
    } catch (_) {if(revision===sess.revision && currentKey===state.productKey){button.disabled=false;button.textContent="Повторить загрузку";}}
  };
}
function parseConstraint(property, raw, unit) {
  const s=String(raw).trim().replace(",",".");let op="eq",value=s,value_to=null;
  const range=s.match(/^(-?\d+(?:\.\d+)?)\s*[–-]\s*(-?\d+(?:\.\d+)?)$/);
  if(range){op="between";value=range[1];value_to=range[2];}
  else for(const [pattern,kind] of [[/^(≥|>=)\s*/,"ge"],[/^(≤|<=)\s*/,"le"],[/^>\s*/,"gt"],[/^<\s*/,"lt"],[/^(≠|!=|не )\s*/,"ne"]]) {
    if(pattern.test(s)){op=kind;value=s.replace(pattern,"");break;}
  }
  return {property,op,value,value_to,unit:unit||null};
}
function upsert(c) {state.overrides=state.overrides.filter((x)=>x.property!==c.property);state.overrides.push(c);changed();run("draft","confirm");}
function renderProps(d) {
  $("addProp").innerHTML=(d.properties||[]).map((p,i)=>`<option value="${i}">${esc(p.name)}</option>`).join("");
  const fill=()=>{const p=d.properties?.[+$("addProp").value];if(!p)return;
    $("addValues").innerHTML=p.values.map((v)=>`<option value="${esc(v)}">`).join("");$("addUnit").value=p.units[0]||"";};
  $("addProp").onchange=fill;fill();
}
function resetForNewText() {
  state.overrides=[];state.answers=[];state.answersHash=null;state.corrections={};state.rejected=[];state.confirmed=[];
  state.productKey=null;state.loadedProducts=[];$("addRow").hidden=true;
}
$("addRowBtn").onclick=()=>{$("addRow").hidden=!$("addRow").hidden;};
$("addApply").onclick=()=>{const p=state.last?.properties?.[+$("addProp").value], value=$("addValue").value.trim();if(!p||!value)return;
  const c=parseConstraint(p.code,value,$("addUnit").value);if(c.op==="eq")c.op=$("addOp").value;$("addValue").value="";upsert(c);};
$("desc").addEventListener("input",()=>{if($("desc").value!==state.text)resetForNewText();state.text=$("desc").value;changed();schedule();});
function submit() {clearTimeout(timer);clearTimeout(modelTimer);changed();run("submitted");}
$("desc").addEventListener("keydown",(e)=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();submit();}});
$("submitBtn").onclick=submit;
$("examples").innerHTML=EXAMPLES.map((e)=>`<button class="chip" type="button">${esc(e)}</button>`).join("");
$("examples").querySelectorAll("button").forEach((b)=>b.onclick=()=>{resetForNewText();$("desc").value=b.textContent;state.text=b.textContent;changed();schedule();});
