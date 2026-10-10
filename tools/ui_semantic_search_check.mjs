// Focused CDP regression: real typing updates relevant previews and preserves revision guards.
// Uses an already running Chrome at --remote-debugging-port=9333; no npm dependencies.
const base = process.argv[2] || "http://127.0.0.1:8000";
const tabs = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const page = tabs.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map(), errors = [];
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id) { pending.get(m.id)?.(m); pending.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errors.push(m.params.exceptionDetails);
});
const send = (method, params = {}) => new Promise((resolve) => {
  const n = ++id; pending.set(n, resolve); ws.send(JSON.stringify({ id: n, method, params }));
});
const js = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
  return r.result?.result?.value;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const type = (text) => js(`(() => { const el=document.getElementById('desc'); el.value=${JSON.stringify(text)}; el.dispatchEvent(new Event('input',{bubbles:true})); })()`);
await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable");
await send("Network.setCacheDisabled", { cacheDisabled: true });
await send("Page.navigate", { url: base }); await sleep(1000);
await type("молоток"); await sleep(1000);
const first = await js("document.querySelector('#candidates .cand__name')?.innerText");
const title = await js("document.getElementById('candTitle').innerText");
if (!first?.includes("Молоток") || !title.includes("Предварительные")) throw new Error(`Unexpected preview: ${first}, ${title}`);
for (const q of ["ст", "стул", "стул на металлическом каркасе"]) { await type(q); await sleep(30); }
await sleep(1100);
const latest = await js("document.querySelector('#candidates .cand__name')?.innerText");
const typingLatencyMs = await js("state.latency.draft?.ms");
if (!latest?.includes("Стул")) throw new Error(`Late/irrelevant preview: ${latest}`);
await js("document.querySelector('#question button[data-q=\"0\"]').click()"); await sleep(1000);
const confirmedTitle = await js("document.getElementById('candTitle').innerText");
if (confirmedTitle !== "Кандидаты") throw new Error("Type confirmation did not switch to real validation");
if (errors.length) throw new Error(JSON.stringify(errors));
console.log(JSON.stringify({ typing_preview: first, rapid_typing_preview: latest, typingLatencyMs, confirmedTitle, javascript_errors: errors.length }, null, 2));
ws.close();
