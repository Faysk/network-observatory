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
const refresh=node('button','Atualizar painel'),download=node('button','Exportar resumo JSON');refresh.type=download.type='button';toolbar.append(group,period,search,refresh,download);panel.append(toolbar);
const notice=node('p','','observation-notice');notice.setAttribute('role','status');panel.append(notice);
const summaryGrid=node('div',undefined,'observation-overview');panel.append(summaryGrid);
const viewNote=node('p','Selecione uma fonte para inspecionar os dados. Os indicadores mostram valores reportados; não classificam automaticamente a segurança da rede.','observation-reading-note');panel.append(viewNote);
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
let payload=null,busy=false;
Object.assign(labels,{conflicting_fields:'Campos divergentes entre linhas reportadas',reported_rows:'Linhas reportadas para este MAC'});
group.addEventListener('change',()=>{if(payload)render(payload);});
search.addEventListener('input',()=>{if(payload)renderSources(payload);});
document.querySelector('a[href="#routerObservability"]')?.addEventListener('click',()=>{document.getElementById('sidebar')?.classList.remove('open');});
const time=v=>v?new Date(v).toLocaleString('pt-PT'):'Sem leitura';
async function get(url){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);try{const r=await fetch(url,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error();return await r.json();}finally{clearTimeout(timer);}}
async function historyPage(source,output,button,after=0){
 button.disabled=true;
 try{
  const a=await get(`/api/router/observability/archive?source=${encodeURIComponent(source.id)}&limit=100&after=${after}`);
  if(!after)output.replaceChildren(node('p',`Primeiras ${a.records.length} observações guardadas${a.has_more?' · carregue as páginas seguintes para continuar':''}.`));
  else button.remove();
  for(const item of a.records){const d=node('details');d.append(node('summary',`${time(item.ts)} · ${item.status==='ok'?'Disponível':'Indisponível'}`));if(item.data?.length)d.append(table(item.data,source));else d.append(node('p',item.status==='ok'?'Nenhum registo.':'Leitura indisponível.'));output.append(d);}
  if(a.has_more){const more=node('button','Carregar mais observações');more.type='button';more.addEventListener('click',()=>historyPage(source,output,more,a.next_after));output.append(more);}
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
 const preview=recordPreview(source);if(preview)result.append(preview);
 return result;
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
 const query=search.value.toLocaleLowerCase().trim();
 const allowed=(group.value==='all'?all:all.filter(section=>section.id===group.value)).map(section=>({
   ...section,sources:section.sources.filter(src=>!query||[src.title,src.id,VM.header(src).description].join(' ').toLocaleLowerCase().includes(query))
 })).filter(section=>section.sources.length);
 if(!allowed.length)cards.append(node('p','Nenhuma fonte corresponde à pesquisa. Experimenta outro termo.','observation-search-empty'));
 for(const section of allowed){
   const sectionBox=node('section',undefined,'observation-section');
   sectionBox.id='diagnostic-'+section.id;
   const header=node('div',undefined,'observation-section-head');
   const heading=node('div');
   heading.append(node('h3',section.title),node('p',section.description));
   header.append(heading,badge(section.sources.filter(s=>s.quality==='ok').length+'/'+section.sources.length+' atuais'));
   sectionBox.append(header);
   const grid=node('div',undefined,'observation-section-grid');
   for(const source of section.sources){
     const h=VM.header(source);
     const card=node('details',undefined,'observation-source');card.dataset.source=source.id;card.open=opened.has(source.id);
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
     content.append(sourceOverview(source),technical(source));
     const actions=node('div',undefined,'observation-source-actions');
     const history=node('button','Consultar observações guardadas');history.type='button';
     const output=node('div',undefined,'observation-archive');
     history.addEventListener('click',()=>historyPage(source,output,history));
     actions.append(history);content.append(actions,output);
     card.append(content);grid.append(card);
   }
   sectionBox.append(grid);cards.append(sectionBox);
 }
}
function renderSummary(data){
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
function render(data){
 renderSummary(data);
 renderSources(data);
 renderChanges(data);
 unsupported.replaceChildren(...Object.values(data.unsupported||{}).map(v=>node('li',v)));
 notice.textContent=data.sources.filter(s=>s.quality==='ok').length+'/'+data.sources.length+' fontes atuais · consulta '+time(new Date().toISOString())+'.';
}
async function load(){if(busy)return;busy=true;refresh.disabled=true;notice.textContent='A consultar leituras guardadas…';try{payload=await get(`/api/router/observability?hours=${period.value}`);render(payload);}catch{notice.textContent='API indisponível. Os valores apresentados pertencem à última consulta bem-sucedida.';}finally{busy=false;refresh.disabled=false;}}
refresh.addEventListener('click',load);period.addEventListener('change',load);download.addEventListener('click',()=>{if(!payload)return;const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})),a=node('a');a.href=url;a.download='router-observations-private.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});load();setInterval(()=>{if(!document.hidden&&!panel.contains(document.activeElement))load();},60000);
})();
