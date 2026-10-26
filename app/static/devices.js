/* Real per-device views; raw exports and seven windows use the local historian. */
(()=>{'use strict';
const {state:app,$,$$,esc,fmt,time,duration,retention,api,toast,tile,keyvals,empty,chart,trap}=window.FNO;
const Inventory=window.FNOInventory;
if(!Inventory)throw Error('FNO inventory selector missing');
const state={id:null,period:'24h',tab:'overview',filter:'all',query:'',bundle:null,request:0,
  category:'all',confidence:'all',vendor:'all',macKind:'all',status:'all',band:'all',sort:'status',limit:40,
  expandedGroups:{online:true,offline:false,unknown:true,stale:false},explorerScrollTop:0};
let lastHomeMarkup=null, lastInventorySignature=null, deviceController=null;
function preserveFocus(root, update){
 const active=document.activeElement, key=active?.dataset?.openDevice||active?.dataset?.toggleGroup;
 const inside=root.contains(active);update();
 if(inside&&key){const next=Array.from(root.querySelectorAll('[data-open-device],[data-toggle-group]')).find(x=>(x.dataset.openDevice||x.dataset.toggleGroup)===key);(next||$('#deviceExplorerSearch'))?.focus({preventScroll:true});}
}
function devices(){return Inventory.select(Array.isArray(app.clients)?app.clients:[],{sort:'status'});}
function status(c){return {online:'Online reportado',offline:'Offline reportado',unknown:'Sem indicação',stale:'Sem leitura recente'}[c.presence||Inventory.presence(c)];}
const DEVICE_CATEGORIES=new Set(['smartphone','tablet','laptop','desktop','game_console','smart_tv','streaming_box','printer','camera','robot_vacuum','network_device','iot','computer','android_device','unknown']);
const CATEGORY_LABELS={smartphone:'Smartphone',tablet:'Tablet',laptop:'Notebook',desktop:'Computador',game_console:'Console',smart_tv:'Smart TV',streaming_box:'Multimédia',printer:'Impressora',camera:'Câmara',robot_vacuum:'Aspirador robô',network_device:'Equipamento de rede',iot:'IoT',computer:'Computador',android_device:'Equipamento Android',unknown:'Categoria desconhecida'};
const PLATFORM_LABELS={android:'Android',ios:'iOS/iPadOS',windows:'Windows',linux:'Linux',macos:'macOS'};
const CONFIDENCE_LABELS={high:'Alta',medium:'Média',low:'Baixa',unknown:'Desconhecida'};
function categoryOf(c){const category=c?.presentation?.category||c?.classification?.category;return DEVICE_CATEGORIES.has(category)?category:'unknown';}
function iconMarkup(c){const choice=c?.presentation?.icon;const category=DEVICE_CATEGORIES.has(choice)?choice:categoryOf(c);return '<svg class="device-category-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="/device-icons.svg#'+category+'"></use></svg>';}
function categoryLabel(c){const label=CATEGORY_LABELS[categoryOf(c)];return c?.presentation?.category?label+' · Personalizado':c?.classification?.display_name_source==='history'?label+' · Histórico':c?.classification?.confidence==='low'&&categoryOf(c)!=='unknown'?label+' · Inferido':label;}
function identitySubtitle(c){
 const label=categoryLabel(c);
 const platform=PLATFORM_LABELS[c?.classification?.platform_family];
 // Do not repeat Android or imply a phone/tablet when only DHCP says Android.
 const suffix=platform&&!(categoryOf(c)==='android_device'&&platform==='Android')?' · '+platform:'';
 return label+suffix;
}
function row(c){const link=Inventory.connection(c,app.status?.huawei),radio=Inventory.wifiContext(c,app.status?.huawei);return `<button class="device-list-row" data-open-device="${c.id}" aria-label="Ver detalhes e histórico de ${esc(c.name)}; ${esc(categoryLabel(c))}"><span class="device-label"><span class="device-avatar category-${categoryOf(c)}">${iconMarkup(c)}</span><span class="device-label-text"><strong>${esc(c.name)}</strong><small>${esc(identitySubtitle(c)+(c.network==='wifi'?' · '+radio.label:''))}</small></span></span><span class="device-col"><small>Estado</small><span class="device-status ${!c.recent||c.reported_status!=='Online'?'offline':''}">${esc(status(c))}</span></span><span class="device-col"><small>Interface</small><strong>${esc(c.network==='wired'?'Ethernet':c.network==='wifi'?(radio.band?'Wi-Fi · '+radio.band:'Wi-Fi · banda não identificada'):'Não determinada')}</strong></span><span class="device-col"><small>Sinal / ligação</small><strong title="${esc(link.title)}">${esc(link.label)}</strong></span><span class="device-col"><small>Último IP reportado</small><strong>${esc(c.ips?.[0]||'Sem dados')}</strong></span><svg class="ic device-row-chevron" aria-hidden="true"><use href="#i-chevron"/></svg></button>`;}
function filtered(){const results=Inventory.select(Array.isArray(app.clients)?app.clients:[],state);return state.band==='all'?results:results.filter(c=>Inventory.wifiContext(c,app.status?.huawei).band===(state.band==='24'?'2,4 GHz':'5 GHz'));}
function inventorySkeletons(){return window.FNO.loading?Array.from({length:4},()=>window.FNO.loading('Carregando dispositivo…',true)).join(''):empty('Carregando inventário…');}
function renderList(){
 const list=filtered(),phase=app.resources?.inventory?.phase;
 const msg=list.length?'':state.query||state.filter!=='all'||state.category!=='all'||state.status!=='all'||state.band!=='all'
   ?'Nenhuma identidade corresponde à pesquisa ou aos filtros.'
   :phase==='error'?'O inventário está indisponível.'
   :phase==='loading'||!app.api?'A aguardar o primeiro inventário…'
   :'Nenhuma identidade MAC observada.';
 const markup=list.length?list.slice(0,5).map(row).join(''):phase==='loading'?inventorySkeletons():empty(msg);
 if(lastHomeMarkup!==markup){$('#deviceList').innerHTML=markup;lastHomeMarkup=markup;}
 $('.device-list-footer>span').textContent=!app.clients.length&&!['ready','empty'].includes(phase)?'Inventário ainda não disponível':`${list.length} identidades MAC · Huawei HTTP · contagem por endereço, não por aparelho físico`;
 if(state.id===null&&!$('#deviceLayer').hidden)renderExplorerResults();
}
function explorer(){
 const list=filtered();
 $('#deviceDrawerTitle').textContent='Explorar dispositivos';
 $('#deviceCrumb').textContent='INVENTÁRIO OBSERVADO';
 $('#deviceSubtitle').textContent='Cada MAC é uma identidade observada; não equivale necessariamente a um aparelho físico.';
 $('#deviceIcon').className='identity-symbol category-unknown';
 $('#deviceIcon').innerHTML=iconMarkup(null);
 $('#deviceConnectionBadge').textContent=String((app.clients||[]).length);
 $('#deviceTabs').hidden=true;$('.device-period-wrap').hidden=true;
 $('#deviceExportCsv').hidden=true;$('#deviceExportJson').hidden=true;
 const option=(value,label,active)=>'<option value="'+value+'"'+(active===value?' selected':'')+'>'+esc(label)+'</option>';
 const categories=[['all','Todas as categorias'],...Object.entries(CATEGORY_LABELS)];
 $('#deviceDetailContent').innerHTML=`<section class="d-panel device-explorer">
   <div class="device-explorer-heading"><div><h3>Identidades da rede</h3><p class="d-subtitle">Contagens por MAC reportado · sem associação automática entre endereços</p></div><span class="device-explorer-total" id="deviceExplorerTotal"></span></div>
   <div class="device-explorer-counters" id="deviceExplorerCounters"></div>
   <div class="device-explorer-toolbar">
     <label class="device-explorer-search"><span>Pesquisar identidades</span><input id="deviceExplorerSearch" type="search" autocomplete="off" placeholder="Nome, IP, MAC, fabricante…" value="${esc(state.query)}"></label>
     <label>Categoria<select id="deviceExplorerCategory">${categories.map(([v,label])=>option(v,label,state.category)).join('')}</select></label>
     <label>Banda Wi-Fi<select id="deviceExplorerBand">${[['all','Todas'],['24','2,4 GHz'],['5','5 GHz']].map(([v,label])=>option(v,label,state.band)).join('')}</select></label>
     <label>Estado<select id="deviceExplorerStatus">${[['all','Todos os estados'],['online','Online reportado'],['offline','Offline reportado'],['unknown','Sem indicação'],['stale','Desatualizado']].map(([v,label])=>option(v,label,state.status)).join('')}</select></label>
     <label>Ordenar<select id="deviceExplorerSort">${[['status','Por estado'],['name','Nome'],['recent','Última observação'],['signal','Sinal Wi-Fi']].map(([v,label])=>option(v,label,state.sort)).join('')}</select></label>
   </div>
   <div class="device-explorer-subfilters" role="group" aria-label="Filtros de identificação">
     <button type="button" data-inv-filter="macKind" data-value="all">Todos os MACs</button>
     <button type="button" data-inv-filter="macKind" data-value="local">MAC local</button>
     <button type="button" data-inv-filter="macKind" data-value="global">MAC global</button>
     <button type="button" data-inv-filter="vendor" data-value="known">Fabricante encontrado</button>
     <button type="button" data-inv-filter="confidence" data-value="low">Baixa confiança</button>
     <button type="button" data-inv-filter="confidence" data-value="unknown">Não classificado</button>
     <button type="button" data-inv-reset>Limpar filtros</button>
   </div>
   <div id="deviceExplorerMessage" role="status" aria-live="polite"></div>
   <div id="deviceExplorerResults" aria-busy="false"></div>
   <div class="device-explorer-pagination" id="deviceExplorerPagination"></div>
 </section>`;
 renderExplorerResults();
}
function renderExplorerResults(){
 const root=$('#deviceExplorerResults');if(!root)return;
 const raw=Array.isArray(app.clients)?app.clients:[],all=Inventory.counts(raw),list=filtered();
 $('#deviceConnectionBadge').textContent=raw.length||['ready','empty','stale'].includes(app.resources?.inventory?.phase)?String(all.identities):'—';
 const known=raw.length||['ready','empty','stale'].includes(app.resources?.inventory?.phase);
 $('#deviceExplorerTotal').textContent=known?`${all.identities} MACs observados`:'Inventário ainda não disponível';
 const counters=[['online','Online'],['offline','Offline'],['unknown','Sem indicação'],['stale','Leitura antiga']];
 const counterMarkup=counters.map(([kind,label])=>`<div class="device-explorer-counter"><small>${label}</small><strong>${known?all[kind]:'—'}</strong></div>`).join('');
 const summary=$('#deviceExplorerCounters');if(summary.innerHTML!==counterMarkup)summary.innerHTML=counterMarkup;
 const phase=app.resources?.inventory?.phase||(app.api?'ready':'idle');
 root.setAttribute('aria-busy',String(phase==='loading'));
 const message=$('#deviceExplorerMessage');
 message.textContent=phase==='error'?'Não foi possível carregar o inventário.':
   phase==='stale'?'Inventário anterior preservado; atualização falhou.':
   phase==='loading'?'A atualizar inventário…':
   `${list.length} identidades correspondem aos filtros.`;
 if(['error','stale'].includes(phase)){const retry=document.createElement('button');retry.type='button';retry.dataset.retryResource='inventory';retry.textContent='Tentar novamente';message.append(' ',retry);}
 const groups=[['online','Online reportado'],['offline','Offline reportado'],['unknown','Sem indicação'],['stale','Sem leitura recente']];
 const visible=list.filter(c=>state.expandedGroups[c.presence]!==false);
 const shown=visible.slice(0,state.limit);
 const markup=groups.map(([kind,label])=>{
   const members=list.filter(c=>c.presence===kind);
   if(!members.length)return '';
   const expanded=state.expandedGroups[kind]!==false;
   const entries=expanded?shown.filter(c=>c.presence===kind).map(row).join(''):'';
   return `<section class="device-explorer-group" data-group="${kind}"><button class="device-explorer-group-toggle" type="button" data-toggle-group="${kind}" aria-expanded="${expanded}"><span>${esc(label)} · ${members.length}</span><span aria-hidden="true">${expanded?'−':'+'}</span></button>${expanded?'<div class="device-list">'+entries+'</div>':''}</section>`;
 }).join('');
 const emptyMessage=phase==='error'&&!all.identities?'Inventário indisponível.':
   !raw.length?(phase==='loading'||phase==='idle'?'A aguardar primeira leitura…':'Nenhuma identidade foi observada.'):
   !list.length?'Nenhum resultado corresponde à pesquisa e aos filtros.':
   !visible.length?'Todos os grupos filtrados estão recolhidos.':'';
 const content=!raw.length&&['loading','idle'].includes(phase)?inventorySkeletons():markup||(emptyMessage?empty(emptyMessage):'');
 if(root.dataset.markup!==content){preserveFocus(root,()=>{root.innerHTML=content;});root.dataset.markup=content;}
 const pages=$('#deviceExplorerPagination');
 const pageMarkup=visible.length>state.limit?`<button type="button" data-inv-more>Mostrar mais 40 · ${Math.min(state.limit,visible.length)} de ${visible.length}</button>`:
   visible.length?`<span>Exibindo ${visible.length} identidades · sem varreduras adicionais</span>`:'';
 if(pages.innerHTML!==pageMarkup){const moreFocused=pages.contains(document.activeElement);pages.innerHTML=pageMarkup;if(moreFocused)(pages.querySelector('button')||$('#deviceExplorerSearch'))?.focus({preventScroll:true});}
 const subfilters=$$('.device-explorer-subfilters [data-inv-filter]');
 subfilters.forEach(button=>{
   const active=state[button.dataset.invFilter]===button.dataset.value;
   button.classList.toggle('active',active);
   button.setAttribute('aria-pressed',String(active));
 });
}
async function openDevice(id=null){
 const entering=$('#deviceLayer').hidden;
 if(entering)state.lastFocus=document.activeElement;
 if(!entering&&state.id===null&&id!==null)state.explorerScrollTop=$('#deviceDrawerScroll').scrollTop;
 state.id=id;state.period='24h';state.tab='overview';state.bundle=null;
 $('#deviceLayer').hidden=false;document.body.classList.add('device-open');
 $('#sidebar').classList.remove('open');$('#menuToggle').setAttribute('aria-expanded','false');
 $('.shell').inert=true;$('#sheetLayer').inert=true;
 if(entering)$('#deviceDrawerScroll').scrollTop=0;
 $('#deviceDrawer').focus();
 if(id===null){explorer();return;}
 $('#deviceDrawerScroll').scrollTop=0;
 await load();
}
function close(){
 deviceController?.abort();deviceController=null;
 state.request++;state.id=null;
 $('#deviceLayer').hidden=true;document.body.classList.remove('device-open');
 $('#sheetLayer').inert=false;$('.shell').inert=!$('#sheetLayer').hidden;
 const source=state.lastFocus?.isConnected?state.lastFocus:$('#deviceOpenAll');
 source?.focus({preventScroll:true});
}
async function load(){
 deviceController?.abort();deviceController=new AbortController();
 const controller=deviceController,id=state.id,period=state.period,request=++state.request;
 state.bundle=null;
 $('#deviceRangeText').textContent='Período selecionado: '+period;
 $$('[data-dperiod]').forEach(el=>{const active=el.dataset.dperiod===period;el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active));});
 $('#deviceExportCsv').disabled=true;$('#deviceExportJson').disabled=true;
 const root=$('#deviceDetailContent');root.setAttribute('aria-busy','true');root.innerHTML=window.FNO.loading?window.FNO.loading('A carregar observações…'):empty('A carregar observações…');
 try{
  const data=await api('/api/v1/devices/'+id+'?period='+period,{signal:controller.signal});
  if(request!==state.request)return;
  state.bundle=data;render();
  $('#deviceExportCsv').disabled=false;$('#deviceExportJson').disabled=false;
 }catch(error){
  if(request===state.request&&!controller.signal.aborted){root.innerHTML=empty('Não foi possível carregar as observações: '+error.message)+'<button type="button" class="device-back-button" data-device-retry>Tentar novamente</button>';}
 }finally{if(request===state.request)root.setAttribute('aria-busy','false');}
}
function backToExplorer(){
 deviceController?.abort();deviceController=null;
 state.request++;state.id=null;state.bundle=null;
 explorer();
 $('#deviceDrawerScroll').scrollTop=state.explorerScrollTop;
 const search=$('#deviceExplorerSearch');
 if(search)search.focus({preventScroll:true});
}
function panel(title,body,sub=''){return `<section class="d-panel"><div class="d-panel-head"><div><h3 class="d-panel-title">${esc(title)}</h3><p class="d-panel-sub">${esc(sub)}</p></div></div>${body}</section>`;}
function historyChart(id,title,subtitle=''){return panel(title,`<div class="d-chart" id="${id}"></div><p class="d-chart-foot" id="${id}-selection">Usa o rato ou as setas no gráfico para inspecionar amostras.</p>`,subtitle);}
function wifiHistory(b){
 const records=Array.isArray(b.wifi_history)?b.wifi_history:[];
 return panel('Histórico da interface Wi-Fi',`<div class="d-sessions">${records.slice(-30).reverse().map(record=>`<div class="d-session-row"><div><strong>${esc(time(record.observed_at))}</strong><small>${esc((record.links||[]).map(link=>[link.interface,link.band==='2.4GHz'?'2,4 GHz':link.band==='5GHz'?'5 GHz':'banda não identificada',link.channel?'canal '+link.channel:null].filter(Boolean).join(' · ')).join(' / '))}</small></div></div>`).join('')||empty('Ainda sem associação Wi-Fi identificada nesta janela.')}</div><p class="d-subtitle">Mudanças entre observações, não horários exatos de roaming ou de ligação. Banda só quando verificada na mesma recolha; dados antigos podem ter apenas WLAN.</p>`);
}
function sessions(b){return panel('Períodos de presença observada',`<div class="d-sessions">${b.sessions.slice(-20).reverse().map(s=>`<div class="d-session-row"><div><strong>${esc(time(s.started_at))} — ${esc(time(s.last_observed_at))}</strong><small>Origem: ${esc(s.source)} · ${s.end_reason==='sample_gap'?'Interrompido por lacuna':'Estado reportado / limite da janela'} · estimado por amostras</small></div><span class="d-session-duration">≈ ${esc(duration(s.observed_duration_seconds))}</span></div>`).join('')||empty('Sem amostras online neste período.')}</div><p class="d-subtitle">${b.session_count} segmentos observados; são exibidos os últimos 20. Não são horários exatos de associação. Lacunas dividem segmentos e não comprovam reconexão.</p>`);}
function render(){const b=state.bundle;if(!b)return;const c=devices().find(x=>x.id===state.id),d=b.device;const radio=Inventory.wifiContext(c,app.status?.huawei);const wifiLabel=c?.network==='wifi'?radio.label:'Não aplicável ou não reportado';$('#deviceTabs').hidden=false;$('.device-period-wrap').hidden=false;$('#deviceExportCsv').hidden=false;$('#deviceExportJson').hidden=false;$('#deviceDrawerTitle').textContent=c?.name||d.names?.[0]||d.mac;$('#deviceCrumb').textContent='HISTÓRICO REAL';$('#deviceIcon').className='identity-symbol category-'+categoryOf(c);$('#deviceIcon').innerHTML=iconMarkup(c);$('#deviceSubtitle').textContent=`${d.mac} · última observação ${time(d.collected_at)}`+(c?.network==='wifi'?' · '+wifiLabel:'');$('#deviceConnectionBadge').textContent=c?status(c):d.quality==='stale'?'Sem leitura recente':d.reported_status;
 $('#deviceRangeText').textContent=`${time(b.period.from)} — ${time(b.period.to)}`;
 $('.device-provenance>span').textContent=`Fonte: ${b.source} · ${b.quality.sample_count} amostras / ${b.quality.expected_count} esperadas · cobertura ${fmt(b.quality.coverage_percent)}% · última leitura na janela ${time(b.collected_at)}. Presença reportada; PHY não mede tráfego Internet.`;
 $$('[data-dperiod]').forEach(el=>{const active=el.dataset.dperiod===state.period;el.classList.toggle('active',active);el.setAttribute('aria-pressed',active);});
 $$('[data-dtab]').forEach(el=>{const active=el.dataset.dtab===state.tab;el.classList.toggle('active',active);el.setAttribute('aria-selected',active);});
 const root=$('#deviceDetailContent');
 if(state.tab==='overview')root.innerHTML=`<div class="d-cards">${tile('Presença reportada',fmt(b.presence.percent_of_known_samples),'%','Percentagem das amostras com estado conhecido')}${tile('Tempo online estimado',duration(b.presence.observed_duration_seconds),'','Estimativa entre leituras online com intervalo até 180s')}${tile('RSSI médio',fmt(b.stats.rssi_dbm.avg),'dBm','AP · média aritmética amostral')}${tile('Segmentos online',fmt(b.session_count,0),'','Lacunas não são reconexões confirmadas')}</div>${historyChart('presenceChart','Histórico de presença','Percentagem de leituras online em cada intervalo (0–100%). Lacuna = sem dados.')}${sessions(b)}${wifiHistory(b)}`;
 if(state.tab==='traffic')root.innerHTML=`<div class="d-cards">${tile('Download','Sem dados','Mb/s','Sem contadores individuais validados')}${tile('Upload','Sem dados','Mb/s','PHY não é tráfego')}${tile('Volume recebido','Sem dados','GB','Não atribuímos contadores da porta a este aparelho')}${tile('Volume enviado','Sem dados','GB','Sem fonte validada')}</div>${panel('Tráfego de Internet por aparelho',empty('O firmware validado não fornece uma fonte de bytes por aparelho neste coletor. Não são geradas curvas ou estimativas a partir dos totais WAN/LAN/Wi-Fi.'))}${historyChart('phyTrafficChart','Taxas de ligação PHY reportadas','RX/TX na perspetiva do router; não representam consumo nem velocidade de Internet')}`;
 if(state.tab==='connection')root.innerHTML=`<div class="d-cards">${tile('RSSI mínimo',fmt(b.stats.rssi_dbm.min),'dBm','Valor AP reportado')}${tile('RSSI máximo',fmt(b.stats.rssi_dbm.max),'dBm','Extremo do arquivo')}${tile('SNR médio',fmt(b.stats.snr_db.avg),'dB','Valor reportado pelo fabricante')}${tile('RTT LAN','Sem dados','ms','Não há sonda configurada para este cliente')}</div>${historyChart('signalChart','Sinal reportado pelo AP','Ethernet não tem RSSI. Intervalos sem medição ficam vazios.')}${historyChart('phyChart','Taxas PHY RX/TX','Taxas de ligação, em Mbit/s; perspetiva do router')}${panel('Ligação Wi-Fi observada',keyvals([['Banda atual',wifiLabel],['Interface(s)',radio.interfaces.map(x=>x.interface).join(' · ')||'Não identificada'],['Canal',radio.interfaces.map(x=>x.channel).filter(Boolean).join(' · ')||'Não reportado'],['SSID','Não reportado nesta fonte'],['Precisão','Associação observada; não indica antena física nem momento exato de roaming']]))}${wifiHistory(b)}${sessions(b)}`;
 if(state.tab==='events')root.innerHTML=panel('Eventos persistidos deste aparelho',b.events.map(e=>`<div class="d-event"><time>${esc(time(e.ts))}</time><span class="dot ${e.severity==='warning'?'warning':''}"></span><div><strong>${esc(e.title)}</strong><p>${esc(e.detail)}</p></div><code>${esc(e.source)}</code></div>`).join('')||empty('Sem eventos deste aparelho no período. Não são fabricados eventos para amostras ausentes.'));
 if(state.tab==='identity')root.innerHTML=panel('Identidade e fontes',keyvals([['MAC reportado',d.mac],['Nomes / aliases',d.names?.join(' · ')||'Não reportados'],['Endereços reportados',d.ips?.join(' · ')||'Não reportados'],['Portas / interfaces',d.ports?.join(' · ')||'Não reportadas'],['Banda Wi-Fi observada',wifiLabel],['WLAN observada',radio.interfaces.map(x=>x.interface).join(' · ')||'Não identificada'],['SSID','Não reportado pelo coletor'],['Tipos reportados',d.device_types?.join(' · ')||'Não reportados'],['Primeira observação no arquivo',time(d.first_seen)],['Última observação',time(d.collected_at)],['Identificação manual',c?.presentation?.source==='manual'?'Personalizado pelo operador':'Sem personalização'],['Categoria sugerida',categoryLabel(c)],['Plataforma sugerida',PLATFORM_LABELS[c?.classification?.platform_family]||'Desconhecida'],['Associação manual',c?.association?.group_id?'Identidades associadas pelo operador; históricos separados':'Sem associação'],['Possíveis relações',(c?.possible_relations||[]).map(x=>x.mac+' · mesmo nome reportado'+(x.conflict?' · sinais conflitantes':'')+' · confiança baixa, não confirmado').join(' / ')||'Sem sugestão'],['Confiança qualitativa',CONFIDENCE_LABELS[c?.classification?.confidence]||'Desconhecida'],['Evidências / regras',(c?.classification?.evidence||[]).map(e=>e.rule).join(' · ')||'Não existem indícios suficientes'],['Tipo do MAC',c?.identity?.mac_type||'unknown'],['Fonte do fabricante',c?.identity?.oui_source==='wireshark_manuf'?'Wireshark · base pública offline':'IEEE / não disponível'],['Identificação histórica',c?.classification?.historical_observed_at?time(c.classification.historical_observed_at):'Sem evidência histórica aplicada'],['Titular do bloco MAC',c?.identity?.oui_vendor||'Não identificado / não disponível'],['Semântica do fabricante','Assignee de bloco da interface; não prova marca nem modelo do aparelho'],['Fonte',b.source],['Confiança','Identidade reportada, sem associação entre MACs aleatórios'],['Cobertura da janela',fmt(b.quality.coverage_percent)+'%'],['Amostras esperadas',b.quality.expected_count],['Lacunas observadas',b.quality.sample_gaps],['Taxas individuais / RTT','Sem dados'],['Retenção',retention(app.status?.retention_days)]]))+panel('Histórico de identidade',`<div id="identityHistory">${(b.identity_history||[]).map(x=>keyvals([['Observação',time(x.collected_at)],['Nomes',x.names.join(' · ')],['IPs',x.ips.join(' · ')],['Interfaces',x.ports.join(' · ')]] )).join('')||empty('Sem alterações de identidade na janela.')}</div>`)+wifiHistory(b);
 root.insertAdjacentHTML('afterbegin','<button class="device-back-button" type="button" data-inv-back>← Voltar ao inventário</button>');
 const draw=(id,defs)=>{const node=$('#'+id);if(node)chart(node,b.series,defs,b.period,$('#'+id+'-selection'));};
 draw('presenceChart',[{key:'presence',label:'Presença reportada',color:'#69e9dc',unit:'%'}]);
 draw('signalChart',[{key:'rssi_dbm',label:'RSSI AP',color:'#69e9dc',unit:'dBm'}]);
 ['phyChart','phyTrafficChart'].forEach(id=>draw(id,[{key:'link_rx_phy_mbps',label:'RX PHY',color:'#c3a4ff',unit:'Mbit/s'},{key:'link_tx_phy_mbps',label:'TX PHY',color:'#69e9dc',unit:'Mbit/s'}]));
}
function exportFile(format){if(!state.id||!state.bundle)return;const a=document.createElement('a');a.href=`/api/v1/devices/${state.id}/export.${format}?period=${state.period}`;a.download=`faysk-${state.id}-${state.period}.${format}`;document.body.append(a);a.click();a.remove();toast('Exportação das observações completas do período solicitada.');}
$('#deviceSearch').addEventListener('input',e=>{
 state.query=e.target.value.toLocaleLowerCase().trim();
 state.limit=40;renderList();
});
$$('[data-device-filter]').forEach(el=>el.addEventListener('click',()=>{state.filter=el.dataset.deviceFilter;$$('[data-device-filter]').forEach(b=>{const on=b===el;b.classList.toggle('active',on);b.setAttribute('aria-pressed',on);});renderList();}));
$('#deviceList').addEventListener('click',e=>{const el=e.target.closest('[data-open-device]');if(el)openDevice(el.dataset.openDevice);});
$('#deviceDetailContent').addEventListener('input',e=>{
 if(e.target.id==='deviceExplorerSearch'){
   state.query=e.target.value.toLocaleLowerCase().trim();
   state.limit=40;
   if($('#deviceSearch'))$('#deviceSearch').value=e.target.value;
   renderList();
 }
});
$('#deviceDetailContent').addEventListener('change',e=>{
 const field={deviceExplorerCategory:'category',deviceExplorerBand:'band',deviceExplorerStatus:'status',deviceExplorerSort:'sort'}[e.target.id];
 if(field){state[field]=e.target.value;state.limit=40;renderList();}
});
$('#deviceDetailContent').addEventListener('click',e=>{
 if(e.target.closest('[data-device-retry]')){load();return;}
 const back=e.target.closest('[data-inv-back]');if(back){backToExplorer();return;}
 const item=e.target.closest('[data-open-device]');if(item){openDevice(item.dataset.openDevice);return;}
 const more=e.target.closest('[data-inv-more]');if(more){state.limit+=40;renderExplorerResults();return;}
 const toggle=e.target.closest('[data-toggle-group]');if(toggle){
   const kind=toggle.dataset.toggleGroup;
   if(Inventory.STATES.includes(kind)){state.expandedGroups[kind]=!state.expandedGroups[kind];renderExplorerResults();}
   return;
 }
 const filtered=e.target.closest('[data-inv-filter]');if(filtered){
   const key=filtered.dataset.invFilter,value=filtered.dataset.value;
   if(['vendor','confidence','macKind'].includes(key)){
     state[key]=state[key]===value&&value!=='all'?'all':value;
     state.limit=40;renderList();
   }
   return;
 }
 if(e.target.closest('[data-inv-reset]')){
   Object.assign(state,{filter:'all',query:'',category:'all',confidence:'all',vendor:'all',macKind:'all',status:'all',band:'all',sort:'status',limit:40});
   if($('#deviceSearch'))$('#deviceSearch').value='';
   const search=$('#deviceExplorerSearch');if(search)search.value='';
   ['Category','Band','Status','Sort'].forEach(name=>{
     const el=$('#deviceExplorer'+name);if(el)el.value=name==='Sort'?'status':'all';
   });
   $$('[data-device-filter]').forEach(el=>{
     const active=el.dataset.deviceFilter==='all';el.classList.toggle('active',active);
     el.setAttribute('aria-pressed',String(active));
   });
   renderList();
 }
});
$('#deviceOpenAll').addEventListener('click',()=>openDevice());$('#deviceShowAll').addEventListener('click',()=>openDevice());
$('#deviceClose').addEventListener('click',close);$('#deviceBackdrop').addEventListener('click',close);
$('#devicePeriods').addEventListener('click',e=>{const el=e.target.closest('[data-dperiod]');if(el){state.period=el.dataset.dperiod;load();}});
$('#deviceTabs').addEventListener('click',e=>{const el=e.target.closest('[data-dtab]');if(el){state.tab=el.dataset.dtab;render();}});
$('#deviceExportCsv').addEventListener('click',()=>exportFile('csv'));$('#deviceExportJson').addEventListener('click',()=>exportFile('json'));
document.addEventListener('fno:update',()=>{
 const signature=JSON.stringify([app.clients,app.resources?.inventory?.phase,app.status?.huawei?.interfaces,app.status?.huawei?.wifi,app.status?.huawei?.collected_at,app.status?.huawei?.quality]);
 if(signature===lastInventorySignature)return;
 lastInventorySignature=signature;
 renderList();
 // Device historian is not refetched for every unrelated status/overview tick.
 if(state.id&&!$('#deviceLayer').hidden){
   const c=devices().find(device=>device.id===state.id);
   if(c){
     $('#deviceConnectionBadge').textContent=status(c);
     $('#deviceIcon').className='identity-symbol category-'+categoryOf(c);
     $('#deviceIcon').innerHTML=iconMarkup(c);
   }
 }
});
document.addEventListener('fno:devices',()=>openDevice());
document.addEventListener('keydown',e=>{if(!$('#deviceLayer').hidden){if(e.key==='Escape')close();else trap(e,$('#deviceDrawer'));}});
renderList();
})();
