'use strict';
const assert=require('node:assert/strict');
const inv=require('../app/static/device_inventory.js');
const sample=(i)=>({mac:'02:00:00:'+i.toString(16).padStart(6,'0').match(/../g).join(':'),
 names:['Fixture '+i],quality:i%4===3?'stale':'ok',reported_status:['Online','Offline','Unknown'][i%3],
 classification:{category:i%2?'smartphone':'unknown',confidence:'low'},identity:{mac_type:'locally_administered',oui_vendor:null},
 ips:['192.0.2.'+(i%250+1)],stations:i%2?[{rssi_dbm:-50}]:[],ports:i%2?[]:['LAN1']});
for(const size of [19,1000]){
 const raw=Array.from({length:size},(_,i)=>sample(i));
 const totals=inv.counts(raw);assert.equal(totals.identities,size);
 assert.equal(totals.online+totals.offline+totals.unknown+totals.stale,size);
 const list=inv.select(raw,{status:'online',category:'smartphone',macKind:'local',filter:'wifi'});
 assert(list.every(c=>c.presence==='online'&&c.effectiveCategory==='smartphone'&&c.network==='wifi'));
 const ordered=inv.select(raw);assert(ordered[0].presence==='online');
 assert.equal(ordered.slice(0,40).length,Math.min(40,size));
 assert.deepEqual(inv.select(raw,{query:'not a fixture'}),[]);
}
const custom=sample(0);custom.presentation={source:'manual',nickname:'A <custom> name',category:'tablet',icon:'camera'};
const selected=inv.select([custom],{query:'<custom>',category:'tablet'});
assert.equal(selected.length,1);assert.equal(selected[0].name,'A <custom> name');
assert.equal(selected[0].classification.category,'unknown');
assert.equal(inv.presence({...sample(1),quality:'stale',reported_status:'Online'}),'stale');
// A type supplied by the router should produce a readable label even when the
// hostname is only a raw MAC. The source values remain available in the object.
const nameless=sample(1);
nameless.names=[nameless.mac];
nameless.device_types=['PS5'];
nameless.classification={category:'game_console',confidence:'medium'};
const inferred=inv.prepare(nameless);
assert.equal(inferred.name,'PlayStation 5');
assert.deepEqual(inferred.names,[nameless.mac]);
assert.equal(inferred.mac,nameless.mac);
assert.equal(inv.select([nameless],{query:nameless.mac}).length,1);
const android=sample(2);
android.names=['wlan0'];
android.device_types=['android-dhcp-8.0.0'];
android.classification={category:'android_device',platform_family:'android',confidence:'low'};
const guessed=inv.prepare(android);
assert.equal(guessed.name,'Equipamento Android');
assert.equal(guessed.hasReportedName,false);
assert.deepEqual(guessed.names,['wlan0']);
const unknown=sample(3);
unknown.names=[unknown.mac];
unknown.ports=['wlan0'];
unknown.classification={category:'unknown',confidence:'unknown'};
assert.equal(inv.prepare(unknown).name,'Dispositivo Wi-Fi não identificado');
// Manual preferences outrank suggestions without modifying original identity.
unknown.presentation={source:'manual',nickname:'Meu dispositivo',category:'tablet'};
const saved=inv.prepare(unknown);
assert.equal(saved.name,'Meu dispositivo');
assert.equal(saved.effectiveCategory,'tablet');

console.log('Inventory: 19/1000 identities, combined filters, stale semantics, ordering and manual precedence passed.');

// Fresh negotiated port speed, never inferred from device model or Internet speed.
const now=Date.now(),at=new Date(now).toISOString();
const wired=inv.prepare({...sample(0),quality:'ok',reported_status:'Online',last_seen:at,ports:['ETH:LAN4','InternetGatewayDevice.LANDevice.1.LANEthernetInterfaceConfig.4']});
const h={quality:'ok',collected_at:at,interfaces:{lan4:{link_up:true,speed_mbps:2500,duplex:'full'}}};
for(const [speed,label] of [[10,'10 Mb/s'],[100,'100 Mb/s'],[1000,'1 Gb/s'],[2500,'2,5 Gb/s'],[5000,'5 Gb/s'],[10000,'10 Gb/s']]){
 h.interfaces.lan4.speed_mbps=speed;assert.equal(inv.connection(wired,h,now).label,label);
}
for(const client of [{...wired,reported_status:'Offline'},{...wired,quality:'stale'},{...wired,last_seen:new Date(now-181000).toISOString()},{...wired,ports:['ETH:LAN3','ETH:LAN4']},{...wired,ports:['Ethernet']},{...wired,ports:['ETH:LAN40']}])assert.equal(inv.connection(client,h,now).label,'Velocidade indisponível');
assert.equal(inv.connection(wired,{...h,quality:'stale'},now).label,'Velocidade indisponível');
assert.equal(inv.connection(wired,{...h,collected_at:new Date(now-181000).toISOString()},now).label,'Velocidade indisponível');
h.interfaces.lan4.link_up=false;assert.equal(inv.connection(wired,h,now).label,'Velocidade indisponível');
h.interfaces.lan4.link_up=true;h.interfaces.lan4.speed_mbps=null;assert.equal(inv.connection(wired,h,now).label,'Velocidade indisponível');
assert.equal(inv.connection(inv.prepare({...sample(1),quality:'ok',reported_status:'Online'}),h,now).label,'Banda desconhecida · -50 dBm');
console.log('Ethernet negotiated link tests passed');

const wifiClient=inv.prepare({...sample(1),quality:'ok',reported_status:'Online',
  last_seen:at,stations:[{interface:'wlan5',rssi_dbm:-62}],ports:['WIFI:SSID5']});
const radios={quality:'ok',collected_at:at,wifi:{wlan5:{band:'5GHz',channel:100},wlan1:{band:'2.4GHz',channel:6}}};
assert.equal(inv.wifiContext(wifiClient,radios,now).band,'5 GHz');
assert.deepEqual(inv.wifiContext(wifiClient,radios,now).interfaces,[{interface:'wlan5',band:'5 GHz',channel:100}]);
assert.equal(inv.connection(wifiClient,radios,now).label,'5 GHz · -62 dBm');
assert.equal(inv.wifiContext({...wifiClient,last_seen:new Date(now-61000).toISOString()},radios,now).band,null);
assert.equal(inv.wifiContext({...wifiClient,quality:'stale'},radios,now).band,null);
assert.equal(inv.wifiContext(wifiClient,{...radios,quality:'stale'},now).band,null);
assert.equal(inv.wifiContext(wifiClient,{...radios,collected_at:new Date(now-181000).toISOString()},now).band,null);
assert.equal(inv.wifiContext(wifiClient,{...radios,wifi:{}},now).band,null);
assert.equal(inv.wifiContext(wifiClient,{...radios,wifi:{wlan5:{channel:100}}},now).band,null);
const multiple={...wifiClient,stations:[{interface:'wlan1',rssi_dbm:-61},{interface:'wlan5',rssi_dbm:-62}]};
assert.equal(inv.wifiContext(multiple,radios,now).band,null);
assert.equal(inv.wifiContext(multiple,radios,now).interfaces.length,2);
assert.equal(inv.wifiContext(wifiClient,{...radios,wifi:{wlan5:{band:'6GHz',channel:37}}},now).band,null);
assert.equal(inv.wifiContext(wifiClient,radios,now).title.includes('canal 100'),true);
console.log('Same-snapshot Wi-Fi interface/band, multiple, unknown and stale checks passed.');
