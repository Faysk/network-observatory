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
  function prepare(c){
    const names=Array.isArray(c?.names)?c.names:[];
    const mac=String(c?.mac||'');
    return {...c, id:mac.replaceAll(':',''),name:names[0]||mac,
      station:Array.isArray(c?.stations)?c.stations[0]||{}:{},
      network:network(c),recent:c?.quality==='ok',presence:presence(c)};
  }
  function haystack(c){
    return [c.name,c.mac,c.last_seen,c.classification?.category,
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
         (c.classification?.category||'unknown')!==options.category)return false;
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
  const api={STATES,presence,network,prepare,filter,compare,select,counts};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.FNOInventory=api;
})(typeof window!=='undefined'?window:{});
