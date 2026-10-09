"use strict";
// Состояние сеанса: текст, ручные правки, ответы на уточнения, выбор исправлений опечаток.
const state = { text: "", overrides: [], answers: [], answersHash: null, corrections: {}, last: null, lastReq: null };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STATUS_TEXT = {
  matched: "Определён конечный код КТРУ", clarification_needed: "Нужно уточнение", conflict: "Противоречие",
  not_found: "Ничего не найдено", manual_choice: "Нужен ручной выбор", error: "Ошибка",
};
const EXAMPLES = [
  "пассатижи слесарные 180 мм",
  "стул на металлическом каркасе с мягким сиденьем и мягкой спинкой",
  "шуроповерт аккумуляторный 2 аккумулятора",
  "молоток кровельный 0,5 кг",
  "куртка зимняя из кожи мужская размер 52",
  "дрель ручная электрическая мощность 500 в",
];

let timer = null, seq = 0;

function schedule() { clearTimeout(timer); timer = setTimeout(run, 600); }

async function run() {
  const text = $("desc").value.trim();
  if (!text) { renderIdle(); return; }
  const req = { text, overrides: state.overrides, answers: state.answers, corrections: state.corrections };
  if (state.answersHash) req.answers_query_hash = state.answersHash;
  const my = ++seq;
  $("status").className = "status";
  $("status").innerHTML = '<span class="spinner"></span>Поиск…';
  try {
    const r = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const data = await r.json();
    if (my !== seq) return; // пришёл устаревший ответ
    state.last = data; state.lastReq = req;
    render(data);
  } catch (e) {
    if (my !== seq) return;
    $("status").className = "status status--error";
    $("status").textContent = "Ошибка запроса: " + e.message;
  }
}

function renderIdle() {
  $("status").className = "status status--idle"; $("status").textContent = "Ожидание описания";
  for (const id of ["final", "question", "stages", "candidates", "corrections", "unrecognized", "completeness"]) $(id).innerHTML = "";
  $("features").innerHTML = '<tr><td colspan="5" class="muted">Введите описание</td></tr>';
  $("issuesCard").hidden = true; $("historyBox").hidden = true; $("exportBtn").disabled = true; $("addRowBtn").disabled = true;
}

function render(d) {
  $("status").className = "status status--" + d.status;
  $("status").innerHTML = `${esc(STATUS_TEXT[d.status] || d.status)}<small>${esc(d.message)}</small>`;
  $("exportBtn").disabled = false;
  $("addRowBtn").disabled = !d.properties.length;
  renderCorrections(d); renderHistory(d); renderFeatures(d); renderFinal(d); renderQuestion(d);
  renderIssues(d); renderStages(d); renderCandidates(d); renderProps(d);
  $("versions").textContent = "Версии: " + Object.entries(d.versions).map(([k, v]) => `${k} ${v}`).join(" · ") + ` · ${d.elapsed_ms} мс`;
}

function renderCorrections(d) {
  const box = $("corrections"); box.innerHTML = "";
  for (const c of d.corrections) {
    if (c.status === "corrected" || c.status === "user_choice") {
      box.insertAdjacentHTML("beforeend", `<div class="small" style="margin-top:8px">Исправлено: <span class="chip chip--ok">${esc(c.original)} → ${esc(c.corrected)}</span> <span class="muted">${esc(c.note)}</span></div>`);
    } else {
      const opts = c.options.map((o) => `<button class="chip chip--warn" data-orig="${esc(c.original)}" data-opt="${esc(o)}">${esc(o)}</button>`).join(" ");
      box.insertAdjacentHTML("beforeend", `<div class="small" style="margin-top:8px">«${esc(c.original)}» — выберите вариант: ${opts} <button class="chip" data-orig="${esc(c.original)}" data-opt="${esc(c.original)}">оставить как есть</button></div>`);
    }
  }
  box.querySelectorAll("button[data-orig]").forEach((b) => b.onclick = () => { state.corrections[b.dataset.orig] = b.dataset.opt; run(); });
}

function renderHistory(d) {
  const h = d.query.history || [];
  $("historyBox").hidden = !h.length;
  $("history").innerHTML = h.map((s) => `<li><b>${esc(s.step)}</b>: ${esc(s.note)}<br><span class="muted">${esc(s.before)} → ${esc(s.after)}</span></li>`).join("");
}

const SRC = { text: ["из текста", "tag--text"], override: ["вручную", "tag--override"], answer: ["ответ", "tag--answer"] };
const FST = {
  bound: ["", ""], ambiguous: ["неоднозначно", "tag--warn"], unknown_property: ["нет такого свойства", "tag--bad"],
  overridden: ["переопределено", "tag--muted"], removed: ["удалено", "tag--muted"],
};

function featureValue(f) {
  const ops = { eq: "", ne: "≠ ", ge: "≥ ", gt: "> ", le: "≤ ", lt: "< " };
  if (f.op === "between") return `${f.value}–${f.value_to}`;
  return (ops[f.op] || "") + (f.value ?? "");
}

function renderFeatures(d) {
  const tb = $("features");
  if (!d.features.length) { tb.innerHTML = '<tr><td colspan="5" class="muted">Характеристики не извлечены</td></tr>'; }
  else {
    tb.innerHTML = d.features.map((f, i) => {
      const [srcT, srcC] = SRC[f.source]; const [stT, stC] = FST[f.status];
      const dim = f.status === "overridden" || f.status === "removed";
      let prop = f.property_name ? esc(f.property_name) : '<span class="muted">—</span>';
      if (f.status === "ambiguous" && f.options.length) {
        prop = `<select data-amb="${i}"><option value="">выберите свойство…</option>${f.options.map((o, k) => `<option value="${k}">${esc(o.property_name)}${o.value ? " = " + esc(o.value) : ""}</option>`).join("")}</select>`;
      }
      const editable = f.status === "bound" && f.property_name;
      const val = editable ? `<input data-edit="${i}" value="${esc(featureValue(f))}" size="10">` : `<span class="${dim ? "strike" : ""}">${esc(featureValue(f))}</span>`;
      const ev = f.evidence ? `<div class="ev">«${esc(f.evidence)}»</div>` : "";
      const note = f.note ? `<div class="ev">${esc(f.note)}</div>` : "";
      const del = f.property_name && f.status === "bound" ? `<button class="btn btn--danger btn--small" data-del="${i}" title="удалить">✕</button>` : "";
      return `<tr><td>${prop}${ev}</td><td>${val}${note}</td><td>${esc(f.unit || "")}</td>
        <td><span class="tag ${srcC}">${srcT}</span> ${stT ? `<span class="tag ${stC}">${stT}</span>` : ""}</td><td>${del}</td></tr>`;
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
    run();
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
  state.overrides.push(c); run();
}

function renderFinal(d) {
  $("final").innerHTML = d.final_code ? `<div class="card final"><div class="muted small">Конечная позиция КТРУ</div>
    <div class="final__code">${esc(d.final_code)}</div><div>${esc(d.final_name)}</div>
    <div class="small muted" style="margin-top:6px">Все условия проверены в полной области типа; обязательные свойства заполнены.</div></div>` : "";
}

function renderQuestion(d) {
  const q = d.question; const box = $("question");
  if (!q) { box.innerHTML = ""; return; }
  const opts = q.options.map((o, i) => `<button class="opt" data-q="${i}">${esc(o.label)}<small>→ ${o.remaining}</small></button>`).join("");
  const num = q.allows_number ? `<div class="num-answer"><input id="qNum" placeholder="число"><span>${esc(q.unit || "")}</span><button class="btn btn--small" id="qNumBtn">Ответить</button></div>` : "";
  box.innerHTML = `<div class="card question"><div class="question__text">${esc(q.text)}</div>
    <div class="small muted" style="margin-bottom:8px">Сейчас ${q.current_remaining} поз.; в худшем случае останется ${q.worst_case_remaining}. ${esc(q.reason)}</div>
    <div class="options">${opts}</div>${num}</div>`;
  box.querySelectorAll("button[data-q]").forEach((b) => b.onclick = () => answer(q.options[+b.dataset.q].answer, d.query_hash));
  if (q.allows_number) $("qNumBtn").onclick = () => {
    const v = $("qNum").value.trim(); if (!v) return;
    answer(parseConstraint(q.property_code, v, q.unit), d.query_hash);
  };
}

function answer(c, hash) {
  if (q_isManual(c)) { state.overrides = state.overrides.filter((o) => o.property !== "__type__"); }
  state.answers = state.answers.filter((a) => a.property !== c.property);
  state.answers.push(c); state.answersHash = hash; run();
}
const q_isManual = (c) => c.property === "__type__";

function renderIssues(d) {
  $("issuesCard").hidden = !d.issues.length;
  $("issues").innerHTML = d.issues.map((i) => `<li class="${i.level}">${esc(i.message)}</li>`).join("");
}

function renderStages(d) {
  $("stages").innerHTML = d.stages.map((s) => `<li>${esc(s.stage)}: <b>${s.remaining}</b>${s.removed ? ` <span class="muted">(−${s.removed})</span>` : ""}<div class="small muted">${esc(s.note)}</div></li>`).join("");
  const c = d.completeness;
  $("completeness").innerHTML = `Бэкенд: ${esc(c.backend)}. Поиск: ${c.retrieval_returned} из ${c.retrieval_total_hits}${c.retrieval_complete ? "" : " (top-K)"}.
    Область типа: ${c.type_domain_returned} из ${c.type_domain_total} — ${c.type_domain_complete ? "проверена полностью" : "проверена НЕ полностью"}.
    Тип ${c.type_confirmed ? "подтверждён" : "не подтверждён"}. ${esc(c.note)}`;
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
  // новое описание: прежние ответы на уточнения больше не относятся к нему
  if ($("desc").value.trim() !== state.text) { state.answers = []; state.answersHash = null; state.corrections = {}; }
  state.text = $("desc").value.trim();
  schedule();
});
$("examples").innerHTML = EXAMPLES.map((e) => `<button class="chip" type="button">${esc(e)}</button>`).join("");
$("examples").querySelectorAll("button").forEach((b) => b.onclick = () => {
  $("desc").value = b.textContent; state.overrides = []; state.answers = []; state.answersHash = null; state.corrections = {};
  state.text = b.textContent; run();
});
fetch("/api/catalog").then((r) => r.json()).then((c) => {
  const cov = Object.values(c.coverage || {}).map((x) => `${x.title}: ${x.active_final} кон. / ${x.active_templates} шабл.`).join(" · ");
  $("catalogInfo").innerHTML = `Снимок КТРУ: ${esc(c.snapshot)} · на дату ${esc(c.as_of)} · поиск: ${esc(c.search_backend)}<br>${esc(cov)}`;
}).catch(() => { $("catalogInfo").textContent = "каталог недоступен"; });
