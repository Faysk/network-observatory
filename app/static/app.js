/* Original local API integration for the supplied v0.4 design. No demo generators. */
'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=1)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('pt-PT',{maximumFractionDigits:d});
const time=v=>v?new Date(v).toLocaleString('pt-PT',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'Sem dados';
const retention=days=>days===0?'Sem limite':days==null?'Sem informação':fmt(days,0)+' dias';
const fresh=ts=>{const age=Date.now()-Date.parse(ts);return age>=-5000&&age<=180000;};
const duration=v=>v==null?'Sem dados':`${Math.floor(v/3600)}h ${Math.floor(v%3600/60)}m`;
const state={status:null,overview:null,clients:[],metric:null,counterMode:'observed',period:'24h',bundle:null,filter:'all',main:true,secondary:true,request:0,api:false,resources:{
 status:{phase:'idle'},overview:{phase:'idle'},inventory:{phase:'idle'}
 }};
const config={
 traffic:{title:'Contadores WAN',desc:'Bytes cumulativos reportados. Não são consumo do período nem velocidade de Internet.',a:'wan_rx_bytes',b:'wan_tx_bytes',main:'Contador RX',secondary:'Contador TX',unit:'GiB',scale:2**30},
 router:{title:'Router Huawei',desc:'CPU e memória reais; temperatura óptica não é temperatura da CPU.',a:'cpu_pct',b:'memory_pct',main:'CPU',secondary:'RAM',unit:'%',scale:1},
 latency:{title:'Desempenho e conectividade',desc:'Tempo de ligação TCP do servidor ao gateway e a 1.1.1.1:443. Não é ping, DNS ou teste de velocidade.',a:'router_ms',b:'internet_ms',main:'TCP gateway',secondary:'TCP exterior',unit:'ms',scale:1,probes:true},
 devices:{title:'Presença dos aparelhos',desc:'Aparelhos reportados online em cada amostra. Ausência na tabela não prova desconexão.',a:'online_clients',b:null,main:'Online reportados',unit:'aparelhos',scale:1},
 wifi:{title:'Wi-Fi e sinal',desc:'RSSI médio das estações observadas pelo AP, sem inferir qualidade de Internet.',a:'rssi_dbm',b:null,main:'RSSI médio reportado',unit:'dBm',scale:1},
 health:{title:'Estado da recolha e conectividade',desc:'Observações de resposta TCP, sem pontuação sintética de experiência.',a:'router_online',b:'internet_online',main:'Gateway responde',secondary:'Exterior responde',unit:'0/1',scale:1,probes:true},
 events:{title:'Eventos e logs',desc:'Eventos persistidos pela aplicação. Logs internos do router não são recolhidos.',a:null,b:null,main:'Eventos',unit:'',scale:1},
 integrations:{title:'Integrações e fontes',desc:'Estados derivados das últimas leituras recebidas, sem introdução de tokens no navegador.',a:null,b:null,main:'Fontes',unit:'',scale:1}
};
function parseTelemetryJson(text){
 const tokens=/"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
 return JSON.parse(text.replace(tokens,token=>token[0]!== '"'&&!/[.eE]/.test(token)&&!Number.isSafeInteger(Number(token))?JSON.stringify(token):token));
}
async function api(url,{signal,timeout=20000}={}){
 const controller=new AbortController(),relay=()=>controller.abort();
 if(signal){if(signal.aborted)controller.abort();else signal.addEventListener('abort',relay,{once:true});}
 const timer=setTimeout(()=>controller.abort(),timeout);
 try{const r=await fetch(url,{signal:controller.signal,cache:'no-store'});
   if(!r.ok)throw Error('Resposta '+r.status);
   return r.text?parseTelemetryJson(await r.text()):await r.json();
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',relay);}
}
const bundleCache=new Map(),sheetFlights=new Map(),BUNDLE_TTL=20000;
let activeSheetAbort=null;
function abortSheet(){
 if(activeSheetAbort){activeSheetAbort.abort();activeSheetAbort=null;}
}
function cachedFullBundle(period){
 const cached=bundleCache.get(period);
 if(cached&&Date.now()-cached.at<BUNDLE_TTL)return cached.data;
 // A legacy fully-loaded home bundle may be reused; a summary cannot.
 if(period==='24h'&&state.overview?.stats&&state.overview?.probes&&state.overview?.series)return state.overview;
 return null;
}
async function sheetBundle(period,signal){
 const cached=cachedFullBundle(period);
 if(cached)return cached;
 let flight=sheetFlights.get(period);
 // A previous consumer may have aborted this flight before its finally ran.
 // A new visit needs a fresh request rather than inheriting AbortError.
 if(flight?.controller.signal.aborted){sheetFlights.delete(period);flight=null;}
 if(!flight){
   const controller=new AbortController(),consumers=new Set();
   const pending=api('/api/v1/overview?period='+encodeURIComponent(period),{signal:controller.signal})
     .then(data=>{
       if(!data||!data.period||!data.stats||!Array.isArray(data.series))throw Error('Histórico inválido');
       bundleCache.set(period,{at:Date.now(),data});
       while(bundleCache.size>4)bundleCache.delete(bundleCache.keys().next().value);
       return data;
     }).finally(()=>{if(sheetFlights.get(period)?.pending===pending)sheetFlights.delete(period)});
   flight={pending,controller,consumers};sheetFlights.set(period,flight);
 }
 const token={};flight.consumers.add(token);
 const release=()=>{
   flight.consumers.delete(token);
   if(!flight.consumers.size&&sheetFlights.get(period)===flight)flight.controller.abort();
 };
 if(signal?.aborted){release();throw new DOMException('Cancelled','AbortError')}
 signal?.addEventListener('abort',release,{once:true});
 try{return await flight.pending}
 finally{signal?.removeEventListener('abort',release);release();}
}
function resourceMarkup(name,label){
 const meta=state.resources[name],phase=meta.phase,old=phase==='stale';
 const retry=phase==='error'||phase==='stale';
 const message=phase==='loading'?(meta.at?'Atualizando '+label+' · leitura anterior visível…':'A carregar '+label+'…'):phase==='error'?'Falha ao carregar '+label+'.':old?'Última leitura preservada, mas a atualização falhou.':phase==='empty'?'Não foram encontrados dados de '+label+'.':'';
 return message?'<span>'+esc(message)+'</span>'+(retry?' <button type="button" data-retry-resource="'+name+'">Tentar novamente</button>':''):'';
}
function blockFeedback(node,name){
 if(!node)return;
 const meta=state.resources[name],pending=meta.phase==='loading';
 node.classList.add('resource-block');node.dataset.loadPhase=meta.phase;
 node.dataset.firstLoad=String(pending&&!meta.at);node.setAttribute('aria-busy',String(pending));
 let badge=node.querySelector(':scope > .block-load-status');
 if(!badge){badge=document.createElement('span');badge.className='block-load-status';badge.setAttribute('aria-hidden','true');node.append(badge);}
 const text=pending?(meta.at?'Atualizando…':'Carregando…'):meta.phase==='stale'?'Atualização falhou':meta.phase==='error'?'Falha ao carregar':'';
 if(badge.textContent!==text)badge.textContent=text;
 badge.hidden=!text;
}
function updateResourceRegions(){
 $$('.telemetry-mini').forEach(node=>blockFeedback(node,'status'));
 document.body.dataset.initialLoading=String(!state.status&&state.resources.status.phase==='loading');
 for(const [selector,name] of [['.metric-card[data-detail="traffic"]','overview'],['.metric-card[data-detail="latency"]','status'],['.metric-card[data-detail="router"]','status'],['.metric-card[data-detail="devices"]','inventory'],['.hero-main','status'],['.hero-score','overview'],['.traffic-summary-values','status'],['.event-preview','overview'],['.signal-foot','status'],['.signal-main','overview'],['#deviceSection','inventory']])blockFeedback($(selector),name);
 for(const [name,id,label] of [['overview','#overviewState','histórico'],['inventory','#inventoryState','inventário']]){
   const el=$(id);if(!el)continue;
   const phase=state.resources[name].phase;
   el.dataset.phase=phase;el.setAttribute('aria-busy',String(phase==='loading'));
   el.innerHTML=resourceMarkup(name,label);
 }
 const chartNode=$('#overviewChart');if(chartNode){
   const pending=state.resources.overview.phase==='loading';
   chartNode.setAttribute('aria-busy',String(pending));
   if(pending&&!state.overview)chartNode.innerHTML='<div class="load-placeholder" aria-hidden="true"><i></i><i></i><i></i></div>';
   else if(!pending&&!state.overview)chartNode.replaceChildren();
 }
}
function publishResource(name,data){
 if(name==='status'){state.status=data;state.api=true;}
 if(name==='overview')state.overview=data;
 if(name==='inventory')state.clients=data.clients;
 const isEmpty=name==='overview'?!(data.series?.length||data.probes?.length||data.events?.length):
   name==='inventory'?!data.clients?.length:false;
 state.resources[name]={phase:isEmpty?'empty':'ready',at:Date.now()};
 renderHome();updateResourceRegions();
}
const resourceFlights=new Map();
function fetchResource(name){
 if(resourceFlights.has(name))return resourceFlights.get(name);
 const pending=loadResource(name).finally(()=>resourceFlights.delete(name));
 resourceFlights.set(name,pending);return pending;
}
async function loadResource(name){
 state.resources[name]={...state.resources[name],phase:'loading'};
 updateResourceRegions();
 try{
   const path={status:'/api/status',overview:'/api/v1/overview?period=24h&view=summary',
                inventory:'/api/router/clients'}[name];
   const data=await api(path);
   if(name==='inventory'&&!Array.isArray(data?.clients))throw Error('Inventário inválido');
   if(name==='overview'&&(!data?.period||!Array.isArray(data.series)))throw Error('Resumo inválido');
   publishResource(name,data);
   return true;
 }catch(error){
   if(name==='status')state.api=false;
   const had=name==='status'?!!state.status:name==='overview'?!!state.overview:state.resources.inventory.at!=null;
   state.resources[name]={phase:had?'stale':'error',at:state.resources[name].at||null,error:String(error)};
   renderHome();updateResourceRegions();
   return false;
 }
}

function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('visible'),4500);}
function tile(label,value,unit='',foot=''){return `<article class="d-stat"><div class="d-stat-label">${esc(label)}</div><strong>${esc(value)} <small>${esc(unit)}</small></strong><span>${esc(foot)}</span></article>`;}
function keyvals(rows){return `<div class="d-keyvals">${rows.map(([k,v])=>`<div class="d-keyval"><small>${esc(k)}</small><strong>${esc(v??'Sem dados')}</strong></div>`).join('')}</div>`;}
function loading(message,compact=false){return `<div class="load-placeholder ${compact?'load-compact':''}" ${compact?'aria-hidden="true"':'role="status"'}><span>${esc(message)}</span><i aria-hidden="true"></i><i aria-hidden="true"></i><i aria-hidden="true"></i></div>`;}
function empty(message){return `<div class="d-fallback">${esc(message)}</div>`;}
function seriesPath(series,key,period,x,y){
 let path='',previous=null;
 const resolution=Math.max(60,period.resolution_seconds||60),origin=Date.parse(period.from);
 for(const p of series){
   const value=p[key];if(!Number.isFinite(value)){previous=null;continue;}
   const incomplete=!period.sampled_preview&&(p.max_gap_seconds>180||(p.values?.[key]?.sample_count<p.sample_count));
   const epochs=key.includes('_observed_')?'observed_epochs':'counter_epochs';
   const counterDrop=previous&&key.startsWith('wan_')&&(value<previous[key]||(p[epochs]?.[key]!=null&&previous[epochs]?.[key]!=null&&p[epochs][key]!==previous[epochs][key]));
   const gap=counterDrop||previous&&(period.sampled_preview?
     Math.floor((Date.parse(p.timestamp)-origin)/(resolution*1000))-Math.floor((Date.parse(previous.timestamp)-origin)/(resolution*1000))>1:
     Date.parse(p.timestamp)-Date.parse(previous.timestamp_end||previous.timestamp)>180000);
   path+=`${previous&&!gap&&!incomplete?'L':'M'}${x(p.timestamp).toFixed(2)},${y(value).toFixed(2)} `;
   previous=incomplete?null:p;
 }
 return path;
}
function chart(node,series,defs,period,selection){
 node.replaceChildren();const valid=series.filter(p=>defs.some(d=>Number.isFinite(p[d.key])));
 if(!valid.length){node.innerHTML=empty('Sem amostras desta métrica no período selecionado.');return;}
 const width=800,height=245,left=58,right=16,top=22,bottom=32;
 const start=Date.parse(period.from),end=Date.parse(period.to),step=period.resolution_seconds||60;
 const nums=series.flatMap(p=>defs.flatMap(d=>{const v=p.values?.[d.key];return [p[d.key],v?.min,v?.max].filter(Number.isFinite).map(x=>x/(d.scale||1));}));
 let low=Math.min(...nums),high=Math.max(...nums);const pad=Math.max(1,(high-low)*.12);low-=pad;high+=pad;if(defs.some(d=>d.key==='presence')){low=0;high=100;}if(defs.some(d=>d.key==='router_online'||d.key==='internet_online')){low=0;high=1;}
 const percent=defs.every(d=>['cpu_pct','memory_pct','presence'].includes(d.key));if(percent){low=Math.max(0,low);high=Math.min(100,high);}else if(defs.every(d=>d.key!=='rssi_dbm'))low=Math.max(0,low);if(high<=low)high=low+1;
 const x=t=>left+(Date.parse(t)-start)/Math.max(1,end-start)*(width-left-right), y=v=>top+(1-(v-low)/(high-low))*(height-top-bottom);
 let content='';for(let i=0;i<5;i++){const yy=top+i*(height-top-bottom)/4;content+=`<line x1="${left}" x2="${width-right}" y1="${yy}" y2="${yy}" stroke="#304558" stroke-dasharray="3 5"/><text x="${left-8}" y="${yy+4}" text-anchor="end" fill="#91a7ba" font-size="11">${fmt(high-i*(high-low)/4)}</text>`;}
 for(let i=0;i<4;i++){const t=start+i*(end-start)/3;content+=`<text x="${left+i*(width-left-right)/3}" y="${height-6}" text-anchor="${i===0?'start':i===3?'end':'middle'}" fill="#91a7ba" font-size="11">${esc(time(new Date(t).toISOString()))}</text>`;}
 defs.forEach(d=>{
   const path=seriesPath(series,d.key,period,x,v=>y(v/(d.scale||1)));
   for(const p of series){const extrema=p.values?.[d.key];if(!d.key.startsWith('wan_')&&Number.isFinite(p[d.key])&&extrema&&extrema.min!==extrema.max)content+=`<line x1="${x(p.timestamp)}" x2="${x(p.timestamp)}" y1="${y(extrema.min/(d.scale||1))}" y2="${y(extrema.max/(d.scale||1))}" stroke="${d.color}" opacity=".35"/>`;}
   // A genuinely isolated observation must remain visible without inventing a link.
   for(const segment of path.matchAll(/M(-?[\d.]+),(-?[\d.]+)([^M]*)/g))if(!segment[3].includes('L'))content+=`<circle cx="${segment[1]}" cy="${segment[2]}" r="1.5" fill="${d.color}"/>`;
   content+=`<path class="history-series-line" d="${path}" fill="none" stroke="${d.color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`;
 });
 node.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Histórico real com intervalos sem amostras">${content}<line class="inspect-line" x1="0" x2="0" y1="${top}" y2="${height-bottom}" stroke="#c5eadd" opacity="0"/><rect class="inspect-area" x="${left}" y="${top}" width="${width-left-right}" height="${height-top-bottom}" fill="transparent" tabindex="0" role="img" aria-label="Inspecionar amostras com setas esquerda e direita"/></svg>`;
 const area=$('.inspect-area',node),line=$('.inspect-line',node),svg=area.ownerSVGElement;let index=valid.length-1;
 node.classList.add('interactive-chart');
 const tip=document.createElement('div');tip.className='chart-inspector';tip.hidden=true;tip.setAttribute('role','tooltip');node.append(tip);
 const markers=document.createElementNS('http://www.w3.org/2000/svg','g');markers.setAttribute('pointer-events','none');svg.insertBefore(markers,area);
 function hide(){tip.hidden=true;line.setAttribute('opacity','0');markers.replaceChildren();}
 function inspect(i,distance=null){index=Math.max(0,Math.min(valid.length-1,i));const p=valid[index],xx=x(p.timestamp);
 line.setAttribute('x1',xx);line.setAttribute('x2',xx);line.setAttribute('opacity','1');line.setAttribute('stroke-dasharray','4 5');
 markers.innerHTML=defs.filter(d=>Number.isFinite(p[d.key])).map(d=>`<circle cx="${xx}" cy="${y(p[d.key]/(d.scale||1))}" r="5" fill="${d.color}" stroke="#161021" stroke-width="2"/>`).join('');
 const stamp=new Date(p.timestamp).toLocaleString('pt-PT',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
 tip.innerHTML=`<strong class="inspector-time">${esc(stamp)}</strong>${defs.map(d=>{const v=p[d.key],stats=p.values?.[d.key];return `<div class="inspector-row"><span><svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="3.5" fill="${d.color}"/></svg>${esc(d.label)}</span><b>${Number.isFinite(v)?esc(fmt(v/(d.scale||1),3)):'Sem dados'} <small>${esc(d.unit||'')}</small></b></div>${stats&&stats.min!==stats.max?`<div class="inspector-range">Mín. ${esc(fmt(stats.min/(d.scale||1),3))} · Máx. ${esc(fmt(stats.max/(d.scale||1),3))} ${esc(d.unit||'')}</div>`:''}`;}).join('')}<span class="inspector-meta">${esc(p.sample_count??1)} amostras · ${defs.some(d=>d.key.includes('_observed_'))?'soma de incrementos válidos':p.values?'média do intervalo':'observação original'}${p.max_gap_seconds>180?' · contém lacuna':''}${distance==null?'':' · leitura mais próxima ('+fmt(distance/60,1)+' min do cursor)'}</span>`;
 tip.hidden=false;
 // Use the actual SVG matrix: aspect-ratio letterboxing must not offset the cursor.
 const point=svg.createSVGPoint();point.x=xx;point.y=top;const screen=point.matrixTransform(svg.getScreenCTM()),box=node.getBoundingClientRect();
 const pos=screen.x-box.left;tip.style.left=Math.max(8,Math.min(box.width-tip.offsetWidth-8,pos+16>box.width-tip.offsetWidth?pos-tip.offsetWidth-16:pos+16))+'px';tip.style.top=Math.max(4,screen.y-box.top+8)+'px';
 if(selection)selection.textContent=`${stamp} · ${defs.map(d=>`${d.label}: ${fmt(p[d.key]==null?null:p[d.key]/(d.scale||1),3)} ${d.unit||''}`).join(' · ')} · ${p.sample_count??1} amostras · ${defs.some(d=>d.key.includes('_observed_'))?'soma de incrementos válidos':p.values?'média do intervalo':'observação original'}`;
 }
 function pointer(e){const matrix=svg.getScreenCTM();if(!matrix)return;const point=svg.createSVGPoint();point.x=e.clientX;point.y=e.clientY;const local=point.matrixTransform(matrix.inverse()),t=start+Math.max(0,Math.min(1,(local.x-left)/(width-left-right)))*(end-start);let best=0;
 for(let i=1;i<valid.length;i++)if(Math.abs(Date.parse(valid[i].timestamp)-t)<Math.abs(Date.parse(valid[best].timestamp)-t))best=i;
 inspect(best,Math.abs(Date.parse(valid[best].timestamp)-t)/1000);
 }
 area.addEventListener('pointermove',pointer);area.addEventListener('pointerdown',pointer);
 area.addEventListener('pointerleave',()=>{if(document.activeElement!==area)hide();});area.addEventListener('blur',hide);
 area.addEventListener('focus',()=>inspect(index));area.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End','Escape'].includes(e.key)){e.preventDefault();if(e.key==='Escape'){hide();return;}inspect(e.key==='Home'?0:e.key==='End'?valid.length-1:index+(e.key==='ArrowRight'?1:-1));}});
}
function appOnline(){const meta=state.resources.inventory,ready=['ready','empty'].includes(meta.phase)||(meta.phase==='loading'&&meta.at!=null);return state.api&&ready?state.clients.filter(c=>c.quality==='ok'&&c.reported_status==='Online').length:null;}
function renderHome(){
 const s=state.status,h=s?.huawei||{},current=state.api&&h.quality==='ok'&&fresh(h.collected_at),m=current?h.metrics||{}:{},o=state.overview;
 const probe=s?.probe,probeCurrent=state.api&&probe&&fresh(probe.ts);
 $('.demo-chip').textContent=current?'● RECOLHA ATIVA':'● SEM LEITURA RECENTE';
 $('.notice>span').textContent=current?`Leitura real · ${time(h.collected_at)} · Retenção: ${retention(s.retention_days)} · origem ${h.source}`:'Sem leitura recente. Os valores atuais ficam indisponíveis; o histórico continua preservado.';
 $('.local-status small').textContent=current?'Coletor Huawei ativo':'A aguardar coletor';
 $('#health-title').textContent=current?'A tua rede, em observação.':'A aguardar telemetria.';
 $('.hero-main p').textContent=probeCurrent?`Gateway: ${probe.router_online==null?'sem dados':probe.router_online?'responde':'sem resposta TCP'} · exterior: ${probe.internet_online==null?'sem dados':probe.internet_online?'responde':'sem resposta TCP'}.`:'Sem sondas TCP recentes para avaliar a conectividade.';
 const coverage=o?.quality?.coverage_percent;
 $('.signal-main p').textContent='Percentual da janela com uma coleta gravada há no máximo 3 minutos. Não é disponibilidade da Internet.';
 $('[data-metric="score"]').textContent=fmt(coverage,2);$('.quality-dial strong').textContent=fmt(coverage,2);
 $('.ring-fill').style.strokeDashoffset=String(2*Math.PI*49*(1-(coverage||0)/100));$('.dial-value').style.strokeDashoffset=String(2*Math.PI*37*(1-(coverage||0)/100));
 $('.score-copy>strong').textContent=`${fmt(o?.quality?.sample_count,0)} coletas`;
 $('.score-copy small').textContent='Leitura recente: até 3 min · intervalo médio '+fmt(o?.quality?.observed_interval_mean_seconds,1)+' s';
 $('.hero-score .score-ring').setAttribute('aria-label',`Cobertura temporal da recolha: ${fmt(coverage,2)} por cento`);
 let wan=current?Object.entries(h.wan_states||{}).find(([,v])=>v.services?.includes('Internet'))?.[0]:null;
 const counters=wan?h.interfaces?.[wan]:null;
 const observedRx=o?.counter_period?.observed_increments?.wan_rx_bytes?.bytes;
 $('[data-metric="down"]').textContent=fmt(observedRx==null?null:observedRx/2**30,2);
 $('[data-metric="down"]').closest('.metric-card').title='Última hora: soma dos incrementos RX válidos; quedas e lacunas excluídas. Pode estar incompleta. Até '+time(o?.counter_period?.to);
 $('[data-metric="latency"]').textContent=fmt(probeCurrent?probe.router_ms:null);
 $('[data-metric="cpu"]').textContent=fmt(m.cpu_pct);
 const online=appOnline();
 $('[data-metric="devices"]').textContent=fmt(online,0);$('[data-metric="devices"]').nextElementSibling.textContent='/ '+(state.resources.inventory.at!=null?state.clients.length:'—');
 $('.traffic-summary-values').innerHTML=`<div><span class="label-with-dot"><i class="series-dot download"></i> RX REPORTADO</span><strong>${fmt(counters?.rx_bytes==null?null:counters.rx_bytes/2**30,2)} <small>GiB</small></strong></div><div><span class="label-with-dot"><i class="series-dot upload"></i> TX REPORTADO</span><strong>${fmt(counters?.tx_bytes==null?null:counters.tx_bytes/2**30,2)} <small>GiB</small></strong></div><div class="mini-time">${esc(time(h.collected_at))}</div>`;
 if(o)chart($('#overviewChart'),o.counter_series||o.series,[{key:'wan_rx_bytes',label:'RX acumulado',color:'#c3a4ff',scale:2**30,unit:'GiB'},{key:'wan_tx_bytes',label:'TX acumulado',color:'#69e9dc',scale:2**30,unit:'GiB'}],o.counter_period||{...o.period,sampled_preview:!!o.summary?.sampled});
 $('.axis-row').hidden=true;
 $('.signal-foot').innerHTML=`<span>TCP gateway<strong>${fmt(probeCurrent?probe.router_ms:null)} ms</strong></span><span>TCP exterior<strong>${fmt(probeCurrent?probe.internet_ms:null)} ms</strong></span><span>Última sonda<strong>${esc(time(probe?.ts))}</strong></span>`;
 const events=o?.events||[];$('.nav-number').textContent=String(events.length);
 $('.event-preview').innerHTML=events.length?events.slice(0,3).map(e=>`<button class="event-line event-open" data-event="${e.id}"><span class="event-dot ${e.severity==='warning'||e.severity==='critical'?'amber-dot':'mint-dot'}"></span><span><strong>${esc(e.title)}</strong><small>${esc(time(e.ts))}</small></span><span class="event-pill neutral-pill">${esc(e.severity)}</span></button>`).join(''):empty('Sem eventos registados nesta janela.');
 ['traffic','latency','router','devices'].forEach(metric=>{
   const c=config[metric],key=metric==='traffic'?'wan_rx_observed_bytes':c.a,rows=metric==='traffic'?o?.counter_series:c.probes?o?.probes:o?.series,node=$('#spark-'+metric);node.replaceChildren();
   const vals=(rows||[]).map(r=>r[key]).filter(Number.isFinite);if(vals.length<2)return;
   const min=Math.min(...vals),max=Math.max(...vals),period=metric==='traffic'?o.counter_period:{...o.period,sampled_preview:!!o.summary?.sampled};
   const points=seriesPath(rows,key,period,t=>(Date.parse(t)-Date.parse(period.from))/Math.max(1,Date.parse(period.to)-Date.parse(period.from))*108,v=>24-(v-min)/Math.max(1,max-min)*20);
   node.innerHTML=`<path d="${points}" fill="none" stroke="${metric==='latency'?'#d0a7ff':'#7de6c4'}" stroke-width="2"/>`;
 });
 updateResourceRegions();
 document.dispatchEvent(new CustomEvent('fno:update'));
}
async function refresh(){
 if(state.refreshing||document.hidden)return;
 state.refreshing=true;document.body.classList.add('is-loading');
 $('#modeToggle').disabled=true;$('#modeToggle').setAttribute('aria-busy','true');
 try{
   // Publish status before any slower aggregate or inventory returns.
   await Promise.allSettled(['status','overview','inventory'].map(name=>fetchResource(name)));
 }finally{
   state.refreshing=false;document.body.classList.remove('is-loading');
   $('#modeToggle').disabled=false;$('#modeToggle').setAttribute('aria-busy','false');
 }
}
function integrationPanel(){const s=state.status,h=s?.huawei||{},probe=s?.probe,partial=Object.entries(h.sections||{}).filter(([k,v])=>k!=='router_logs'&&v!=='ok').map(([k])=>k);return keyvals([
 ['Huawei HTTP',state.api&&h.quality==='ok'?(partial.length?'Parcial ('+partial.join(', ')+') · ':'Ativo · ')+time(h.collected_at):'Sem leitura recente'],
 ['Sondas TCP',state.api&&probe&&fresh(probe.ts)?'Ativas · '+time(probe.ts):'Sem leitura recente'],
 ['Intervalo médio observado',fmt(state.overview?.quality?.observed_interval_mean_seconds,1)+' s'],['Histórico SQLite',state.api?'Disponível · retenção: '+retention(s.retention_days):'Servidor sem resposta'],['Logs internos Huawei','Não recolhidos'],['Consumo por aparelho','Sem fonte validada'],['Autenticação','Gerida internamente pelo coletor'],['Fila persistente',state.api&&s.recording?fmt(s.recording.pending_samples,0)+' amostras pendentes':'Sem dados'],['Exportação','CSV/JSON completos por aparelho e período']]);}
function panelExtras(metric){const h=state.status?.huawei||{},fresh=state.api&&h.quality==='ok';if(metric==='integrations')return integrationPanel();if(!fresh&&['router','wifi'].includes(metric))return empty('Sem leitura atual. Consulta o histórico e a hora das amostras.');
 if(metric==='router')return keyvals([['Firmware',h.firmware],['RAM',fmt(h.metrics?.memory_pct)+'%'],['Tempo ligado',duration(h.metrics?.uptime_seconds)],['Óptica RX',fmt(h.metrics?.optical_rx_dbm)+' dBm'],['Óptica TX',fmt(h.metrics?.optical_tx_dbm)+' dBm'],['Temperatura do transceiver',fmt(h.metrics?.optical_temp_c)+' °C'],['PON',h.health?.pon_connected==null?'Sem dados':h.health.pon_connected?'Ligado':'Desligado'],...Object.entries(h.interfaces||{}).map(([k,v])=>[k.toUpperCase(),`RX ${fmt(v.rx_bytes,0)} bytes · TX ${fmt(v.tx_bytes,0)} bytes · erros RX/TX ${fmt(v.rx_errors,0)}/${fmt(v.tx_errors,0)}${k.startsWith('lan')?` · ${v.link_up==null?'estado não reportado':v.link_up?'ligada '+fmt(v.speed_mbps,0)+' Mbit/s':'sem ligação'}`:''}`])]);
 if(metric==='wifi')return keyvals(Object.entries(h.wifi||{}).map(([k,v])=>[k.toUpperCase(),`${v.enabled==null?'Estado não reportado':v.enabled?'Ativa':'Inativa'} · ${v.band||'banda desconhecida'} · canal ${fmt(v.channel,0)} · RX ${fmt(v.rx_bytes,0)} bytes · TX ${fmt(v.tx_bytes,0)} bytes · erros ${fmt(v.rx_errors,0)}/${fmt(v.tx_errors,0)}`]));
 if(metric==='health')return integrationPanel();return '';}
async function openSheet(metric){
 if(metric==='devices'){document.dispatchEvent(new CustomEvent('fno:devices'));return;}
 if(state.metric)abortSheet();
 state.metric=config[metric]?metric:'router';state.period='24h';state.filter='all';state.main=true;state.secondary=true;state.lastFocus=document.activeElement;
 $('#sidebar').classList.remove('open');$('#menuToggle').setAttribute('aria-expanded','false');
 $('#sheetLayer').hidden=false;document.body.classList.add('sheet-open');$('.shell').inert=true;
 $('#detailSheet').focus();await loadSheet();
}
function closeSheet(){
 abortSheet();state.metric=null;state.bundle=null;state.request++;
 $('#sheetLayer').hidden=true;document.body.classList.remove('sheet-open');
 $('.shell').inert=false;state.lastFocus?.focus({preventScroll:true});
}
function updateSheetMeta(){
 const c=config[state.metric];if(!c)return;
 $('#detailTitle').textContent=c.title;$('#detailCrumb').textContent=c.title.toUpperCase();
 $('#detailDesc').textContent=c.desc;$('#chartTitle').textContent=c.title;
 $('#detailEyebrow').textContent='INVESTIGAÇÃO / LEITURAS REAIS';
 $$('[data-period]').forEach(el=>{const active=el.dataset.period===state.period;
   el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active))});
 $('#legendBox').innerHTML=[
   ...(c.a?[['main',c.main,state.main]]:[]),
   ...(c.b?[['secondary',c.secondary,state.secondary]]:[])
 ].map(([key,label,on])=>'<button type="button" class="legend-button '+(on?'':'off')+
    '" data-series="'+key+'" aria-pressed="'+on+'">'+esc(label)+'</button>').join('');
 $('#chartSubtitle').textContent='Período '+state.period+' · a aguardar a consulta atual.';
 $('#resolutionText').textContent='Cobertura e resolução a carregar para '+state.period+'.';
}
async function loadSheet(){
 if(!state.metric)return;
 abortSheet();
 const request=++state.request,metric=state.metric,period=state.period;
 const controller=new AbortController();activeSheetAbort=controller;
 state.bundle=null;updateSheetMeta();$('#historyChart').dataset.phase='loading';
 $('#historyChart').setAttribute('aria-busy','true');
 $('#exportCsv').disabled=true;$('#detailStats').replaceChildren();
 $('#analysisRows').replaceChildren();$('#detailEvents').replaceChildren();
 $('#selectionSummary').textContent='A carregar '+period+'. Dados do período anterior não são apresentados.';
 $('#analysisText').textContent=config[metric].desc;
 $('#historyChart').innerHTML=loading('A carregar histórico de '+period+'…');
 $('#detailStats').innerHTML=Array.from({length:4},()=>loading('Carregando métrica…',true)).join('');
 $('#analysisRows').innerHTML=loading('Carregando leituras…',true);$('#detailEvents').innerHTML=loading('Carregando eventos…',true);
 for(const node of [$('#detailStats'),$('#analysisRows'),$('#detailEvents')])node.setAttribute('aria-busy','true');
 try{
   const bundle=await sheetBundle(period,controller.signal);
   if(controller.signal.aborted||request!==state.request||state.metric!==metric||state.period!==period)return;
   state.bundle=bundle;renderSheet();
   const populated=bundle.series.length||bundle.probes?.length||bundle.events?.length;
   if(!populated){
     $('#historyChart').innerHTML=empty('Não existem amostras neste período.');
     $('#historyChart').dataset.phase='empty';
   }else $('#historyChart').dataset.phase='ready';
 }catch(e){
   if(controller.signal.aborted||request!==state.request||state.metric!==metric)return;
   $('#historyChart').dataset.phase='error';
   $('#detailStats').replaceChildren();$('#analysisRows').innerHTML=empty('Leituras indisponíveis; tente novamente.');$('#detailEvents').innerHTML=empty('Eventos não carregados.');
   $('#historyChart').innerHTML='<div role="alert">Não foi possível carregar o histórico de '+esc(period)+
     '. <button type="button" data-sheet-retry>Tentar novamente</button></div>';
   $('#chartSubtitle').textContent='Histórico de '+period+' indisponível. Pode tentar novamente.';
 }finally{
   if(request===state.request&&state.metric===metric){
     $('#historyChart').setAttribute('aria-busy','false');
     for(const node of [$('#detailStats'),$('#analysisRows'),$('#detailEvents')])node.setAttribute('aria-busy','false');
     if(activeSheetAbort===controller)activeSheetAbort=null;
   }
 }
}
function renderSheet(){const c=config[state.metric],b=state.bundle;if(!c||!b)return;$('#detailTitle').textContent=c.title;$('#detailCrumb').textContent=c.title.toUpperCase();$('#detailDesc').textContent=c.desc;$('#detailEyebrow').textContent='INVESTIGAÇÃO / LEITURAS REAIS';$('#chartTitle').textContent=c.title;$('#chartSubtitle').textContent=`${time(b.period.from)} — ${time(b.period.to)} · ${state.metric==='traffic'&&b.counter_series?'observações originais; quebras preservadas':'médias por intervalo; extremos preservados'}`;
 $$('[data-period]').forEach(el=>{const active=el.dataset.period===state.period;el.classList.toggle('active',active);el.setAttribute('aria-pressed',active);});
 const observed=state.metric==='traffic'&&state.counterMode!=='raw'&&b.counter_period?.observed_increments;
 if(observed){$('#detailTitle').textContent=$('#chartTitle').textContent='Incrementos WAN observados';$('#detailDesc').textContent='Soma dos aumentos entre leituras consecutivas válidas. Quedas e lacunas são excluídas; pode estar incompleta. Não é consumo total nem velocidade.';$('#chartSubtitle').textContent=`${time(b.period.from)} — ${time(b.period.to)} · somado antes da redução de pontos; quebras preservadas`;}
 const defs=[...(c.a&&state.main?[{key:c.a,label:c.main,color:'#c3a4ff',scale:c.scale,unit:c.unit}]:[]),...(c.b&&state.secondary?[{key:c.b,label:c.secondary,color:'#69e9dc',scale:c.scale,unit:c.unit}]:[])];
 if(observed)for(const d of defs){d.key=d.key.replace('_bytes','_observed_bytes');d.label=d.label.replace('Contador','Incrementos');}
 $('#legendBox').innerHTML=[...(c.a?[['main',c.main,state.main]]:[]),...(c.b?[['secondary',c.secondary,state.secondary]]:[])].map(([key,label,on])=>`<button class="legend-button ${on?'':'off'}" data-series="${key}" aria-pressed="${on}">${esc(observed?label.replace('Contador','Incrementos'):label)}</button>`).join('')+(state.metric==='traffic'?`<button class="legend-button" data-counter-mode="${observed?'raw':'observed'}">${observed?'Ver contadores brutos':'Ver incrementos observados'}</button>`:'');
 if(defs.length)chart($('#historyChart'),state.metric==='traffic'&&b.counter_series?b.counter_series:c.probes?b.probes:b.series,defs,state.metric==='traffic'&&b.counter_period?b.counter_period:b.period,$('#selectionSummary'));else $('#historyChart').innerHTML=empty('Consulta as fontes e eventos abaixo. Não existe uma série numérica para esta vista.');
 const stats=c.probes?b.probe_stats:b.stats,a=stats[c.a]||{};
 $('#detailStats').innerHTML=tile('Mínimo',fmt(a.min==null?null:a.min/c.scale),c.unit,'Valor real no arquivo')+tile('Média amostral',fmt(a.avg==null?null:a.avg/c.scale),c.unit,'Média aritmética das leituras')+tile('Máximo',fmt(a.max==null?null:a.max/c.scale),c.unit,'Extremo preservado')+tile('Amostras válidas',fmt(a.sample_count||0,0),'','Desta métrica no período');
 if(observed){const rx=observed.wan_rx_bytes,tx=observed.wan_tx_bytes;$('#detailStats').innerHTML=tile('Incrementos RX',fmt(rx.bytes==null?null:rx.bytes/2**30),'GiB','Soma dos aumentos válidos; pode estar incompleta')+tile('Incrementos TX',fmt(tx.bytes==null?null:tx.bytes/2**30),'GiB','Sem correção presumida de volta do contador')+tile('Pares válidos RX / TX',`${rx.valid_pairs} / ${tx.valid_pairs}`,'','Leituras consecutivas até 180 s')+tile('Transições excluídas RX / TX',`${rx.excluded_transitions} / ${tx.excluded_transitions}`,'','Quedas, lacunas ou dados inválidos');}
 if(!c.a)$('#detailStats').innerHTML=tile('Eventos no período',fmt(b.events.length,0),'','Registros persistidos')+tile('Avisos',fmt(b.events.filter(e=>e.severity==='warning').length,0))+tile('Críticos',fmt(b.events.filter(e=>e.severity==='critical').length,0))+tile('Cobertura da coleta',fmt(b.quality.coverage_percent),'%');
 $('#resolutionText').textContent=`Intervalos de ${duration(b.period.resolution_seconds)} · cobertura router ${fmt(b.quality.coverage_percent)}%`;
 $('#analysisText').textContent=observed?$('#detailDesc').textContent:c.desc;$('#analysisRows').innerHTML=keyvals([['Fonte','huawei-b7-http / TCP local conforme métrica'],['Amostras router',b.quality.sample_count],['Esperadas a cada 60s',b.quality.expected_count],['Cobertura router',fmt(b.quality.coverage_percent)+'%']])+panelExtras(state.metric);
 const events=b.events.filter(e=>state.filter==='all'||['warning','critical'].includes(e.severity));$('#detailEvents').innerHTML=events.map(e=>`<div class="event-record"><span class="event-time">${esc(time(e.ts))}</span><div class="event-content"><strong>${esc(e.title)}</strong><span>${esc(e.detail)} · ${esc(e.source)}</span></div></div>`).join('')||empty('Sem eventos deste tipo no período.');
 $('#selectionSummary').textContent='Usa o rato ou as setas no gráfico para consultar as leituras. Intervalos sem dados não são interpolados.';$('#sheetFootnote').textContent=observed?'Incrementos positivos somados nas amostras originais; transições excluídas não foram reconstruídas. Não representa consumo total.':'Fonte e período preservados. Sem taxas WAN corrigidas, sem pontuação artificial.';$('#exportCsv').disabled=false;$('#exportCsv').textContent=state.metric==='events'?'Exportar eventos exibidos (CSV)':'Exportar CSV dos intervalos';$('#exportCsv').hidden=state.metric==='integrations';
}
function download(name,text,mime){const url=URL.createObjectURL(new Blob([text],{type:mime})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
function exportSummary(){
 if(!state.bundle)return;const b=state.bundle,c=config[state.metric],events=state.metric==='events';
 const rows=events?b.events.filter(e=>state.filter==='all'||['warning','critical'].includes(e.severity)):(state.metric==='traffic'&&b.counter_series?b.counter_series:c.probes?b.probes:b.series);
 const fields=events?['ts','severity','category','title','detail','source']:['timestamp','timestamp_end','sample_count',c.a,c.b,c.a&&c.a+'_min',c.a&&c.a+'_max',c.b&&c.b+'_min',c.b&&c.b+'_max',...(state.metric==='traffic'?['wan_rx_observed_bytes','wan_tx_observed_bytes']:[]),'source','aggregation'].filter(Boolean);
 const value=(p,k)=>{if(k==='source')return events?p.source:c.probes?'local_tcp_probe':'huawei-b7-http';if(k==='aggregation')return state.metric==='traffic'&&b.counter_series?'original_counter_and_sum_of_valid_positive_deltas':'bucket_mean_with_min_max_envelope';if(k.endsWith('_min')||k.endsWith('_max')){const suffix=k.slice(-3);return p.values?.[k.slice(0,-4)]?.[suffix]??'';}return p[k]??'';};
 const csv=[fields,...rows.map(p=>fields.map(k=>value(p,k)))].map(row=>row.map(v=>{const text=String(v);return '"'+(/^[=+@]/.test(text)?"'"+text:text).replaceAll('"','""')+'"';}).join(',')).join('\r\n');
 download(`faysk-${state.metric}-${state.period}-intervalos.csv`,'\ufeff'+csv,'text/csv;charset=utf-8');
}

function trap(event,layer){if(event.key!=='Tab')return;const nodes=$$('button,a[href],input,[tabindex="0"]',layer).filter(el=>!el.disabled&&el.getClientRects().length);if(!nodes.length)return;if(event.shiftKey&&document.activeElement===nodes[0]){event.preventDefault();nodes.at(-1).focus();}else if(!event.shiftKey&&document.activeElement===nodes.at(-1)){event.preventDefault();nodes[0].focus();}}
function init(){
 $$('[data-detail]').forEach(el=>el.addEventListener('click',()=>openSheet(el.dataset.detail)));
 $('#modeToggle').addEventListener('click',refresh);$('#sheetClose').addEventListener('click',closeSheet);$('#sheetBackdrop').addEventListener('click',closeSheet);
 $('#periodButtons').addEventListener('click',e=>{const el=e.target.closest('[data-period]');if(el&&state.period!==el.dataset.period){state.period=el.dataset.period;loadSheet();}});
 $('#historyChart').addEventListener('click',e=>{if(e.target.closest('[data-sheet-retry]'))loadSheet();});
 document.addEventListener('click',e=>{const b=e.target.closest('[data-retry-resource]');if(b)fetchResource(b.dataset.retryResource);});
 $('#legendBox').addEventListener('click',e=>{const mode=e.target.closest('[data-counter-mode]');if(mode){state.counterMode=mode.dataset.counterMode;renderSheet();return;}const el=e.target.closest('[data-series]');if(!el)return;state[el.dataset.series]=!state[el.dataset.series];if(!state.main&&!state.secondary)state.main=true;renderSheet();});
 $('#eventsFilter').addEventListener('click',()=>{state.filter=state.filter==='all'?'warning':'all';$('#eventsFilter').textContent=state.filter==='all'?'Todos':'Avisos';renderSheet();});
 $('#exportCsv').addEventListener('click',exportSummary);$('#infoBtn').addEventListener('click',()=>openSheet('integrations'));
 $('#menuToggle').addEventListener('click',()=>{const on=$('#sidebar').classList.toggle('open');$('#menuToggle').setAttribute('aria-expanded',on);});
 $('.brand').addEventListener('click',()=>$('#sidebar').classList.remove('open'));
 $('.event-preview').addEventListener('click',e=>{if(e.target.closest('[data-event]'))openSheet('events');});
 document.addEventListener('keydown',e=>{if(!$('#sheetLayer').hidden){if(e.key==='Escape')closeSheet();else trap(e,$('#detailSheet'));}});
 const tick=()=>$('#clock').textContent=new Date().toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'});tick();setInterval(tick,15000);refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
}
window.FNO={state,$,$$,esc,fmt,time,duration,retention,api,toast,tile,keyvals,empty,loading,chart,download,trap,blockFeedback};
init();
