// Браузерная проверка интерфейса через Chrome DevTools Protocol (без npm-пакетов; node ≥ 22).
// Нужен запущенный Chrome: google-chrome --headless=new --remote-debugging-port=9333 about:blank
// node tools/ui_check.mjs http://127.0.0.1:8765 OUT_DIR
import { writeFileSync, mkdirSync } from "node:fs";

const [, , base = "http://127.0.0.1:8765", out = "reports/ui"] = process.argv;
mkdirSync(out, { recursive: true });
const tabs = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const page = tabs.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0; const wait = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } });
const cdp = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const js = async (expr) => (await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = async (name) => {
  const r = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  writeFileSync(`${out}/${name}.png`, Buffer.from(r.result.data, "base64"));
};
await cdp("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1500, deviceScaleFactor: 1, mobile: false });
await cdp("Page.enable");
await cdp("Page.navigate", { url: base + "/" });
await sleep(1500);
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok, info }); };

async function type(text) {
  await js(`(() => { const d = document.getElementById("desc"); d.value = ${JSON.stringify(text)};
    d.dispatchEvent(new Event("input", { bubbles: true })); })()`);
}
async function enter() {
  await js(`document.getElementById("desc").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }))`);
}

// 1. черновик при вводе
await type("пассатижи слесарные 190 мм");
await sleep(800);
let st = await js(`document.getElementById("status").innerText`);
check("draft_matched", /Определён конечный код/.test(st) && /черновик/.test(st), st.slice(0, 120));
check("ui_state_editing", /Черновик/.test(await js(`document.getElementById("uiState").innerText`)));
check("latency_shown", /Черновик \(ввод → отрисовка\): \d+ мс/.test(await js(`document.getElementById("latency").innerText`)),
  await js(`document.getElementById("latency").innerText`));
await shot("01_draft");

// 2. Enter — полный разбор
await enter();
await sleep(1000);
st = await js(`document.getElementById("status").innerText`);
check("submitted_full", /полный разбор/.test(st), st.slice(0, 120));
check("ui_state_resolved", /Полный разбор/.test(await js(`document.getElementById("uiState").innerText`)));

// 3. быстрый ввод: ответ применяется только для последней версии
for (const t of ["кресло", "кресло офисное", "кресло офисное с подлокотниками", "кресло офисное с подлокотниками черный каркас, красное сиденье"]) {
  await type(t); await sleep(30);
}
await sleep(900);
const feats = await js(`document.getElementById("features").innerText`);
check("last_revision_applied", /Цвет каркаса/.test(feats) && /Цвет сиденья/.test(feats), feats.slice(0, 200));
check("components_shown", /frame/.test(feats) && /seat/.test(feats));
await shot("02_components");

// 4. правдоподобие → подтверждение
await type("кресло офисное с подлокотниками высота сиденья 45 м");
await sleep(800);
const q = await js(`document.getElementById("question").innerText`);
check("plausibility_confirm_question", /Подтвердите трактовку/.test(q), q.slice(0, 200));
await shot("03_confirm");
await js(`document.querySelector("#question button[data-q='0']").click()`);
await sleep(800);
st = await js(`document.getElementById("status").innerText`);
check("confirmed_then_matched", /Определён конечный код/.test(st), st.slice(0, 120));

// 5. смена описания сбрасывает ответы и показывает сброс
await type("пассатижи слесарные");
await sleep(800);
await js(`document.querySelector("#question button[data-q='0']")?.click()`);
await sleep(800);
await type("пассатижи рыбацкие");
await sleep(800);
const corr = await js(`document.getElementById("corrections").innerText`);
check("reset_notice", /сброшены/.test(corr), corr);
await shot("04_reset");

// 6. раздельные результаты: код определён, обязательное не заполнено
await type("дрель ручная электрическая сетевая");
await sleep(800);
const res = await js(`document.getElementById("resolution").innerText`);
check("code_vs_completion", /код определён однозначно/.test(res) && /не завершено/.test(res), res.slice(0, 250));
await shot("05_resolution");

writeFileSync(`${out}/ui_check.json`, JSON.stringify(results, null, 1));
console.log(JSON.stringify(results, null, 1));
ws.close();
process.exit(results.every((r) => r.ok) ? 0 : 1);
