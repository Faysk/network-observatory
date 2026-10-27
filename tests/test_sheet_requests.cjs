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
const partialBand=(first,last,value)=>({
 timestamp:stamp(first),timestamp_end:stamp(last),sample_count:4,max_gap_seconds:60,
 rssi_24_dbm:value,values:{rssi_24_dbm:{
   sample_count:2,first_observed_at:stamp(first),last_observed_at:stamp(last),max_gap_seconds:last-first}}
});
const bandPeriod={from:stamp(0),resolution_seconds:240,sampled_preview:false};
const bandLine=rows=>traceContext.trace(rows,'rssi_24_dbm',bandPeriod,
 t=>(Date.parse(t)-origin)/1000,v=>v);
const closeBands=[partialBand(20,150,-69),partialBand(270,350,-67)];
assert(bandLine(closeBands).includes('L'),'Valid sparse 2.4 GHz samples must form a line when observed <180s apart');
const remoteBands=[partialBand(20,100,-69),partialBand(370,420,-67)];
assert(!bandLine(remoteBands).includes('L'),'2.4 GHz must break if metric observations differ by >180s');
const insideGap=[partialBand(20,220,-69),partialBand(270,350,-67)];
assert(!bandLine(insideGap).includes('L'),'An internal gap >180s must not be interpolated');
const oldBands=closeBands.map(({values,...other})=>({...other,values:{rssi_24_dbm:{sample_count:2}}}));
assert(!bandLine(oldBands).includes('L'),'Old API buckets without evidence must remain conservative');
console.log('Wi-Fi per-band adjacency uses actual metric timestamps; missing intervals remain gaps.');


// Signed RSSI bands must not be clamped to a positive 0..1 chart.
const domainContext={Number,Math};vm.createContext(domainContext);
vm.runInContext(source.slice(source.indexOf('function chartDomain('),source.indexOf('function chart('))+';this.domain=chartDomain',domainContext);
const bandDefs=[{key:'rssi_24_dbm',unit:'dBm',scale:1},{key:'rssi_5_dbm',unit:'dBm',scale:1}];
const bands=[
 {rssi_24_dbm:-65,rssi_5_dbm:-58,values:{rssi_24_dbm:{min:-73,max:-63},rssi_5_dbm:{min:-62,max:-55}}},
 {rssi_24_dbm:null,rssi_5_dbm:-56,values:{rssi_24_dbm:{min:null,max:null},rssi_5_dbm:{min:-57,max:-56}}},
 {rssi_24_dbm:-69,rssi_5_dbm:null}
];
const bandDomain=domainContext.domain(bands,bandDefs);
assert(bandDomain.low<=-73&&bandDomain.high>=-55,'RSSI signed extrema must remain inside plot');
assert(bandDomain.high<0,'Negative dBm readings must never use 0..1 default domain');
const only24=domainContext.domain([{rssi_24_dbm:-80,rssi_5_dbm:null}],bandDefs);
assert(only24.low<-80&&only24.high>-80&&only24.high<0,'single 2.4 GHz sample must be visible');
assert.equal(domainContext.domain([{rssi_24_dbm:null,rssi_5_dbm:null}],bandDefs),null,'missing readings have no domain');
const percentDomain=domainContext.domain([{cpu_pct:0},{cpu_pct:67}],[{key:'cpu_pct',unit:'%',scale:1}]);
assert.equal(percentDomain.low,0,'CPU chart keeps nonnegative baseline');
const counterDomain=domainContext.domain([{wan_rx_bytes:2**30},{wan_rx_bytes:4*2**30}],[{key:'wan_rx_bytes',unit:'GiB',scale:2**30}]);
assert.equal(counterDomain.low,0,'nonnegative WAN counter chart still starts at zero');
assert(source.includes("main:'RSSI médio · 2,4 GHz'"),'Wi-Fi legend must not call RSSI client counts');
console.log('Wi-Fi chart: negative dBm domain, partial/missing bands, extrema and other metrics remain correct.');

for(const file of ['app/static/app.js','app/static/s7/js/app.js']){
 const code=fs.readFileSync(file,'utf8'),start=code.indexOf('function parseTelemetryJson('),end=code.indexOf('async function ',start);
 const c={JSON,Number};vm.createContext(c);vm.runInContext(code.slice(start,end)+';this.parse=parseTelemetryJson',c);
 const value=c.parse('{"big":9007199254740993,"negative":-9007199254740993,"literal":"9007199254740993 \\"x\\"","fraction":0.12345678901234567,"exponent":1e3,"zero":0,"unknown":null}');
 assert.equal(value.big,'9007199254740993');assert.equal(value.negative,'-9007199254740993');assert.equal(value.exponent,1000);assert.equal(value.zero,0);assert.equal(value.unknown,null);assert.equal(typeof value.fraction,'number');
}
assert(!traceContext.trace([{...point(840,3),wan_rx_bytes:3},{...point(1740,1),wan_rx_bytes:1}],'wan_rx_bytes',period,t=>Date.parse(t),v=>v).includes('L'),'Counter decrease must interrupt line, not look like negative traffic');
console.log('Precision: unsafe JSON integers preserved; WAN counter decreases remain discontinuities.');
