/* Pure, source-aware view model. No synthetic measurements or router requests. */
(function(root){
 'use strict';
 const SECTIONS=[
  {id:'wifi',title:'Rádios e Wi-Fi',description:'Canais, redes, estações e capacidades reportadas.',sources:['radio_settings','radios','station_details','wifi_backhaul','wifi_features','wps','band_steering','wifi_schedule','guest_limits','guest_network']},
  {id:'clients',title:'Dispositivos e endereçamento',description:'Concessões, dispositivos e endereços observados.',sources:['dhcp','client_details','client_addresses','client_modes']},
  {id:'policies',title:'Regras e acesso',description:'Regras configuradas, sem classificação automática de segurança.',sources:['upnp','firewall_v4','firewall_v6','wan_acl','mac_policy','wan_nat']},
  {id:'network',title:'Rede, interfaces e IPv6',description:'Ligação, topologia, DHCP, DNS e IPv6.',sources:['ipv6','ipv6_lan','lan_settings','topology']},
  {id:'services',title:'Serviços e hardware',description:'USB, voz, DLNA e partilha de ficheiros.',sources:['usb_voice','file_services','dlna','voice_schedule']}
 ];
 const INFO={
  radio_settings:['Configuração de cada interface Wi-Fi.','Interfaces','interface','channel_reported'],
  guest_limits:['Limites configurados da rede convidada; unidade por validar.','Perfis','slot','upload_limit_reported'],
  upnp:['Encaminhamentos UPnP observados, não sessões de Internet.','Mapeamentos','protocol','external_port'],
  firewall_v4:['Códigos da política IPv4, sem interpretação de proteção.','Políticas','policy_code','right_code'],
  firewall_v6:['Códigos da política IPv6, sem interpretação de proteção.','Políticas','policy_code','right_code'],
  wan_acl:['Acesso de gestão WAN configurado; não representa teste de exposição.','Regras','protocol_code','enabled'],
  dhcp:['Concessões DHCP reportadas; não garantem presença online.','Concessões','interface_reported','lease_remaining_seconds'],
  client_details:['Identidades identificadas pelo Huawei; conflitos mantidos.','Identidades','status_reported','ip'],
  ipv6:['Estado e anúncios IPv6; endereços públicos removidos da fonte.','Registos IPv6','kind','connection_state'],
  wps:['Estado configurado do WPS por WLAN.','Interfaces','interface','enabled'],
  wifi_features:['Funcionalidades Wi-Fi configuradas.','Registos','mlo_enabled',null],
  usb_voice:['Hardware reportado, voz e componentes Wi-Fi.','Componentes','kind','registration_state'],
  lan_settings:['Servidor DHCP, DNS, LAN e reservas.','Configurações','kind','enabled'],
  ipv6_lan:['Anúncios e DNS IPv6 na rede local.','Registos','kind','enabled'],
  topology:['Topologia lógica reportada, não mapa físico da rede.','Portas lógicas','mode_reported','vlan_reported'],
  radios:['Rádios e bandas informados pelo equipamento.','Rádios','band','enabled'],
  band_steering:['MACs nas exclusões de seleção de banda.','Exclusões','mac',null],
  wifi_schedule:['Agendamento configurado; não prova execução no momento.','Agendamentos','enabled','start_reported'],
  mac_policy:['Códigos de filtragem de MAC.','Políticas','filter_policy','filter_right'],
  file_services:['Serviços FTP/SFTP configurados.','Serviços','kind','enabled'],
  dlna:['Configuração do serviço DLNA.','Registos','enabled','share_all'],
  wan_nat:['NAT e serviços configurados por interface WAN.','Interfaces WAN','services_reported','nat_enabled'],
  voice_schedule:['Políticas de horário de toque do serviço de voz.','Registos','enabled','policy_code'],
  wifi_backhaul:['Airtime fairness e backhaul reportados por WLAN.','Interfaces','interface','airtime_fairness'],
  client_addresses:['Endereços que o Huawei associa a clientes.','Endereços','status_reported','ip'],
  station_details:['Estações Wi-Fi com RSSI e taxa PHY observados.','Estações','interface','rssi_dbm'],
  client_modes:['Modos de trabalho Wi-Fi por identidade MAC.','Clientes','work_mode_reported','mac'],
  guest_network:['Pool de endereçamento da rede convidada.','Pools','slot','pool_start_ip']
 };
 const distributionKeys={
   radios:'band',station_details:'interface',dhcp:'interface_reported',client_details:'status_reported',
   client_addresses:'status_reported',client_modes:'work_mode_reported',upnp:'protocol',
   ipv6:'kind',usb_voice:'kind',lan_settings:'kind',topology:'mode_reported',
   file_services:'kind',wan_nat:'nat_enabled',wifi_backhaul:'backhaul_reported'
 };
 const shown=(v)=>v===null||v===undefined||v===''?'Sem dados':v===true?'Sim':v===false?'Não':String(v);
 const valid=(v)=>typeof v==='number'&&Number.isFinite(v);
 const info=(id)=>INFO[id]||['Dados reportados pela interface do router.','Registos',null,null];
 function sections(sources){
   const byId=new Map((Array.isArray(sources)?sources:[]).map(s=>[s.id,s]));
   return SECTIONS.map(section=>({...section,sources:section.sources.map(id=>byId.get(id)).filter(Boolean)}))
     .filter(section=>section.sources.length);
 }
 function summary(sources,changes=[]){
   const sourceList=Array.isArray(sources)?sources:[];
   const current=sourceList.filter(s=>s.quality==='ok').length;
   const old=sourceList.filter(s=>s.quality==='stale').length;
   const absent=sourceList.length-current-old;
   return {total:sourceList.length,current,old,absent,changes:changes.length,
     records:sourceList.reduce((acc,s)=>acc+(Array.isArray(s.data)?s.data.length:0),0)};
 }
 function numericOverview(rows,field){
   const numbers=rows.map(r=>r?.[field]).filter(valid);
   if(!numbers.length)return null;
   return {count:numbers.length,min:Math.min(...numbers),max:Math.max(...numbers),avg:numbers.reduce((a,b)=>a+b,0)/numbers.length};
 }
 function distribution(source){
   const key=distributionKeys[source.id];
   if(!key||!Array.isArray(source.data))return null;
   const counts=new Map();
   for(const r of source.data){
     if(!r||typeof r!=='object')continue;
     const value=r[key];
     const name=value===null||value===undefined||value===''?'Não reportado':shown(value);
     counts.set(name,(counts.get(name)||0)+1);
   }
   if(!counts.size)return null;
   const buckets=[...counts].map(([label,count])=>({label,count})).sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label,'pt-PT'));
   const visible=buckets.slice(0,6);
   if(buckets.length>6)visible.push({label:'Outros',count:buckets.slice(6).reduce((n,x)=>n+x.count,0)});
   return {field:key,label:info(source.id)[2],items:visible,total:[...counts.values()].reduce((a,b)=>a+b,0)};
 }
 function header(source){
   const rows=Array.isArray(source.data)?source.data:[];
   const [description,noun,first,second]=info(source.id);
   const examples=rows.slice(0,2).map(row=>first&&row[first]!=null?shown(row[first]):null).filter(Boolean);
   const detail=examples.length?examples.join(' · ')+(rows.length>examples.length?' · …':''):description;
   return {description,noun,count:rows.length,detail,first,second};
 }
 function highlights(source){
   const rows=Array.isArray(source.data)?source.data:[];
   if(!rows.length)return [];
   const sample=rows[0],out=[],id=source.id;
   function add(label,value,meaning){
     if(value===undefined||value===null||value==='')return;
     out.push({label,value:shown(value),meaning:meaning||''});
   }
   if(id==='station_details'){
     const rssi=numericOverview(rows,'rssi_dbm'),snr=numericOverview(rows,'snr_db_reported');
     if(rssi)add('RSSI médio das estações',Math.round(rssi.avg*10)/10+' dBm',rssi.count+' valores reportados; não é potência do rádio');
     if(snr)add('SNR médio',Math.round(snr.avg*10)/10+' dB',snr.count+' valores reportados');
   }else if(id==='radio_settings'){
     const channels=rows.filter(r=>valid(r.channel_reported)).map(r=>r.interface+': '+r.channel_reported);
     if(channels.length)add('Canais reportados',channels.slice(0,5).join(' · '),'Configuração; pode diferir do canal efetivo');
     const power=rows.filter(r=>valid(r.power_pct));
     if(power.length)add('Potência configurada',power.map(r=>r.interface+': '+r.power_pct+'%').slice(0,3).join(' · '),'Percentagem configurada, não dBm irradiados');
   }else if(id==='upnp'){
     add('Mapeamentos ativados',rows.filter(r=>r.enabled===true).length+' de '+rows.length,'UPnP observado; não equivale a tráfego ativo');
   }else if(id==='dhcp'){
     add('Concessões reportadas',rows.length,'Uma concessão não comprova que o dispositivo esteja online');
   }else if(id==='radios'){
     add('Rádios ativados',rows.filter(r=>r.enabled===true).length+' de '+rows.length,'Estado reportado');
   }else if(id==='guest_limits'){
     add('Perfis reportados',rows.length,'As unidades dos limites ainda exigem validação');
   }else if(id==='client_details'){
     add('Com divergências',rows.filter(r=>r.conflicting_fields?.length).length,'Campos conflitantes preservados como desconhecidos');
   }else if(id==='wan_nat'){
     add('NAT configurado',rows.filter(r=>r.nat_enabled===true).length+' de '+rows.length,'Não é um teste de acessibilidade externa');
   }else if(id==='file_services'){
     add('Serviços ativados',rows.filter(r=>r.enabled===true).length+' de '+rows.length,'Configuração, sem teste de exposição WAN');
   }else if(id==='lan_settings'){
     const dhcp=rows.find(r=>r.kind==='dhcp_server');
     if(dhcp)add('Servidor DHCP',dhcp.enabled===true?'Ativado':dhcp.enabled===false?'Desativado':'Não reportado','Configuração');
     if(dhcp?.pool_start_ip)add('Pool LAN',dhcp.pool_start_ip+(dhcp.pool_end_ip?' → '+dhcp.pool_end_ip:''),'Endereçamento local');
   }else if(id==='wifi_features'){
     if(typeof sample.mlo_enabled==='boolean')add('Multi-Link Operation',sample.mlo_enabled?'Configurado ativo':'Configurado inativo','MLO configurado; não comprova negociação por cliente');
   }else if(id==='wps'){
     add('WPS ativado',rows.filter(r=>r.enabled===true).length+' de '+rows.length,'Configuração por interface');
   }else if(id==='ipv6'){
     add('Interfaces reportadas',rows.filter(r=>r.connection_state!=null).length,'Estado descrito pelo router');
   }
   // Add representative fields without inventing units or interpreting opaque policy codes.
   const priority={
      radio_settings:['standard_reported','auto_channel','pmf','wmm'],
      station_details:['work_mode_reported','supports_11r','ofdma'],
      dhcp:['lease_remaining_seconds','address_source_reported'],
      guest_network:['pool_start_ip','pool_end_ip'],
      guest_limits:['upload_limit_reported','download_limit_reported'],
      firewall_v4:['right_code','policy_code','level_code'],
      firewall_v6:['right_code','policy_code','level_code'],
      mac_policy:['filter_right','filter_policy'],
      wan_acl:['protocol_code','source_restricted'],
      wifi_schedule:['start_reported','end_reported'],
      ipv6_lan:['enabled','managed','other_config'],
      dlna:['enabled','share_all'],
      voice_schedule:['enabled','policy_code'],
      topology:['mode_reported','vlan_reported'],
      wifi_backhaul:['airtime_fairness','backhaul_reported'],
      usb_voice:['registration_state','component_reported'],
      file_services:['kind','port'],
      client_modes:['work_mode_reported'],
      client_addresses:['status_reported'],
      wifi_features:['mlo_enabled'],
      radios:['band']
   }[id]||[];
   const fieldLabels={standard_reported:'Padrão',auto_channel:'Canal automático',pmf:'PMF',wmm:'WMM',
      enabled:'Ativado',managed:'Gestão IPv6',other_config:'Outra config. IPv6',share_all:'Partilha completa',
      protocol_code:'Protocolo reportado',source_restricted:'Origem restrita',kind:'Tipo',
      air_time:'Airtime',band:'Banda',port:'Porta',status_reported:'Estado reportado',
      start_reported:'Início',end_reported:'Fim',work_mode_reported:'Modo',
      lease_remaining_seconds:'Concessão restante (s)',address_source_reported:'Origem do IP',
      pool_start_ip:'Início pool',pool_end_ip:'Fim pool',policy_code:'Código política',
      right_code:'Código permissão',level_code:'Código nível',filter_right:'Permissão MAC',
      filter_policy:'Política MAC',download_limit_reported:'Limite download (unidade não confirmada)',
      upload_limit_reported:'Limite upload (unidade não confirmada)',vlan_reported:'VLAN',
      mode_reported:'Modo',airtime_fairness:'Airtime fairness',backhaul_reported:'Backhaul',
      component_reported:'Componente',registration_state:'Registo',mlo_enabled:'MLO',supports_11r:'802.11r',
      ofdma:'OFDMA',pmf:'PMF'};
   for(const key of priority){
     if(out.length>=4)break;
     const value=sample?.[key];
     if(value===null||value===undefined||value==='')continue;
     if(out.some(a=>a.label===fieldLabels[key]))continue;
     add(fieldLabels[key]||key,value,rows.length>1?'Exemplo da primeira linha; ver restantes na tabela':'Valor reportado');
   }
   return out.slice(0,4);
 }
 function changeBins(changes,hours,now=Date.now(),bins=12){
   const hoursNum=Number(hours);
   if(!Number.isFinite(hoursNum)||hoursNum<=0)return [];
   const start=now-hoursNum*3600000,span=(now-start)/bins;
   const counts=Array(bins).fill(0);
   for(const entry of Array.isArray(changes)?changes:[]){
     const ts=Date.parse(entry?.observed_at);
     if(Number.isFinite(ts)&&ts>=start&&ts<=now){
       const idx=Math.min(bins-1,Math.max(0,Math.floor((ts-start)/span)));
       counts[idx]++;
     }
   }
   return counts.map((count,i)=>({count,start:new Date(start+i*span).toISOString(),end:new Date(start+(i+1)*span).toISOString()}));
 }
 function trendSegments(points,key,cadenceSeconds=300){
   const segments=[];
   const maxGap=Math.max(1,Number(cadenceSeconds)||300)*3*1000;
   let current=[],lastTime=null;
   for(const point of Array.isArray(points)?points:[]){
     const ts=Date.parse(point?.ts),value=point?.[key];
     const validPoint=point?.status==='ok'&&valid(value)&&Number.isFinite(ts);
     if(!validPoint){
       if(current.length)segments.push(current);
       current=[];lastTime=null;continue;
     }
     if(lastTime!=null&&(ts<=lastTime||ts-lastTime>maxGap)){
       if(current.length)segments.push(current);
       current=[];
     }
     current.push({ts,value});
     lastTime=ts;
   }
   if(current.length)segments.push(current);
   return segments;
 }
 function trendDomain(segments,unit){
   const values=(segments||[]).flatMap(segment=>segment.map(v=>v.value));
   if(!values.length)return null;
   let min=Math.min(...values),max=Math.max(...values);
   if(unit==='registos'){
     min=0;max=Math.max(1,max);
   }else if(min===max){
     const pad=unit==='dBm'||unit==='dB'?3:Math.max(1,Math.abs(min)*.08);
     min-=pad;max+=pad;
   }else{
     const pad=Math.max(0.1,(max-min)*.08);
     min-=pad;max+=pad;
   }
   return {min,max,total:values.length};
 }
 const api={SECTIONS,INFO,sections,summary,header,highlights,distribution,changeBins,shown,numericOverview,trendSegments,trendDomain};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
 else root.FNOObservabilityView=api;
})(typeof window!=='undefined'?window:{});
