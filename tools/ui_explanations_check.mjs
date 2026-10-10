// Uses an already running Chrome/CDP; opens and closes its own test tab.
const base=process.argv[2]||"http://127.0.0.1:8001";
const target=await(await fetch("http://127.0.0.1:9333/json/new?"+encodeURIComponent(base),{method:"PUT"})).json();
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve)=>ws.addEventListener("open",resolve,{once:true}));
let seq=0;const waits=new Map(),errors=[];
ws.addEventListener("message",(e)=>{const m=JSON.parse(e.data);if(m.id){waits.get(m.id)?.(m);waits.delete(m.id);}if(m.method==="Runtime.exceptionThrown")errors.push(m.params.exceptionDetails);});
const send=(method,params={})=>new Promise((resolve)=>{const id=++seq;waits.set(id,resolve);ws.send(JSON.stringify({id,method,params}));});
const js=async(expression)=>{const r=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result.result.value;};
const sleep=(ms)=>new Promise((resolve)=>setTimeout(resolve,ms));
async function until(expression){const end=Date.now()+15000;while(Date.now()<end){const r=await js(expression);if(r)return r;await sleep(100);}throw Error("Timeout: "+expression);}
async function type(text){await js(`(()=>{const el=document.getElementById('desc');el.value=${JSON.stringify(text)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await until(`state.last?.query?.original===${JSON.stringify(text)}&&state.last.revision===sess.revision`);}
function assert(ok,message){if(!ok)throw Error(message);}
try {
  await send("Runtime.enable");await until("!!document.getElementById('desc') && typeof state !== 'undefined'");
  await type("молоток");
  assert(await js("document.getElementById('ktruCount').innerText.includes('11')"),"Missing KTRU-only count");
  assert(await js("document.getElementById('results').innerText.includes('Позиции КТРУ (11)') && document.getElementById('results').innerText.includes('Примеры товаров СТЕ')"),"Mixed source counters");
  await js("document.getElementById('loadMore').click()");
  await until("document.querySelectorAll('#results [data-product-id]').length > 25");
  await type("стул");await type("стул на металлическом каркасе");
  await type("стул на металлическом каркасе с мягким сиденьем и мягкой спинкой");
  const history=await js("document.getElementById('narrowing').innerText");
  assert(history.includes("11 → 4 → 1"),"Missing narrowing history: "+history);
  await type("перчатки швейные для защиты от внешних воздействий");
  assert(await js("!state.last.final_code && !!state.last.question && !document.getElementById('question').hidden"),"Generic gloves were resolved prematurely");
  await type("перчатки швейные для защиты от внешних воздействий, вид защиты: от пониженных температур");
  assert(await js("state.last.final_code==='14.12.30.150-00000006'"),"Gloves clarification failed");
  await type("дрель ручная электрическая от сети мощность 600 в");
  assert(await js("state.last.status==='conflict' && document.getElementById('explanations').innerText.includes('размерность')"),"Missing dimensional error explanation");
  await type("стул деревянный метеллический");
  assert(await js("state.last.status==='conflict' && document.getElementById('resultsCard').hidden && document.getElementById('corrections').innerText.includes('Исправлено')"),"Conflict/typo explanation failed");
  await type("молоток слесарный 500 г");
  assert(await js("document.getElementById('features').innerText.includes('0,5') && document.getElementById('productFilters').innerText.includes('Масса')"),"Missing conversion/applied filters");
  assert(errors.length===0,JSON.stringify(errors));
  console.log(JSON.stringify({separateCounts:true,narrowing:history,glovesClarified:true,errorExplanation:true,pagination:true,normalization:true,javascriptErrors:errors.length},null,2));
} finally {
  ws.close();await fetch("http://127.0.0.1:9333/json/close/"+target.id);
}
