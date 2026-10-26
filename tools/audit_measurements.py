"""Read-only display/math audit. Does not certify physical sensors or start a collector."""
import argparse,json,math,os,shutil,sys,urllib.request,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def audit(host,status,overview,inventory):
    checks=[]
    def check(name,condition,available=True):
        checks.append({'name':name,'status':'unknown' if not available else 'pass' if condition else 'fail'})
    def numeric(value):return type(value) in (int,float) and math.isfinite(value)
    def bounded(name,value,low,high):check(name,numeric(value) and low<=value<=high,value is not None)
    cpu=host.get('cpu',{});memory=host.get('memory',{});battery=host.get('battery',{});network=host.get('network',{})
    bounded('host.cpu.percent',cpu.get('usagePercent'),0,100)
    check('host.cpu.cores',all(v is None or numeric(v) and 0<=v<=100 for v in cpu.get('coresPercent',[])),bool(cpu.get('coresPercent')))
    for key in ('levelPercent',):bounded('host.battery.'+key,battery.get(key),0,100)
    for key in ('rxMbps','txMbps'):bounded('host.network.'+key,network.get(key),0,float('inf'))
    total,used,available=(memory.get(k) for k in ('totalMB','usedMB','availableMB'))
    check('host.memory.used_plus_available_equals_total',numeric(total) and numeric(used) and numeric(available) and abs(total-used-available)<1e-6,all(v is not None for v in (total,used,available)))
    raw=host.get('details',{}).get('metrics',{}).get('memory.meminfo',{}).get('value') or {}
    check('host.memory.total_kib_to_mib',numeric(total) and abs(total-raw.get('MemTotal',0)/1024)<1e-6,total is not None and 'MemTotal' in raw)
    for key in ('usedMB','cachedMB','swapMB','swapUsedMB'):bounded('host.memory.'+key,memory.get(key),0,float('inf'))
    for index,volume in enumerate(host.get('storage',[])):
        name='host.storage.'+str(index);cap=volume.get('totalGB',0)*2**30;used=volume.get('usedGB',0)*2**30
        free=volume.get('freeBytes');available=volume.get('availableBytes')
        check(name+'.bytes_consistent',numeric(free) and numeric(available) and cap>0 and 0<=available<=free<=cap and abs(cap-used-free)<=volume.get('blockSizeBytes',4096),free is not None and available is not None)
    d=host.get('diagnostics',{})
    for key in ('apiMeanMs','apiP95Ms','samplingMs','sqliteReadMs','processCpuPercent','processRssMB'):bounded('host.diagnostics.'+key,d.get(key),0,float('inf'))
    check('host.internal_reserve_alert',all(v.get('id')!='internal' or (v.get('availableBytes',0)<2**31)==('internal' in d.get('lowStorage',[])) for v in host.get('storage',[])),bool(host.get('storage')))
    metrics=status.get('huawei',{}).get('metrics',{})
    for key in ('cpu_pct','memory_pct'):bounded('router.'+key,metrics.get(key),0,100)
    probe=status.get('probe') or {}
    for key in ('router_ms','internet_ms'):bounded('router.tcp.'+key,probe.get(key),0,float('inf'))
    q=overview.get('quality',{});span=q.get('window_seconds');covered=q.get('covered_seconds')
    check('router.coverage.time_formula',numeric(span) and span>0 and numeric(covered) and abs(q.get('coverage_percent',-1)-covered/span*100)<1e-6,span is not None)
    check('router.coverage.explicit_semantics',q.get('coverage_semantics')=='time_with_stored_observation_no_older_than_180_seconds')
    check('router.wan.no_unvalidated_speed',overview.get('measurement_semantics',{}).get('wan_rate_available') is False)
    clients=inventory.get('clients')
    check('router.inventory.contract',isinstance(clients,list))
    details=host.get('details',{}).get('metrics',{})
    # Every exposed raw family must retain availability and provenance; no payloads are recorded.
    for family in ('cpu','memory','network','battery','power','disk','zram','process','gpu','devfreq','thermal','pressure'):
        entries=[v for k,v in details.items() if k.split('.')[0]==family]
        check('host.sources.'+family,all(v.get('source') and v.get('unit') and v.get('status') in ('ok','unavailable','denied','absent','invalid','io-error') and (v.get('status')=='ok' or v.get('value') is None) for v in entries),bool(entries))
    return {'checks':checks,'summary':{s:sum(c['status']==s for c in checks) for s in ('pass','fail','unknown')},
            'limits':['Validates formulas, units, availability and contracts; not calibration or physical truth.',
                      'WAN width, reset and multiple wraps remain unvalidated; no Mbps/consumption invented.',
                      'CPU is a sampled window, process CPU 100% means one core; TCP is not ICMP.',
                      'Legacy API MB/GB field names represent MiB/GiB; original driver units remain explicit.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live-url',required=True);p.add_argument('--allow-live',action='store_true');p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    url=urllib.parse.urlsplit(args.live_url)
    if not args.allow_live or url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:p.error('Requires explicit authorized application origin and --allow-live')
    if args.output.exists() or not args.output.parent.is_dir():p.error('Use a new output in an existing directory')
    if os.environ.get('PREFIX','').startswith('/data/data/com.termux/') and (not str(args.output.resolve()).startswith('/storage/') or shutil.disk_usage('/data/data/com.termux/files/home').free<2**31):p.error('Reports on microSD only; preserve 2 GiB internal')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        with opener.open(args.live_url.rstrip('/')+path,timeout=20) as response:
            body=response.read(4*1024**2+1)
            if len(body)>4*1024**2:raise ValueError('bounded response exceeded')
            return json.loads(body)
    report=audit(get('/api/host/snapshot'),get('/api/status'),get('/api/v1/overview?period=24h&view=summary'),get('/api/router/clients'))
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report['summary']))
    return int(report['summary']['fail']>0)
if __name__=='__main__':raise SystemExit(main())
