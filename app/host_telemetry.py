"""Read-only host telemetry. Cached sampling, separate lossless SQLite history."""
from .host_sources import cpu_ids, kernel_release
from . import request_timing
import copy
import secrets
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from collections import deque
from contextlib import closing

RANGES = {'1h':3600,'6h':21600,'12h':43200,'24h':86400,'7d':604800,'30d':2592000,'1a':31536000}
METRICS = {'cpu':('cpu','usagePercent'),'memory':None,'rx':('network','rxMbps'),'tx':('network','txMbps'),
           'battery':('battery','levelPercent'),'temp':('battery','temperatureC'),'latency':('network','latencyMs'),'storage':None}

def read(path):
    try:return Path(path).read_text().strip()
    except (OSError,UnicodeError):return None

def number(value, scale=1):
    try:return float(value)/scale
    except (ValueError,TypeError):return None

def empty_snapshot():
    return {'timestamp':None,'device':{'name':platform.node(),'model':None,'soc':None,'cores':len(cpu_ids()),'architecture':platform.machine(),'os':platform.system(),'firmware':None,'uptimeSec':None},
      'cpu':{'usagePercent':None,'frequencyMHz':None,'coresPercent':[],'temperatureC':None},
      'memory':dict.fromkeys(('totalMB','usedMB','cachedMB','swapMB')),
      'battery':dict.fromkeys(('levelPercent','status','temperatureC','voltageMV','currentMA','health','plugged')),
      'network':dict.fromkeys(('interface','ip','ssid','signalDbm','linkMbps','rxMbps','txMbps','latencyMs','packetLossPercent','connected')),
      'storage':[],'services':[],'events':[],'diagnostics':{},'availability':{},'source':'termux-host-readonly','quality':'starting'}

class HostMonitor:
    def __init__(self, db_path, port=8767, interval=60):
        self.main_db=Path(db_path);self.path=self.main_db.parent/'host-telemetry.db'
        self.port=port;self.interval=max(60,interval);self.lock=threading.Lock();self.snapshot_data=empty_snapshot()
        self.stop_event=threading.Event();self.thread=None;self.previous_cpu={};self.previous_net=None;self.previous_process=None
        self.api=deque(maxlen=128);self.collection_ms=None;self.started=time.monotonic();self.last_error=None
        self.identity=None;self.history_error=None;self.projection_error=None
        self.agent_nonce=secrets.token_hex(16)
        self.history_cache={};self.history_lock=threading.Lock()
        self.history_key_locks={};self.history_slots=threading.BoundedSemaphore(2)
        self.history_generation=0
    def start(self):
        if self.thread is None:
            self.thread=threading.Thread(target=self.loop,name='host-telemetry',daemon=True);self.thread.start()
        return self
    def stop(self):self.stop_event.set()
    def record_api(self,path,duration):
        if not path.startswith('/api/') or path.startswith('/api/host/'):return
        with self.lock:self.api.append((path,round(duration,2)))
    def record_collection(self,duration):
        with self.lock:self.collection_ms=round(duration,2)
    def loop(self):
        while not self.stop_event.is_set():
            try:self.sample()
            except Exception as exc:
                self.last_error=type(exc).__name__
            self.stop_event.wait(self.interval)
    def snapshot(self):
        with self.lock:s=copy.deepcopy(self.snapshot_data)
        if s['timestamp']:
            age=max(0,time.time()-datetime.fromisoformat(s['timestamp']).timestamp())
            s['ageSeconds']=round(age,1);s['quality']='stale' if age>self.interval*2.5 else 'ok'
        s['diagnostics']['lastError']=self.last_error
        s['diagnostics']['historyError']=self.history_error
        s['diagnostics']['chartProjectionError']=self.projection_error
        return s
    def cpu(self):
        current={}
        for line in (read('/proc/stat') or '').splitlines():
            parts=line.split()
            if parts and (parts[0]=='cpu' or parts[0][3:].isdigit()):
                values=list(map(int,parts[1:]));current[parts[0]]=(sum(values[:8]),sum(values[3:5]))
        usage={}
        for key,(total,idle) in current.items():
            old=self.previous_cpu.get(key)
            usage[key]=round(100*(1-(idle-old[1])/(total-old[0])),2) if old and total>old[0] else None
        self.previous_cpu=current
        return usage.get('cpu'),[usage[k] for k in sorted(current,key=lambda k:int(k[3:]) if k!='cpu' else -1) if k!='cpu']
    def agent_cpu(self):
        """Read bounded numeric samples from the local ADB-started agent; no commands."""
        request=self.main_db.parent/'adb-agent.request'
        result={'status':'unavailable','ageSeconds':None,'windowSec':None}
        try:
            if read(request)!=self.agent_nonce:
                tmp=request.with_suffix('.tmp')
                tmp.write_text(self.agent_nonce+'\n',encoding='ascii');tmp.replace(request)
            path=self.main_db.parent/'adb-cpu.snapshot'
            if not path.is_file():return result
            if path.stat().st_size>16384:raise ValueError('oversize')
            lines=path.read_text(encoding='ascii').splitlines()
            if lines[0].split()!=['S7CPU1',self.agent_nonce]:
                result['status']='waiting-new-session';return result
            frames={};section=None;times={};extra={'vmstat':{},'disk':{},'stat':{}}
            for line in lines[1:]:
                fields=line.split()
                if not fields:continue
                if fields[0] in ('before','after'):
                    section=fields[0];times[section]=float(fields[1]);frames[section]={}
                elif fields[0] in ('vmstat','stat'):
                    if len(fields)!=3 or not fields[1].replace('_','').isalnum():raise ValueError('invalid key')
                    value=int(fields[2])
                    if not 0<=value<=2**63-1:raise ValueError('invalid extra counter')
                    extra[fields[0]][fields[1]]=value
                elif fields[0]=='disk':
                    if fields[1] not in ('mmcblk0','mmcblk1','sda'):raise ValueError('invalid disk')
                    values=[int(v) for v in fields[2:]]
                    if not 11<=len(values)<=20 or any(v<0 or v>2**63-1 for v in values):raise ValueError('invalid disk counters')
                    extra['disk'][fields[1]]=values
                elif fields[0]=='loadavg':
                    import math
                    values=[float(v) for v in fields[1:]]
                    if len(values)!=3 or any(not math.isfinite(v) or v<0 for v in values):raise ValueError('invalid load')
                    extra['loadavg']=values
                elif section and (fields[0]=='cpu' or fields[0].startswith('cpu') and fields[0][3:].isdigit()):
                    values=[int(v) for v in fields[1:]]
                    if len(values)!=8 or any(v<0 or v>2**63-1 for v in values):raise ValueError('invalid counters')
                    frames[section][fields[0]]=values
            now=time.clock_gettime(time.CLOCK_BOOTTIME)
            age=now-times['after'];window=times['after']-times['before']
            result.update(ageSeconds=round(age,1),windowSec=round(window,2))
            if age< -2 or age>150 or not .5<=window<=10:
                result['status']='stale';return result
            usage={}
            for name,new in frames['after'].items():
                old=frames['before'].get(name)
                if old is None:continue
                delta=sum(new)-sum(old);idle=sum(new[3:5])-sum(old[3:5])
                usage[name]=round(100*(delta-idle)/delta,2) if delta>0 and 0<=idle<=delta else None
            if usage.get('cpu') is None:raise ValueError('missing aggregate')
            result.update(status='ok',usagePercent=usage['cpu'],coresPercent=[usage.get('cpu'+str(i)) for i in range(max(cpu_ids(),default=-1)+1)],rawFrames=frames,bootTimes=times,extraCounters=extra)
        except (OSError,ValueError,KeyError,IndexError,AttributeError,UnicodeError):
            result['status']='unavailable'
        return result
    @staticmethod
    def boot_uptime():
        try:return time.clock_gettime(time.CLOCK_BOOTTIME)
        except (AttributeError,OSError):return None
    def battery(self):
        base=Path('/sys/class/power_supply/battery')
        b={'levelPercent':number(read(base/'capacity')),'temperatureC':number(read(base/'temp'),10),
           'voltageMV':number(read(base/'voltage_now'),1000),'currentMA':None,
           'status':read(base/'status'),'health':read(base/'health'),'plugged':None}
        for kind in ('usb','ac','wireless'):
            if read(base.parent/kind/'online')=='1':b['plugged']=kind.upper()
        # Optional official helper only; a timeout never blocks HTTP requests.
        if b['levelPercent'] is None and shutil.which('termux-battery-status'):
            try:
                p=subprocess.run(['termux-battery-status'],capture_output=True,text=True,timeout=3,check=False)
                d=json.loads(p.stdout)
                b.update(levelPercent=number(d.get('percentage')),temperatureC=number(d.get('temperature')),
                         voltageMV=number(d.get('voltage')),status=d.get('status'),health=d.get('health'),plugged=d.get('plugged'))
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
        return b
    def network(self):
        n=empty_snapshot()['network'];raw=read('/proc/net/dev');now=time.monotonic()
        if raw:
            rows={a.strip():b.split() for line in raw.splitlines() if ':' in line for a,b in [line.split(':',1)]}
            interface='wlan0' if 'wlan0' in rows else next((i for i in rows if i!='lo'),None)
            if interface:
                n['interface']=interface;v=rows[interface];rx,tx=int(v[0]),int(v[8])
                old=self.previous_net
                if old and old[0]==interface and now>old[3] and rx>=old[1] and tx>=old[2]:
                    n['rxMbps']=round((rx-old[1])*8/(now-old[3])/1e6,4);n['txMbps']=round((tx-old[2])*8/(now-old[3])/1e6,4)
                self.previous_net=(interface,rx,tx,now)
                state=read('/sys/class/net/'+interface+'/operstate');n['connected']=True if state=='up' else False if state=='down' else None
        if platform.system()=='Linux':
            try:
                import fcntl,struct
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                    name=(n['interface'] or 'wlan0').encode()[:15]
                    n['ip']=socket.inet_ntoa(fcntl.ioctl(sock.fileno(),0x8915,struct.pack('256s',name))[20:24])
            except (OSError,ImportError):pass
        return n
    def sample(self):
        began=time.perf_counter();s=empty_snapshot();s['timestamp']=datetime.now(timezone.utc).isoformat()
        if self.identity is None:
            self.identity=s['device']
            if shutil.which('getprop'):
                for field,prop in [('model','ro.product.model'),('os','ro.build.version.release'),('firmware','ro.build.display.id')]:
                    try:self.identity[field]=subprocess.check_output(['getprop',prop],text=True,timeout=2).strip() or None
                    except (OSError,subprocess.SubprocessError):pass
                if self.identity['model']=='SM-G935F':self.identity.update(name='Samsung Galaxy S7 Edge',soc='Exynos 8890 (inventário do modelo)')
        s['device']=dict(self.identity);s['device']['uptimeSec']=self.boot_uptime()
        s['cpu']['usagePercent'],s['cpu']['coresPercent']=self.cpu()
        agent=self.agent_cpu()
        if agent['status']=='ok':
            s['cpu']['usagePercent']=agent['usagePercent'];s['cpu']['coresPercent']=agent['coresPercent']
        frequencies=[number(read(p),1000) for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq')]
        frequencies=[v for v in frequencies if v is not None]
        s['cpu']['frequencyMHz']=round(sum(frequencies)/len(frequencies)) if frequencies else None
        mem={}
        for line in (read('/proc/meminfo') or '').splitlines():
            k,_,v=line.partition(':');mem[k]=number(v.strip().split(' ')[0],1024)
        total=mem.get('MemTotal');available=mem.get('MemAvailable')
        s['memory']={'totalMB':total,'usedMB':total-available if total is not None and available is not None else None,
                     'cachedMB':mem.get('Cached'),'swapMB':mem.get('SwapTotal')}
        s['battery']=self.battery();s['network']=self.network()
        home=Path.home();sd=home/'storage/external-1'
        for ident,label,path in [('internal','Armazenamento interno',home),('sd','Cartão microSD',sd)]:
            try:
                st=os.statvfs(path);s['storage'].append({'id':ident,'label':label,'mount':str(path.resolve()),
                    'totalGB':st.f_blocks*st.f_frsize/1024**3,'usedGB':(st.f_blocks-st.f_bfree)*st.f_frsize/1024**3,
                    'freeBytes':st.f_bfree*st.f_frsize,'availableBytes':st.f_bavail*st.f_frsize,
                    'blockSizeBytes':st.f_frsize,'inodesTotal':st.f_files,'inodesFree':st.f_ffree})
            except (OSError,AttributeError):pass
        # Only the current application process, never enumerate Android applications.
        proc={k:number(v.strip().split(' ')[0],1024) for line in (read('/proc/self/status') or '').splitlines() if ':' in line for k,v in [line.split(':',1)] if k in ('VmRSS','VmHWM')}
        now=time.monotonic();cpu_time=time.process_time();old=self.previous_process
        process_cpu=round((cpu_time-old[0])/(now-old[1])*100,2) if old and now>old[1] else None
        self.previous_process=(cpu_time,now)
        size=lambda p:p.stat().st_size if p.exists() else 0
        query_ms=None
        try:
            t=time.perf_counter()
            with closing(sqlite3.connect(self.main_db.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                db.execute('SELECT MAX(id) FROM huawei_samples').fetchone()
            query_ms=round((time.perf_counter()-t)*1000,2)
        except sqlite3.Error:pass
        with self.lock:api=list(self.api);collection=self.collection_ms
        api_values=sorted(v for _,v in api)
        s['diagnostics']={'pid':os.getpid(),'processRssMB':proc.get('VmRSS'),'processCpuPercent':process_cpu,
            'processCpuSemantics':'100% = um núcleo ocupado','processUptimeSec':round(now-self.started),'databaseMB':size(self.main_db)/1024**2,
            'walMB':size(Path(str(self.main_db)+'-wal'))/1024**2,'sqliteReadMs':query_ms,'routerCollectionMs':collection,
            'apiMeanMs':round(sum(api_values)/len(api_values),2) if api_values else None,
            'apiP95Ms':api_values[min(len(api_values)-1,int(len(api_values)*.95))] if api_values else None,
            'apiSamples':len(api),'apiWindow':'últimas 128 requisições API, sem /api/host',
            'slowRoutes':[{'path':k,'ms':v} for k,v in sorted(api,key=lambda p:p[1],reverse=True)[:5]],
            'dataLocation':str(self.main_db.parent),'pendingSamples':sum(1 for _ in (self.main_db.parent/'outbox').glob('*.json')),
            'agentStatus':agent['status'],'agentAgeSeconds':agent['ageSeconds'],'cpuWindowSec':agent['windowSec'],
            'samplingIntervalSec':self.interval,'historyRetentionDays':None,'bootAutostart':self.boot_status(),'supervisor':'runit' if os.environ.get('SVDIR') or (Path(os.environ.get('PREFIX','/nonexistent'))/'var/service/l-monitor').exists() else 'Não detectado'}
        s['services']=[{'id':'collector','name':'Monitor e coletor Huawei','description':'Processo que fornece esta medição','port':self.port,'status':'running','managedBy':s['diagnostics']['supervisor']}]
        s['availability']={k:{'available':any(isinstance(v,(int,float)) and not isinstance(v,bool) for v in s[k].values()),'source':source,'note':note} for k,source,note in [
            ('cpu','/proc/stat e cpufreq','Percentuais exigem duas amostras; temperatura da CPU não validada.'),
            ('memory','/proc/meminfo','Uso = total menos MemAvailable; swap mostra capacidade, não uso.'),
            ('battery','sysfs power_supply ou Termux:API','Temperatura da bateria, distinta da CPU. Campos bloqueados ficam null.'),
            ('network','/proc/net/dev, sysfs e ioctl local','Taxas médias do próprio host entre amostras; sem sondas novas. SSID/sinal não coletados.') ]}
        s['availability']['cpu']['source']='Agente local ADB: /proc/stat' if agent['status']=='ok' else '/proc/stat do Termux; agente ADB sem amostra válida'
        s['availability']['cpu']['note']='Amostra de aproximadamente 1 segundo a cada minuto; núcleos ausentes ficam sem dados. Reativar agente por USB após reboot.'
        from .host_sources import collect
        s['details']=collect();s['details']['measuredAt']=s['timestamp']
        s['details']['inventory']={'kernelRelease':kernel_release(),'architecture':platform.machine(),'pythonVersion':platform.python_version()}
        s['details']['hostDatabase']={'bytes':size(self.path),'walBytes':size(Path(str(self.path)+'-wal'))}
        s['diagnostics']['lowStorage']=[v['id'] for v in s['storage'] if v.get('availableBytes',0)<1024**3]
        s['diagnostics']['storagePolicy']='No automatic deletion; failed writes reported in historyError.'
        if agent['status']=='ok':
            for name,key,unit in [('memory.vmstat','vmstat','kernel counters'),('cpu.loadavg','loadavg','runnable tasks'),('disk.counters','disk','sectors and counts')]:
                value=agent.get('extraCounters',{}).get(key)
                if value:
                    previous=s['details']['metrics'][name]
                    s['details']['metrics'][name]={**previous,'value':value,'status':'ok','source':'adb-shell:'+previous['source'],'measuredAtBootSec':agent.get('bootTimes',{}).get('after')}
        
        s['details']['cpuAgent']={k:v for k,v in agent.items() if k not in ('usagePercent','coresPercent')}
        s['details']['agentMeasuredAtBootSec']=agent.get('bootTimes',{}).get('after')
        s['quality']='ok';s['diagnostics']['samplingMs']=round((time.perf_counter()-began)*1000,2)
        try:
            s['diagnostics']['historyWriteMs']=getattr(self,'previous_write_ms',None)
            s['diagnostics']['historyWriteTiming']='previous completed transaction'
            t=time.perf_counter();self.persist(s);self.previous_write_ms=round((time.perf_counter()-t)*1000,2);self.history_error=None
        except (OSError,sqlite3.Error) as exc:self.history_error=type(exc).__name__;s['diagnostics']['historyWriteMs']=None
        with self.lock:self.snapshot_data=s
        self.last_error=None
        return s
    def boot_status(self):
        # Configuration is not proof of a physical reboot test.
        if not (Path.home()/'.termux/boot/10-s7-start').is_file():return 'Não configurado'
        try:
            marker=self.main_db.parent/'boot-validation.json'
            if marker.stat().st_size<=4096:
                validation=json.loads(marker.read_text())
                if validation.get('physicalRebootVerified') is True and validation.get('validatedAt'):
                    return 'Verificado após reboot em '+str(validation['validatedAt'])[:32]
        except (OSError,ValueError,TypeError):pass
        return 'Configurado; teste de reboot pendente'
    def persist(self,s):
        # Parent must already exist on the configured volume. No internal fallback.
        if not self.path.parent.is_dir():raise OSError('Configured volume unavailable')
        with closing(sqlite3.connect(self.path,timeout=5)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('CREATE TABLE IF NOT EXISTS host_samples(ts REAL PRIMARY KEY,payload TEXT NOT NULL)')
            from .read_models import init_host, project_host, safe_project
            init_host(db)
            # Cursor stays strictly increasing even if wall-clock is corrected backwards.
            import math
            last=db.execute('SELECT MAX(ts) FROM host_samples').fetchone()[0]
            stamp=time.time()
            if last is not None and stamp<=last:stamp=math.nextafter(last,math.inf)
            db.execute('INSERT INTO host_samples VALUES (?,?)',(stamp,json.dumps(s,allow_nan=False)))
            self.projection_error=safe_project(db,project_host,stamp)
            # Unlimited retention: chart aggregation never replaces original records.
            db.execute('PRAGMA user_version=2')
        # Only ephemeral aggregation is invalidated, never the original SD archive.
        with self.history_lock:
            self.history_generation+=1
            self.history_cache.clear()
    def archive(self,after=0,limit=100):
        import math
        try:after=float(after);limit=int(limit)
        except (TypeError,ValueError):raise ValueError('Cursor ou limite inválido')
        if not math.isfinite(after) or after<0 or not 1<=limit<=500:raise ValueError('Cursor ou limite inválido')
        if not self.path.is_file():return {'records':[],'nextAfter':None,'hasMore':False}
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2,factory=request_timing.Connection)) as db:
            rows=db.execute('SELECT ts,payload FROM host_samples WHERE ts>? ORDER BY ts LIMIT ?',(after,limit+1)).fetchall()
        page=rows[:limit]
        return {'records':[{'cursor':ts,'sample':json.loads(payload)} for ts,payload in page],
                'nextAfter':page[-1][0] if page else None,'hasMore':len(rows)>limit,'retention':'unlimited','schemaVersion':2}
    def catalog(self):
        s=self.snapshot();details=s.get('details',{})
        return {'schemaVersion':2,'measuredAt':details.get('measuredAt'),'samplingIntervalSec':self.interval,
                'retention':'unlimited','sources':{k:{a:b for a,b in v.items() if a!='value'} for k,v in details.get('metrics',{}).items()},
                'cpuAgent':{k:v for k,v in details.get('cpuAgent',{}).items() if k not in ('rawFrames','bootTimes','extraCounters')},
                'notes':['Raw counters preserved in archive; charts are aggregated views.',
                         'Current monitor process only; no application inventory, personal files, logs, GPS or credentials.',
                         'Denied, absent and invalid readings remain null. No root or permission bypass.']}
    def history(self,metric,range_name):
        if metric not in METRICS or range_name not in RANGES:raise ValueError('Métrica ou intervalo inválido')
        key=(metric,range_name)
        with self.history_lock:
            cached=self.history_cache.get(key)
            if cached and cached[1]==self.history_generation and time.monotonic()-cached[0]<60:
                return copy.deepcopy(cached[2])
            per_key=self.history_key_locks.setdefault(range_name,threading.Lock())
        # Identical requests share one calculation; unrelated metrics do not share the same lock.
        with request_timing.acquire(per_key):
            with self.history_lock:
                cached=self.history_cache.get(key)
                if cached and cached[1]==self.history_generation and time.monotonic()-cached[0]<60:
                    return copy.deepcopy(cached[2])
                generation=self.history_generation
            # Protect SD I/O with at most two distinct concurrent read queries.
            with request_timing.acquire(self.history_slots):
                result=self.query_history(metric,range_name)
            with self.history_lock:
                if generation==self.history_generation:
                    if len(self.history_cache)>=56:
                        oldest=min(self.history_cache,key=lambda k:self.history_cache[k][0])
                        del self.history_cache[oldest]
                    self.history_cache[key]=(time.monotonic(),generation,result)
            return copy.deepcopy(result)
    def query_history(self,metric,range_name):
        if metric not in METRICS or range_name not in RANGES:raise ValueError('Métrica ou intervalo inválido')
        if not self.path.is_file():return []
        seconds=RANGES[range_name];bucket=max(60,seconds//360)
        # Scan the large raw JSON archive once for all chart metrics in a range.
        # Concurrent cpu/memory/rx/tx readers share the range lock and these results.
        names=list(METRICS)
        from .read_models import query_host
        with self.history_lock:generation=self.history_generation
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2,factory=request_timing.Connection)) as db:
            rows=query_host(db,time.time()-seconds,bucket)
        result={name:[] for name in names}
        for row in rows:
            stamp=datetime.fromtimestamp(row[0],timezone.utc).isoformat()
            for index,name in enumerate(names):result[name].append({'time':stamp,'value':row[index+1]})
        with self.history_lock:
            if generation==self.history_generation:
                for name in names:
                    self.history_cache[(name,range_name)]=(time.monotonic(),generation,result[name])
                while len(self.history_cache)>56:
                    oldest=min(self.history_cache,key=lambda k:self.history_cache[k][0])
                    del self.history_cache[oldest]
        return copy.deepcopy(result[metric])

_monitor=None
_monitor_lock=threading.Lock()
def start(db_path,port):
    global _monitor
    with _monitor_lock:
        if _monitor is None:_monitor=HostMonitor(db_path,port).start()
    return _monitor
def record_api(path,ms):
    if _monitor:_monitor.record_api(path,ms)
def record_collection(ms):
    if _monitor:_monitor.record_collection(ms)
