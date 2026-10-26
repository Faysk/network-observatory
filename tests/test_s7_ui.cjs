const fs=require('fs'),vm=require('vm'),assert=require('assert');
const element=()=>({innerHTML:'',textContent:'',dataset:{},className:'',classList:{add(){},remove(){}},addEventListener(){},focus(){},appendChild(){}});
const nodes=new Map();const doc={querySelector(s){if(!nodes.has(s))nodes.set(s,element());return nodes.get(s)},body:{dataset:{}},addEventListener(){},hidden:false};
const context={window:{},document:doc,localStorage:{getItem(){return null},setItem(){}},location:{protocol:'http:',host:'test:8767'},navigator:{},console,Date,Map,Math,Number,String,JSON,Object,Array,Promise,AbortController,setTimeout,clearTimeout,setInterval(){},URL,Blob};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('app/static/s7/js/data.js','utf8'),context);
let source=fs.readFileSync('app/static/s7/js/app.js','utf8').replace(/\r\n/g,'\n');
source=source.replace('setTheme(state.theme);render();updateClock();','window.testS7={state,validSnapshot,checkAPI,num,render,emptySnapshot,pageFunctions,availableEntries,sourceDetail,explorerResults};setTheme(state.theme);render();updateClock();').replace('checkAPI(false);\n})();','})();');
vm.runInContext(source,context);
(async()=>{const t=context.testS7;assert.strictEqual(t.num(null),'Sem dados');assert.strictEqual(t.num(0),'0');let s=t.emptySnapshot();s.timestamp=new Date().toISOString();s.quality='ok';assert(t.validSnapshot(s));
context.fetch=async url=>({ok:true,json:async()=>url.includes('history')?[]:s});await t.checkAPI();assert.strictEqual(t.state.mode,'real');s.timestamp=new Date(Date.now()-240000).toISOString();await t.checkAPI();assert.strictEqual(t.state.mode,'offline');s.timestamp=new Date().toISOString();await t.checkAPI();assert.strictEqual(t.state.mode,'real');assert.strictEqual(t.state.snapshot.battery.levelPercent,null);
for(const key of Object.keys(t.pageFunctions)){t.state.page=key;t.render()}
context.fetch=async()=>{throw Error('offline')};await t.checkAPI();assert.strictEqual(t.state.mode,'offline');assert.strictEqual(t.state.snapshot.timestamp,s.timestamp);assert.strictEqual(t.state.snapshot.cpu.usagePercent,null);
t.state.snapshot=t.emptySnapshot();await t.checkAPI();assert.strictEqual(t.state.snapshot.battery.levelPercent,null);assert.strictEqual(t.state.mode,'offline');
t.state.pref='demo';await t.checkAPI();assert.strictEqual(t.state.mode,'demo');t.state.pref='auto';await t.checkAPI();assert.strictEqual(t.state.mode,'offline');assert.strictEqual(t.state.snapshot.battery.levelPercent,null);
t.state.mode='real';t.state.page='activity';t.state.filter='all';t.state.search='';
t.state.snapshot={...t.emptySnapshot(),timestamp:new Date().toISOString(),details:{measuredAt:new Date().toISOString(),metrics:{'gpu.clock':{status:'ok',value:0,unit:'driver raw',source:'/sys/test'},'thermal.blocked':{status:'denied',value:null,unit:'raw',source:'/sys/secret'},'memory.meminfo':{status:'ok',value:{MemFree:0,'<script>':'<img onerror=alert(1)>'},unit:'KiB',source:'/proc/meminfo'}}}};
assert.strictEqual(t.availableEntries().length,2);const explorer=t.explorerResults();assert(explorer.includes('gpu.clock'));assert(!explorer.includes('thermal.blocked'));assert(explorer.includes('>0<'));
const detail=t.sourceDetail('memory.meminfo');assert(detail.includes('&lt;script&gt;'));assert(!detail.includes('<img'));assert(detail.includes('MemFree'));
t.state.search='missing-metric';assert(t.explorerResults().includes('Nenhuma leitura'));t.state.search='';
for(const key of Object.keys(t.pageFunctions)){t.state.page=key;t.render();const html=nodes.get('#main-content').innerHTML;assert(!html.includes('30 dias'));assert(!html.includes('Temperatura de CPU'));assert(!html.includes('Sinal Wi-Fi'));}
t.state.snapshot=t.emptySnapshot();t.state.fetching=true;t.render();assert(nodes.get('#main-content').innerHTML.includes('load-placeholder'));t.state.fetching=false;t.render();assert(!nodes.get('#main-content').innerHTML.includes('load-placeholder'));
console.log('S7 UI: null/zero, partial data, all views, disconnected startup, stale preservation and explicit demo passed.');})().catch(e=>{console.error(e);process.exitCode=1});

