"""Bounded, allowlisted kernel telemetry. No application or personal-data inventory."""
import math
import os
from pathlib import Path

VERSION = 2

def kernel_release():
    # Python on Android maps platform.release() to the Android OS version.
    try:return os.uname().release
    except (AttributeError,OSError):return None

def cpu_ids():
    # cpu_count() on Android may track online cores; sysfs retains offline cores.
    try:
        ids=sorted(int(p.name[3:]) for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*') if p.name[3:].isdigit() and int(p.name[3:])<64)
    except OSError:ids=[]
    return ids or list(range(min(os.cpu_count() or 0,64)))

def collect():
    metrics = {}
    def source(key, path, unit, parser=float, semantics=None):
        item = {'source':str(path),'unit':unit,'value':None,'status':'unavailable'}
        if semantics:item['semantics']=semantics
        try:
            with open(path, encoding='ascii') as f:
                text=f.read(65537)
            if len(text)>65536:raise ValueError('oversize')
            value=parser(text.strip())
            def finite(v):
                if isinstance(v,float) and not math.isfinite(v):raise ValueError('nonfinite')
                if isinstance(v,dict):
                    for x in v.values():finite(x)
                if isinstance(v,list):
                    for x in v:finite(x)
            finite(value);item.update(value=value,status='ok')
        except PermissionError:item['status']='denied'
        except FileNotFoundError:item['status']='absent'
        except (ValueError,IndexError,UnicodeError):item['status']='invalid'
        except OSError:item['status']='io-error'
        metrics[key]=item
        return item['value']
    def pairs(text):
        return {k:int(v.strip().split()[0]) for line in text.splitlines() if ':' in line for k,v in [line.split(':',1)]}
    source('memory.meminfo','/proc/meminfo','KiB',pairs,'Kernel fields in KiB; HugePages counts, if present, remain counts.')
    source('memory.vmstat','/proc/vmstat','kernel counters',lambda t:{p[0]:int(p[1]) for line in t.splitlines() if len(p:=line.split())==2})
    source('cpu.loadavg','/proc/loadavg','runnable tasks',lambda t:[float(x) for x in t.split()[:3]],'Load averages over 1, 5 and 15 minutes; not CPU percent.')
    source('cpu.online','/sys/devices/system/cpu/online','CPU list',str)
    source('cpu.present','/sys/devices/system/cpu/present','CPU list',str)
    for i in cpu_ids():
        base=f'/sys/devices/system/cpu/cpu{i}'
        source(f'cpu.{i}.online',base+'/online','boolean',int)
        for name in ('scaling_cur_freq','scaling_min_freq','scaling_max_freq','cpuinfo_min_freq','cpuinfo_max_freq'):
            source(f'cpu.{i}.{name}',base+'/cpufreq/'+name,'kHz',int)
        source(f'cpu.{i}.governor',base+'/cpufreq/scaling_governor','name',str)
    for i in cpu_ids():
        base=f'/sys/devices/system/cpu/cpu{i}'
        source(f'cpu.{i}.timeInState',base+'/cpufreq/stats/time_in_state','kHz and kernel ticks',lambda t:{p[0]:int(p[1]) for line in t.splitlines() if len(p:=line.split())==2},'Cumulative residency; preserve native ticks without assuming a conversion.')
        source(f'cpu.{i}.frequencyTransitions',base+'/cpufreq/stats/total_trans','transitions',int)
        for state in range(2):
            for field,unit in [('time','microseconds'),('usage','entries'),('latency','microseconds')]:
                source(f'cpu.{i}.idle{state}.{field}',base+f'/cpuidle/state{state}/'+field,unit,int)
    for field in ('clock','utilization'):
        source('gpu.'+field,'/sys/devices/14ac0000.mali/'+field,'Samsung driver raw',int,'Native Mali driver value; unit and sampling window not validated. Zero can occur while idle.')
    for device in ('17000020.devfreq_int','17000030.devfreq_disp','17000010.devfreq_mif','17000040.devfreq_cam'):
        for field in ('cur_freq','min_freq','max_freq'):
            source('devfreq.'+device+'.'+field,'/sys/class/devfreq/'+device+'/'+field,'Samsung driver frequency raw',int,'Frequency scale is driver-specific; no unvalidated conversion to Hz.')
    for device in ('mmcblk0','mmcblk1'):
        source('disk.'+device+'.type','/sys/block/'+device+'/device/type','MMC or SD',str,'Kernel media type; no card identifiers collected.')
        for field in ('logical_block_size','physical_block_size'):
            source('disk.'+device+'.'+field,'/sys/block/'+device+'/queue/'+field,'bytes',int)
    for name,unit in [('capacity','%'),('temp','0.1 C'),('voltage_now','uV'),('current_now','driver raw'),('current_avg','driver raw'),('charge_counter','uAh'),('charge_full','uAh'),('charge_full_design','uAh'),('cycle_count','cycles'),('energy_now','uWh')]:
        source('battery.'+name,'/sys/class/power_supply/battery/'+name,unit,int,
               'Samsung current units/sign not validated; retain raw value.' if name.startswith('current') else None)
    for name in ('status','health','technology','present'):
        source('battery.'+name,'/sys/class/power_supply/battery/'+name,'reported',str)
    for kind in ('usb','ac','wireless'):
        source('power.'+kind,'/sys/class/power_supply/'+kind+'/online','boolean',int)
    for i in range(8):
        source(f'thermal.zone{i}','/sys/class/thermal/thermal_zone'+str(i)+'/temp','driver raw',int,'Unidentified thermal zone; never labelled CPU temperature.')
    for name,unit in [('disksize','bytes'),('mm_stat','kernel positional counters'),('stat','block counters'),('orig_data_size','bytes'),('compr_data_size','bytes'),('mem_used_total','bytes')]:
        source('zram.'+name,'/sys/block/zram0/'+name,unit,lambda t:[int(x) for x in t.split()])
    source('process.io','/proc/self/io','bytes and syscalls',pairs)
    def status(t):
        allowed={'VmPeak','VmSize','VmLck','VmPin','VmHWM','VmRSS','RssAnon','RssFile','RssShmem','VmData','VmStk','VmExe','VmLib','VmPTE','VmSwap','Threads','FDSize','voluntary_ctxt_switches','nonvoluntary_ctxt_switches'}
        return {k:int(v.strip().split()[0]) for line in t.splitlines() if ':' in line for k,v in [line.split(':',1)] if k in allowed}
    source('process.status','/proc/self/status','KiB or counts by field',status)
    fields=('rxBytes','rxPackets','rxErrors','rxDropped','rxFifo','rxFrame','rxCompressed','rxMulticast','txBytes','txPackets','txErrors','txDropped','txFifo','txCollisions','txCarrier','txCompressed')
    def interfaces(t):
        return {a.strip():dict(zip(fields,map(int,b.split()))) for line in t.splitlines() if ':' in line for a,b in [line.split(':',1)]}
    nets=source('network.interfaces','/proc/net/dev','bytes and cumulative counts',interfaces)
    if nets:
        for name in sorted(nets)[:16]:
            if not name.replace('_','').replace('-','').isalnum():continue
            for field,parser in [('operstate',str),('mtu',int),('carrier',int),('speed',int)]:
                source(f'network.{name}.{field}',f'/sys/class/net/{name}/{field}','Mbps' if field=='speed' else 'reported',parser)
    # Explicit capability checks: retain absence/denial, never infer a zero reading.
    source('disk.counters','/proc/diskstats','sectors and counts',lambda t:{p[2]:[int(x) for x in p[3:]] for line in t.splitlines() if len(p:=line.split())>=14 and p[2] in ('mmcblk0','mmcblk1','sda')})
    for kind in ('cpu','memory','io'):
        source('pressure.'+kind,'/proc/pressure/'+kind,'kernel PSI text',str)
    return {'schemaVersion':VERSION,'metrics':metrics,'scope':'host kernel and current monitor process; allowlisted sources only'}
