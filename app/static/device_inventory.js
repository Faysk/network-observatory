/* Pure device inventory selectors. Used by Router UI and Node synthetic tests. */
(function (root) {
  'use strict';
  const STATES=['online','offline','unknown','stale'];
  const RANK={online:0,offline:1,unknown:2,stale:3};
  function presence(c){
    if(!c || c.quality!=='ok')return 'stale';
    if(c.reported_status==='Online')return 'online';
    if(c.reported_status==='Offline')return 'offline';
    return 'unknown';
  }
  function network(c){
    const station=Array.isArray(c?.stations)?c.stations[0]:null;
    const ports=Array.isArray(c?.ports)?c.ports.join(' '):'';
    if(station || /wifi|wlan/i.test(ports))return 'wifi';
    if(/eth|lanethernet|\blan[1-4]\b/i.test(ports))return 'wired';
    return 'unknown';
  }
  // Speed belongs to the router's physical port, not to a bandwidth test.
  function connection(c,huawei,now=Date.now()){
    const kind=network(c);
    if(kind!=='wired')return {label:presence(c)==='online'&&Number.isFinite(c?.station?.rssi_dbm)?c.station.rssi_dbm+' dBm':'Sem dados',title:'Sinal Wi-Fi reportado pelo router'};
    const missing={label:'Velocidade indisponível',title:'Sem velocidade Ethernet atual e inequívoca para este aparelho'};
    const ts=Date.parse(huawei?.collected_at),seen=Date.parse(c?.last_seen);
    if(presence(c)!=='online'||huawei?.quality!=='ok'||!Number.isFinite(ts)||!Number.isFinite(seen)||now-ts>180000||now-ts< -5000||now-seen>180000||now-seen< -5000||Math.abs(ts-seen)>180000)return missing;
    const ports=new Set();
    for(const raw of Array.isArray(c.ports)?c.ports:[]){
      const match=/^(?:ETH:)?LAN([1-4])$/i.exec(raw)||/^InternetGatewayDevice\.LANDevice\.1\.LANEthernetInterfaceConfig\.([1-4])$/i.exec(raw);
      if(match)ports.add('lan'+match[1]);
    }
    if(ports.size!==1)return missing;
    const port=[...ports][0],value=huawei.interfaces?.[port],speed=value?.speed_mbps;
    if(value?.link_up!==true||![10,100,1000,2500,5000,10000].includes(speed))return missing;
    const label=speed>=1000?String(speed/1000).replace('.',',')+' Gb/s':speed+' Mb/s';
    return {label,title:port.toUpperCase()+' · Velocidade negociada da porta do router'+(value.duplex==='half'?' · Half duplex':value.duplex==='full'?' · Full duplex':'')+'. Não mede Internet nem ligações após switches.'+(speed<=100?' Uma ligação de 10/100 Mb/s pode indicar limitação do aparelho, porta, cabo ou configuração.':'')};
  }
  // Preserve original MAC/hostname for search and dossier, but avoid rendering
  // technical placeholders as though they were friendly product names.
  function meaningfulName(value){
    if(typeof value!=='string')return false;
    const name=value.trim();
    return name.length>0 && name.length<=120 &&
      !/^(?:[\da-f]{2}[:-]){5}[\da-f]{2}$/i.test(name) &&
      !/^[\da-f]{12}$/i.test(name) &&
      !/^(?:wlan\d+|eth\d+|wifi|unknown|none|undefined|0|--|msft 5\.0|android[-_ ]?dhcp[\w.\-]*)$/i.test(name);
  }
  function suggestedName(c,category,connection){
    const types=Array.isArray(c?.device_types)?c.device_types:[];
    if(category==='game_console' && types.some(x=>typeof x==='string'&&/^PS5$/i.test(x.trim())))
      return 'PlayStation 5';
    if(category==='game_console'&&/^nintendo/i.test(c?.identity?.oui_vendor||''))return 'Console Nintendo';
    if(category==='android_device')return 'Equipamento Android';
    if(category==='computer')return 'Computador';
    const generic={
      smartphone:'Smartphone',tablet:'Tablet',
      laptop:'Notebook',desktop:'Computador',
      game_console:'Console',robot_vacuum:'Aspirador robô',
      smart_tv:'TV',streaming_box:'Reprodutor multimédia',
      printer:'Impressora',camera:'Câmara',
      network_device:'Equipamento de rede',iot:'Dispositivo IoT'
    };
    return generic[category] || (c?.identity?.oui_vendor?'Dispositivo · '+c.identity.oui_vendor:null) || (connection==='wifi'?'Dispositivo Wi-Fi não identificado':
      connection==='wired'?'Dispositivo Ethernet não identificado':'Dispositivo não identificado');
  }
  function prepare(c){
    const names=Array.isArray(c?.names)?c.names:[];
    const mac=String(c?.mac||'');
    const connection=network(c);
    const effectiveCategory=c?.presentation?.category||c?.classification?.category||'unknown';
    const named=names.find(meaningfulName),historical=c?.classification?.display_name_source==='history'&&meaningfulName(c.classification.display_name_suggestion)?c.classification.display_name_suggestion:null;
    return {...c, id:mac.replaceAll(':',''),name:c?.presentation?.nickname||named||historical||suggestedName(c,effectiveCategory,connection),
      hasReportedName:Boolean(named),effectiveCategory,
      station:Array.isArray(c?.stations)?c.stations[0]||{}:{},
      network:connection,recent:c?.quality==='ok',presence:presence(c)};
  }
  function haystack(c){
    return [c.name,c.mac,c.last_seen,c.effectiveCategory,c.classification?.category,
      c.classification?.platform_family,c.identity?.oui_vendor,
      c.classification?.display_name_suggestion,
      ...(Array.isArray(c.names)?c.names:[]),
      ...(Array.isArray(c.ips)?c.ips:[]),
      ...(Array.isArray(c.device_types)?c.device_types:[])].filter(Boolean).join(' ').toLocaleLowerCase();
  }
  function filter(list,options={}){
    const query=String(options.query||'').toLocaleLowerCase().trim();
    return list.filter(c=>{
      if(options.filter==='online'&&c.presence!=='online')return false;
      if(['wifi','wired'].includes(options.filter)&&c.network!==options.filter)return false;
      if(options.category && options.category!=='all'&&
         c.effectiveCategory!==options.category)return false;
      if(options.confidence && options.confidence!=='all'&&
         (c.classification?.confidence||'unknown')!==options.confidence)return false;
      if(options.macKind==='local'&&c.identity?.mac_type!=='locally_administered')return false;
      if(options.macKind==='global'&&c.identity?.mac_type!=='global')return false;
      if(options.vendor==='known'&&!c.identity?.oui_vendor)return false;
      if(options.vendor==='unknown'&&!!c.identity?.oui_vendor)return false;
      if(options.status && options.status!=='all'&&c.presence!==options.status)return false;
      return !query||haystack(c).includes(query);
    });
  }
  function compare(a,b,sort='status'){
    const names=()=>String(a.name||a.mac).localeCompare(String(b.name||b.mac),'pt-PT',{sensitivity:'base'});
    let primary=0;
    if(sort==='name')primary=names();
    else if(sort==='recent')primary=(Date.parse(b.last_seen)||0)-(Date.parse(a.last_seen)||0);
    else if(sort==='signal'){
      const va=typeof a.station?.rssi_dbm==='number'?a.station.rssi_dbm:-Infinity;
      const vb=typeof b.station?.rssi_dbm==='number'?b.station.rssi_dbm:-Infinity;
      primary=va===-Infinity&&vb===-Infinity?0:
        va===-Infinity?1:vb===-Infinity?-1:vb-va;
    }
    else primary=(RANK[a.presence]??4)-(RANK[b.presence]??4);
    return primary||names()||String(a.mac||'').localeCompare(String(b.mac||''));
  }
  function select(raw,options={}){
    return filter(raw.map(prepare),options).sort((a,b)=>compare(a,b,options.sort));
  }
  function counts(raw){
    const totals={identities:0,online:0,offline:0,unknown:0,stale:0};
    for(const item of raw){
      const kind=presence(item);
      totals[kind]++;
      totals.identities++;
    }
    return totals;
  }
  const api={STATES,presence,network,connection,prepare,filter,compare,select,counts};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.FNOInventory=api;
})(typeof window!=='undefined'?window:{});
