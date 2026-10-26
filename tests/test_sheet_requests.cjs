'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/static/app.js','utf8');
let requests=[];
const context={state:{overview:null},AbortController,DOMException,Date,Map,Set,setTimeout,clearTimeout,
 fetch:(_url,{signal})=>new Promise((resolve,reject)=>{
  const request={resolve:()=>resolve({ok:true,json:async()=>({period:{key:'24h'},stats:{},series:[]})})};
  requests.push(request);
  signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
 })};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('async function api('),source.indexOf('function resourceMarkup('))+';this.sheetBundle=sheetBundle',context);
(async()=>{
 const first=new AbortController();
 const old=context.sheetBundle('24h',first.signal).catch(e=>e.name);
 first.abort();
 const next=context.sheetBundle('24h',new AbortController().signal);
 assert.equal(requests.length,2,'Reopening an aborted key must start a fresh request');
 requests[1].resolve();
 assert.equal(await old,'AbortError');
 assert.equal((await next).period.key,'24h');
 const cached=await context.sheetBundle('24h',new AbortController().signal);
 assert.equal(cached.period.key,'24h');assert.equal(requests.length,2);
 console.log('Sheet requests: cancelled-key reentry succeeds and valid bundle remains cached.');
})().catch(e=>{console.error(e);process.exitCode=1});

const inventoryContext={state:{api:true,clients:[],resources:{inventory:{phase:'loading'}}}};
vm.createContext(inventoryContext);
vm.runInContext(source.slice(source.indexOf('function appOnline()'),source.indexOf('function renderHome()'))+';this.count=appOnline',inventoryContext);
assert.equal(inventoryContext.count(),null,'Pending inventory is unknown, not zero');
inventoryContext.state.resources.inventory.phase='empty';assert.equal(inventoryContext.count(),0);
inventoryContext.state.resources.inventory.phase='error';assert.equal(inventoryContext.count(),null);
inventoryContext.state.clients=[{quality:'ok',reported_status:'Online'}];inventoryContext.state.resources.inventory={phase:'loading',at:123};assert.equal(inventoryContext.count(),1,'Known count should survive refresh');inventoryContext.state.resources.inventory.phase='stale';assert.equal(inventoryContext.count(),null,'Failed refresh must not label old count live');
console.log('Inventory feedback: loading/error stay unknown; confirmed empty stays zero.');

// Preview samples are intentionally sparse; connect adjacent sampled buckets.
const traceContext={Date,Number,Math};vm.createContext(traceContext);
vm.runInContext(source.slice(source.indexOf('function seriesPath('),source.indexOf('function chart('))+';this.trace=seriesPath',traceContext);
const origin=Date.parse('2026-01-01T00:00:00Z'),stamp=seconds=>new Date(origin+seconds*1000).toISOString();
const point=(seconds,value)=>({timestamp:stamp(seconds),timestamp_end:stamp(seconds),value,max_gap_seconds:0,sample_count:1});
const period={from:stamp(0),resolution_seconds:900,sampled_preview:true};
const draw=rows=>traceContext.trace(rows,'value',period,t=>(Date.parse(t)-origin)/1000,v=>v);
assert.equal((draw([point(840,0),point(1740,2),point(2640,3)]).match(/L/g)||[]).length,2);
assert(!draw([point(840,1),point(2640,2)]).includes('L'),'Missing summary bucket must break line');
assert(!draw([point(840,1),point(1740,null),point(2640,2)]).includes('L'),'Unknown must break line');
assert(!traceContext.trace([point(0,1),point(600,2)],'value',{...period,sampled_preview:false},t=>Date.parse(t),v=>v).includes('L'),'Real detailed gaps must remain gaps');
console.log('Router lines: adjacent preview buckets connect; missing/null/detailed gaps remain interrupted.');
