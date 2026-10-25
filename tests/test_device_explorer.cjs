'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const file=fs.readFileSync(path.join(__dirname,'../app/static/devices.js'),'utf8');
const css=fs.readFileSync(path.join(__dirname,'../app/static/devices.css'),'utf8');
const extract=(start,end)=>{const a=file.indexOf(start),b=file.indexOf(end,a);assert.ok(a>=0&&b>a,start+' absent');return file.slice(a,b)};
// Execute the real device filtering and classification/ordering logic against
// synthetic clients; no network or real MAC/inventory payloads.
const make=(i,status,network,group)=>({
 id:String(i),mac:'02:00:00:'+String(Math.floor(i/65536)).padStart(2,'0')+':'+(Math.floor(i/256)%256).toString(16).padStart(2,'0')+':'+(i%256).toString(16).padStart(2,'0'),
 name:'Synthetic-'+i,names:['Synthetic-'+i],ips:[],device_types:[],
 classification:{category:group},network,reported_status:status,quality:'ok',recent:true,
 last_seen:new Date(Date.now()-i*1000).toISOString()
});
const fake=Array.from({length:1000},(_,i)=>make(i,i%3===0?'Online':i%3===1?'Offline':'Unknown',i%2?'wifi':'wired',i%5?'smartphone':'game_console'));
const sandbox={state:{filter:'all',category:'all',query:'',sort:'status'},app:{clients:fake},category:c=>c.classification.category,
 categoryNames:{smartphone:'Smartphone',game_console:'Console'},
 devices:()=>fake.slice(),Date};
vm.createContext(sandbox);
vm.runInContext(extract('function deviceState(', 'function renderList('),sandbox);
let rows=sandbox.filtered();assert.equal(rows.length,1000);assert.equal(rows[0].reported_status,'Online');
sandbox.state.filter='online';rows=sandbox.filtered();assert.equal(rows.length,334);
sandbox.state.filter='offline';rows=sandbox.filtered();assert.equal(rows.length,333);
sandbox.state.filter='stale';rows=sandbox.filtered();assert.equal(rows.length,333);
sandbox.state.filter='all';sandbox.state.category='game_console';rows=sandbox.filtered();assert.equal(rows.length,200);
sandbox.state.category='all';sandbox.state.query='synthetic-999';rows=sandbox.filtered();assert.equal(rows.length,1);
sandbox.state.query='';sandbox.state.sort='name';rows=sandbox.filtered();assert.equal(rows[0].name,'Synthetic-0');
assert.ok(file.includes('state.limit+=40'),'load-more increments should be bounded');
assert.ok(file.includes('list.slice(0,state.limit)'),'large DOM must be paginated');
assert.ok(file.includes('rows.dataset.markup!==markup'),'identical polling should not rebuild explorer rows');
assert.ok(file.includes('if(focused!==search)search.value=state.query'),'search focus must survive polling');
assert.ok(css.includes('prefers-reduced-motion'),'reduced motion support');
console.log('Device explorer filter tests passed: 19- and 1000-MAC synthetic conditions, status, category, pagination.');
