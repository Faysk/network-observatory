/* Observatório S7 — fonte determinística de dados fictícios.
   Nunca confundir valores DEMO com telemetria real do aparelho. */
(function(){
  'use strict';
  const clamp = (x,a,b)=>Math.max(a,Math.min(b,x));
  const round=(n,d=1)=>Number(n.toFixed(d));
  const phases={cpu:.8,memory:2.7,rx:1.4,tx:4.1,temp:2.1,battery:5.6,latency:0.2,storage:3.4};
  const ranges={"1h":{points:90,hours:1},"6h":{points:96,hours:6},"12h":{points:96,hours:12},"24h":{points:96,hours:24},"7d":{points:112,hours:168},"30d":{points:120,hours:720},"1a":{points:120,hours:8760}};
  function signal(i, key, count=90){
    const p=phases[key]||1;
    const t=i / Math.max(1,count-1);
    return Math.sin(t*19+p)*.52+Math.cos(t*44+p*1.3)*.26+Math.sin(t*91+p)*.12 + (Math.sin((i+1)*12.9898 + p*64)*.10);
  }
  function series(metric,range='1h'){
    const cfg=ranges[range]||ranges['1h']; const now=Date.now(); const span=cfg.hours*3600000;
    return Array.from({length:cfg.points},(_,i)=>{
      const n=signal(i,metric,cfg.points), c=signal(i+21,metric,cfg.points);
      let value;
      switch(metric){
        case 'cpu':value=clamp(27+n*19+Math.max(0,Math.sin(i*.59+1))*15,4,94);break;
        case 'memory':value=clamp(53+n*4+((i/cfg.points)*5),38,72);break;
        case 'rx':value=clamp(1.8+Math.max(0,n*4.0)+Math.max(0,c*1.8),.08,12.5);break;
        case 'tx':value=clamp(.8+Math.max(0,n*2.5)+Math.max(0,c*.6),.05,7.5);break;
        case 'temp':value=clamp(34.8+n*2.2+Math.max(0,c),30,41.4);break;
        case 'battery':value=clamp(74+Math.sin(i/(cfg.points-1)*4.1+1.2)*7+n*.65,55,90);break;
        case 'latency':value=clamp(13+n*6+Math.max(0,c)*10,2,58);break;
        case 'storage':value=clamp(72.4+i/cfg.points*.7+n*.1,70,75);break;
        default:value=clamp(45+n*15,0,100);
      }
      return {time:now-span+(i/(cfg.points-1))*span,value:round(value,2)};
    });
  }
  const snapshotBase={
    source:'demo',timestamp:new Date().toISOString(),
    device:{name:'Samsung Galaxy S7 Edge',model:'SM-G935F',soc:'Samsung Exynos 8890',cores:8,architecture:'ARM64',os:'Android 8.0 Oreo',firmware:'G935FXXS8ETK2',hostname:'s7-edge',uptimeSec:4*86400+16*3600+42*60},
    cpu:{usagePercent:27.4,frequencyMHz:1456,coresPercent:[34,29,22,38,12,10,18,15],temperatureC:null},
    memory:{totalMB:4096,usedMB:2154,cachedMB:622,swapMB:null},
    battery:{levelPercent:82,status:'Carregando',temperatureC:34.8,voltageMV:null,currentMA:null,health:'Não verificado',plugged:'USB'},
    network:{interface:'wlan0',ip:'192.0.2.10',ssid:'Example-WiFi',signalDbm:-54,linkMbps:null,rxMbps:2.46,txMbps:.68,latencyMs:12.6,packetLossPercent:0,connected:true},
    storage:[{id:'internal',label:'Armazenamento interno',mount:'/data',totalGB:25,usedGB:18.8},{id:'sd',label:'Cartão microSD',mount:'/storage/0000-0000',totalGB:59,usedGB:.019}],
    services:[{id:'ssh',name:'OpenSSH',description:'Acesso remoto via Windows Terminal',port:8022,status:'running',managedBy:'Termux'},{id:'web',name:'Interface HTTP',description:'Servidor web do painel (exemplo)',port:9090,status:'running',managedBy:'Termux'},{id:'collector',name:'Coletor de métricas',description:'Coleta periódica (exemplo)',port:null,status:'running',managedBy:'Python'},{id:'backup',name:'Rotina de backup',description:'Agendamento ainda não validado',port:null,status:'warning',managedBy:'Script'}],
    features:{cpuTotal:true,cpuPerCore:true,ram:true,battery:true,batteryTemp:true,cpuTemp:false,wifiSignal:true,rxTx:true,storage:true,allProcesses:false},
    events:[
      {id:1,at:-2,type:'info',title:'Amostra de telemetria registrada',detail:'CPU, memória, armazenamento e rede (dado fictício)'},
      {id:2,at:-14,type:'success',title:'Serviço SSH está respondendo',detail:'Porta 8022 · verificação simulada'},
      {id:3,at:-46,type:'info',title:'Sincronização de histórico',detail:'Amostra de referência adicionada à série temporal'},
      {id:4,at:-91,type:'warning',title:'Monitor de bateria',detail:'Estado de saúde ainda não verificado no aparelho'},
      {id:5,at:-180,type:'success',title:'Cartão microSD detectado',detail:'Armazenamento identificado: 0000-0000'},
      {id:6,at:-330,type:'info',title:'Sessão de terminal',detail:'Acesso SSH demonstrativo pelo Windows'},
      {id:7,at:-680,type:'info',title:'Sistema inicializado',detail:'Uptime meramente ilustrativo no modo demo'},
      {id:8,at:-1220,type:'warning',title:'Sensor de CPU indisponível',detail:'Temperatura de CPU sem root não foi comprovada'},
    ]
  };
  function demoSnapshot(tick=0){
    const s=JSON.parse(JSON.stringify(snapshotBase)),t=tick;
    s.timestamp=new Date().toISOString();
    s.cpu.usagePercent=round(clamp(28+Math.sin(t*.62)*8+Math.cos(t*.28)*4,5,94));
    s.cpu.coresPercent=s.cpu.coresPercent.map((n,i)=>round(clamp(n+Math.sin(t*.62+i*.75)*9,1,94)));
    s.cpu.frequencyMHz=Math.round(1350+Math.sin(t*.35)*180);
    s.memory.usedMB=Math.round(2154+Math.sin(t*.23)*68);
    s.network.rxMbps=round(clamp(2.5+Math.sin(t*.9)*1.2+Math.sin(t*.31)*.9,.05,8),2);
    s.network.txMbps=round(clamp(.72+Math.sin(t*.55+1)*.51,.04,3),2);
    s.network.latencyMs=round(clamp(12.6+Math.sin(t*.4)*4,2,29));
    s.battery.temperatureC=round(34.8+Math.sin(t*.18)*.7);
    s.device.uptimeSec+=t*3;
    return s;
  }
  window.S7DemoData={snapshotBase,series,demoSnapshot,ranges};
})();
