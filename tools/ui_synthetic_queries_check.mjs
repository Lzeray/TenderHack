// Real browser input for a deterministic stratified sample of the catalogue-generated suite.
// Does not mark catalogue correctness as passed merely because rendering works.
import {readFileSync,writeFileSync} from "node:fs";
const base=process.argv[2]||"http://127.0.0.1:8000", out=process.argv[3]||"reports/synthetic_browser.json";
const cases=readFileSync(new URL("../benchmark/suites/synthetic.jsonl",import.meta.url),"utf8").trim().split("\n").map(JSON.parse);
const selected=[],counts=new Map();
for(const c of cases){const variant=c.id.split("-").at(-1),key=c.category+":"+variant;if((counts.get(key)||0)>=2)continue;counts.set(key,(counts.get(key)||0)+1);selected.push(c);}
const tabs=await(await fetch("http://127.0.0.1:9333/json/list")).json();
const ws=new WebSocket(tabs.find(t=>t.type==="page").webSocketDebuggerUrl);
await new Promise(r=>ws.addEventListener("open",r,{once:true}));
let seq=0;const waits=new Map(),errors=[];
ws.addEventListener("message",e=>{const m=JSON.parse(e.data);if(m.id){waits.get(m.id)?.(m);waits.delete(m.id);}if(m.method==="Runtime.exceptionThrown")errors.push(m.params.exceptionDetails);});
const send=(method,params={})=>new Promise(r=>{const id=++seq;waits.set(id,r);ws.send(JSON.stringify({id,method,params}));});
const js=async expression=>{const r=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.result?.exceptionDetails)throw new Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result?.value;};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(expr){const end=Date.now()+20000;while(Date.now()<end){const r=await js(expr);if(r)return r;await sleep(75);}throw new Error("Timeout: "+expr);}
async function type(text){await js(`(()=>{const el=document.getElementById('desc');el.value=${JSON.stringify(text)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await until(`state.last?.query?.original===${JSON.stringify(text)}&&state.last.revision===sess.revision`);return await js(`({revision:state.last.revision,status:state.last.status,finalCode:state.last.final_code,total:state.last.results_total,visibleCodes:[...document.querySelectorAll('#results [data-catalog-code]')].map(el=>el.dataset.catalogCode),compatible:state.last.compatible_codes,resultsHidden:document.getElementById('resultsCard').hidden,profile:state.last.query_profile})`);}
await send("Runtime.enable");await send("Page.enable");await send("Network.enable");await send("Network.setCacheDisabled",{cacheDisabled:true});await send("Page.navigate",{url:base});await sleep(1000);
const rows=[];
for(const c of selected){const r=await type(c.text);const rendered=r.status==="conflict"?r.visibleCodes.length===0:r.visibleCodes.length===r.total;const catalogueExpected=c.expected_status.includes(r.status==="clarification_needed"?"clarification":r.status);rows.push({id:c.id,text:c.text,rendered,expectedStatus:catalogueExpected,...r});if(!rendered)throw new Error("Incomplete rendering: "+c.id);}
for(const text of ["ст","стул дерев","стул деревянный метеллический"]){await js(`document.getElementById('desc').value=${JSON.stringify(text)};document.getElementById('desc').dispatchEvent(new Event('input',{bubbles:true}))`);await sleep(25);}
await until("state.last?.query?.original==='стул деревянный метеллический'&&state.last.revision===sess.revision");
const conflict=await js("state.last.status==='conflict'&&document.getElementById('resultsCard').hidden");
const recovery=await type("стул на металлическом каркасе");
if(!conflict||recovery.total===0||errors.length)throw new Error("Stateful input checks failed");
const report={source:"benchmark/suites/synthetic.jsonl",selection:"up to 2 cases per category/variant, in file order",cases:rows.length,rendered:rows.filter(r=>r.rendered).length,statusMatches:rows.filter(r=>r.expectedStatus).length,rapidInputGuard:true,conflict:true,recovery:true,javascriptErrors:errors.length,rows};
writeFileSync(out,JSON.stringify(report,null,2));console.log(JSON.stringify({...report,rows:undefined},null,2));ws.close();
