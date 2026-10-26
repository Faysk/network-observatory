/* Read-only source snapshots; all values use textContent, including device labels. */
(()=>{'use strict';
const page=document.querySelector('.page');if(!page)return;
const VM=window.FNOObservabilityView;if(!VM)throw Error('Observability visual model missing');
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const panel=node('section',undefined,'observation-panel');panel.id='routerObservability';panel.tabIndex=-1;panel.setAttribute('aria-labelledby','observationTitle');
const title=node('h2','Configuração e diagnóstico');title.id='observationTitle';panel.append(title);
panel.append(node('p','Leituras adicionais a cada 5 minutos. Alterações representam diferenças entre observações; o horário exato e a causa não são conhecidos.'));
const collector=node('p','A consultar o estado do coletor…','observation-collector');collector.setAttribute('role','status');panel.append(collector);
const toolbar=node('div',undefined,'observation-toolbar'),period=node('select');period.setAttribute('aria-label','Período das alterações');
for(const [value,label] of [[24,'Últimas 24 horas'],[168,'Últimos 7 dias'],[720,'Últimos 30 dias'],[8784,'Últimos 366 dias']]){const o=node('option',label);o.value=value;period.append(o);}
const group=node('select');group.setAttribute('aria-label','Grupo de fontes');
for(const [value,label] of [['all','Todas as fontes'],['wifi','Wi-Fi'],['clients','Clientes e DHCP'],['network','LAN, WAN e IPv6'],['policies','Políticas e UPnP'],['services','Hardware e serviços']]){const option=node('option',label);option.value=value;group.append(option);}
const search=node('input',undefined,'observation-source-search');search.type='search';search.placeholder='Pesquisar fonte ou diagnóstico…';search.setAttribute('aria-label','Pesquisar fontes de diagnóstico');
const refresh=node('button','Atualizar painel'),download=node('button','Exportar JSON privado');refresh.type=download.type='button';toolbar.append(group,period,search,refresh,download);panel.append(toolbar);
const notice=node('p','','observation-notice');notice.setAttribute('role','status');panel.append(notice);
const summaryGrid=node('div',undefined,'observation-overview');panel.append(summaryGrid);
const viewNote=node('p','Selecione uma fonte para inspecionar os dados. Os indicadores mostram valores reportados; não classificam automaticamente a segurança da rede.','observation-reading-note');panel.append(viewNote);
const operationsBox=node('section',undefined,'observation-operations');
operationsBox.setAttribute('aria-labelledby','operationsTitle');
const operationsHeader=node('div',undefined,'observation-operations-header');
const operationsHeading=node('div');const operationsTitle=node('h3','Saúde e alertas do Observatory');
operationsTitle.id='operationsTitle';
operationsHeading.append(operationsTitle,node('p','Diagnóstico passivo do servidor, armazenamento e recolha. Alertas configurados localmente; nenhum envio externo.'));
const operationsStatus=node('span','A consultar…','observation-badge');operationsStatus.setAttribute('role','status');
operationsHeader.append(operationsHeading,operationsStatus);
const operationsMetrics=node('div',undefined,'observation-operations-metrics');
const operationsAlerts=node('div',undefined,'observation-operations-alerts');
const operationsTrend=node('details',undefined,'observation-operations-trend');
operationsTrend.append(node('summary','Explorar histórico real de RAM, disco e desempenho'));
const operationsTrendBody=node('div',undefined,'observation-operations-trend-body');
operationsTrend.append(operationsTrendBody);
operationsBox.append(operationsHeader,operationsMetrics,operationsAlerts,operationsTrend);
panel.append(operationsBox);
const categoryNav=node('nav',undefined,'observation-category-nav');
categoryNav.setAttribute('aria-label','Explorar áreas de diagnóstico');
panel.append(categoryNav);
const quickbar=node('div',undefined,'observation-quickfilters');
quickbar.setAttribute('role','group');quickbar.setAttribute('aria-label','Filtrar por situação');
const quickOptions=[['all','Todas'],['changed','Com alterações'],['missing','Sem leitura atual']];
let quickMode='all';
for(const [value,label] of quickOptions){
 const b=node('button',label,'observation-filter-chip');
 b.type='button';b.dataset.quick=value;b.setAttribute('aria-pressed',String(value==='all'));
 b.addEventListener('click',()=>{
   quickMode=value;
   for(const el of quickbar.querySelectorAll('[data-quick]'))el.setAttribute('aria-pressed',String(el.dataset.quick===value));
   applyFilters();
 });
 quickbar.append(b);
}
const matching=node('span','','observation-match-count');matching.setAttribute('role','status');
quickbar.append(matching);panel.append(quickbar);
const cards=node('div',undefined,'observation-cards');panel.append(cards);
const timelineTitle=node('div',undefined,'observation-timeline-head');
timelineTitle.append(node('h3','Histórico de alterações observadas'),node('p','Diferenças detetadas entre amostras sucessivas, não o instante exato da alteração.'));
panel.append(timelineTitle);
const changeChart=node('div',undefined,'observation-change-chart');panel.append(changeChart);
const changes=node('div',undefined,'observation-changes');panel.append(changes);
const limits=node('details'),limitTitle=node('summary','Limites e significado dos dados');limits.append(limitTitle,node('p','Largura do canal é a política configurada. Limites da rede convidada e alguns tempos são valores reportados cuja escala ainda precisa de confirmação. Tempos DHCP não comprovam duração online. Códigos de política são preservados sem interpretação não validada. Endereços WAN, números de telefone, nomes de ficheiros USB, palavras-passe e PIN WPS são excluídos. Exportações contêm identidades da LAN e devem ser tratadas como privadas.'));
const unsupported=node('ul');limits.append(unsupported);panel.append(limits);page.append(panel);
const labels={interface:'Interface',slot:'Entrada',kind:'Tipo',enabled:'Ativo',hidden:'Rede oculta',auto_channel:'Canal automático',channel_reported:'Canal reportado',power_pct:'Potência configurada (%)',width_policy_code:'Política de largura',standard_reported:'Padrão configurado',work_mode_reported:'Modo configurado',auto_channel_scope_reported:'Âmbito do canal automático',mcs_setting:'MCS configurado',rssi_threshold_setting:'Limiar RSSI configurado',rssi_threshold_enabled:'Limiar RSSI ativo',channel_plus_setting:'Canal adicional configurado',wmm:'WMM',pmf:'Proteção de gestão (PMF)',beamforming:'Beamforming',ocac:'OCAC',scs:'SCS',periodic_auto_channel:'Canal automático periódico',qhop:'QHOP',service_enabled:'Serviço ativo',dtim_setting:'DTIM configurado',beacon_setting:'Beacon configurado',rts_threshold:'Limiar RTS',frag_threshold:'Limiar de fragmentação',airtime_fairness:'Airtime fairness',channel_scope:'Âmbito do canal',mu_mimo_enabled:'MU-MIMO configurado',preamble_setting:'Preâmbulo configurado',upload_limit_reported:'Limite de envio (reportado)',download_limit_reported:'Limite de receção (reportado)',lease_seconds_reported:'Duração UPnP (s, reportada)',remote_restricted:'Origem remota restrita',external_port:'Porta externa',internal_port:'Porta interna',protocol:'Protocolo',client_ip:'IP do cliente',description:'Descrição',mac:'MAC',ip:'IP local',name:'Nome reportado',alias:'Apelido reportado',lease_remaining_seconds:'Concessão restante (s)',lease_elapsed_reported_seconds:'Tempo DHCP reportado (s)',type_reported:'Tipo reportado',interface_reported:'Interface reportada',address_source_reported:'Origem do endereço',port_reported:'Porta reportada',ip_type_reported:'Tipo de IP',status_reported:'Estado reportado',port_type_reported:'Tipo de porta',time_reported:'Tempo reportado (escala por validar)',ipv4_enabled:'IPv4 ativo',ipv6_enabled:'IPv6 ativo',category_reported:'Categoria reportada',manual_type_reported:'Categoria definida no router',right_code:'Código de permissão',policy_code:'Código de política',level_code:'Código de nível',protocol_code:'Código de protocolo',wan_ref:'Referência WAN',source_restricted:'Origem restrita',connection_state:'Estado da ligação',encapsulation_reported:'Encapsulamento',dns_present:'DNS presente',aftr_present:'AFTR presente',gateway_present:'Gateway presente',uptime_seconds_reported:'Tempo IPv6 reportado (s)',origin_reported:'Origem reportada',present:'Presente',preferred_seconds_reported:'Validade preferida (s)',valid_seconds_reported:'Validade (s)',remaining_seconds_reported:'Tempo restante (s)',method_reported:'Método WPS',mlo_enabled:'MLO configurado',safe_remove_reported:'Remoção segura reportada',registration_state:'Estado do registo',call_state_reported:'Estado da chamada',registration_error:'Erro de registo',band:'Banda',component_reported:'Componente Wi-Fi reportado',lease_duration_seconds_reported:'Duração DHCP (s)',dns_override_present:'DNS personalizado presente',server_present:'Servidor presente',override_allowed:'Substituição permitida',managed:'Endereços geridos',other_config:'Outra configuração',l3_enabled:'Camada 3 ativa',mode_reported:'Modo reportado',vlan_reported:'VLAN',multicast_vlan_enabled:'VLAN multicast ativa',multicast_vlan_reported:'VLAN multicast',start_reported:'Início',end_reported:'Fim',repeat_days_code:'Código dos dias',ssid_mask_code:'Código da seleção de redes',filter_right:'Permissão MAC',filter_policy:'Política MAC',wlan_filter_right:'Permissão MAC Wi-Fi',wlan_filter_policy:'Política MAC Wi-Fi',port:'Porta',user_count:'Utilizadores configurados',share_all:'Partilha total configurada',wan_enabled:'Acesso WAN configurado',subnet_mask:'Máscara LAN',nat_enabled:'NAT configurado',services_reported:'Serviços WAN',connection_type_reported:'Tipo de ligação',backhaul_reported:'Backhaul reportado'};
Object.assign(labels,{pmf_policy_reported:'Política PMF reportada',wifi_mode_reported:'Modo Wi-Fi reportado',beacon_type_reported:'Autenticação configurada',basic_encryption_reported:'Cifra básica configurada',wpa_encryption_reported:'Cifra WPA configurada',ieee_encryption_reported:'Cifra IEEE configurada',mixed_encryption_reported:'Cifra mista configurada',rekey_interval_reported:'Intervalo de renovação reportado',pool_start_ip:'Início do pool',pool_end_ip:'Fim do pool',source_interface_ref:'Referência da interface',lease_reported:'Concessão reportada',resource_unit_reported:'Unidade de recurso reportada',rx_link_mbps:'Taxa PHY RX (Mbps)',tx_link_mbps:'Taxa PHY TX (Mbps)',rssi_dbm:'RSSI (dBm)',noise_dbm_reported:'Ruído reportado (dBm)',snr_db_reported:'SNR reportado (dB)',signal_quality_reported:'Qualidade de sinal reportada',power_save:'Poupança de energia',high_band:'Banda alta',supports_11k:'802.11k reportado',supports_11v:'802.11v reportado',supports_11w:'802.11w reportado',supports_11r:'802.11r reportado',dual_band:'Duas bandas reportadas',twt_requester:'TWT requester',twt_responder:'TWT responder',bss_coloring:'BSS coloring',ofdma:'OFDMA',mu_mimo:'MU-MIMO reportado',mimo:'MIMO reportado'});
const groups={wifi:['radio_settings','guest_limits','guest_network','wps','wifi_features','radios','wifi_backhaul','station_details'],clients:['dhcp','client_details','client_addresses','client_modes'],network:['ipv6','lan_settings','ipv6_lan','topology','wan_nat'],policies:['upnp','firewall_v4','firewall_v6','wan_acl','band_steering','wifi_schedule','mac_policy'],services:['usb_voice','file_services','dlna','voice_schedule']};
let payload=null,busy=false,pendingReload=false;
Object.assign(labels,{conflicting_fields:'Campos divergentes entre linhas reportadas',reported_rows:'Linhas reportadas para este MAC'});
group.addEventListener('change',()=>{applyFilters();updateCategoryNav();});
search.addEventListener('input',applyFilters);
document.querySelector('a[href="#routerObservability"]')?.addEventListener('click',()=>{document.getElementById('sidebar')?.classList.remove('open');});
const time=v=>v?new Date(v).toLocaleString('pt-PT'):'Sem leitura';
async function get(url){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);try{const r=await fetch(url,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error();return await r.json();}finally{clearTimeout(timer);}}
async function historyPage(source,output,button,before=0){
 button.disabled=true;
 try{
  const a=await get(`/api/router/observability/archive/recent?source=${encodeURIComponent(source.id)}&limit=50&before=${before}`);
  if(!before)output.replaceChildren(node('p',`Últimas ${a.records.length} observações guardadas${a.has_more?' · existem leituras anteriores':''}.`));
  else button.remove();
  for(const item of a.records){
   const d=node('details',undefined,'observation-archive-entry');
   d.append(node('summary',`${time(item.ts)} · ${item.status==='ok'?'Disponível':'Indisponível'}`));
   d.addEventListener('toggle',()=>{
     if(!d.open||d.childNodes.length>1)return;
     if(item.data?.length)d.append(table(item.data,source));
     else d.append(node('p',item.status==='ok'?'Nenhum registo.':'Leitura indisponível.'));
   });
   output.append(d);
  }
  if(a.has_more){const more=node('button','Carregar leituras anteriores');more.type='button';more.addEventListener('click',()=>historyPage(source,output,more,a.next_before));output.append(more);}
 }catch{output.append(node('p','Não foi possível consultar o arquivo. Pode tentar novamente.'));}
 finally{button.disabled=false;}
}
function state(){const c=window.FNO?.state?.status?.collector;collector.textContent=c?({ok:'Coletor ativo',collecting:'Recolha em curso',auth_blocked:'Autenticação bloqueada. O painel e o histórico continuam disponíveis; verificar acesso e reiniciar o serviço para retomar.',backoff:'Coletor em espera após falha. Histórico disponível.',not_started:'Coletor ainda sem estado nesta execução.'}[c.state]||'Estado desconhecido'):'Estado do coletor indisponível';collector.dataset.state=c?.state||'unknown';}
document.addEventListener('fno:update',state);state();
function table(data,source){const wrap=node('div',undefined,'observation-table');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Dados de '+source.title);const t=node('table'),head=node('thead'),tr=node('tr'),body=node('tbody');const keys=[...new Set(data.flatMap(r=>Object.keys(r)))];for(const k of keys){const th=node('th',labels[k]||k);th.scope='col';tr.append(th);}head.append(tr);t.append(head);for(const row of data){const r=node('tr');for(const k of keys){let v=row[k];if(k==='width_policy_code'&&v!=null)v=payload.width_policies?.[v]??`Código ${v}`;r.append(node('td',v==null?'Sem dados':v===true?'Sim':v===false?'Não':String(v)));}body.append(r);}t.append(body);wrap.append(t);return wrap;}
function badge(text,variant='neutral'){
 const b=node('span',text,'observation-badge '+variant);return b;
}
function metric(label,value,note=''){
 const m=node('div',undefined,'observation-metric');
 m.append(node('span',label,'observation-metric-name'),node('strong',String(value),'observation-metric-value'));
 if(note)m.append(node('small',note,'observation-metric-note'));
 return m;
}
function readable(key,value){
 if(key==='width_policy_code'&&value!==null&&value!==undefined)return payload?.width_policies?.[value]||'Código '+value;
 if(value===true)return 'Sim';
 if(value===false)return 'Não';
 if(value===null||value===undefined||value==='')return 'Sem dados';
 return String(value);
}
function recordPreview(source){
 const rows=Array.isArray(source.data)?source.data:[];
 if(!rows.length)return null;
 const chosen={
  radio_settings:['channel_reported','power_pct','width_policy_code','standard_reported','enabled'],
  radios:['band','enabled'],
  station_details:['rssi_dbm','snr_db_reported','rx_link_mbps','tx_link_mbps','work_mode_reported'],
  dhcp:['ip','interface_reported','lease_remaining_seconds','address_source_reported'],
  client_details:['ip','port_reported','status_reported','type_reported','lease_remaining_seconds'],
  client_addresses:['ip','port_reported','status_reported','time_reported'],
  client_modes:['ip','work_mode_reported'],
  upnp:['external_port','internal_port','protocol','client_ip','enabled'],
  topology:['mode_reported','vlan_reported','l3_enabled'],
  lan_settings:['enabled','pool_start_ip','pool_end_ip','dns_override_present'],
  wan_nat:['services_reported','nat_enabled','ipv4_enabled','connection_type_reported'],
  guest_limits:['upload_limit_reported','download_limit_reported'],
  guest_network:['pool_start_ip','pool_end_ip'],
  wifi_schedule:['start_reported','end_reported','enabled','repeat_days_code'],
  wifi_backhaul:['airtime_fairness','backhaul_reported'],
  usb_voice:['band','component_reported','registration_state','status_reported'],
  file_services:['enabled','port','user_count','wan_enabled'],
  ipv6:['kind','connection_state','dns_present','gateway_present'],
  ipv6_lan:['enabled','managed','other_config'],
  wps:['enabled','method_reported'],
  band_steering:['mac'],
  mac_policy:['filter_right','filter_policy','wlan_filter_right','wlan_filter_policy'],
  firewall_v4:['right_code','policy_code','level_code'],
  firewall_v6:['right_code','policy_code','level_code'],
  wan_acl:['enabled','protocol_code','source_restricted'],
  voice_schedule:['enabled','policy_code'],
  wifi_features:['mlo_enabled'],
  dlna:['enabled','share_all']
 }[source.id]||[];
 const titleKeys=['name','description','interface','band','kind','ip','slot','mac'];
 const view=node('div',undefined,'observation-record-preview');
 const heading=node('div',undefined,'observation-graphic-title');
 heading.append(node('strong','Detalhes por registo'),node('small','Amostra atual · até 6 registos'));
 view.append(heading);
 const grid=node('div',undefined,'observation-record-grid');
 for(const [i,entry] of rows.slice(0,6).entries()){
   if(!entry||typeof entry!=='object')continue;
   const card=node('article',undefined,'observation-record-card');
   const titleKey=titleKeys.find(k=>entry[k]!==undefined&&entry[k]!==null&&entry[k]!=='');
   const name=titleKey?(labels[titleKey]||titleKey)+': '+readable(titleKey,entry[titleKey]):'Registo '+(i+1);
   card.append(node('strong',name,'observation-record-title'));
   const fields=node('dl',undefined,'observation-record-fields');
   const keys=[...chosen,...Object.keys(entry)].filter((k,idx,list)=>list.indexOf(k)===idx&&k!==titleKey&&entry[k]!=null&&entry[k]!=='').slice(0,5);
   for(const key of keys){
     fields.append(node('dt',labels[key]||key),node('dd',readable(key,entry[key])));
   }
   if(fields.childNodes.length)card.append(fields);
   grid.append(card);
 }
 view.append(grid);
 if(rows.length>6)view.append(node('small','Mais '+(rows.length-6)+' registos na tabela técnica.'));
 return view;
}
function detailedConfiguration(source){
 const rows=Array.isArray(source.data)?source.data:[];
 const area=node('div',undefined,'observation-specialized');
 const grouped=new Set();
 const booleanFields=['enabled','hidden','auto_channel','wps_enabled','pmf','wmm','beamforming','mlo_enabled','airtime_fairness',
  'nat_enabled','wan_enabled','ipv4_enabled','ipv6_enabled','dns_override_present','safe_remove_reported',
  'managed','other_config','service_enabled','share_all','mu_mimo_enabled','supports_11r','supports_11v','supports_11w'];
 const boolRows=[];
 for(let index=0;index<Math.min(6,rows.length);index++){
  const entry=rows[index];
  if(!entry||typeof entry!=='object')continue;
  const name=entry.interface||entry.kind||entry.band||entry.slot||'Registo '+(index+1);
  for(const field of booleanFields){
   if(typeof entry[field]!=='boolean')continue;
   const key=String(name)+' '+field;
   if(grouped.has(key))continue;grouped.add(key);
   boolRows.push({name,field,value:entry[field]});
  }
 }
 if(boolRows.length){
  const section=node('div',undefined,'observation-boolean-panel');
  section.append(node('div','Estados de configuração reportados · não representam uma avaliação de segurança','observation-insight-heading'));
  const grid=node('div',undefined,'observation-boolean-grid');
  for(const v of boolRows.slice(0,16)){
    const tile=node('div',undefined,'observation-boolean-tile');
    tile.append(node('small',(labels[v.field]||v.field)+' · '+v.name));
    const flag=node('strong',v.value?'Ativado':'Desativado','observation-boolean-value');
    flag.dataset.value=String(v.value);
    tile.append(flag);grid.append(tile);
  }
  section.append(grid);
  if(boolRows.length>16)section.append(node('small',boolRows.length-16+' estados adicionais na tabela técnica.'));
  area.append(section);
 }
 if(source.id==='dhcp'||source.id==='client_details'){
  const key=source.id==='dhcp'?'lease_remaining_seconds':'lease_remaining_seconds';
  const values=rows.map(row=>row?.[key]).filter(v=>Number.isFinite(v)&&v>=0);
  if(values.length){
   const box=node('div',undefined,'observation-lease-panel');
   const min=Math.min(...values),max=Math.max(...values),avg=values.reduce((a,b)=>a+b,0)/values.length;
   box.append(node('strong','Concessões DHCP reportadas','observation-insight-heading'),
    node('p','Tempo restante das concessões, não tempo online dos dispositivos.','observation-provenance'));
   const stats=node('div',undefined,'observation-inline-stats');
   for(const [title,val] of [['Menor',min],['Média',avg],['Maior',max]])
     stats.append(metric(title,(val/60).toFixed(1)+' min','Valor reportado'));
   box.append(stats);area.append(box);
  }
 }
 if(source.id==='radio_settings' || source.id==='radios'){
  const radio=node('div',undefined,'observation-radio-layout');
  radio.append(node('strong','Interfaces e canais disponíveis','observation-insight-heading'));
  const cells=node('div',undefined,'observation-radio-grid');
  for(const item of rows.slice(0,10)){
   const iface=node('div',undefined,'observation-radio-card');
   iface.append(node('strong',item.interface||item.band||'Rádio reportado'));
   const bits=[
     item.band||null,
     Number.isFinite(item.channel_reported)?'Canal '+item.channel_reported:null,
     Number.isFinite(item.power_pct)?'Potência configurada '+item.power_pct+'%':null,
     item.enabled===true?'Ativado':item.enabled===false?'Desativado':null
   ].filter(Boolean);
   iface.append(node('small',bits.join(' · ')||'Sem metadados adicionais'));
   cells.append(iface);
  }
  radio.append(cells,node('small','WLAN pode identificar interface virtual, não cadeia MIMO nem antena física.'));area.append(radio);
 }
 if(source.id==='upnp'&&rows.length){
  const flow=node('div',undefined,'observation-upnp-list');flow.append(node('strong','Encaminhamentos de portas observados','observation-insight-heading'));
  for(const item of rows.slice(0,6)){
   const line=node('div',undefined,'observation-upnp-row');
   const left=node('span',(item.protocol||'Protocolo desconhecido')+' / '+(item.external_port??'—'));
   const arrow=node('span','→','observation-upnp-arrow');
   const right=node('span',(item.client_ip||'Destino desconhecido')+':'+(item.internal_port??'—'));
   line.append(left,arrow,right);flow.append(line);
  }
  flow.append(node('small','Mapeamento configurado: não comprova exposição externa nem sessão ativa.'));
  area.append(flow);
 }
 return area.childNodes.length?area:null;
}
function sourceOverview(source){
 const h=VM.header(source),n=VM.highlights(source);
 const result=node('div',undefined,'observation-quick');
 result.append(metric(h.noun,source.data===null?'—':h.count,source.data===null?'Ainda não existe leitura válida':h.description));
 if(source.data?.length&&n.length){
   for(const x of n.slice(0,3))result.append(metric(x.label,x.value,x.meaning));
 }
 if(source.data?.length){
   const overview=VM.distribution(source);
   if(overview && overview.items.length){
     const graph=node('div',undefined,'observation-distribution'),heading=node('div',undefined,'observation-graphic-title');
     heading.append(node('strong','Distribuição dos registos'),node('small','Contagem por '+(labels[overview.field]||overview.field)));
     graph.append(heading);
     const max=Math.max(...overview.items.map(x=>x.count),1);
     for(const item of overview.items){
       const r=node('div',undefined,'observation-bar-row');
       r.append(node('span',item.label,'observation-bar-name'));
       const track=node('span',undefined,'observation-bar-track'),fill=node('span',undefined,'observation-bar-fill');
       fill.style.width=(100*item.count/max).toFixed(1)+'%';
       track.append(fill);
       r.append(track,node('strong',String(item.count),'observation-bar-number'));
       graph.append(r);
     }
     result.append(graph);
   }
 }
 if(source.id==='station_details' && Array.isArray(source.data)){
   const stations=source.data.filter(r=>typeof r.rssi_dbm==='number'&&Number.isFinite(r.rssi_dbm));
   if(stations.length){
     const gauge=node('div',undefined,'observation-stations');
     gauge.append(node('h4','Sinal por estação · RSSI'));
     gauge.append(node('p','Escala visual −100 a −30 dBm. É sinal medido pelo AP para cada estação, não uma pontuação de qualidade.'));
     for(const r of stations.slice(0,8)){
       const entry=node('div',undefined,'observation-station');
       const label=node('span',r.description||r.interface||'Estação','observation-station-name');
       const track=node('div',undefined,'observation-signal-track'),dot=node('span',undefined,'observation-signal-dot');
       dot.style.left=(Math.max(0,Math.min(1,(r.rssi_dbm+100)/70))*100).toFixed(1)+'%';
       track.append(dot);
       entry.append(label,track,node('strong',r.rssi_dbm+' dBm'));
       gauge.append(entry);
     }
     if(stations.length>8)gauge.append(node('small',stations.length-8+' estações adicionais disponíveis na tabela.'));
     result.append(gauge);
   }
 }
 const special=detailedConfiguration(source);if(special)result.append(special);
 const preview=recordPreview(source);if(preview)result.append(preview);
 return result;
}
function svgNode(tag,attrs={},textValue){
 const el=document.createElementNS('http://www.w3.org/2000/svg',tag);
 for(const [key,value] of Object.entries(attrs))el.setAttribute(key,String(value));
 if(textValue!==undefined)el.textContent=String(textValue);
 return el;
}
function chartDate(ts){
 return new Date(ts).toLocaleString('pt-PT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}
function trendPanel(data){
 const content=node('div',undefined,'observation-trend-inner');
 const points=Array.isArray(data.points)?data.points:[];
 const head=node('div',undefined,'observation-trend-header');
 head.append(node('h4','Evolução no período'),badge(points.length+' leituras guardadas'));
 content.append(head);
 const message=node('p',undefined,'observation-trend-message');
 message.textContent=data.truncated
  ?'Prévia incompleta: apenas as '+points.length+' observações mais recentes do período. Leituras antigas continuam no arquivo.'
  :'Leituras reais desta fonte no período. A ausência de pontos não é representada como zero.';
 content.append(message);
 if(!points.length){content.append(node('p','Não existem observações guardadas para esta fonte neste período.','observation-trend-empty'));return content;}
 const status=points.filter(p=>p.status==='ok').length;
 content.append(node('p',status+' leituras disponíveis · '+(points.length-status)+' indisponíveis · '+chartDate(points[0].ts)+' a '+chartDate(points[points.length-1].ts),'observation-trend-range'));
 const options=Array.isArray(data.metrics)?data.metrics:[];
 const select=node('select');select.setAttribute('aria-label','Métrica do histórico desta fonte');
 for(const metric of options){
   const option=node('option',metric.label);option.value=metric.key;select.append(option);
 }
 const lineLabel=node('label','Métrica histórica: ','observation-trend-select');
 lineLabel.append(select);content.append(lineLabel);
 const visual=node('div',undefined,'observation-trend-visual');content.append(visual);
 function draw(){
   visual.replaceChildren();
   const metric=options.find(m=>m.key===select.value)||options[0];if(!metric)return;
   const segments=VM.trendSegments(points,metric.key,data.cadence_seconds);
   const domain=VM.trendDomain(segments,metric.unit);
   if(!domain){
     visual.append(node('p','Nenhuma medição numérica válida para esta métrica na janela. Estados indisponíveis e valores null não são zero.'));
     return;
   }
   const caption=node('p',domain.total+' medições válidas · sem interpolação entre lacunas','observation-trend-caption');
   const svg=svgNode('svg',{viewBox:'0 0 900 265',role:'img',
      'aria-label':metric.label+' — '+domain.total+' medições válidas, de '+chartDate(points[0].ts)+' a '+chartDate(points[points.length-1].ts)});
   svg.classList.add('observation-trend-svg');
   const plot={left:56,right:872,top:22,bottom:220};
   const first=Date.parse(points[0].ts),last=Date.parse(points[points.length-1].ts);
   const extent=Math.max(1,last-first);
   const x=t=>plot.left+(t-first)/extent*(plot.right-plot.left);
   const y=v=>plot.bottom-(v-domain.min)/(domain.max-domain.min)*(plot.bottom-plot.top);
   const format=n=>metric.unit==='registos'?String(Math.round(n)):String(Math.round(n*10)/10);
   for(let i=0;i<=4;i++){
     const value=domain.min+(domain.max-domain.min)*(1-i/4),yy=plot.top+(plot.bottom-plot.top)*i;
     svg.append(svgNode('line',{x1:plot.left,x2:plot.right,y1:yy,y2:yy,class:'observation-trend-gridline'}));
     svg.append(svgNode('text',{x:plot.left-9,y:yy+4,'text-anchor':'end',class:'observation-trend-axis'},format(value)));
   }
   const t1=svgNode('text',{x:plot.left,y:248,class:'observation-trend-axis'},chartDate(points[0].ts));
   const t2=svgNode('text',{x:plot.right,y:248,'text-anchor':'end',class:'observation-trend-axis'},chartDate(points[points.length-1].ts));
   svg.append(t1,t2);
   const used=segments.flat();
   for(const segment of segments){
     const points2=segment.map(p=>[x(p.ts),y(p.value)]);
     if(points2.length>1){
       svg.append(svgNode('path',{d:points2.map((p,i)=>(i?'L':'M')+p[0].toFixed(2)+','+p[1].toFixed(2)).join(' '),
         class:'observation-trend-line',fill:'none'}));
     }
     for(const [index,p] of segment.entries()){
       if(segment.length>90&&index%Math.ceil(segment.length/90)!==0&&index!==segment.length-1)continue;
       const dot=svgNode('circle',{cx:x(p.ts),cy:y(p.value),r:3.4,class:'observation-trend-dot'});
       dot.append(svgNode('title',{},chartDate(p.ts)+' · '+p.value+' '+metric.unit));
       svg.append(dot);
     }
   }
   visual.append(svg,caption);
   if(used.length===1)visual.append(node('p','Existe apenas uma medição válida; foi assinalada como ponto, sem desenhar uma tendência.'));
 }
 select.addEventListener('change',draw);
 draw();
 return content;
}
function sourceTrend(source,button,slot){
 if(button.dataset.trendState==='failed'){slot.replaceChildren();button.dataset.trendState='';}
 if(!slot.hidden&&slot.childNodes.length){slot.hidden=true;button.textContent='Ver gráfico histórico';return;}
 if(slot.childNodes.length){slot.hidden=false;button.textContent='Ocultar gráfico histórico';return;}
 button.disabled=true;button.textContent='A carregar histórico…';slot.hidden=false;
 slot.replaceChildren(node('p','A consultar a fonte selecionada…'));
 const hours=period.value;
 get('/api/router/observability/trend?source='+encodeURIComponent(source.id)+'&hours='+encodeURIComponent(hours))
  .then(result=>{slot.replaceChildren(trendPanel(result));button.dataset.trendState='loaded';button.textContent='Ocultar gráfico histórico';})
  .catch(()=>{slot.replaceChildren(node('p','Não foi possível carregar o histórico desta fonte.'));button.dataset.trendState='failed';button.textContent='Tentar novamente';})
  .finally(()=>{button.disabled=false;});
}
function technical(source){
 const raw=node('details',undefined,'observation-raw'),head=node('summary','Inspecionar tabela técnica · '+(source.data?.length||0)+' linhas');
 const contents=node('div',undefined,'observation-raw-body');
 raw.append(head,contents);
 function loadRows(){
   if(contents.childNodes.length)return;
   if(source.data?.length)contents.append(table(source.data,source));
   else contents.append(node('p',source.data?'Nenhum registo nesta leitura.':'Leitura ainda indisponível.'));
 }
 // Small tables are cheap and preserve full-text accessibility and inspection.
 // Large inventories remain lazy so the initial page does not build thousands of TDs.
 if(Array.isArray(source.data)&&source.data.length<=3)loadRows();
 raw.addEventListener('toggle',()=>{if(raw.open)loadRows();});
 return raw;
}
function renderSources(data){
 const opened=new Set([...cards.querySelectorAll('details.observation-source[open]')].map(n=>n.dataset.source));
 cards.replaceChildren();
 const countsBySource=new Map();
 for(const c of data.changes)countsBySource.set(c.source,(countsBySource.get(c.source)||0)+1);
 const all=VM.sections(data.sources);
 for(const section of all){
   const sectionBox=node('section',undefined,'observation-section');
   sectionBox.id='diagnostic-'+section.id;sectionBox.dataset.section=section.id;
   const header=node('div',undefined,'observation-section-head');
   const heading=node('div');
   heading.append(node('h3',section.title),node('p',section.description));
   header.append(heading,badge(section.sources.filter(s=>s.quality==='ok').length+'/'+section.sources.length+' atuais'));
   sectionBox.append(header);
   const grid=node('div',undefined,'observation-section-grid');
   for(const source of section.sources){
     const h=VM.header(source);
     const card=node('details',undefined,'observation-source');card.dataset.source=source.id;card.dataset.section=section.id;card.open=opened.has(source.id);
     if(source.quality!=='ok')card.dataset.quality=source.quality;
     const summary=node('summary',undefined,'observation-source-summary');
     const lead=node('span',undefined,'observation-source-lead');
     lead.append(node('span',source.title,'observation-source-title'));
     lead.append(node('small',h.description,'observation-source-description'));
     const bottom=node('span',undefined,'observation-source-meta');
     bottom.append(node('span',source.data===null?'Sem leitura válida':h.noun+': '+h.count));
     if(countsBySource.has(source.id))bottom.append(badge(countsBySource.get(source.id)+' alterações','modified'));
     lead.append(bottom);
     const quality=source.quality==='ok'?'Atual':source.quality==='stale'?'Leitura antiga':'Indisponível';
     const flags=node('span',undefined,'observation-source-flags');
     flags.append(badge(quality,source.quality==='ok'?'present':source.quality==='stale'?'aged':'missing'));
     summary.append(lead,flags);card.append(summary);
     const content=node('div',undefined,'observation-source-content');
     content.append(node('p','Última leitura válida: '+time(source.collected_at)+(source.age_seconds==null?'':' · há '+source.age_seconds+' s')+'. Última tentativa: '+(source.attempt_status==='ok'?'disponível':source.attempt_status==='not_collected'?'não recolhida':'indisponível')+(source.reason?' · '+({schema:'formato não reconhecido',transport:'falha de comunicação',http:'falha HTTP',authentication:'autenticação',budget:'limite de tempo'}[source.reason]||'falha'):'')+'.','observation-provenance'));
     const overviewSlot=node('div',undefined,'observation-source-overview');
     content.append(overviewSlot);
     const populate=()=>{
       if(!overviewSlot.childNodes.length)overviewSlot.append(sourceOverview(source),technical(source));
     };
     card.addEventListener('toggle',()=>{if(card.open)populate();});
     if(card.open)populate();
     const actions=node('div',undefined,'observation-source-actions');
     const history=node('button','Consultar observações guardadas');history.type='button';
     const output=node('div',undefined,'observation-archive');
     history.addEventListener('click',()=>historyPage(source,output,history));
     const trendButton=node('button','Ver gráfico histórico');trendButton.type='button';
     const trendSlot=node('div',undefined,'observation-trend');trendSlot.hidden=true;
     trendButton.addEventListener('click',()=>sourceTrend(source,trendButton,trendSlot));
     actions.append(trendButton,history);content.append(actions,trendSlot,output);
     card.append(content);grid.append(card);
   }
   sectionBox.append(grid);cards.append(sectionBox);
 }
 applyFilters();
}
function applyFilters(){
 if(!payload)return;
 const query=search.value.toLocaleLowerCase().trim(),changed=new Set(payload.changes.map(c=>c.source));
 let visible=0;
 for(const section of cards.querySelectorAll('.observation-section')){
   let count=0;
   for(const card of section.querySelectorAll('.observation-source')){
     const source=payload.sources.find(s=>s.id===card.dataset.source);
     const text=[source?.title,source?.id,VM.header(source||{}).description].join(' ').toLocaleLowerCase();
     const match=(group.value==='all'||group.value===section.dataset.section)&&(!query||text.includes(query))&&
       (quickMode==='all'||quickMode==='changed'&&changed.has(source?.id)||
        quickMode==='missing'&&source?.quality!=='ok');
     card.hidden=!match;if(match){visible++;count++;}
   }
   section.hidden=count===0;
 }
 matching.textContent=visible+' de '+payload.sources.length+' fontes visíveis';
 let empty=cards.querySelector('.observation-search-empty');
 if(!visible){
   if(!empty){empty=node('p','Nenhuma fonte corresponde aos filtros. Podes mudar a pesquisa ou escolher “Todas”.','observation-search-empty');cards.append(empty);}
   empty.hidden=false;
 }else if(empty)empty.hidden=true;
}
function updateCategoryNav(){
 for(const button of categoryNav.querySelectorAll('[data-observation-category]')){
   const selected=button.dataset.observationCategory===group.value;
   button.setAttribute('aria-pressed',String(selected));
 }
}
function renderCategoryNav(data){
 categoryNav.replaceChildren();
 const available=new Map(VM.sections(data.sources).map(x=>[x.id,x]));
 const view=VM.SECTIONS.map(x=>available.get(x.id)||{...x,sources:[]});
 const options=[
    {id:'all',title:'Todas',subtitle:'Panorama',total:data.sources.length,current:data.sources.filter(s=>s.quality==='ok').length},
    ...view.map(v=>({id:v.id,title:({wifi:'Wi-Fi',clients:'Dispositivos',policies:'Regras',network:'Rede e IPv6',services:'Serviços'})[v.id]||v.title,
       subtitle:v.title,total:v.sources.length,current:v.sources.filter(s=>s.quality==='ok').length}))
 ];
 for(const option of options){
   const button=node('button',undefined,'observation-category-card');button.type='button';
   button.dataset.observationCategory=option.id;
   if(!option.total){button.disabled=true;button.title='Sem fontes deste grupo na resposta atual';}
   button.setAttribute('aria-label',option.title+' · '+option.current+' de '+option.total+' fontes atuais');
   const top=node('span',undefined,'observation-category-top');
   top.append(node('strong',option.title),node('span',option.current+'/'+option.total,'observation-category-total'));
   const meter=node('span',undefined,'observation-category-meter');
   const fill=node('span',undefined,'observation-category-meter-fill');
   fill.style.width=(option.total?option.current/option.total*100:0).toFixed(1)+'%';
   meter.append(fill);
   button.append(top,meter,node('small',!option.total?'Nenhuma fonte recebida':option.current===option.total?'Todas com leitura atual':option.total-option.current+' sem leitura atual'));
   button.addEventListener('click',()=>{
     group.value=option.id;search.value='';quickMode='all';
     for(const el of quickbar.querySelectorAll('[data-quick]'))el.setAttribute('aria-pressed',String(el.dataset.quick==='all'));
     applyFilters();updateCategoryNav();
     cards.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
   });
   categoryNav.append(button);
 }
 updateCategoryNav();
}
function renderSummary(data){
 renderCategoryNav(data);
 summaryGrid.replaceChildren();
 const x=VM.summary(data.sources,data.changes);
 for(const [label,value,help] of [
   ['Fontes atuais',x.current+' / '+x.total,'Respondem com leitura válida recente'],
   ['Com leitura antiga',x.old,'Dados preservados, sem confirmação atual'],
   ['Registos reportados',x.records,'Soma de linhas das últimas leituras; não aparelhos únicos'],
   ['Alterações no período',x.changes+(data.changes_truncated?'+':''),'Diferenças observadas; prévia limitada a 500']]){
   const tile=metric(label,value,help);tile.classList.add('observation-kpi');summaryGrid.append(tile);
 }
}
function renderChanges(data){
 changes.replaceChildren();changeChart.replaceChildren();
 const h=VM.changeBins(data.changes,data.hours);
 if(h.length){
   const full=node('div',undefined,'observation-change-axis');
   const bars=node('div',undefined,'observation-change-bars');
   bars.setAttribute('role','img');bars.setAttribute('aria-label','Distribuição de '+data.changes.length+' alterações observadas no período selecionado'+(data.changes_truncated?'; prévia incompleta':''));
   const max=Math.max(...h.map(x=>x.count),1);
   for(const item of h){
     const col=node('span',undefined,'observation-change-column');
     const bar=node('span',undefined,'observation-change-column-fill');
     bar.style.height=(item.count>0?Math.max(5,100*item.count/max):0)+'%';
     col.title=item.count+' alterações entre '+time(item.start)+' e '+time(item.end);
     col.append(bar);bars.append(col);
   }
   full.append(node('span',time(h[0].start)),node('span',time(h[h.length-1].end)));
   changeChart.append(node('h4','Distribuição temporal das diferenças registadas'),bars,full);
   if(data.changes_truncated)changeChart.append(node('p','Prévia incompleta: foram retornadas apenas as primeiras 500 alterações. O gráfico não representa a totalidade do período.'));
 }
 if(!data.changes.length)changes.append(node('p','Nenhuma diferença observada neste período. A primeira leitura estabelece a referência. Ausência de alterações não comprova que a configuração nunca mudou.'));
 for(const c of data.changes){
   const source=data.sources.find(s=>s.id===c.source)||{title:c.source},d=c.detail,entry=node('details',undefined,'observation-change');
   const title=node('summary',undefined);
   title.append(node('strong',source.title),node('time',time(c.observed_at)),badge(c.crosses_gap?'Atravessa lacuna':'Mudança observada',c.crosses_gap?'aged':'modified'));
   entry.append(title,node('p',d.before_count+' → '+d.after_count+' registos. Campos: '+(d.changed_fields.map(k=>labels[k]||k).join(', ')||'composição dos registos')+(d.added!=null?' · '+d.added+' adicionados, '+d.removed+' removidos':'')+'. Janela entre '+time(c.previous_at)+' e '+time(c.observed_at)+'.'));
   const compare=node('button','Comparar leituras'),output=node('div');compare.type='button';compare.addEventListener('click',async()=>{compare.disabled=true;try{const result=await get('/api/router/observability/change?id='+c.id);output.replaceChildren();for(const [key,label] of [['before','Antes'],['after','Depois']]){output.append(node('h4',label));if(result[key]?.length)output.append(table(result[key],source));else output.append(node('p',result[key]?'Nenhum registo.':'Observação já não disponível na retenção atual.'));}}catch{output.replaceChildren(node('p','Comparação indisponível.'));}finally{compare.disabled=false;}});entry.append(compare,output);changes.append(entry);
 }
 if(data.changes_truncated)changes.append(node('p','A prévia mostra até 500 alterações. Use um período menor; os registos originais permanecem no arquivo.'));
}
let operationsLoaded=false,operationsHistoryData=null;
function renderOperationsHistory(){
 if(!operationsTrend.open||!operationsHistoryData)return;
 const oldMetric=operationsTrendBody.querySelector('select')?.value;
 operationsTrendBody.replaceChildren();
 const h=operationsHistoryData;
 if(Array.isArray(h.points)&&h.points.length){
   operationsTrendBody.append(trendPanel({title:'Saúde do Observatory',points:h.points,
     metrics:h.metrics||[],cadence_seconds:60,truncated:h.truncated}));
   const control=operationsTrendBody.querySelector('select');
   if(control&&oldMetric&&[...control.options].some(o=>o.value===oldMetric)){
     control.value=oldMetric;control.dispatchEvent(new Event('change'));
   }
 }else operationsTrendBody.append(node('p','Sem histórico do host disponível. A recolha no S7 pode ainda não estar ativa.'));
}
operationsTrend.addEventListener('toggle',renderOperationsHistory);
function renderOperations(result){
 operationsLoaded=true;operationsMetrics.replaceChildren();operationsAlerts.replaceChildren();
 const h=result.health||{},active=Array.isArray(result.alerts)?result.alerts:[];
 const hasCritical=active.some(x=>x.severity==='critical');
 const hasWarning=active.some(x=>x.severity==='warning');
 const rulesOff=result.rules?.enabled===false;
 const incomplete=h.hostSampleAgeMinutes==null||h.collectorSuccessAgeMinutes==null||h.volumeAccessible===false;
 operationsStatus.textContent=hasCritical?'Estado crítico':
   hasWarning?'Requer atenção':
   rulesOff?'Regras desativadas':
   incomplete?'Telemetria incompleta':
   active.length?'Observações registadas':'Sem alertas ativos';
 // Disabled alerts and unknown health must never inherit the green "present" badge.
 operationsStatus.className='observation-badge '+(hasCritical?'missing':hasWarning||rulesOff||incomplete?'aged':active.length?'':'present');
 function num(v,unit,digits=1){return typeof v==='number'&&Number.isFinite(v)?v.toFixed(digits)+(unit?' '+unit:''):'Sem medição';}
 const tiles=[
  ['RAM do processo',num(h.processRssMB,'MB'),'Da última leitura válida do S7'],
  ['Volume do arquivo',num(h.volumeFreeGiB,'GiB'),'Espaço livre na unidade configurada'],
  ['SQLite + WAL',num(h.databaseMB,'MB')+' / '+num(h.walMB,'MB'),'Tamanho dos ficheiros, não espaço reservado'],
  ['API p95',num(h.apiP95Ms,'ms'),'Amostra das últimas 128 requisições'],
  ['Coletor Huawei',h.collectorState||'Desconhecido','Sucesso há '+num(h.collectorSuccessAgeMinutes,'min')],
  ['Crescimento SQLite',num(h.growthMBPerDay,'MB/dia'),
   h.growthSampleAgeMinutes==null?'Só calculado após ≥6 horas de leituras':
   'Taxa histórica · última amostra há '+num(h.growthSampleAgeMinutes,'min')]
 ];
 for(const [title,value,note] of tiles)operationsMetrics.append(metric(title,value,note));
 if(result.rulesSource==='invalid_file_disabled')
   operationsAlerts.append(node('p','Configuração local de alertas inválida: regras desativadas até correção.','observation-operations-warning'));
 if(!active.length)operationsAlerts.append(node('p',result.rules?.enabled===false?'Alertas desativados na configuração local.':
    'Nenhuma condição das regras configuradas foi detetada nas leituras disponíveis. Isso não comprova ausência de problemas.','observation-operations-empty'));
 for(const entry of active.slice(0,20)){
   const line=node('div',undefined,'observation-alert-row');line.dataset.severity=entry.severity||'info';
   const label=entry.severity==='critical'?'Crítico':entry.severity==='warning'?'Atenção':'Informativo';
   const textBox=node('div');textBox.append(node('strong',entry.title||'Observação'),node('small',entry.detail||''));
   line.append(badge(label,entry.severity==='critical'?'missing':entry.severity==='warning'?'aged':'neutral'),textBox);
   operationsAlerts.append(line);
 }
 const footer=node('div',undefined,'observation-operations-footer');
 footer.append(node('small','Regras: '+(result.rulesSource==='local_file'?'configuração local':result.rulesSource==='defaults'?'valores padrão':result.rulesSource||'não identificada')+
  ' · Apenas alertas passivos nesta página. Não são enviados e-mails ou notificações externas.'));
 operationsAlerts.append(footer);
 operationsHistoryData=result.history||{};
 if(operationsTrend.open)renderOperationsHistory();
}
async function loadOperations(){
 try{
  const result=await get('/api/router/operations');
  renderOperations(result);
 }catch{
  operationsStatus.textContent=operationsLoaded?'Última leitura · sem atualização':'Telemetria indisponível';
  operationsStatus.className='observation-badge aged';
  const warning=node('p','Não foi possível atualizar a saúde do Observatory. As métricas anteriores, se exibidas, podem estar desatualizadas.','observation-operations-warning');
  if(operationsLoaded){
    // Repeated refresh failures should not pile up duplicate stale notices.
    operationsAlerts.querySelectorAll('[data-stale-warning]').forEach(entry=>entry.remove());
    warning.dataset.staleWarning='true';
    operationsAlerts.prepend(warning);
  }else{
    operationsAlerts.replaceChildren(warning);
  }
 }
}
function render(data){
 renderSummary(data);
 renderSources(data);
 renderChanges(data);
 unsupported.replaceChildren(...Object.values(data.unsupported||{}).map(v=>node('li',v)));
 notice.textContent=data.sources.filter(s=>s.quality==='ok').length+'/'+data.sources.length+' fontes atuais · consulta '+time(new Date().toISOString())+'.';
}
async function load(){if(busy){pendingReload=true;return;}busy=true;refresh.disabled=true;notice.textContent='A consultar leituras guardadas…';try{payload=await get(`/api/router/observability?hours=${period.value}`);render(payload);}catch{notice.textContent='API indisponível. Os valores apresentados pertencem à última consulta bem-sucedida.';}finally{busy=false;refresh.disabled=false;loadOperations();if(pendingReload){pendingReload=false;load();}}}
refresh.addEventListener('click',load);period.addEventListener('change',load);download.addEventListener('click',()=>{if(!payload)return;const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),a=node('a');a.href=url;a.download='router-observations-private.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});load();setInterval(()=>{if(!document.hidden&&!panel.contains(document.activeElement))load();},60000);
})();
