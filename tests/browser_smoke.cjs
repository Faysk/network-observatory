'use strict';
// Synthetic localhost-only HTTP and Chromium fixture. No real S7/router requests.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),os=require('node:os');
const {spawn}=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),staticRoot=path.join(root,'app/static');
const chrome=process.env.CHROME_PATH||['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(fs.existsSync);
if(!chrome)throw Error('Chromium/Chrome required for browser integration');
const stamp=new Date().toISOString(),now=Date.now();
const full=(period)=>({
 period:{key:period,from:new Date(now-86400000).toISOString(),to:stamp,resolution_seconds:600},
 series:[{timestamp:new Date(now-120000).toISOString(),timestamp_end:new Date(now-120000).toISOString(),sample_count:1,max_gap_seconds:0,cpu_pct:0,wan_rx_bytes:1000,wan_tx_bytes:0}],
 probes:[{timestamp:new Date(now-120000).toISOString(),timestamp_end:new Date(now-120000).toISOString(),sample_count:1,max_gap_seconds:0,router_ms:0,internet_ms:null}],
 stats:{cpu_pct:{min:0,max:0,avg:0,sample_count:1}},probe_stats:{router_ms:{min:0,max:0,avg:0,sample_count:1}},
 events:[],quality:{coverage_percent:1,sample_count:1,expected_count:1440}
});
const status={huawei:{quality:'ok',collected_at:stamp,source:'fixture',metrics:{cpu_pct:0},
 wan_states:{wan0:{services:['Internet']}},interfaces:{wan0:{rx_bytes:0,tx_bytes:0}}},
 probe:{ts:stamp,router_online:1,router_ms:0,internet_online:1,internet_ms:null},retention_days:0};
const counts={status:0,summary:0,full:{},inventory:0};
const types={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'};
const send=(res,obj,code=200,delay=0)=>setTimeout(()=>{if(res.destroyed)return;let body=JSON.stringify(obj);
 res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(body);},delay);
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1'),pathname=url.pathname;
 if(pathname==='/api/status'){counts.status++;send(res,status,200,25);return;}
 if(pathname==='/api/router/clients'){counts.inventory++;send(res,{clients:[]},200,80);return;}
 if(pathname==='/api/v1/overview'){
  const period=url.searchParams.get('period')||'24h';
  if(url.searchParams.get('view')==='summary'){
    counts.summary++;
    const obj=full(period);delete obj.stats;delete obj.probe_stats;obj.summary={sampled:true};
    send(res,counts.summary===1?{error:'Synthetic failure'}:obj,counts.summary===1?500:200,counts.summary===1?1100:50);return;
  }
  counts.full[period]=(counts.full[period]||0)+1;
  const broken=period==='1y'&&counts.full[period]===1;
  send(res,broken?{error:'Synthetic failure'}:full(period),broken?500:200,period==='24h'?1200:period==='7d'?1400:85);
  return;
 }
 let local;
 if(pathname==='/tests/browser_fixture.html')local=path.join(root,'tests/browser_fixture.html');
 else if(pathname==='/router/'||pathname==='/router')local=path.join(staticRoot,'index.html');
 else if(pathname.startsWith('/router/'))local=path.join(staticRoot,decodeURIComponent(pathname.slice('/router/'.length)));
 else local=path.join(staticRoot,decodeURIComponent(pathname.slice(1)));
 if(!local.startsWith(staticRoot+path.sep)&&!local.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
 if(!fs.existsSync(local)||!fs.statSync(local).isFile()){res.writeHead(404);res.end('Not found');return;}
 res.writeHead(200,{'Content-Type':types[path.extname(local)]||'application/octet-stream'});
 fs.createReadStream(local).pipe(res);
});
server.listen(0,'127.0.0.1',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'network-observatory-browser-'));
 const target='http://127.0.0.1:'+server.address().port+'/tests/browser_fixture.html';
 const args=['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run',
  '--user-data-dir='+dir,'--virtual-time-budget=24000','--dump-dom',target];
 const proc=spawn(chrome,args);let stdout='',stderr='';
 proc.stdout.on('data',x=>stdout+=x);proc.stderr.on('data',x=>stderr+=x);
 const kill=setTimeout(()=>proc.kill('SIGKILL'),45000);
 try{
  const code=await new Promise((resolve,reject)=>{proc.on('error',reject);proc.on('close',resolve);});
  const match=stdout.match(/<div id="smoke" data-status="([^"]+)">([^<]*)<\/div>/);
  console.log('Network browser',match?.[1],match?.[2],'requests',counts);
  assert.equal(code,0,'Chromium did not exit cleanly: '+stderr.slice(-300));
  assert.equal(match?.[1],'pass',match?.[2]||'Browser integration failed');
  assert.equal(counts.summary,2,'Summary should retry once, never reload whole page');
  assert.equal(counts.full['1y'],2,'Retry and cached repeat must make only two year requests');
 }catch(e){console.error(e);process.exitCode=1;}
 finally{clearTimeout(kill);server.close();fs.rmSync(dir,{recursive:true,force:true});}
});