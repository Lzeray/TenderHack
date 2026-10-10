// Сценарий интерфейса: скрытая строка «тип; ключ: значение» (docs/PARSE_INPUT_PLAN.md, P4).
// Chrome с --remote-debugging-port=9333, сервер на 127.0.0.1:8000:
//   node tools/ui_canonical_check.mjs [http://127.0.0.1:8000]
const base = process.argv[2] || "http://127.0.0.1:8000";
const tabs = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const ws = new WebSocket(tabs.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener("open", r, { once: true }));
let seq = 0; const waits = new Map(), errors = [], requests = [];
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.id) { waits.get(m.id)?.(m); waits.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errors.push(m.params.exceptionDetails);
  if (m.method === "Network.requestWillBeSent" && m.params.request.url.endsWith("/api/search"))
    requests.push(JSON.parse(m.params.request.postData || "{}"));
  if (m.method === "Network.loadingFinished" && responses.has(m.params.requestId)) done.push(m.params.requestId);
  if (m.method === "Network.responseReceived" && m.params.response.url.endsWith("/api/search")) responses.add(m.params.requestId);
});
const responses = new Set(), done = [];
// последний ответ, который показан на экране: тот же текст, что в поле ввода
async function shown() {
  const input = await js("document.getElementById('desc').value");
  for (const id of [...done].reverse()) {
    const b = await send("Network.getResponseBody", { requestId: id });
    const d = JSON.parse(b.result.body);
    if (d.query?.original === input) return d;
  }
  return null;
}
const boundOf = d => (d?.features || []).filter(f => f.status === "bound").map(f => `${f.property_name}=${f.value}`);
const send = (method, params = {}) => new Promise(r => { const id = ++seq; waits.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const js = async expression => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
  return r.result?.result?.value;
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(expr, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { const v = await js(expr); if (v) return v; await sleep(100); }
  const shown = await js("document.querySelector('.chars-panel')?.innerText?.slice(0, 600)");
  throw new Error("Timeout: " + expr + " | Панель: " + shown + " | Ввод: " + await js("document.getElementById('desc').value"));
}
const panel = () => js("document.querySelector('.chars-panel')?.innerText || ''");
const settled = () => sleep(1600);    // черновик 200 мс + разбор 1000 мс
async function type(text) {
  if (process.env.UI_DEBUG) console.error("ввод:", text, "| поле:", await js("String(document.getElementById('desc'))"), await js("location.href"));
  await js(`(() => { const el = document.getElementById('desc');
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    set.call(el, ${JSON.stringify(text)}); el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await sleep(250);                   // React применяет ввод до отправки формы
}
async function enter() {
  await js("document.querySelector('form.search-box').requestSubmit()");
  await settled();
}
await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable");
await send("Network.setCacheDisabled", { cacheDisabled: true });
await send("Page.navigate", { url: base });
await until("document.getElementById('desc') instanceof HTMLInputElement", 30000);
const out = {};

// 1. «стол деревянный столешница лдсп» — без вопросов о привязке
await type("стол деревянный столешница лдсп"); await enter();
let p = await panel();
out.parse = { frame: p.includes("Тип каркаса"), tabletop: p.includes("Вид материала столешницы"), ask: p.includes("Уточните свойство") };
if (!out.parse.frame || !out.parse.tabletop || out.parse.ask) throw new Error("parse: " + JSON.stringify(out.parse) + "\n" + p);

// 2. «стол лдсп»: выбор варианта убирает плашку; дописали текст — выбор остался; стёрли «лдсп» — выбора нет
await type("стол лдсп"); await enter();
await until("!!document.querySelector('.char-select')");
await js(`(() => { const s = document.querySelector('.char-select');
  const i = [...s.options].findIndex(o => o.text.startsWith('Вид материала столешницы'));
  s.value = String(i - 1); s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
await settled();
const TOP = "Вид материала столешницы=ЛДСП";
out.choice = { selectGone: !(await js("!!document.querySelector('.char-select')")), value: boundOf(await shown()).includes(TOP) };
await type("стол лдсп деревянный"); await enter();
let d = await shown();
out.choiceAfterAppend = { selectGone: !(await js("!!document.querySelector('.char-select')")), value: boundOf(d).includes(TOP),
  frame: boundOf(d).includes("Тип каркаса=Деревянный"), canonical: d?.canonical?.text };
await type("стол деревянный"); await enter();
d = await shown();
out.choiceAfterDelete = { value: boundOf(d).includes(TOP), canonical: d?.canonical?.text };
if (!out.choice.selectGone || !out.choiceAfterAppend.selectGone || !out.choiceAfterAppend.value || out.choiceAfterDelete.value)
  throw new Error("choice: " + JSON.stringify(out));

// 3. орфография по Enter: в строке ввода исправляется только она
await type("стулл деревяный"); await enter();
out.spelling = await js("document.getElementById('desc').value");
if (out.spelling !== "стул деревянный") throw new Error("spelling: " + out.spelling);

out.canonicalSent = requests.filter(r => r.canonical).length;
out.lastCanonical = requests.at(-1)?.canonical?.text;
out.javascriptErrors = errors.length;
if (errors.length) throw new Error(JSON.stringify(errors));
console.log(JSON.stringify(out, null, 2));
ws.close();
