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
console.log('Inventory feedback: loading/error stay unknown; confirmed empty stays zero.');
