/* OBSERVATÓRIO S7 — API do host em /api/host/, cache e sensores opcionais.
 * Demo somente explícita; falhas preservam a última leitura com aviso. */
(function(){
'use strict';
const Demo=window.S7DemoData;
const $=s=>document.querySelector(s);
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=0)=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d}):'Sem dados';
const divide=(a,b,scale=1)=>a==null||b==null||!b?null:a/b*scale;
const subtract=(a,b)=>a==null||b==null?null:a-b;
const cap=(v,a,b)=>Math.max(a,Math.min(b,v));
const prettyTime=dt=>new Date(dt).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const dateTime=dt=>new Date(dt).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});
const duration=s=>{if(!Number.isFinite(s))return '—';const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return `${d?d+'d ':''}${h}h ${m}min`};
const nav=[['overview','Visão geral','layout-dashboard'],['performance','Desempenho','activity'],['network','Rede do S7','wifi'],['storage','Armazenamento','hard-drive'],['battery','Bateria & energia','thermometer'],['services','Monitor & coleta','server'],['activity','Explorar dados','list'],['settings','Configurações','settings']];
const ranges=[['1h','1h'],['6h','6h'],['12h','12h'],['24h','24h'],['7d','7d'],['30d','30d'],['1a','1 ano']];
const paths={
 'layout-dashboard':'<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
 'activity':'<path d="M2 12h4l3-8 5 16 3-8h5"/>','wifi':'<path d="M2 9a16 16 0 0 1 20 0M5 12.5a11 11 0 0 1 14 0M8.5 16a6 6 0 0 1 7 0"/><circle cx="12" cy="20" r="1" fill="currentColor" stroke="none"/>',
 'hard-drive':'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 12h18"/><circle cx="7.5" cy="15.5" r=".9" fill="currentColor" stroke="none"/>',
 'thermometer':'<path d="M14 14.8V5a3 3 0 0 0-6 0v9.8a5 5 0 1 0 6 0Z"/><path d="M11 9v9"/>',
 'server':'<rect x="3" y="3" width="18" height="8" rx="2"/><rect x="3" y="13" width="18" height="8" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h7M11 17h7"/>',
 'list':'<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
 'settings':'<circle cx="12" cy="12" r="3"/><path d="M20 13.5v-3l-2.3-.7-.7-1.6 1-2.2-2.1-2.1-2.2 1-1.6-.7L11.5 2h-3l-.7 2.3-1.6.7-2.2-1L2 6.1l1 2.2-.7 1.6L0 10.5v3l2.3.7.7 1.6-1 2.2L4 20l2.2-1 1.6.7.7 2.3h3l.7-2.3 1.6-.7 2.2 1 2.1-2.1-1-2.2.7-1.6z" transform="translate(1 0) scale(.92 1)"/>',
 'sun':'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
 'moon':'<path d="M20.7 14.1A9 9 0 0 1 9.9 3.3 9 9 0 1 0 20.7 14.1Z"/>',
 'cpu':'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/><rect x="10" y="10" width="4" height="4" rx=".5"/>',
 'database':'<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
 'battery':'<rect x="2" y="6" width="18" height="12" rx="2"/><path d="M22 10v4M6 12h9"/>',
 'clock':'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>','shield':'<path d="M12 2 20 6v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/>',
 'arrow-up-right':'<path d="M7 17 17 7M7 7h10v10"/>','arrow-right':'<path d="M5 12h14M13 6l6 6-6 6"/>','download':'<path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/>',
 'refresh':'<path d="M20 6v5h-5M4 18v-5h5M5.5 9a7 7 0 0 1 12.5-2l2 4M4 13l2 4a7 7 0 0 0 12.5-2"/>',
 'pause':'<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
 'play':'<path d="m8 5 12 7-12 7z"/>','terminal':'<rect x="2" y="3" width="20" height="18" rx="2"/><path d="m6 9 4 3-4 3M12 16h5"/>',
 'globe':'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-6 6-6 12 0 18M12 3c6 6 6 12 0 18"/>',
 'signal':'<path d="M3 20v-3M8 20v-7M13 20v-11M18 20V4"/>','check':'<path d="m4 12 5 5L20 6"/>','info':'<circle cx="12" cy="12" r="10"/><path d="M12 11v6M12 7h.01"/>',
 'alert':'<path d="M10.2 3 1.8 18a2 2 0 0 0 1.8 3h16.8a2 2 0 0 0 1.8-3L13.8 3a2 2 0 0 0-3.6 0Z"/><path d="M12 9v5M12 18h.01"/>',
 'copy':'<rect x="7" y="7" width="14" height="14" rx="2"/><path d="M17 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2"/>','smartphone':'<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 19h2"/>',
 'cloud':'<path d="M7 18a5 5 0 0 1-.8-10 7 7 0 0 1 13.6 2 4 4 0 0 1-.8 8z"/>','power':'<path d="M12 2v10M6.5 5.5a9 9 0 1 0 11 0"/>',
 'layers':'<path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/>','search':'<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
 'zap':'<path d="M13 2 4 13h7l-1 9 10-12h-7z"/>','external':'<path d="M14 4h6v6M20 4l-9 9M20 14v6H4V4h6"/>'
};
function ic(n){return `<svg class="icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[n]||paths.info}</svg>`}
function readSetting(k,fallback){try{return localStorage.getItem('s7_'+k)??fallback}catch{return fallback}}
function saveSetting(k,v){try{localStorage.setItem('s7_'+k,String(v))}catch{}}
function emptySnapshot(){return {timestamp:null,device:{name:'Servidor S7',os:null,uptimeSec:null},cpu:{usagePercent:null,frequencyMHz:null,temperatureC:null,coresPercent:[]},memory:{totalMB:null,usedMB:null,cachedMB:null,swapMB:null},battery:{levelPercent:null,status:null,temperatureC:null,voltageMV:null,currentMA:null,health:null,plugged:null},network:{interface:null,ip:null,ssid:null,signalDbm:null,linkMbps:null,rxMbps:null,txMbps:null,latencyMs:null,connected:null},storage:[],services:[],events:[],diagnostics:{},availability:{}};}
const state={page:'overview',range:readSetting('range','24h'),theme:readSetting('theme','dark'),pref:'auto',motion:readSetting('motion','on')!=='off',historyTimes:{},lastPage:null,mode:'offline',snapshot:emptySnapshot(),paused:false,tick:0,filter:'all',search:'',history:{},historyStatus:{},fetching:false,explorerLimit:48};
let chartID=0;let chartRegistry=new Map(),previousChartSelection=new Map();
const HISTORY_TTL_MS=60000,HISTORY_CACHE_LIMIT=28;
const historyFlights=new Map();
const requiredHistory={overview:['cpu','memory','rx','tx'],performance:['cpu','memory'],network:['rx','tx'],storage:['storage'],battery:['battery','temp']};
const currentHistoryKeys=()=>new Set((requiredHistory[state.page]||[]).map(metric=>metric+':'+state.range));
let renderQueued=false;
let lastRenderedRange=state.range;
function scheduleRender(){
 if(renderQueued)return;
 renderQueued=true;
 // rAF batches writes in visible tabs; timeout fallback handles throttled/headless frames.
 let flushed=false;
 const flush=()=>{if(flushed)return;flushed=true;renderQueued=false;render()};
 if(typeof requestAnimationFrame==='function')requestAnimationFrame(flush);
 else setTimeout(flush,0);
 setTimeout(flush,80);
}
function historyAnnouncement(message){const el=$('#history-announcement');if(el)el.textContent=message;}
function cacheHistory(key,values){
 state.history[key]=values;state.historyTimes[key]=Date.now();
 const keys=Object.keys(state.historyTimes);
 if(keys.length>HISTORY_CACHE_LIMIT){
   keys.sort((a,b)=>state.historyTimes[a]-state.historyTimes[b]);
   let count=keys.length;
   for(const evicted of keys){
     if(count<=HISTORY_CACHE_LIMIT)break;
     if(historyFlights.has(evicted)&&evicted!==key)continue;
     delete state.history[evicted];delete state.historyTimes[evicted];delete state.historyStatus[evicted];
     count--;
   }
 }
}
function cancelUnusedHistory(){
 const needed=currentHistoryKeys();
 for(const [key,entry] of historyFlights){
   if(!needed.has(key)){entry.controller.abort();historyFlights.delete(key);
     if(state.historyStatus[key]?.phase==='loading')delete state.historyStatus[key];}
 }
}
function historyState(metric,range=state.range){
 const key=metric+':'+range,meta=state.historyStatus[key];
 if(meta)return meta.phase;
 if(Array.isArray(state.history[key]))return state.history[key].length?'success':'empty';
 return 'idle';
}
function toast(text){const el=document.createElement('div');el.className='toast';el.textContent=text;$('#toast-region').appendChild(el);setTimeout(()=>el.remove(),3900);}
function setTheme(t){state.theme=t;saveSetting('theme',t);document.body.dataset.theme=t;$('#theme-toggle').innerHTML=ic(t==='dark'?'sun':'moon')}
function setNav(){ $('#main-nav').innerHTML=nav.map(([key,label,icon],idx)=>`<button type="button" class="nav-item ${state.page===key?'active':''}" data-nav="${key}" aria-current="${state.page===key?'page':'false'}">${ic(icon)}<span>${label}</span>${idx===0?'<span class="nav-trailing">⌘1</span>':''}</button>`).join('')}
function head(title,desc,buttons=''){return `<div class="page-head"><div><div class="eyebrow">GALAXY S7 EDGE / OBSERVATORY</div><h1>${title}</h1><p class="page-subtitle">${desc}</p></div><div class="page-actions">${buttons}</div></div>`}
function btn(label,icon,action,cls=''){return `<button type="button" class="btn ${cls}" data-${action}>${ic(icon)}${label}</button>`}
function rangeSwitch(){return `<div class="range-switch" role="group" aria-label="Intervalo de histórico">${ranges.map(([k,label])=>`<button class="range-button ${state.range===k?'active':''}" type="button" data-range="${k}" aria-pressed="${state.range===k}">${label}</button>`).join('')}</div>`}
function cardTitle(title,desc='',other=''){return `<div class="card-title-row"><div><h2>${title}</h2>${desc?`<p>${desc}</p>`:''}</div>${other}</div>`}
function tile(label,val,unit=''){return `<div class="stat-tile"><span>${label}</span><strong>${val}${unit?` <small>${unit}</small>`:''}</strong></div>`}
function pct(n){return n==null?'Sem dados':`${num(n,1)}%`}
function humanRate(m){return m==null?'Sem dados':`${num(m,2)} Mb/s`}
function meter(v,c=''){if(v==null)return '<div class="muted small">Sem dados</div>';return `<div class="meter ${c}"><span style="width:${cap(Number(v)||0,.1,100)}%"></span></div>`}
function detailsRow(label,value){return `<div class="details-row"><span>${label}</span><strong>${value}</strong></div>`}
function sectionHead(title,subtitle,page){return `<div class="section-head"><div><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:''}</div>${page?`<button class="link-button" data-nav="${page}" type="button">Ver detalhes ${ic('arrow-up-right')}</button>`:''}</div>`}
function kpi(label,value,unit,sub,icon){return `<article class="card kpi-card"><div class="kpi-top"><span class="kpi-label">${label}</span><span class="metric-icon">${ic(icon)}</span></div><div class="kpi-value"><strong>${value}</strong><span>${unit}</span></div><div class="kpi-foot"><span>${sub}</span><span class="trend">${state.mode==='demo'?'SIM.':state.mode==='offline'?'ANTIGA':'LOCAL'}</span></div><div class="kpi-accent-bar"></div></article>`}
function keyLine(labels){return `<div class="chart-key">${labels.map(([label,color])=>`<span><i class="key-dot ${color||''}"></i>${label}</span>`).join('')}</div>`}
function curve(series,x0,y0,w,h,min,max){let previous=null;return series.map(p=>{if(p.value==null||!Number.isFinite(p.value)){previous=null;return '';}const x=x0+(p.time-series[0].time)/Math.max(1,series[series.length-1].time-series[0].time)*w,y=y0+h-(cap(p.value,min,max)-min)/(max-min)*h;const command=previous!==null&&p.time-previous<Math.max(180000,({ '1h':3600,'6h':21600,'12h':43200,'24h':86400,'7d':604800,'30d':2592000,'1a':31536000 }[state.range]||86400)/360*2500)?'L':'M';previous=p.time;return `${command}${x.toFixed(1)},${y.toFixed(1)}`}).join(' ')}
function chart(metric,opts={}){
  const cfg={cpu:{max:100,color:'accent',unit:'%'},memory:{max:100,color:'blue',unit:'%'},rx:{max:12,color:'blue',unit:'Mb/s'},tx:{max:12,color:'accent',unit:'Mb/s'},battery:{max:100,color:'accent',unit:'%'},temp:{max:45,color:'orange',unit:'°C'},latency:{max:60,color:'blue',unit:'ms'},storage:{max:100,color:'violet',unit:'%' }}[metric]||{max:100,color:'accent',unit:'%'};
  const id=`plot${++chartID}`,wid=700,hei=215,x0=40,y0=12,w=650,h=172;let max=opts.max||cfg.max,min=opts.min||0;
  const vals=state.mode!=='demo'?(state.history[`${metric}:${state.range}`]||null):Demo.series(metric,state.range);
  const secondary=opts.secondary;
  const vals2=secondary?(state.mode!=='demo'?(state.history[`${secondary}:${state.range}`]||null):Demo.series(secondary,state.range)):null;
  const phases=[metric,...(secondary?[secondary]:[])].map(name=>state.mode==='demo'?'success':historyState(name));
  const phase=phases.includes('error')?'error':phases.includes('stale')?'stale':phases.includes('loading')?'loading':phases[0];
  const old=phase==='stale',pending=phase==='loading',failed=phase==='error';
  const retry=`<button type="button" class="link-button history-retry" data-retry-history="${esc([metric,...(secondary?[secondary]:[])].join(','))}">Tentar novamente</button>`;
  const message=failed?'Não foi possível carregar este histórico.':old?'Falha ao atualizar — exibindo apenas a última série válida deste período.':pending?'Carregando histórico deste período…':phase==='empty'?'Não há amostras registradas neste período.':'Ainda não há amostras suficientes neste período.';
  const statusLabel=(pending||failed||old)?`<div class="history-state history-${phase}" role="status">${pending?'<span class="history-spinner" aria-hidden="true"></span>':''}<span>${message}</span>${failed||old?retry:''}</div>`:'';
  if(!vals||vals.length<2||!vals.some(p=>p.value!=null)){
    return `<div class="history-region" data-history-region="${esc(metric)}" aria-busy="${pending}">${statusLabel||`<div class="empty history-empty" role="status">${message}</div>`}</div>`;
  }
  if(['rx','tx','temp'].includes(metric)){const all=[...vals,...(vals2||[])].map(p=>p.value).filter(v=>v!=null&&Number.isFinite(v));if(all.length){max=Math.max(metric==='temp'?1:.01,...all)*1.15;if(metric==='temp')min=Math.max(0,Math.min(...all)-3);}}
  chartRegistry.set(id,{values:vals,secondaryValues:vals2,secondaryName:secondary,min,max,unit:cfg.unit,metric,x0,y0,w,h,selectedIndex:previousChartSelection.get(state.page+':'+state.range+':'+metric+':'+(secondary||''))});
  const d1=curve(vals,x0,y0,w,h,min,max), d2=vals2&&vals2.length>=2?curve(vals2,x0,y0,w,h,min,max):null;
  const color=cfg.color==='accent'?'var(--accent)':cfg.color==='blue'?'var(--blue)':cfg.color==='orange'?'var(--orange)':'var(--violet)';
  const gradId=`fade${id}`;
  return `<div class="history-region" data-history-region="${esc(metric)}" aria-busy="${pending}">${statusLabel}<div class="chart-holder ${opts.tall?'tall':''} ${opts.compact?'compact':''}" data-chart="${id}" tabindex="0" role="group" aria-label="Gráfico ${esc(metric)} para ${state.range}. Use as setas para inspecionar os pontos.">
    <svg viewBox="0 0 ${wid} ${hei}" preserveAspectRatio="none" role="img" aria-label="Série temporal ${esc(metric)}">
      <defs><linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${color}" stop-opacity=".18"/><stop offset="100%" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
      ${[0,.25,.5,.75,1].map(f=>`<line x1="${x0}" x2="${x0+w}" y1="${y0+h*(1-f)}" y2="${y0+h*(1-f)}" stroke="var(--border)" stroke-dasharray="3 6" stroke-width="1"/><text x="${x0-9}" y="${y0+h*(1-f)+3}" text-anchor="end" fill="var(--muted)" font-size="10">${num(min+(max-min)*f,max<1?2:max<10?1:0)}</text>`).join('')}
      
      <path class="telemetry-line" pathLength="1" d="${d1}" fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      ${d2?`<path d="${d2}" fill="none" stroke="${opts.secondaryColor||'var(--violet)'}" opacity=".84" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`:''}
      <g class="plot-crosshair" visibility="hidden"><line x1="0" y1="${y0}" x2="0" y2="${y0+h}" stroke="var(--secondary)" stroke-dasharray="4 5" opacity=".8"/><circle cx="0" cy="0" r="4" fill="${color}" stroke="var(--surface)" stroke-width="2"/></g>
      <rect x="${x0}" y="${y0}" width="${w}" height="${h}" fill="transparent" />
    </svg>
    <div class="axis-foot"><span>${labelTime(vals[0].time)}</span><span>${labelTime(vals[Math.floor(vals.length*.33)].time)}</span><span>${labelTime(vals[Math.floor(vals.length*.66)].time)}</span><span>${labelTime(vals[vals.length-1].time)}</span></div>
  </div></div>`;
}
function labelTime(ts){let opt=state.range==='1a'?{month:'short',year:'2-digit'}:['7d','30d'].includes(state.range)?{day:'2-digit',month:'short'}:{hour:'2-digit',minute:'2-digit'};return new Date(ts).toLocaleString('pt-BR',opt)}
function card(content,cols='span-6',extra=''){return `<section class="card ${cols} ${extra}">${content}</section>`}
function serviceItem(s){const status=s.status==='running'?'Ativo':s.status==='warning'?'Pendente':'Parado';return `<div class="service-item"><div class="service-badge">${ic(s.id==='ssh'?'terminal':s.id==='web'?'globe':s.id==='collector'?'activity':'database')}</div><div class="service-copy"><strong>${esc(s.name)}</strong><small>${esc(s.description)}${s.port?' · porta '+num(s.port):''}</small></div><span class="status-pill ${s.status==='warning'?'warning':s.status==='running'?'':'muted'}">${status}</span></div>`}
function storageRow(s){const percent=(divide(s.usedGB,s.totalGB,100));return `<div class="storage-row"><div class="storage-row-head"><span class="storage-row-title">${ic(s.id==='internal'?'hard-drive':'database')}${esc(s.label)}</span><span class="storage-row-values"><strong>${num(s.usedGB,s.usedGB<1?3:1)} GiB</strong> / ${num(s.totalGB)} GiB</span></div>${meter(percent,s.id==='internal'?'orange':'blue')}<div class="storage-sub"><span>${esc(s.mount)}</span><span>${num(percent==null?null:100-percent,1)}% livre</span></div></div>`}
function eventItem(e){let minutes=Math.abs(e.at||0);return `<div class="event-item"><div class="event-mark ${e.type}"></div><div class="event-copy"><strong>${esc(e.title)}</strong><span>${esc(e.detail)}</span></div><time>${minutes<60?minutes+' min':Math.round(minutes/60)+' h'}</time></div>`}
function batteryRing(p){const circ=2*Math.PI*48;return `<div class="battery-ring"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="48" fill="none" stroke="var(--surface-3)" stroke-width="8"/><circle cx="60" cy="60" r="48" fill="none" stroke="var(--accent)" stroke-linecap="round" stroke-width="8" stroke-dasharray="${circ}" stroke-dashoffset="${p==null?circ:circ*(1-p/100)}"/></svg><div class="ring-content"><strong>${num(p)}%</strong><small>carga</small></div></div>`}
function sourceMap(){const d=state.snapshot.details||{},out={...(d.metrics||{})},agent=d.cpuAgent;if(agent?.status==='ok'){if(agent.rawFrames)out['cpu.agentFrames']={status:'ok',value:agent.rawFrames,source:'adb-shell:/proc/stat',unit:'kernel CPU ticks',semantics:'Contadores originais nas duas leituras; a utilização é calculada pela diferença entre elas.'};if(agent.extraCounters?.stat)out['cpu.kernelEvents']={status:'ok',value:agent.extraCounters.stat,source:'adb-shell:/proc/stat',unit:'kernel counters',semantics:'Contadores globais do kernel; btime é o instante do boot em segundos Unix.'};}return out;}
function availableEntries(prefixes){return Object.entries(sourceMap()).filter(([k,m])=>m.status==='ok'&&m.value!==null&&m.value!==undefined&&(!prefixes||prefixes.some(p=>k===p||k.startsWith(p+'.'))));}
const rawMetric=key=>state.snapshot.details?.metrics?.[key]?.status==='ok'?state.snapshot.details.metrics[key].value:null;
const scalar=key=>{const v=rawMetric(key);return typeof v==='number'?v:null};
const bytes=v=>v==null?'—':v>=1024**3?num(v/1024**3,2)+' GiB':v>=1024**2?num(v/1024**2,1)+' MiB':v>=1024?num(v/1024,1)+' KiB':num(v)+' B';
const present=v=>v!==null&&v!==undefined&&v!=='';
const row=(label,value,unit='')=>present(value)?detailsRow(esc(label),`${typeof value==='number'?num(value,Number.isInteger(value)?0:2):esc(value)}${unit?' <small>'+esc(unit)+'</small>':''}`):'';
const statCard=(label,value,unit,sub,icon)=>present(value)?kpi(label,typeof value==='number'?num(value,unit==='%'?(label==='CARGA'?0:1):unit==='°C'?1:Number.isInteger(value)?0:2):esc(value),esc(unit),esc(sub),icon).replace('card kpi-card','card kpi-card span-3'):'';
const groupNames={cpu:'Processador',gpu:'GPU Mali',devfreq:'Barramentos',memory:'Memória',zram:'zRAM',battery:'Bateria',power:'Alimentação',network:'Rede',disk:'Discos',process:'Processo do monitor',pressure:'Pressão do sistema',thermal:'Sensores'};
const fieldNames={agentFrames:'Leituras originais da CPU',kernelEvents:'Atividade global do kernel',usagePercent:'Utilização',frequencyMHz:'Frequência',online:'Online',present:'Presentes',scaling_cur_freq:'Frequência atual',scaling_min_freq:'Limite mínimo',scaling_max_freq:'Limite máximo',cpuinfo_min_freq:'Mínimo do hardware',cpuinfo_max_freq:'Máximo do hardware',governor:'Governor',timeInState:'Tempo por frequência',frequencyTransitions:'Trocas de frequência',loadavg:'Carga média · 1 / 5 / 15 min',meminfo:'Mapa da memória',vmstat:'Paginação e memória',interfaces:'Contadores por interface',clock:'Clock reportado',utilization:'Atividade reportada',cur_freq:'Frequência atual',min_freq:'Limite mínimo',max_freq:'Limite máximo',disksize:'Capacidade configurada',mm_stat:'Estatísticas de compressão',stat:'Contadores de blocos',orig_data_size:'Dados originais',compr_data_size:'Dados comprimidos',mem_used_total:'Memória utilizada',capacity:'Carga',temp:'Temperatura original',voltage_now:'Tensão original',current_now:'Corrente original',current_avg:'Corrente média original',charge_counter:'Contador de carga',charge_full:'Capacidade máxima reportada',charge_full_design:'Capacidade de projeto',cycle_count:'Ciclos',energy_now:'Energia',status:'Estado',health:'Saúde reportada',technology:'Tecnologia',counters:'Atividade de disco',io:'Leituras e escritas do processo',operstate:'Estado da interface',mtu:'MTU',carrier:'Portadora',speed:'Velocidade reportada',logical_block_size:'Bloco lógico',physical_block_size:'Bloco físico',type:'Tipo de mídia',time:'Tempo em repouso',usage:'Entradas em repouso',latency:'Latência de saída'};
function sourceLabel(key){const parts=key.split('.'),last=parts.at(-1);let label=fieldNames[last]||last;const cpu=key.match(/^cpu\.(\d+)\./);if(cpu)label='Núcleo '+cpu[1]+' · '+(key.match(/\.idle(\d+)\./)?'Repouso '+key.match(/\.idle(\d+)\./)[1]+' · ':'')+label;else if(parts[0]==='devfreq')label=(key.match(/devfreq_(\w+)/)?.[1]||parts[1]).toUpperCase()+' · '+label;else if(parts.length>2)label=parts.slice(1,-1).join(' · ')+' · '+label;return label;}
function unitLabel(unit){return ({'Samsung driver raw':'valor bruto do driver','Samsung driver frequency raw':'frequência bruta','kernel CPU ticks':'ticks de CPU','kernel counters':'contadores cumulativos','runnable tasks':'carga média','reported':'reportado pelo sistema','boolean':'estado','kernel positional counters':'contadores na ordem do kernel','block counters':'contadores de blocos','bytes and cumulative counts':'bytes e contagens','bytes and syscalls':'bytes e chamadas','KiB or counts by field':'KiB / contagens','kHz and kernel ticks':'kHz / ticks do kernel','CPU list':'núcleos','transitions':'transições','entries':'entradas','microseconds':'µs','name':'identificador','MMC or SD':'tipo de mídia','driver raw':'valor bruto do driver','sectors and counts':'setores / contagens','0.1 C':'décimos de °C','uV':'µV','uAh':'µAh','uWh':'µWh','cycles':'ciclos'})[unit]||unit;}
function sourceSummary(m){const v=m.value;if(Array.isArray(v))return v.length===1?num(v[0]):num(v.length)+' valores';if(v&&typeof v==='object')return num(Object.keys(v).length)+' campos';return typeof v==='number'?num(v,Number.isInteger(v)?0:2):esc(v);}
function sourceCards(entries){return entries.map(([key,m])=>`<details class="source-card" data-source="${esc(key)}"><summary><span class="source-glyph">${ic(({cpu:'cpu',memory:'database',network:'wifi',battery:'battery',disk:'hard-drive',process:'activity'})[key.split('.')[0]]||'layers')}</span><span class="source-copy"><strong>${esc(sourceLabel(key))}</strong><small>${esc(key)}</small></span><span class="source-value">${sourceSummary(m)}<small>${esc(unitLabel(m.unit))}</small></span><span class="disclosure-arrow" aria-hidden="true">+</span></summary><div class="source-body"></div></details>`).join('');}
function sourceSection(prefixes,title='Leituras detalhadas'){const entries=availableEntries(prefixes);if(!entries.length)return '';return `<details class="source-section"><summary><span>${ic('layers')} ${esc(title)} <b>${entries.length}</b></span><small>Explorar contadores ${ic('arrow-right')}</small></summary><div class="source-grid">${sourceCards(entries)}</div></details>`;}
function sourceSemantics(key,m){if(key.startsWith('gpu.'))return 'Valor original do driver Mali. Escala e janela de medição ainda não validadas; zero pode ocorrer em repouso.';if(key.startsWith('devfreq.'))return 'Frequência original do driver Samsung. A escala foi preservada, sem conversão presumida para Hz.';if(key.startsWith('battery.current'))return 'Corrente original do driver Samsung. Unidade e sinal ainda não foram validados.';if(key.endsWith('.timeInState'))return 'Tempo acumulado por frequência. Os ticks originais foram preservados sem conversão presumida.';if(key==='memory.meminfo')return 'Campos em KiB; HugePages, quando presentes, representam contagens.';if(key==='cpu.loadavg')return 'Carga média em 1, 5 e 15 minutos. Representa tarefas em execução ou espera, não percentual de CPU.';if(key.endsWith('.type'))return 'Tipo de mídia informado pelo kernel. Nenhum identificador do cartão é coletado.';return m.semantics||'';}
function sourceDetail(key){const m=sourceMap()[key];if(!m||m.status!=='ok')return '';const flattened=[];function flatten(v,p=''){if(v&&typeof v==='object')Object.entries(v).forEach(([k,x])=>flatten(x,p?p+'.'+k:k));else flattened.push([p||'Valor',v]);}flatten(m.value);return `<div class="source-provenance"><span>FONTE</span><code>${esc(m.source)}</code><span>AMOSTRA</span><strong>${esc(dateTime(state.snapshot.details.measuredAt||state.snapshot.timestamp))}</strong>${m.measuredAtBootSec!=null?`<span>AGENTE · DESDE BOOT</span><strong>${num(m.measuredAtBootSec,2)} s</strong>`:''}</div>${m.semantics?`<p class="source-note">${esc(sourceSemantics(key,m))}</p>`:''}<div class="counter-list">${flattened.map(([k,v])=>`<div><code>${esc(k)}</code><strong>${typeof v==='number'?num(v,Number.isInteger(v)?0:3):esc(v)}</strong></div>`).join('')}</div><div class="source-unit">Unidade original: ${esc(m.unit)}</div>`;}
function coreCards(){const s=state.snapshot,cores=s.cpu.coresPercent||[];return `<div class="core-grid">${Array.from({length:s.device.cores||cores.length},(_,i)=>{const use=cores[i],freq=scalar(`cpu.${i}.scaling_cur_freq`),online=rawMetric(`cpu.${i}.online`);return `<div class="core-box ${use==null?'core-idle':''}"><div class="core-title"><span>NÚCLEO ${i}</span><strong>${use!=null?num(use,1)+'%':online===0?'OFFLINE':'SEM AMOSTRA'}</strong></div>${use!=null?meter(use):'<div class="core-rest"></div>'}${freq!=null?`<small>${num(freq/1000)} MHz</small>`:''}</div>`;}).join('')}</div>`;}
function graphCard(title,desc,metric,secondary,span='span-6'){const label={cpu:'CPU',memory:'RAM',rx:'Recebido',tx:'Enviado',battery:'Carga',temp:'Bateria',storage:'Ocupação'};return card(`<div class="chart-card">${cardTitle(title,desc,rangeSwitch())}${keyLine([[label[metric]||metric,metric==='rx'?'blue':metric==='temp'?'orange':''],...(secondary?[[label[secondary],secondary==='tx'?'':'violet']]:[])])}${chart(metric,{secondary,secondaryColor:secondary==='tx'?'var(--accent)':undefined})}</div>`,span);}
function renderOverview(){const s=state.snapshot,m=s.memory,b=s.battery,n=s.network,d=s.diagnostics||{},count=availableEntries().length;return `${head('O S7, por inteiro.','O que está acontecendo no seu servidor, do sistema ao cartão SD.',btn('Exportar leitura','download','export="snapshot"'))}<div class="cards-grid">
${card(`<div class="device-hero"><div><div class="hero-overline"><span class="dot"></span>${state.mode==='real'?'TELEMETRIA LOCAL':'ÚLTIMA LEITURA'}</div><h2>Galaxy S7 <em>Edge</em></h2><p>${esc(s.device.soc||s.device.model||'Servidor pessoal')} · ${esc(s.device.architecture||'')}</p><div class="hero-chips">${present(s.device.os)?`<span>Android ${esc(s.device.os)}</span>`:''}<span>${count} leituras disponíveis</span><span>Dados no microSD</span></div></div><div class="device-orbit" aria-hidden="true"><div class="orbit-ring"></div><div class="orbit-ring second"></div><div class="orbit-phone">${ic('smartphone')}<span>S7</span></div><i></i></div></div><div class="hero-live-strip"><span>${ic('clock')} Em operação <strong>${duration(s.device.uptimeSec)}</strong></span>${present(s.cpu.frequencyMHz)?`<span>${ic('cpu')} Frequência <strong>${num(s.cpu.frequencyMHz)} MHz</strong></span>`:''}<button class="link-button" data-nav="services">Ver o monitor ${ic('arrow-right')}</button></div>`,'span-12','device-hero-card')}
${statCard('CPU',s.cpu.usagePercent,'%','Janela de '+num(d.cpuWindowSec,2)+' s · agente local','cpu')}${statCard('MEMÓRIA',divide(m.usedMB,m.totalMB,100),'%',bytes(m.usedMB==null?null:m.usedMB*1024**2)+' em uso','database')}${statCard('TEMPERATURA',b.temperatureC,'°C','Sensor da bateria','thermometer')}${statCard('CARGA',b.levelPercent,'%',translate(b.status)+(b.plugged?' · '+b.plugged:''),'battery')}
</div>${sectionHead('Pulso do servidor','Inspecione os pontos dos gráficos ou altere o período.','performance')}<div class="cards-grid">${graphCard('CPU & memória','Utilização em percentual','cpu','memory','span-7')}${graphCard('Tráfego do S7','Recebido e enviado pelo aparelho · Mb/s','rx','tx','span-5')}
${s.storage.length?card(`<div class="card-pad">${cardTitle('Espaço para continuar','Volumes medidos no aparelho',btn('Detalhes','arrow-up-right','nav="storage"'))}${s.storage.map(storageRow).join('')}</div>`,'span-7'):''}
${card(`<div class="card-pad">${cardTitle('Coleta em funcionamento','Histórico completo, separado do router')}<div class="collection-visual"><span class="collection-node">${ic('smartphone')}</span><span class="collection-track"><i></i></span><span class="collection-node">${ic('database')}</span><strong>microSD</strong></div>${row('Ritmo de coleta',d.samplingIntervalSec,'s')}${row('Agente local',agentLabel(d.agentStatus))}${row('Última amostra',s.timestamp?dateTime(s.timestamp):null)}${row('Histórico','Sem expiração automática')}<button class="btn" data-nav="activity">${ic('layers')} Explorar todas as leituras</button></div>`,'span-5')}</div>`;}
function translate(v){return ({Full:'Carregada',Charging:'Carregando',Discharging:'Descarregando','Not charging':'Sem carregar',Good:'Boa',Unknown:'Não informado'})[v]||v||'';}
function agentLabel(v){return ({ok:'Ativo no celular',unavailable:'Sem amostra atual','waiting-new-session':'Sincronizando sessão',stale:'Amostra desatualizada'})[v]||v||'';}
function renderPerformance(){const s=state.snapshot,mem=rawMetric('memory.meminfo')||{},load=rawMetric('cpu.loadavg');const cached=mem.Cached,swapUsed=mem.SwapTotal!=null&&mem.SwapFree!=null?mem.SwapTotal-mem.SwapFree:null;return `${head('Cada núcleo. Cada detalhe.','CPU, memória, compressão e atividade do hardware.',btn('Atualizar','refresh','refresh'))}<div class="cards-grid">${statCard('CPU GLOBAL',s.cpu.usagePercent,'%','Percentual na janela do agente','cpu')}${statCard('RAM EM USO',divide(s.memory.usedMB,1024),'GiB','Total − memória disponível','database')}${statCard('CACHE',cached==null?null:bytes(cached*1024),'','Cache de páginas do kernel','layers')}${statCard('SWAP EM USO',swapUsed==null?null:bytes(swapUsed*1024),'','SwapTotal − SwapFree','hard-drive')}
${card(`<div class="card-pad">${cardTitle('Oito núcleos, uma máquina','Uso na janela de '+num(s.diagnostics.cpuWindowSec,2)+' s · idade na coleta: '+num(s.diagnostics.agentAgeSeconds,1)+' s')}${coreCards()}${load?`<div class="load-strip">${load.map((v,i)=>`<div><span>CARGA · ${[1,5,15][i]} MIN</span><strong>${num(v,2)}</strong></div>`).join('')}</div><p class="small muted">Carga média representa tarefas em execução ou espera; não é percentual.</p>`:''}</div>`,'span-12')}${graphCard('CPU & RAM','Evolução do uso no período','cpu','memory','span-12')}
${renderMemoryBreakdown(mem)}${renderGpu()} </div>${sourceSection(['cpu','memory','zram','gpu','devfreq'],'Contadores do sistema e do hardware')}`;}
function renderMemoryBreakdown(m){if(!present(m.MemTotal))return '';const fields=[['Disponível',m.MemAvailable,'var(--accent)'],['Cache',m.Cached,'var(--blue)'],['Slab',m.Slab,'var(--violet)'],['Buffers',m.Buffers,'var(--orange)']].filter(([,v])=>v!=null);return card(`<div class="card-pad">${cardTitle('Por dentro da memória','Campos do kernel · categorias podem se sobrepor')}<div class="memory-total">${bytes(m.MemTotal*1024)}<small>acessíveis ao sistema</small></div>${fields.map(([k,v,c])=>`<div class="memory-line"><span><i style="background:${c}"></i>${k}</span><strong>${bytes(v*1024)}</strong><div class="memory-track"><b style="width:${cap(v/m.MemTotal*100,0,100)}%;background:${c}"></b></div></div>`).join('')}</div>`,'span-6');}
function renderGpu(){const entries=availableEntries(['gpu','devfreq']);if(!entries.length)return '';return card(`<div class="card-pad">${cardTitle('GPU & barramentos','Leituras nativas do driver Samsung')}<div class="raw-reading-grid">${entries.filter(([k])=>k.startsWith('gpu.')||k.endsWith('.cur_freq')).map(([k,m])=>`<div><span>${esc(sourceLabel(k))}</span><strong>${sourceSummary(m)}</strong><small>valor bruto · escala não validada</small></div>`).join('')}</div><p class="small muted">Os valores originais são preservados. Zero pode indicar repouso.</p></div>`,'span-6');}
function renderNetwork(){const s=state.snapshot,n=s.network,interfaces=rawMetric('network.interfaces')||{};return `${head('O tráfego do S7.','Contadores do próprio aparelho, separados do tráfego total da rede.',btn('Exportar leitura','download','export="snapshot"'))}<div class="cards-grid">${statCard('RECEBENDO',n.rxMbps,'Mb/s','Média entre duas coletas','download')}${statCard('ENVIANDO',n.txMbps,'Mb/s','Média entre duas coletas','arrow-up-right')}${present(n.interface)?statCard('INTERFACE',n.interface,'',n.connected?'Conectada':'Estado observado','wifi'):''}${statCard('INTERFACES',Object.keys(interfaces).length,'','Visíveis ao kernel','layers')}${graphCard('Recebido & enviado','Taxas médias em Mb/s','rx','tx','span-12')}
${Object.entries(interfaces).filter(([name,v])=>name===n.interface||v.rxBytes>0||v.txBytes>0).map(([name,v])=>card(`<div class="card-pad">${cardTitle(esc(name),'Contadores cumulativos desde a criação da interface',`<span class="status-pill">${esc(rawMetric('network.'+name+'.operstate')||'Observada')}</span>`)}<div class="interface-totals"><div><span>↓ RECEBIDO</span><strong>${bytes(v.rxBytes)}</strong></div><div><span>↑ ENVIADO</span><strong>${bytes(v.txBytes)}</strong></div></div><div class="interface-counts">${row('Pacotes recebidos',v.rxPackets)}${row('Pacotes enviados',v.txPackets)}${row('Erros · RX / TX',num(v.rxErrors)+' / '+num(v.txErrors))}${row('Descartes · RX / TX',num(v.rxDropped)+' / '+num(v.txDropped))}${row('MTU',rawMetric('network.'+name+'.mtu'))}</div></div>`,'span-6')).join('')}</div>${sourceSection(['network'],'Todos os contadores de rede')}`;}
function renderStorage(){const s=state.snapshot,d=s.diagnostics||{},host=s.details?.hostDatabase||{},disks=rawMetric('disk.counters')||{};return `${head('Espaço & persistência.','O cartão guarda as amostras completas e o histórico do router.',btn('Exportar leitura','download','export="snapshot"'))}<div class="cards-grid">${s.storage.map(v=>statCard(v.id==='sd'?'MICROSD DISPONÍVEL':'INTERNO DISPONÍVEL',v.availableBytes==null?null:bytes(v.availableBytes),'','Espaço disponível ao usuário',v.id==='sd'?'database':'hard-drive')).join('')}${statCard('BANCO DO HARDWARE',host.bytes==null?null:bytes(host.bytes),'','host-telemetry.db','database')}${statCard('BANCO DO ROUTER',d.databaseMB,'MiB','observatory.db','database')}
${card(`<div class="card-pad">${cardTitle('Volumes do aparelho','Capacidade e espaço disponível reais')}${s.storage.map(v=>storageRow(v)+`<div class="volume-extra">${row('Disponível ao usuário',v.availableBytes==null?null:bytes(v.availableBytes))}${row('Bloco do sistema de arquivos',v.blockSizeBytes,'B')}${v.inodesTotal>0?row('Inodes livres / total',num(v.inodesFree)+' / '+num(v.inodesTotal)):''}</div>`).join('')}</div>`,'span-7')}${card(`<div class="card-pad">${cardTitle('Registros completos','Retenção sem expiração automática')}<div class="retention-mark">${ic('database')}<div><strong>Cada amostra conta.</strong><span>Os gráficos resumem. O banco preserva.</span></div></div>${row('Diretório dos dados',d.dataLocation)}${row('WAL do hardware',host.walBytes==null?null:bytes(host.walBytes))}${row('WAL do router',d.walMB,'MiB')}${row('Última gravação concluída',d.historyWriteMs,'ms')}<p class="small muted">O histórico cresce continuamente. Espaço livre e falhas de gravação são acompanhados pelo monitor.</p></div>`,'span-5')}
${graphCard('Ocupação do armazenamento interno','Percentual utilizado · período selecionado','storage',null,'span-12')}${Object.entries(disks).map(([name,v])=>card(`<div class="card-pad">${cardTitle(esc(name),'Contadores do dispositivo de blocos')}${row('Tipo de mídia',rawMetric('disk.'+name+'.type'))}${row('Leituras concluídas',v[0])}${row('Setores lidos',v[2])}${row('Escritas concluídas',v[4])}${row('Setores escritos',v[6])}${row('I/O em andamento',v[8])}${row('Tempo ocupado em I/O',v[9],'ms')}</div>`,'span-6')).join('')}</div>${sourceSection(['disk'],'Contadores de armazenamento')}`;}
function renderBattery(){const b=state.snapshot.battery;return `${head('Energia, em tempo real.','Carga, alimentação e temperatura medidas no aparelho.',btn('Atualizar','refresh','refresh'))}<div class="cards-grid">${present(b.levelPercent)?card(`<div class="card-pad">${cardTitle('Bateria','Estado reportado pelo sistema')}<div class="battery-display">${batteryRing(b.levelPercent)}<div class="battery-details"><div class="big-number">${esc(translate(b.status))}</div><p>${esc(b.plugged||'Alimentação reportada pelo sistema')}</p></div></div>${row('Temperatura da bateria',b.temperatureC,'°C')}${row('Tensão',b.voltageMV,'mV')}${row('Saúde reportada',translate(b.health))}${row('Tecnologia',rawMetric('battery.technology'))}</div>`,'span-5'):''}${graphCard('Histórico de carga','Percentual da bateria no período','battery',null,'span-7')}${present(b.temperatureC)?graphCard('Temperatura da bateria','Leitura do sensor da bateria · °C','temp',null,'span-12'):''}</div>${sourceSection(['battery','power'],'Leituras originais de energia')}`;}
function renderServices(){const s=state.snapshot,d=s.diagnostics||{},p=rawMetric('process.status')||{},io=rawMetric('process.io')||{};return `${head('O monitor, por dentro.','Consumo da aplicação e saúde da coleta no próprio celular.')}<div class="cards-grid">${statCard('CPU DO MONITOR',d.processCpuPercent,'%','100% equivale a um núcleo','cpu')}${statCard('MEMÓRIA DO MONITOR',d.processRssMB,'MiB','Memória residente do Python','database')}${statCard('TEMPO DE COLETA',d.samplingMs,'ms','Amostragem do hardware, sem commit','clock')}${statCard('THREADS',p.Threads,'','Threads do processo','layers')}${card(`<div class="card-pad">${cardTitle('Instância do servidor','Processo que fornece o painel')}${s.services.map(serviceItem).join('')}${row('Supervisor',d.supervisor)}${row('PID',d.pid)}${row('Tempo em execução',duration(d.processUptimeSec))}${row('Agente de hardware',agentLabel(d.agentStatus))}${row('Idade do agente na coleta',d.agentAgeSeconds,'s')}${row('Janela da CPU',d.cpuWindowSec,'s')}${row('Arquivo pendente de envio',d.pendingSamples)}</div>`,'span-6')}${card(`<div class="card-pad">${cardTitle('Leituras & gravações','Contadores do próprio processo')}${row('Bytes lidos por chamadas',present(io.rchar)?bytes(io.rchar):null)}${row('Bytes enviados por chamadas',present(io.wchar)?bytes(io.wchar):null)}${row('Leituras de armazenamento',present(io.read_bytes)?bytes(io.read_bytes):null)}${row('Escritas de armazenamento',present(io.write_bytes)?bytes(io.write_bytes):null)}${row('Pico de memória residente',present(p.VmHWM)?bytes(p.VmHWM*1024):null)}${row('Trocas de contexto voluntárias',p.voluntary_ctxt_switches)}${row('Trocas de contexto involuntárias',p.nonvoluntary_ctxt_switches)}</div>`,'span-6')}</div>${diagnostics()}${sourceSection(['process'],'Contadores completos do monitor')}`;}
function explorerEntries(){const q=(state.search||'').toLocaleLowerCase('pt-BR');return availableEntries().filter(([k,m])=>(state.filter==='all'||k.split('.')[0]===state.filter)&&(!q||(k+' '+sourceLabel(k)+' '+m.source+' '+JSON.stringify(m.value)).toLocaleLowerCase('pt-BR').includes(q)));}
function explorerResults(){const e=explorerEntries();return `<div class="explorer-count">${e.length} ${e.length===1?'leitura':'leituras'}${state.search?(e.length===1?' encontrada':' encontradas'):(e.length===1?' disponível':' disponíveis')}</div><div class="source-grid">${sourceCards(e.slice(0,state.explorerLimit))}</div>${e.length>state.explorerLimit?`<button type="button" class="btn explorer-more" data-explorer-more>Carregar mais (${e.length-state.explorerLimit} restantes)</button>`:''}${e.length?'':'<div class="search-empty">'+ic('search')+'<h3>Nenhuma leitura corresponde à busca</h3><p>Tente outro termo ou escolha outro grupo.</p><button class="btn" data-clear-search>Limpar filtros</button></div>'}`;}
function renderActivity(){const groups=[...new Set(availableEntries().map(([k])=>k.split('.')[0]))];return `${head('Tudo que o S7 conta.','Busque uma leitura, abra seus contadores e confira a origem de cada valor.',btn('Exportar tudo','download','export="snapshot"'))}<div class="explorer-toolbar"><label class="explorer-search">${ic('search')}<input id="metric-search" type="search" placeholder="Buscar memória, CPU, interface, contador…" aria-label="Pesquisar leituras" value="${esc(state.search)}"></label><select class="select" id="metric-group" aria-label="Grupo de telemetria"><option value="all">Todos os grupos</option>${groups.map(k=>`<option value="${esc(k)}" ${state.filter===k?'selected':''}>${esc(groupNames[k]||k)}</option>`).join('')}</select></div><div id="explorer-results">${explorerResults()}</div>`;}
function renderSettings(){const s=state.snapshot,d=s.diagnostics||{};return `${head('Seu painel. Seu jeito.','Preferências deste navegador e informações do servidor.')}<div class="cards-grid">${card(`<div class="card-pad">${cardTitle('Aparência & atualização')}<div class="setting-row"><div class="setting-copy"><strong>Tema escuro</strong><small>O tema é salvo somente neste navegador.</small></div><button class="toggle ${state.theme==='dark'?'on':''}" data-theme-switch aria-label="Alternar tema" aria-pressed="${state.theme==='dark'}"><span></span></button></div><div class="setting-row"><div class="setting-copy"><strong>Animações suaves</strong><small>Transições leves. A preferência de movimento reduzido do sistema também é respeitada.</small></div><button class="toggle ${state.motion?'on':''}" data-motion aria-label="Alternar animações" aria-pressed="${state.motion}"><span></span></button></div><div class="setting-row"><div class="setting-copy"><strong>Atualização da tela</strong><small>Consulta a cada 30 s; coleta do servidor a cada 60 s.</small></div><button class="btn" data-pause>${state.paused?'Retomar':'Pausar'}</button></div></div>`,'span-6')}${card(`<div class="card-pad">${cardTitle('Inventário observado')}${row('Modelo',s.device.model)}${row('Arquitetura',s.device.architecture)}${row('Android',s.device.os)}${row('Firmware',s.device.firmware)}${row('Kernel',s.details?.inventory?.kernelRelease)}${row('Python',s.details?.inventory?.pythonVersion)}${row('Dados',d.dataLocation)}${row('Leituras disponíveis',availableEntries().length)}${row('Retenção','Sem expiração automática')}</div>`,'span-6')}</div>`;}
function diagnostics(){const d=state.snapshot.diagnostics||{};return `<div class="cards-grid">${card(`<div class="card-pad">${cardTitle('Tempo da coleta','Duração medida no servidor')}${row('Amostragem do hardware',d.samplingMs,'ms')}${row('Gravação anterior do hardware',d.historyWriteMs,'ms')}${row('Leitura indexada do SQLite',d.sqliteReadMs,'ms')}${row('Coleta do router',d.routerCollectionMs,'ms')}</div>`,'span-6')}${d.apiSamples>0?card(`<div class="card-pad">${cardTitle('Resposta das APIs','Últimas '+num(d.apiSamples)+' requisições · sem trânsito pela rede')}${row('Tempo médio',d.apiMeanMs,'ms')}${row('Percentil 95',d.apiP95Ms,'ms')}${(d.slowRoutes||[]).map(r=>row(r.path,r.ms,'ms')).join('')}</div>`,'span-6'):''}</div>`;}
const pageFunctions={overview:renderOverview,performance:renderPerformance,network:renderNetwork,storage:renderStorage,battery:renderBattery,services:renderServices,activity:renderActivity,settings:renderSettings};
function detailedErrorBanner(){const d=state.snapshot.diagnostics||{};return d.historyError?'<div class="callout warning" role="alert"><strong>Falha ao gravar o histórico no cartão: '+esc(d.historyError)+'</strong></div>':d.lowStorage?.length?'<div class="callout warning" role="alert">Pouco espaço disponível: '+esc(d.lowStorage.join(', '))+'.</div>':'';}
// Reconcile existing nodes on the same screen instead of destroying controls and SVGs.
// A detached template is only used to calculate the next structure. Expanded details,
// focused controls and chart elements keep their identity unless their type changes.
function patchNode(oldNode,newNode){
 if(oldNode.isEqualNode?.(newNode))return;
 if(oldNode.nodeType!==newNode.nodeType||oldNode.nodeName!==newNode.nodeName){oldNode.replaceWith(newNode.cloneNode(true));return;}
 if(oldNode.nodeType===3||oldNode.nodeType===8){if(oldNode.nodeValue!==newNode.nodeValue)oldNode.nodeValue=newNode.nodeValue;return;}
 if(oldNode.nodeType!==1)return;
 const keepOpen=oldNode.tagName==='DETAILS'&&oldNode.open;
 for(const attr of Array.from(oldNode.attributes)){
   if(keepOpen&&attr.name==='open')continue;
   if(!newNode.hasAttribute(attr.name))oldNode.removeAttribute(attr.name);
 }
 for(const attr of Array.from(newNode.attributes)){
   if(attr.name==='open'&&oldNode.tagName==='DETAILS')continue;
   if(oldNode.getAttribute(attr.name)!==attr.value)oldNode.setAttribute(attr.name,attr.value);
 }
 if(oldNode.matches?.('.source-body')&&oldNode.closest('details')?.open&&!newNode.innerHTML)return;
 if(oldNode.matches?.('input,textarea,select')&&oldNode===document.activeElement){
   // Never overwrite live keyboard input when polling.
   return;
 }
 const before=Array.from(oldNode.childNodes),after=Array.from(newNode.childNodes);
 for(let i=0;i<after.length;i++){
   if(before[i])patchNode(before[i],after[i]);
   else oldNode.appendChild(after[i].cloneNode(true));
 }
 for(let i=after.length;i<before.length;i++)before[i].remove();
}
function updateMain(main,html,entering){
 if(entering||!document.createElement){main.innerHTML=html;return;}
 const template=document.createElement('template');template.innerHTML=html;
 const from=Array.from(main.childNodes),to=Array.from(template.content.childNodes);
 for(let i=0;i<to.length;i++){if(from[i])patchNode(from[i],to[i]);else main.appendChild(to[i].cloneNode(true));}
 for(let i=to.length;i<from.length;i++)from[i].remove();
}
function updateChrome(){
 const connected=state.mode==='real',demo=state.mode==='demo';
 const label=demo?'DEMONSTRAÇÃO':connected?'API LOCAL':state.snapshot.timestamp?'LEITURA ANTIGA':'SEM CONEXÃO';
 const note=demo?'Dados fictícios selecionados explicitamente.':connected?`Coleta no celular · ${dateTime(state.snapshot.timestamp)}`:state.snapshot.timestamp?`Última leitura: ${dateTime(state.snapshot.timestamp)}. Dados abaixo estão desatualizados.`:'Aguardando a primeira medição real. Sensores indisponíveis permanecem sem dados.';
 $('#mode-chip').className='mode-chip '+(connected?'real':'demo');
 $('#mode-chip').innerHTML=`<span></span> ${label}`;
 $('#sidebar-status').textContent=label;$('#sidebar-status-note').textContent=note;
 $('#footer-update').textContent=state.snapshot.timestamp?`Amostra: ${dateTime(state.snapshot.timestamp)}`:'Sem amostra';
 $('#breadcrumb-current').textContent=nav.find(n=>n[0]===state.page)?.[1]||'Visão geral';
 const bar=$('#main-content').querySelector?.('.freshness-bar');
 if(bar){
   bar.classList.toggle('is-stale',!connected);
   const strong=bar.querySelector('strong'),timestamp=bar.querySelector('span:nth-of-type(2)');
   if(strong)strong.textContent=connected?'Conectado ao S7':label;
   if(timestamp)timestamp.textContent=state.snapshot.timestamp?'Amostra de '+prettyTime(state.snapshot.timestamp):'Conectando ao servidor…';
 }
 for(const refresh of Array.from($('#main-content').querySelectorAll?.('[data-refresh]')||[])){
   refresh.disabled=state.fetching;
   refresh.setAttribute('aria-busy',String(state.fetching));
 }
}
function render(){
 const main=$('#main-content'),entering=state.lastPage!==state.page;
 const oldSelections=new Map();
 for(const entry of chartRegistry.values())if(entry.selectedIndex!=null)
   oldSelections.set((state.lastPage||state.page)+':'+lastRenderedRange+':'+entry.metric+':'+(entry.secondaryName||''),entry.selectedIndex);
 previousChartSelection=oldSelections;
 const focused=document.activeElement,selection=focused?.id==='metric-search'?[focused.selectionStart,focused.selectionEnd]:null;
 const opened=Array.from(main.querySelectorAll?.('details[open][data-source],details.source-section[open]')||[]).map(el=>el.dataset.source||'section');
 state.lastPage=state.page;lastRenderedRange=state.range;document.body.dataset.motion=state.motion?'on':'off';
 main.classList?.remove('page-enter');chartRegistry.clear();chartID=0;
 if(entering)setNav();
 const connected=state.mode==='real',demo=state.mode==='demo';
 const label=demo?'DEMONSTRAÇÃO':connected?'API LOCAL':state.snapshot.timestamp?'LEITURA ANTIGA':'SEM CONEXÃO';
 const html=`<div class="freshness-bar ${connected?'':'is-stale'}" role="status"><span class="freshness-dot"></span><strong>${connected?'Conectado ao S7':label}</strong><span>${state.snapshot.timestamp?'Amostra de '+esc(prettyTime(state.snapshot.timestamp)):'Conectando ao servidor…'}</span><button type="button" class="link-button" data-refresh ${state.fetching?'disabled aria-busy="true"':'aria-busy="false"'}>Atualizar ${ic('refresh')}</button></div>${detailedErrorBanner()}`+pageFunctions[state.page]();
 updateMain(main,html,entering);
 if(entering&&state.motion&&!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches)main.classList?.add('page-enter');
 if(entering)for(const el of Array.from(main.querySelectorAll?.('details[data-source],details.source-section')||[]))if(opened.includes(el.dataset.source||'section'))el.open=true;
 if(!entering&&selection&&focused?.isConnected&&focused.setSelectionRange)focused.setSelectionRange(...selection);
 // Expanded sensor bodies were generated lazily; keep the disclosure open and
 // update only its own reading instead of deleting it during DOM reconciliation.
 for(const details of Array.from(main.querySelectorAll?.('details[data-source][open]')||[])){
   const body=details.querySelector('.source-body');
   if(body&&!body.contains(document.activeElement)){
     const fresh=sourceDetail(details.dataset.source);
     if(body.innerHTML!==fresh)body.innerHTML=fresh;
   }
 }
 updateChrome();
 for(const [id,entry] of chartRegistry)if(entry.selectedIndex!=null){
   const holder=main.querySelector?.('[data-chart="'+id+'"]');
   if(holder)inspectChart(holder,undefined,undefined,entry.selectedIndex);
 }
}
function route(key){
 if(!pageFunctions[key])return;
 if(state.page!==key){state.page=key;}
 state.search='';state.filter='all';state.explorerLimit=48;
 $('#sidebar').classList.remove('open');$('#sidebar-scrim').classList.remove('visible');
 cancelUnusedHistory();
 const pending=state.mode!=='demo'?loadHistory():null;
 render();if(pending)pending.catch(()=>{});
 window.scrollTo?.({top:0,behavior:state.motion&&!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'smooth':'auto'});
 $('#main-content').focus({preventScroll:true});
}
async function fetchJson(url,timeout=4000,externalSignal){
 const controller=new AbortController();
 const relay=()=>controller.abort();
 if(externalSignal){if(externalSignal.aborted)controller.abort();else externalSignal.addEventListener('abort',relay,{once:true});}
 const timer=setTimeout(()=>controller.abort(),timeout);
 try{const r=await fetch(url,{signal:controller.signal,cache:'no-store',credentials:'same-origin'});
   if(!r.ok)throw Error('HTTP '+r.status);return await r.json();
 }finally{clearTimeout(timer);externalSignal?.removeEventListener('abort',relay);}
}
function validSnapshot(s){return !!(s&&s.timestamp&&Number.isFinite(Date.parse(s.timestamp))&&s.device&&s.cpu&&Array.isArray(s.cpu.coresPercent)&&s.memory&&s.battery&&s.network&&Array.isArray(s.storage)&&Array.isArray(s.services)&&Array.isArray(s.events));}
async function checkAPI(showMessage=false){
 if(state.fetching||state.paused||document.hidden)return;
 if(state.pref==='demo'){
   if(!Demo){if(showMessage)toast('Dados de demonstração indisponíveis.');return;}
   cancelAllHistory();state.mode='demo';state.snapshot=Demo.demoSnapshot(state.tick);state.history={};state.historyTimes={};state.historyStatus={};render();return;
 }
 state.fetching=true;updateChrome();
 try{
   const result=await fetchJson('/api/host/snapshot',8000);
   if(!validSnapshot(result))throw Error('Aguardando amostra');
   if(!state.snapshot.timestamp)state.lastPage=null;
   const nextMode=result.quality==='stale'||Date.now()-Date.parse(result.timestamp)>180000||Date.parse(result.timestamp)-Date.now()>5000?'offline':'real';
   const snapshotChanged=JSON.stringify(state.snapshot)!==JSON.stringify(result)||state.mode!==nextMode;
   state.snapshot=result;state.mode=nextMode;
   if(snapshotChanged)render();else updateChrome();
   await loadHistory();
   if(showMessage)toast('Leitura recebida da API local.');
 }catch(err){
   if(state.mode==='demo'){state.snapshot=emptySnapshot();state.history={};state.historyStatus={};}
   const changed=state.mode!=='offline';state.mode='offline';
   if(changed)render();else updateChrome();
   if(showMessage)toast('API indisponível; nenhuma simulação ativada.');
 }finally{state.fetching=false;updateChrome();}
}
function cancelAllHistory(){
 for(const [,flight] of historyFlights)flight.controller.abort();
 historyFlights.clear();
 for(const [key,meta] of Object.entries(state.historyStatus))if(meta.phase==='loading'){
   if(Array.isArray(state.history[key]))state.historyStatus[key]={phase:'stale'};
   else delete state.historyStatus[key];
 }
}
function requestHistory(metric,range,{force=false}={}){
 const key=metric+':'+range,time=Date.now();
 if(historyFlights.has(key))return historyFlights.get(key).promise;
 if(!force&&time-(state.historyTimes[key]||0)<HISTORY_TTL_MS)return Promise.resolve(false);
 const controller=new AbortController();
 state.historyStatus[key]={phase:'loading',startedAt:time};
 const request=(async()=>{
   try{
     const result=await fetchJson('/api/host/history?metric='+encodeURIComponent(metric)+'&range='+encodeURIComponent(range),15000,controller.signal);
     if(controller.signal.aborted)return false;
     if(!Array.isArray(result)||!result.every(p=>(p.value===null||typeof p.value==='number'&&Number.isFinite(p.value))&&Number.isFinite(new Date(p.time).getTime())))throw Error('Série inválida');
     const series=result.map(p=>({time:new Date(p.time).getTime(),value:p.value}));
     cacheHistory(key,series);
     state.historyStatus[key]={phase:series.length?'success':'empty',updatedAt:Date.now()};
     if(currentHistoryKeys().has(key)){historyAnnouncement('Histórico de '+metric+' em '+range+' atualizado.');scheduleRender();}
     return true;
   }catch(err){
     if(controller.signal.aborted)return false;
     state.historyStatus[key]={phase:Array.isArray(state.history[key])?'stale':'error',error:String(err.message||err),updatedAt:Date.now()};
     if(currentHistoryKeys().has(key)){historyAnnouncement('Falha ao atualizar histórico de '+metric+' em '+range+'.');scheduleRender();}
     return false;
   }finally{if(historyFlights.get(key)?.controller===controller)historyFlights.delete(key);}
 })();
 historyFlights.set(key,{promise:request,controller});
 return request;
}
async function loadHistory(opts={}){
 if(state.mode==='demo'||state.paused||document.hidden)return false;
 const metrics=requiredHistory[state.page]||[],range=state.range;
 if(!metrics.length)return false;
 const jobs=metrics.map(metric=>requestHistory(metric,range,opts));
 return Promise.all(jobs);
}
function csvEscape(v){return '"'+String(v??'').replace(/"/g,'""')+'"'}
function saveBlob(filename,mime,data){const blob=new Blob([data],{type:mime}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500)}
function exportData(type){const snap=state.snapshot,name=`s7-${type}-${new Date().toISOString().slice(0,10)}`;if(type==='events'){const lines=[['tipo','titulo','detalhe','minutos_relativos'].map(csvEscape).join(',')].concat((snap.events||[]).map(e=>[e.type,e.title,e.detail,e.at].map(csvEscape).join(',')));saveBlob(name+'.csv','text/csv;charset=utf-8','\ufeff'+lines.join('\n'));return}const payload={NOTICE:state.mode==='demo'?'DADOS FICTÍCIOS. NÃO SÃO MEDIÇÕES DO APARELHO.':state.mode==='offline'?'API indisponível; última amostra ou campos sem dados.':'Dados fornecidos pela API local.',source:state.mode,exportedAt:new Date().toISOString(),type,data:type==='snapshot'?snap:type==='network'?snap.network:type==='storage'?snap.storage:snap.services};saveBlob(name+'.json','application/json;charset=utf-8',JSON.stringify(payload,null,2));toast('Exportação gerada no navegador.')}
function copyString(str){navigator.clipboard?.writeText(str).then(()=>toast('Comando copiado.')).catch(()=>toast('Cópia automática indisponível neste navegador.'))}
$('#main-content').addEventListener('click',async e=>{
 const t=e.target.closest('button');if(!t)return;
 if(t.dataset.nav)route(t.dataset.nav);
 else if(t.dataset.range){if(state.range===t.dataset.range)return;state.range=t.dataset.range;saveSetting('range',state.range);cancelUnusedHistory();const pending=loadHistory();render();await pending}
 else if('retryHistory' in t.dataset){const metrics=t.dataset.retryHistory.split(',').filter(metric=>(requiredHistory[state.page]||[]).includes(metric));if(!metrics.length)return;const pending=Promise.all(metrics.map(metric=>requestHistory(metric,state.range,{force:true})));render();await pending}
  else if('refresh' in t.dataset)await checkAPI(true);
 else if(t.dataset.export)exportData(t.dataset.export);
 else if('motion' in t.dataset){state.motion=!state.motion;saveSetting('motion',state.motion?'on':'off');render()}
 else if('clearSearch' in t.dataset){state.search='';state.filter='all';state.explorerLimit=48;render()}
  else if('explorerMore' in t.dataset){state.explorerLimit+=48;$('#explorer-results').innerHTML=explorerResults()}
 else if(t.dataset.filter){state.filter=t.dataset.filter;state.explorerLimit=48;render()}
 else if('pause' in t.dataset){state.paused=!state.paused;if(state.paused)cancelAllHistory();else{const pending=loadHistory();pending.catch(()=>{});}render();toast(state.paused?'Atualização visual pausada.':'Atualização visual retomada.')}
 else if('themeSwitch' in t.dataset){setTheme(state.theme==='dark'?'light':'dark');render()}
 else if('copyCommand' in t.dataset)copyString('cd ~/s7-server/app/dashboard\npython -m http.server 9090 --bind 0.0.0.0');
});
$('#main-content').addEventListener('toggle',e=>{const el=e.target;if(el.matches?.('details[data-source]')&&el.open){const body=el.querySelector('.source-body');if(body&&!body.innerHTML)body.innerHTML=sourceDetail(el.dataset.source);}},true);
$('#main-content').addEventListener('change',e=>{if(e.target.id==='metric-group'){state.filter=e.target.value;state.explorerLimit=48;$('#explorer-results').innerHTML=explorerResults();return;}if(e.target.id==='source-select'){state.pref=e.target.value;saveSetting('source',state.pref);checkAPI(true)}});
$('#main-content').addEventListener('input',e=>{if(e.target.id==='metric-search'){state.search=e.target.value;state.explorerLimit=48;$('#explorer-results').innerHTML=explorerResults()}});
function inspectChart(el,clientX,clientY,requestedIndex){const r=chartRegistry.get(el.dataset.chart);if(!r)return;const rect=el.getBoundingClientRect();let idx=requestedIndex;if(idx==null){const fraction=cap(((clientX-rect.left)/rect.width-r.x0/700)/(r.w/700),0,1),target=r.values[0].time+fraction*(r.values.at(-1).time-r.values[0].time);idx=0;for(let i=1;i<r.values.length;i++)if(Math.abs(r.values[i].time-target)<Math.abs(r.values[idx].time-target))idx=i;}idx=cap(idx,0,r.values.length-1);r.selectedIndex=idx;const data=r.values[idx],tip=$('#tooltip'),cross=el.querySelector('.plot-crosshair');if(!data||data.value==null){tip.hidden=true;cross?.setAttribute('visibility','hidden');return;}const x=r.x0+(data.time-r.values[0].time)/Math.max(1,r.values.at(-1).time-r.values[0].time)*r.w,y=r.y0+r.h-(cap(data.value,r.min,r.max)-r.min)/(r.max-r.min)*r.h;if(cross){cross.setAttribute('visibility','visible');const line=cross.querySelector('line'),circle=cross.querySelector('circle');line.setAttribute('x1',x);line.setAttribute('x2',x);circle.setAttribute('cx',x);circle.setAttribute('cy',y);}const labels={cpu:'CPU',memory:'RAM',rx:'Recebido',tx:'Enviado',temp:'Bateria',battery:'Carga',storage:'Ocupação'};let secondary='';if(r.secondaryValues?.length){let point=r.secondaryValues.reduce((a,b)=>Math.abs(b.time-data.time)<Math.abs(a.time-data.time)?b:a);if(point.value!=null&&Math.abs(point.time-data.time)<180000)secondary='<strong>'+esc(labels[r.secondaryName]||r.secondaryName)+': '+num(point.value,2)+' '+r.unit+'</strong>';}tip.hidden=false;tip.innerHTML='<strong>'+esc(labels[r.metric]||r.metric)+': '+num(data.value,2)+' '+r.unit+'</strong>'+secondary+'<small>'+dateTime(data.time)+'</small>';tip.style.left=cap((clientX??rect.left+rect.width/2)+15,8,window.innerWidth-185)+'px';tip.style.top=Math.max(10,(clientY??rect.top+70)-80)+'px';}
$('#main-content').addEventListener('pointermove',e=>{const el=e.target.closest('[data-chart]');if(el)inspectChart(el,e.clientX,e.clientY)});
$('#main-content').addEventListener('click',e=>{const el=e.target.closest('[data-chart]');if(el)inspectChart(el,e.clientX,e.clientY)});
$('#main-content').addEventListener('keydown',e=>{const el=e.target.closest('[data-chart]');if(!el||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const r=chartRegistry.get(el.dataset.chart);if(!r)return;const idx=e.key==='Home'?0:e.key==='End'?r.values.length-1:(r.selectedIndex??r.values.length-1)+(e.key==='ArrowLeft'?-1:1);inspectChart(el,undefined,undefined,idx);});
$('#main-content').addEventListener('pointerout',e=>{const old=e.target.closest('[data-chart]');if(old&&!old.contains(e.relatedTarget)){const c=old.querySelector('.plot-crosshair');if(c)c.setAttribute('visibility','hidden');$('#tooltip').hidden=true}});
$('#theme-toggle').addEventListener('click',()=>{setTheme(state.theme==='dark'?'light':'dark');render()});
$('#avatar-button').addEventListener('click',()=>route('settings'));
$('#menu-toggle').addEventListener('click',()=>{$('#sidebar').classList.add('open');$('#sidebar-scrim').classList.add('visible')});
$('#sidebar-scrim').addEventListener('click',()=>{$('#sidebar').classList.remove('open');$('#sidebar-scrim').classList.remove('visible')});
$('#main-nav').addEventListener('click',e=>{const b=e.target.closest('[data-nav]');if(b)route(b.dataset.nav)});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('#sidebar').classList.remove('open');$('#sidebar-scrim').classList.remove('visible');$('#tooltip').hidden=true}if(e.ctrlKey&&e.key==='1'){e.preventDefault();route('overview')}});
function updateClock(){$('#clock-label').textContent=prettyTime(new Date())}
setTheme(state.theme);render();updateClock();setInterval(()=>{if(!document.hidden)updateClock()},1000);
setInterval(()=>{if(state.paused||state.mode!=='demo')return;state.tick++;state.snapshot=Demo.demoSnapshot(state.tick);if(document.activeElement?.id==='event-search')return;render()},4000);
setInterval(()=>{if(state.paused||state.pref==='demo'||document.hidden)return;checkAPI(false)},30000);
document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelAllHistory();else if(!state.paused)checkAPI(false)});
checkAPI(false);
})();
