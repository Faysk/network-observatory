'use strict';
const assert=require('node:assert/strict');
const view=require('../app/static/observability_view_model.js');
const all=view.SECTIONS.flatMap(x=>x.sources);
assert.equal(all.length,28,'The 28 Huawei sources must remain navigable');
assert.equal(new Set(all).size,28,'Each source belongs to exactly one section');
assert.equal(Object.keys(view.INFO).length,28);
for(const id of all)assert(view.INFO[id],id);
const sources=all.map((id,i)=>({id,quality:i<24?'ok':i<26?'stale':'unavailable',data:i<26?[]:null}));
const totals=view.summary(sources,[{source:'upnp'},{source:'radios'}]);
assert.deepEqual(totals,{total:28,current:24,old:2,absent:2,changes:2,records:0});
const sections=view.sections(sources);
assert.equal(sections.reduce((a,x)=>a+x.sources.length,0),28);
assert.deepEqual(view.sections([]),[]);
assert.equal(view.shown(0),'0');
assert.equal(view.shown(false),'Não');
assert.equal(view.shown(null),'Sem dados');

const upnp={id:'upnp',data:[{enabled:true,protocol:'TCP',external_port:1234},
  {enabled:false,protocol:'UDP',external_port:2000},{enabled:true,protocol:'TCP',external_port:1235}]};
assert.equal(view.highlights(upnp)[0].value,'2 de 3');
assert.deepEqual(view.distribution(upnp).items,[{label:'TCP',count:2},{label:'UDP',count:1}]);
assert.equal(view.distribution({id:'upnp',data:[]}),null);

const stations={id:'station_details',data:[{interface:'wlan1',rssi_dbm:-50,snr_db_reported:15},
  {interface:'wlan1',rssi_dbm:-60,snr_db_reported:25},
  {interface:'wlan5',rssi_dbm:null,snr_db_reported:null}]};
assert.equal(view.highlights(stations)[0].value,'-55 dBm');
assert.equal(view.highlights(stations)[1].value,'20 dB');
assert.equal(view.numericOverview(stations.data,'rssi_dbm').count,2);
assert.equal(view.distribution(stations).total,3);
assert.equal(view.numericOverview(stations.data,'absent'),null);

const now=Date.parse('2026-10-26T21:00:00Z');
const bins=view.changeBins([
 {observed_at:'2026-10-26T20:00:00Z'},
 {observed_at:'2026-10-26T20:45:00Z'},
 {observed_at:'2026-10-20T20:45:00Z'},
 {observed_at:'garbage'},
],24,now,12);
assert.equal(bins.reduce((a,x)=>a+x.count,0),2);
assert.equal(bins.length,12);
assert.deepEqual(view.changeBins([],0,now),[]);

const radio={id:'radio_settings',data:[{interface:'wlan1',channel_reported:6,power_pct:0,standard_reported:'11ax',auto_channel:false}]};
assert(view.highlights(radio).some(x=>x.value.includes('0%')),'zero transmit power setting must stay visible');
assert(view.highlights(radio).some(x=>x.value==='Não'),'false radio configuration must stay visible');
assert.equal(view.header(radio).count,1);
console.log('Observability: 28/28 group coverage; KPI counts, distributions, readings, zero/false and timeline passed.');
