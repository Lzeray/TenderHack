// User-facing regression: unified results, no debug prose, conflicting input, recovery and load more.
const base=process.argv[2]||"http://127.0.0.1:8000";
const tabs=await(await fetch("http://127.0.0.1:9333/json/list")).json();
const ws=new WebSocket(tabs.find((t)=>t.type==="page").webSocketDebuggerUrl);
await new Promise((r)=>ws.addEventListener("open",r,{once:true}));
let seq=0;const waits=new Map(),errors=[];
ws.addEventListener("message",(e)=>{const m=JSON.parse(e.data);if(m.id){waits.get(m.id)?.(m);waits.delete(m.id);}if(m.method==="Runtime.exceptionThrown")errors.push(m.params.exceptionDetails);});
const send=(method,params={})=>new Promise((r)=>{const id=++seq;waits.set(id,r);ws.send(JSON.stringify({id,method,params}));});
const js=async(expression)=>{const r=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.result?.exceptionDetails)throw new Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result?.value;};
const sleep=(ms)=>new Promise((r)=>setTimeout(r,ms));
async function until(expr,timeout=15000){const end=Date.now()+timeout;while(Date.now()<end){const r=await js(expr);if(r)return r;await sleep(100);}throw new Error("Timeout: "+expr);}
async function type(text){await js(`(()=>{const el=document.getElementById('desc');el.value=${JSON.stringify(text)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await until(`state.last?.query?.original===${JSON.stringify(text)}&&state.last.revision===sess.revision`);}
await send("Runtime.enable");await send("Page.enable");await send("Network.enable");await send("Network.setCacheDisabled",{cacheDisabled:true});
await send("Page.navigate",{url:base});await sleep(1200);
await type("молоток");
const unified=await js("({catalog:document.querySelectorAll('#results [data-catalog-code]').length,products:document.querySelectorAll('#results [data-product-id]').length,heading:document.getElementById('resultsCount').innerText})");
if(!unified.catalog||!unified.products)throw new Error("Results are not unified");
const debug=await js(`new RegExp(${JSON.stringify("unknown|тип/название:|покрытие терминов:|Проверки свойств|Снимок КТРУ|Версии:|Qwen|\\bv\\d+\\b")}).test(document.body.innerText)`);
if(debug)throw new Error("Technical prose remains visible");
await js("document.getElementById('loadMore').click()");
await until("document.querySelectorAll('#results [data-product-id]').length>25");
await type("стул деревянный метеллический");
const conflict=await js("({status:state.last.status,message:document.getElementById('status').innerText,hidden:document.getElementById('resultsCard').hidden,cards:document.querySelectorAll('#results .cand').length,correction:document.getElementById('corrections').innerText})");
if(conflict.status!=="conflict"||!conflict.hidden||conflict.cards||!conflict.message.includes("Уточните описание"))throw new Error(JSON.stringify(conflict));
await until("state.last.stage==='submitted'",10000);
if(await js("state.last.status!=='conflict'"))throw new Error("Model overrode conflict");
await type("стул на металлическом каркасе");
if(await js("document.getElementById('resultsCard').hidden"))throw new Error("Search did not recover after correction");
const colors=await js("getComputedStyle(document.querySelector('.topbar')).backgroundColor");
if(colors!=="rgb(31, 58, 104)")throw new Error("Brand styling changed");
await type("молоток слесарный 500 г");
if(!await js("document.getElementById('features').innerText.includes('0,5')"))throw new Error("Useful unit conversion was removed");
if(errors.length)throw new Error(JSON.stringify(errors));
console.log(JSON.stringify({unified,conflict,recovery:true,loadMore:true,normalization:true,brandColor:colors,javascriptErrors:0},null,2));
ws.close();
