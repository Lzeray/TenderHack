// End-to-end user interactions: type descriptions, narrow results, let Qwen finish, paginate STE.
const base = process.argv[2] || "http://127.0.0.1:8000";
const tabs = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const ws = new WebSocket(tabs.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let seq = 0; const pending = new Map(), errors = [];
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id) { pending.get(m.id)?.(m); pending.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errors.push(m.params.exceptionDetails);
});
const send = (method, params = {}) => new Promise((r) => { const id=++seq; pending.set(id,r); ws.send(JSON.stringify({id,method,params})); });
const js = async (expression) => {
  const r = await send("Runtime.evaluate", {expression, returnByValue:true, awaitPromise:true});
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
  return r.result?.result?.value;
};
const sleep = (ms) => new Promise((r) => setTimeout(r,ms));
async function until(expression, ms=15000) {
  const end=Date.now()+ms;
  while(Date.now()<end) { const value=await js(expression); if(value) return value; await sleep(100); }
  throw new Error("Timed out: "+expression);
}
async function type(text) {
  await js(`(() => { const el=document.getElementById('desc'); el.value=${JSON.stringify(text)}; el.dispatchEvent(new Event('input',{bubbles:true})); })()`);
  await until(`state.last?.query?.original === ${JSON.stringify(text)} && state.last.revision === sess.revision`);
  const result=await js(`({total:state.last.results_total, cards:document.querySelectorAll('#candidates .cand').length,
    ste:state.last.ste_results?.total, fields:state.last.query_profile?.attributes,
    typePicker:document.getElementById('typePicker').hidden, latency:state.latency.draft?.ms})`);
  if(result.total!==result.cards || !result.typePicker) throw new Error("Incomplete results or mandatory type selection: "+JSON.stringify(result));
  return result;
}
await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable");
await send("Network.setCacheDisabled",{cacheDisabled:true}); await send("Page.navigate",{url:base}); await sleep(1200);
const hammer=[];
for(const q of ["молоток","молоток слесарный","молоток слесарный 500 г"]) hammer.push(await type(q));
if(!(hammer[0].total>hammer[1].total && hammer[1].total===1)) throw new Error("Hammer does not narrow");
if(!(hammer[0].ste>hammer[1].ste && hammer[1].ste>hammer[2].ste)) throw new Error("STE filters do not narrow");
if(!hammer[2].fields.some((a)=>a.value==="0.5" && a.unit==="кг")) throw new Error("Mass not normalized");
const chairs=[];
for(const q of ["стул","стул на металлическом каркасе","стул на металлическом каркасе с мягким сиденьем и мягкой спинкой"]) chairs.push(await type(q));
if(!(chairs[0].total>chairs[1].total && chairs[1].total>chairs[2].total && chairs[2].total===1)) throw new Error("Chair does not narrow");
const white=await type("стол белый");
await until("state.last?.stage==='submitted' && state.last.providers.some(p=>p.name==='qwen' && p.used)",45000);
const model=await js("state.last.providers.find(p=>p.name==='qwen')");
if(!["ok","cached"].includes(model.status)) throw new Error("Automatic model branch failed: "+JSON.stringify(model));
const first=await js("document.querySelector('#steItems .cand__code')?.innerText");
await js("document.querySelector('[data-ste-next]').click()");
await until(`document.querySelector('#steItems .cand__code')?.innerText !== ${JSON.stringify(first)}`);
if(errors.length) throw new Error(JSON.stringify(errors));
console.log(JSON.stringify({hammer,chairs,white,automaticQwen:model,pagination:true,jsErrors:errors.length},null,2));
ws.close();
