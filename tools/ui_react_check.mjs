// Real React UI regression through an existing Chrome/CDP. No framework globals are used.
import { writeFile } from "node:fs/promises";

const base = process.argv[2] || "http://127.0.0.1:8001";
const target = await (await fetch("http://127.0.0.1:9333/json/new?about:blank", { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener("open", resolve, { once: true }));
let seq = 0;
const waits = new Map(), exceptions = [], consoleErrors = [];
ws.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (message.id) { waits.get(message.id)?.(message); waits.delete(message.id); }
  if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails);
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") consoleErrors.push(message.params.args);
});
const send = (method, params = {}) => new Promise(resolve => {
  const id = ++seq; waits.set(id, resolve); ws.send(JSON.stringify({ id, method, params }));
});
const js = async expression => {
  const message = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (message.result?.exceptionDetails) throw new Error(JSON.stringify(message.result.exceptionDetails));
  return message.result?.result?.value;
};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(expression, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { const result = await js(expression); if (result) return result; await sleep(100); }
  throw new Error("Timeout: " + expression);
}
function assert(ok, message) { if (!ok) throw new Error(message); }
async function type(text) {
  await js("document.getElementById('desc').focus();document.getElementById('desc').select()");
  await send("Input.insertText", { text });
  await until(`document.querySelector('.catalog-main')?.dataset.query === ${JSON.stringify(text)}`);
}
async function screenshot(path) {
  const shot = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(path, Buffer.from(shot.result.data, "base64"));
}
try {
  await send("Runtime.enable"); await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1050, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url: base });
  await until("!!document.getElementById('desc')");
  assert(await js("document.querySelectorAll('.category-tile').length===3"), "Missing catalogue landing cards");
  await type("моло");
  await until("document.querySelectorAll('#search-suggestions [role=option]').length>0");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "ArrowDown", code: "ArrowDown" });
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter" });
  await until("document.querySelector('.catalog-main')?.dataset.query === 'Молоток'");
  await until("document.querySelectorAll('[data-product-id]').length===25");
  assert(await js("document.getElementById('tab-ktru').innerText.includes('11')"), "KTRU count is not separate");
  assert(await js("document.querySelector('.product-card .card-description').innerText.length>0"), "Missing short description");
  await js("document.querySelector('.card-name').click()");
  await until("document.querySelector('dialog')?.open");
  assert(await js("document.querySelector('dialog').innerText.includes('Характеристики из выгрузки')"), "Missing product details");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await until("!document.querySelector('dialog')");
  await js("document.querySelector('.pagination button').click()");
  await until("document.querySelectorAll('[data-product-id]').length===50");
  if (process.argv.includes("--screenshots")) await screenshot("reports/react_desktop.png");
  await type("стул"); await type("стул на металлическом каркасе");
  await type("стул на металлическом каркасе с мягким сиденьем и мягкой спинкой");
  const history = await js("[...document.querySelectorAll('.narrowing-history > span')].map(s=>s.innerText)");
  assert(JSON.stringify(history.slice(-3)) === '["11","4","1"]', "Invalid narrowing history: " + JSON.stringify(history));
  await js("document.getElementById('tab-ktru').click()");
  await until("document.querySelectorAll('[data-catalog-code]').length===1");
  await type("перчатки швейные для защиты от внешних воздействий");
  assert(await js("!!document.querySelector('#question .choice')"), "Missing clarification");
  await js("[...document.querySelectorAll('#question .choice')].find(b=>b.innerText.includes('пониженных')).click()");
  await until("document.querySelector('.resolved-code')?.innerText.includes('14.12.30.150-00000006')");
  await type("стул деревянный метеллический");
  assert(await js("document.querySelector('.notice-error')?.innerText.includes('противоречие') && !document.querySelector('.product-card')"), "Conflict not visible");
  assert(await js("document.querySelector('.notice-subtle')?.innerText.includes('метеллический')"), "Typo hint not visible");
  await js("document.querySelector('.notice-subtle .text-button').click()");
  await until("document.getElementById('desc').value.includes('металлический')");
  await type("молоток слесарный 500 г");
  assert(await js("document.querySelector('.converted')?.innerText.includes('0,5')"), "Missing unit conversion");
  const input = await js("document.querySelector('[data-feature-name*=Масса] input')?.id");
  assert(input, "Missing editable mass");
  await js(`document.getElementById(${JSON.stringify(input)}).focus();document.getElementById(${JSON.stringify(input)}).select()`);
  await send("Input.insertText", { text: "1000" });
  await js("document.activeElement.blur()");
  await until("[...document.querySelectorAll('.converted')].some(e=>e.innerText.includes('1 кг'))");
  assert(await js("document.querySelector('.applied-filters')?.innerText.includes('1000 г')"), "Raw quantity displayed with a converted number but original unit");
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await sleep(300);
  assert(await js("document.documentElement.scrollWidth <= innerWidth"), "Horizontal overflow on mobile");
  if (process.argv.includes("--screenshots")) await screenshot("reports/react_mobile.png");
  await type("молоток");
  await js("document.getElementById('desc').focus();document.getElementById('desc').select()");
  await send("Input.insertText", { text: "стул на металлическом каркасе" });
  await js("document.getElementById('desc').select()");
  await send("Input.insertText", { text: "молоток слесарный 500 г" });
  await until("document.querySelector('.catalog-main')?.dataset.query==='молоток слесарный 500 г'");
  await sleep(1500);
  assert(await js("document.querySelector('.catalog-main').dataset.query==='молоток слесарный 500 г'"), "Stale request overwrote current query");
  assert(!exceptions.length && !consoleErrors.length, JSON.stringify({ exceptions, consoleErrors }));
  console.log(JSON.stringify({ react: true, autocompleteKeyboard: true, cardsAndDetails: true, pagination: true,
    narrowing: history, clarification: true, errorsAndCorrections: true, manualOverride: true,
    mobileOverflow: false, staleResponsesIgnored: true, javascriptErrors: exceptions.length }, null, 2));
} finally {
  ws.close(); await fetch("http://127.0.0.1:9333/json/close/" + target.id);
}
