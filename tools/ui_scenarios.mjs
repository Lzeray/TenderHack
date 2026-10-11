// Нестандартные действия пользователя в интерфейсе: ввод, дописывание и стирание характеристик, удаление кнопками и
// вручную, очистка строки, ответы на вопросы, опечатки. После каждого шага интерфейс сверяется с ответом сервера:
// строка ввода, карточки КТРУ (совпадают с совместимыми позициями ответа), панели «Выбранные» и «Обязательные»
// (совпадают с признаками ответа), ошибки JavaScript.
//
// Chrome с --remote-debugging-port=9333, сервер:  node tools/ui_scenarios.mjs [http://127.0.0.1:8011] [фильтр]
const base = process.argv[2] || "http://127.0.0.1:8011";
const only = process.argv[3] || "";
const tabs = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const ws = new WebSocket(tabs.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener("open", r, { once: true }));
let seq = 0; const waits = new Map(), errors = [], done = [], pending = new Set();
const responses = new Set();
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.id) { waits.get(m.id)?.(m); waits.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errors.push(m.params.exceptionDetails?.exception?.description || "JS error");
  if (m.method === "Network.requestWillBeSent" && m.params.request.url.endsWith("/api/search")) pending.add(m.params.requestId);
  if (m.method === "Network.responseReceived" && m.params.response.url.endsWith("/api/search")) responses.add(m.params.requestId);
  if (m.method === "Network.loadingFinished") { pending.delete(m.params.requestId); if (responses.has(m.params.requestId)) done.push(m.params.requestId); }
  if (m.method === "Network.loadingFailed") pending.delete(m.params.requestId);
});
const send = (method, params = {}) => new Promise(r => { const id = ++seq; waits.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const js = async expression => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || JSON.stringify(r.result.exceptionDetails));
  return r.result?.result?.value;
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(expr, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await js(expr)) return true; await sleep(100); }
  throw new Error("Timeout: " + expr);
}

// --- действия ---------------------------------------------------------------
const setInput = text => js(`(() => { const el = document.getElementById('desc');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
async function settle() {
  // ввод → черновик (200 мс) → разбор (1000 мс); ждём, пока не останется запросов и скелетонов
  await sleep(1500);
  for (let i = 0; i < 100; i++) {
    const busy = pending.size > 0 || await js("!!document.querySelector('.skeleton-card')");
    if (!busy) { await sleep(250); if (pending.size === 0) return; }
    await sleep(150);
  }
}
async function type(text) { await setInput(text); await sleep(150); await settle(); }
async function enter() { await js("document.querySelector('form.search-box').requestSubmit()"); await settle(); }
async function clearButton() { await js("document.querySelector('.clear-search')?.click()"); await settle(); }
async function openPanels() { await js("document.querySelectorAll('details.side-panel, details.question-panel').forEach(d => d.open = true)"); }
async function removeSelected(name) {
  await openPanels();
  const ok = await js(`(() => { const li = [...document.querySelectorAll('.side-selected .char-item')].find(x => x.querySelector('.char-head b')?.innerText.trim() === ${JSON.stringify(name)});
    const b = li?.querySelector('button[aria-label^="Убрать"]'); if (!b) return false; b.click(); return true; })()`);
  if (!ok) throw new Error("нет кнопки удаления у «" + name + "»");
  await settle();
}
async function setValueIn(panel, name, value) {
  await openPanels();
  const ok = await js(`(() => { const li = [...document.querySelectorAll('${panel} .char-item')].find(x => x.querySelector('.char-head b')?.innerText.trim() === ${JSON.stringify(name)});
    if (!li) return "нет строки";
    const sel = li.querySelector('select');
    if (sel) { const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
      const opt = [...sel.options].find(o => o.value === ${JSON.stringify(value)} || o.text === ${JSON.stringify(value)}); if (!opt) return "нет варианта";
      set.call(sel, opt.value); sel.dispatchEvent(new Event('change', { bubbles: true })); return true; }
    const inp = li.querySelector('input'); if (!inp) return "нет поля";
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    inp.focus(); set.call(inp, ${JSON.stringify(value)}); inp.dispatchEvent(new Event('input', { bubbles: true })); return "blur"; })()`);
  if (ok === "blur") {
    // пауза, как у человека, затем уход с поля (focusout — его слушает React для onBlur)
    await sleep(250);
    await js(`(() => { const li = [...document.querySelectorAll('${panel} .char-item')].find(x => x.querySelector('.char-head b')?.innerText.trim() === ${JSON.stringify(name)});
      li?.querySelector('input')?.dispatchEvent(new FocusEvent('focusout', { bubbles: true })); })()`);
    await settle(); return;
  }
  if (ok !== true) throw new Error(`${panel} «${name}»: ${ok}`);
  await settle();
}
const fillMissing = (name, value) => setValueIn(".side-missing", name, value);
const editSelected = (name, value) => setValueIn(".side-selected", name, value);
async function answer(labelStart) {
  await openPanels();
  const ok = await js(`(() => { const b = [...document.querySelectorAll('#question .choice')].find(x => x.innerText.trim().startsWith(${JSON.stringify(labelStart)}));
    if (!b) return [...document.querySelectorAll('#question .choice')].map(x => x.innerText.trim()).join(" | ") || "нет вопроса"; b.click(); return true; })()`);
  if (ok !== true) throw new Error("нет варианта «" + labelStart + "»: " + ok);
  await settle();
}
async function chooseAmbiguous(optionStart) {
  await openPanels();
  const ok = await js(`(() => { const sel = document.querySelector('.side-selected select.value-select'); if (!sel) return false;
    const opt = [...sel.options].find(o => o.text.startsWith(${JSON.stringify(optionStart)})); if (!opt) return false;
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
    set.call(sel, opt.value); sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
  if (!ok) throw new Error("нет выбора «" + optionStart + "»");
  await settle();
}

async function narrow(s) {
  // отвечаем первым вариантом на то, что спросила система (до двух вопросов)
  for (let i = 0; i < 2; i++) {
    await openPanels();
    const q = await js("[...document.querySelectorAll('#question .choice')].map(x => x.innerText.trim())");
    if (!q || !q.length) break;
    await answer(q[0]).catch(e => fail(s, "ответ " + (i + 1), e.message));
  }
  const u = await ui();
  if (u.cards.length > 8) fail(s, "сужение", `после ответов осталось ${u.cards.length} карточек`);
}

// --- состояние и сверка -------------------------------------------------------
async function lastShown() {
  const input = await js("document.getElementById('desc').value");
  for (const id of [...done].reverse()) {
    const b = await send("Network.getResponseBody", { requestId: id });
    if (!b.result?.body) continue;
    const d = JSON.parse(b.result.body);
    if (d.query?.original === input) return d;
  }
  for (const id of [...done].reverse()) {          // строка исправлена по Enter (орфография): последний ответ
    const b = await send("Network.getResponseBody", { requestId: id });
    if (b.result?.body) return JSON.parse(b.result.body);
  }
  return null;
}
async function ui() {
  await openPanels();
  return js(`(() => ({
    input: document.getElementById('desc').value,
    layout: !!document.querySelector('.catalog-layout'),
    cards: [...document.querySelectorAll('[data-catalog-code]')].map(e => e.dataset.catalogCode),
    count: document.querySelector('.view-label')?.innerText || "",
    selected: [...document.querySelectorAll('.side-selected .char-item')].map(li => ({ name: li.querySelector('.char-head b')?.innerText.trim(),
      tag: li.querySelector('.mini-tag')?.innerText.trim() || "", removable: !!li.querySelector('button[aria-label^="Убрать"]'),
      group: [...li.classList].find(c => c.startsWith('char-') && c !== 'char-item') || "" })),
    missing: [...document.querySelectorAll('.side-missing .char-item')].map(li => li.querySelector('.char-head b')?.innerText.trim()),
    question: document.querySelector('#question summary')?.innerText.trim() || null,
  }))()`);
}
const problems = [];
function fail(scn, step, msg) { problems.push({ scenario: scn, step, problem: msg }); }
async function check(scn, step, expect = {}) {
  const u = await ui();
  const d = u.input.trim() ? await lastShown() : null;
  if (expect.input !== undefined && u.input !== expect.input) fail(scn, step, `строка ввода «${u.input}», ожидалось «${expect.input}»`);
  for (const w of expect.inputHas || []) if (!u.input.toLowerCase().includes(w.toLowerCase())) fail(scn, step, `в строке нет «${w}»: «${u.input}»`);
  for (const w of expect.inputLacks || []) if (u.input.toLowerCase().includes(w.toLowerCase())) fail(scn, step, `в строке осталось «${w}»: «${u.input}»`);
  if (!u.input.trim()) {
    if (u.layout || u.cards.length) fail(scn, step, `строка пуста, а карточки/панели показаны (${u.cards.length})`);
    return { u, d };
  }
  if (!d) { fail(scn, step, "нет ответа сервера для текущей строки"); return { u, d }; }
  const finals = (d.candidates || []).filter(c => c.compatible && !c.is_template).map(c => c.code);
  const expected = d.status === "matched" && d.final_code ? [d.final_code] : finals;
  const a = [...u.cards].sort().join(), b = [...expected].sort().join();
  if (a !== b) fail(scn, step, `карточки (${u.cards.length}) ≠ совместимым позициям ответа (${expected.length}); статус ${d.status}`);
  if ((d.compatible_codes || []).length > finals.length && d.status !== "matched" && !u.count.includes(String(d.compatible_codes.length)))
    fail(scn, step, `показано ${finals.length} карточек из ${d.compatible_codes.length}, а счётчик «${u.count}»`);
  const missing = (d.required_characteristics || []).filter(r => r.status === "missing").map(r => r.name).sort();
  if (u.missing.slice().sort().join("|") !== missing.join("|")) fail(scn, step, `«Обязательные» в панели [${u.missing}] ≠ ответу [${missing}]`);
  const bound = (d.features || []).filter(f => ["bound", "proposed"].includes(f.status) && f.property_name).map(f => f.property_name);
  const shownNames = new Set(u.selected.map(s => s.name));
  for (const n of bound) if (!shownNames.has(n)) fail(scn, step, `признак «${n}» из ответа не показан в «Выбранных»`);
  for (const n of expect.selectedHas || []) if (!shownNames.has(n)) fail(scn, step, `в «Выбранных» нет «${n}»: [${[...shownNames]}]`);
  for (const n of expect.selectedLacks || []) if (shownNames.has(n)) fail(scn, step, `в «Выбранных» осталось «${n}»`);
  if (expect.cardsMax !== undefined && u.cards.length > expect.cardsMax) fail(scn, step, `карточек ${u.cards.length} > ${expect.cardsMax}`);
  if (expect.cardsMin !== undefined && u.cards.length < expect.cardsMin) fail(scn, step, `карточек ${u.cards.length} < ${expect.cardsMin}`);
  if (expect.cardNameAll && u.cards.length) {
    const names = (d.candidates || []).filter(c => u.cards.includes(c.code)).map(c => c.name);
    const bad = names.filter(n => !n.toLowerCase().includes(expect.cardNameAll));
    if (bad.length) fail(scn, step, `карточки не «${expect.cardNameAll}»: ${[...new Set(bad)].slice(0, 3)}`);
  }
  if (expect.status && !expect.status.includes(d.status)) fail(scn, step, `статус ${d.status}, ожидался ${expect.status}`);
  for (const f of (d.features || []).filter(f => f.status === "bound" && f.from_type_name)) {
    const row = u.selected.find(x => x.name === f.property_name);
    if (row?.removable) fail(scn, step, `«${f.property_name}» из слова типа можно удалить кнопкой (вырежет товар из строки)`);
  }
  const reqNames = (d.required_characteristics || []).filter(r => r.status !== "missing").map(r => r.name);
  for (const x of u.selected) if (reqNames.includes(x.name) && x.group !== "char-required") fail(scn, step, `обязательная «${x.name}» не в группе обязательных`);
  if (expect.countLabel && !u.count.includes(expect.countLabel)) fail(scn, step, `счётчик «${u.count}», ожидалось «${expect.countLabel}»`);
  return { u, d };
}

// --- сценарии ----------------------------------------------------------------
const scenarios = {
  async "очистка строки после выбора подтипа (кнопкой)"(s) {
    await type("стул"); await enter();
    await narrow(s);
    await clearButton(); await check(s, "очищено", { input: "" });
    await type("стол"); await enter();
    await check(s, "новый товар «стол»", { cardNameAll: "стол", cardsMin: 30 });
  },
  async "замена всей строки после выбора подтипа (без кнопки)"(s) {
    await type("стул"); await enter();
    await narrow(s);
    await type("стол"); await enter();
    await check(s, "другой товар", { cardNameAll: "стол", cardsMin: 30 });
  },
  async "стирание строки по символам до пустой и новый ввод"(s) {
    await type("куртка"); await enter();
    await narrow(s);
    for (const t of ["куртк", "кур", "к", ""]) await type(t);
    await check(s, "пусто", { input: "" });
    await type("брюки"); await enter();
    await check(s, "брюки", { cardNameAll: "брюки", cardsMin: 10 });
  },
  async "смена типа правкой слова после ответов"(s) {
    await type("стул"); await enter();
    await narrow(s);
    await type("шкаф"); await enter();
    await check(s, "шкаф", { cardNameAll: "шкаф", cardsMin: 20 });
  },
  async "выбор наименования из вопроса и новый товар"(s) {
    await type("брюки"); await enter();
    const { d } = await check(s, "начало");
    if (d?.question?.kind !== "type") return fail(s, "начало", "первый вопрос не о наименовании: " + (d?.question?.property_name || d?.question?.kind));
    await answer("Брюки спортивные").catch(e => fail(s, "ответ", e.message));
    await check(s, "выбрали", { cardNameAll: "брюки спортивные" });
    await type("куртка"); await enter();
    await check(s, "новый товар", { cardNameAll: "куртка", cardsMin: 10 });
  },
  async "удаление вида при типе в том же фрагменте"(s) {
    await type("пассатижи слесарные длиной 190 мм"); await enter();
    await removeSelected("Вид пассатижей").catch(e => fail(s, "удаление вида", e.message));
    await check(s, "удалили вид", { inputHas: ["пассатижи", "190"], inputLacks: ["слесарные"], selectedLacks: ["Вид пассатижей"] });
    await removeSelected("Длина").catch(e => fail(s, "удаление длины", e.message));
    await check(s, "удалили длину", { inputHas: ["пассатижи"], inputLacks: ["190"], selectedLacks: ["Длина"] });
  },
  async "дополнительная характеристика вне КТРУ"(s) {
    await type("стул, цвет: красный"); await enter();
    const u = await ui();
    if (!u.selected.some(x => x.group === "char-extra")) fail(s, "доп", "нет группы дополнительных: " + JSON.stringify(u.selected));
    await check(s, "доп", {});
  },
  async "счётчик при обрезанном списке"(s) {
    await type("одежда"); await enter();
    await check(s, "одежда", { countLabel: "из" });
  },
  async "дописывание характеристики сохраняет ответ на вопрос о типе"(s) {
    await type("брюки"); await enter();
    await answer("Брюки спортивные").catch(e => fail(s, "ответ", e.message));
    await check(s, "после ответа", { cardNameAll: "брюки спортивные" });
    await type("брюки, назначение женские"); await enter();
    await check(s, "дописали", { cardNameAll: "брюки спортивные" });
  },
  async "удаление необязательной кнопкой убирает её из строки"(s) {
    await type("стол деревянный столешница лдсп"); await enter();
    await check(s, "разбор", { selectedHas: ["Тип каркаса", "Вид материала столешницы"] });
    await removeSelected("Тип каркаса").catch(e => fail(s, "удаление", e.message));
    await check(s, "после удаления", { inputLacks: ["деревянный"], selectedLacks: ["Тип каркаса"] });
  },
  async "заполнение обязательной в панели и удаление кнопкой"(s) {
    await type("стол письменный"); await enter();
    const { d } = await check(s, "начало");
    const req = (d?.required_characteristics || []).find(r => r.status === "missing" && r.values?.length);
    if (!req) return fail(s, "начало", "нет незаполненной обязательной с вариантами");
    await fillMissing(req.name, req.values[0]).catch(e => fail(s, "заполнение", e.message));
    await check(s, "заполнено", { inputHas: [req.values[0]], selectedHas: [req.name] });
    await removeSelected(req.name).catch(e => fail(s, "удаление", e.message));
    await check(s, "удалено", { inputLacks: [req.values[0]], selectedLacks: [req.name] });
  },
  async "необязательная из панели, затем удаление вручную из строки"(s) {
    await type("стол письменный"); await enter();
    const { d } = await check(s, "начало");
    const req = (d?.required_characteristics || []).find(r => r.status === "missing" && r.values?.length);
    if (!req) return fail(s, "начало", "нет незаполненной обязательной с вариантами");
    await fillMissing(req.name, req.values[0]).catch(e => fail(s, "заполнение", e.message));
    const u = await ui();
    const cut = u.input.replace(new RegExp(`[,;]?\\s*${req.name}[^,;]*`, "i"), "").trim();
    await type(cut); await enter();
    await check(s, "стёрли вручную", { inputLacks: [req.values[0]], selectedLacks: [req.name] });
  },
  async "правка значения необязательной в панели"(s) {
    await type("стол деревянный столешница лдсп"); await enter();
    await editSelected("Вид материала столешницы", "МДФ").catch(e => fail(s, "правка", e.message));
    await check(s, "после правки", { inputHas: ["мдф"], inputLacks: ["лдсп"] });
  },
  async "выбор варианта неоднозначного значения и стирание фрагмента"(s) {
    await type("стол лдсп"); await enter();
    await chooseAmbiguous("Вид материала столешницы").catch(e => fail(s, "выбор", e.message));
    await check(s, "выбрано", { selectedHas: ["Вид материала столешницы"] });
    await type("стол лдсп деревянный"); await enter();
    await check(s, "дописали", { selectedHas: ["Вид материала столешницы", "Тип каркаса"] });
    await type("стол деревянный"); await enter();
    await check(s, "стёрли «лдсп»", { selectedLacks: ["Вид материала столешницы"] });
  },
  async "ответ на вопрос о характеристике и его удаление кнопкой"(s) {
    await type("пассатижи"); await enter();
    const { d } = await check(s, "начало");
    const q = d?.question;
    if (!q || q.kind !== "property") return fail(s, "начало", "нет вопроса о характеристике");
    await answer(q.options[0].label).catch(e => fail(s, "ответ", e.message));
    await check(s, "ответили", { selectedHas: [q.property_name] });
    await removeSelected(q.property_name).catch(e => fail(s, "удаление", e.message));
    await check(s, "удалили ответ", { selectedLacks: [q.property_name] });
  },
  async "опечатка и Enter"(s) {
    await type("стулл деревяный"); await enter();
    await check(s, "исправлено", { input: "стул деревянный" });
  },
  async "противоречие и его исправление"(s) {
    await type("пассатижи слесарные рыбацкие"); await enter();
    await check(s, "противоречие", { status: ["conflict"] });
    await type("стул металлический"); await enter();
    await check(s, "исправили", { cardsMin: 1 });
  },
  async "быстрый набор без пауз"(s) {
    for (const t of ["ш", "шк", "шка", "шкаф", "шкаф д", "шкаф для о", "шкаф для одежды"]) { await setInput(t); await sleep(60); }
    await settle(); await enter();
    await check(s, "итог", { input: "шкаф для одежды", cardNameAll: "шкаф" });
  },
  async "пробелы вместо текста"(s) {
    await type("стол"); await type("   ");
    await check(s, "пробелы", {});
    const u = await ui();
    if (u.cards.length) fail(s, "пробелы", "показаны карточки для пустой строки");
  },
  async "длинное описание с многими характеристиками"(s) {
    await type("стол письменный, вид материала столешницы: лдсп, вид материала каркаса: металл, конфигурация стола: прямой, назначение стола письменного: для офиса, цвет: белый"); await enter();
    await check(s, "разбор", { selectedHas: ["Вид материала столешницы", "Вид материала каркаса"] });
  },
  async "удаление и повторный ввод той же характеристики"(s) {
    await type("стол деревянный столешница лдсп"); await enter();
    await removeSelected("Вид материала столешницы").catch(e => fail(s, "удаление", e.message));
    await check(s, "удалено", { selectedLacks: ["Вид материала столешницы"] });
    const u = await ui();
    await type(u.input + ", столешница лдсп"); await enter();
    await check(s, "вернули", { selectedHas: ["Вид материала столешницы"] });
  },
  async "правка значения прямо в строке после заполнения через панель"(s) {
    await type("стол деревянный столешница лдсп"); await enter();
    const u = await ui();
    await type(u.input.replace(/лдсп/i, "мдф")); await enter();
    const { d } = await check(s, "правка в строке", { selectedHas: ["Вид материала столешницы"] });
    const f = (d?.features || []).find(x => x.property_name === "Вид материала столешницы");
    if (f && f.value !== "МДФ") fail(s, "правка в строке", `значение «${f.value}», ожидалось «МДФ»`);
  },
  async "числовой ответ на вопрос"(s) {
    await type("пассатижи слесарные"); await enter();
    await openPanels();
    const has = await js("!!document.querySelector('.numeric-answer input')");
    if (!has) return check(s, "без числового вопроса", {});
    await js(`(() => { const el = document.querySelector('.numeric-answer input'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      set.call(el, '190'); el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await sleep(200); await js("document.querySelector('.numeric-answer').requestSubmit()"); await settle();
    await check(s, "ответили числом", { inputHas: ["190"] });
  },
  async "удаление всех характеристик кнопками по очереди"(s) {
    await type("стол письменный, вид материала столешницы: лдсп, вид материала каркаса: металл, конфигурация стола: прямой"); await enter();
    for (let i = 0; i < 5; i++) {
      await openPanels();
      const name = await js(`(() => { const li = [...document.querySelectorAll('.side-selected .char-item')].find(x => x.querySelector('button[aria-label^="Убрать"]'));
        return li?.querySelector('.char-head b')?.innerText.trim() || null; })()`);
      if (!name) break;
      await removeSelected(name).catch(e => fail(s, "удаление " + name, e.message));
      await check(s, "после удаления «" + name + "»", { selectedLacks: [name], inputHas: ["стол"] });
    }
  },
  async "повтор одной характеристики"(s) {
    await type("стол лдсп, столешница лдсп"); await enter();
    await check(s, "повтор", {});
  },
  async "удаление характеристики с отрицанием"(s) {
    await type("стул без подлокотников"); await enter();
    const { d } = await check(s, "разбор");
    const f = (d?.features || []).find(x => x.status === "bound" && !x.from_type_name && x.property_name);
    if (!f) return;
    await removeSelected(f.property_name).catch(e => fail(s, "удаление", e.message));
    await check(s, "удалили", { inputLacks: ["подлокотник"], inputHas: ["стул"], selectedLacks: [f.property_name] });
  },
  async "регистр и ё"(s) {
    await type("СТОЛ Деревянный, Столешница ЛДСП"); await enter();
    await check(s, "регистр", { selectedHas: ["Вид материала столешницы"] });
    await type("стол, тип каркаса: металлический, вид материала столешницы: стёкло закалённое"); await enter();
    await check(s, "ё", {});
  },
  async "английская раскладка и Enter"(s) {
    await type("irfa lkz jlt;ls"); await enter();
    await check(s, "раскладка", { input: "шкаф для одежды", cardNameAll: "шкаф" });
  },
  async "дописывание после выдачи кода"(s) {
    await type("пассатижи слесарные 190 мм"); await enter();
    await check(s, "код");
    await type("пассатижи слесарные 190 мм, цвет: синий"); await enter();
    await check(s, "дописали доп.", {});
    await type("пассатижи слесарные 190 мм, вид пассатижей: рыбацкие"); await enter();
    await check(s, "дописали противоречие", { status: ["conflict"] });
  },
  async "ответ, удаление ответа, снова ответ"(s) {
    await type("пассатижи"); await enter();
    const { d } = await check(s, "начало");
    const q = d?.question;
    if (!q || q.kind !== "property") return;
    await answer(q.options[0].label).catch(e => fail(s, "ответ 1", e.message));
    await removeSelected(q.property_name).catch(e => fail(s, "удаление ответа", e.message));
    await check(s, "удалили ответ", { selectedLacks: [q.property_name] });
    await answer(q.options[1]?.label || q.options[0].label).catch(e => fail(s, "ответ 2", e.message));
    await check(s, "ответ 2", { selectedHas: [q.property_name] });
  },
  async "мусорные запятые и знаки"(s) {
    await type("стол , , деревянный ;; !!! ???"); await enter();
    await check(s, "мусор", { cardNameAll: "стол" });
  },
  async "слитное число и единица"(s) {
    await type("стол высотой 75см"); await enter();
    await check(s, "75см", {});
  },
  async "значение из панели противоречит тексту"(s) {
    await type("стол деревянный"); await enter();
    await fillMissing("Тип каркаса", "Металлический").catch(() => {});
    await check(s, "противоречие из панели", {});
  },
  async "кнопка «Начать новый поиск» при пустой выдаче"(s) {
    await type("пассатижи слесарные рыбацкие"); await enter();
    await js("[...document.querySelectorAll('.empty-results button')].find(b => b.innerText.includes('Начать'))?.click()"); await settle();
    await check(s, "после кнопки", { input: "" });
    await type("стул"); await enter();
    await check(s, "новый поиск", { cardNameAll: "стул" });
  },
  async "кнопка «на главную» после кода"(s) {
    await type("пассатижи слесарные 190 мм"); await enter();
    await check(s, "код", {});
    await js("document.querySelector('.brand').click()"); await settle();
    await check(s, "на главной", { input: "" });
    await type("молоток"); await enter();
    await check(s, "новый поиск", { cardNameAll: "молоток", cardsMin: 5 });
  },
};

await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable");
await send("Network.setCacheDisabled", { cacheDisabled: true });
const report = {};
for (const [name, fn] of Object.entries(scenarios)) {
  if (only && !name.includes(only)) continue;
  done.length = 0; responses.clear();
  await send("Page.navigate", { url: base });
  await until("document.getElementById('desc') instanceof HTMLInputElement", 30000);
  await sleep(300);
  const before = problems.length, errs = errors.length;
  try { await fn(name); } catch (e) { fail(name, "исключение", e.message); }
  if (errors.length > errs) fail(name, "js", errors.slice(errs).join("; "));
  report[name] = problems.length === before ? "ok" : problems.slice(before).map(p => `${p.step}: ${p.problem}`);
}
console.log(JSON.stringify(report, null, 2));
console.log(`\nсценариев: ${Object.keys(report).length}, с проблемами: ${Object.values(report).filter(v => v !== "ok").length}`);
ws.close();
