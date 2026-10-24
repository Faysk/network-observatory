"""Read-only historian views over the original, unlimited observation archive."""
import json
import math
import re
from collections import deque
from datetime import datetime, timezone, timedelta
from . import core

PERIODS={'1h':3600,'6h':21600,'12h':43200,'24h':86400,'7d':604800,'1m':2592000,'1y':31536000}
SOURCE='huawei-b7-http'

def window(period):
    if period not in PERIODS:raise ValueError('Invalid period')
    end=datetime.now(timezone.utc)
    return end-timedelta(seconds=PERIODS[period]),end

def stamp(value):return datetime.fromisoformat(value).timestamp()

def device_mac(identifier):
    if not re.fullmatch(r'[0-9a-f]{12}',identifier):raise ValueError('Invalid device identifier')
    return ':'.join(identifier[i:i+2] for i in range(0,12,2))

def sample(ts,payload):
    stations=payload.get('stations',[])
    # Multiple rows are observations, not separate clients; no aggregate traffic is attributed.
    station=stations[0] if stations else {}
    return {'timestamp':ts,'online':{'Online':True,'Offline':False}.get(payload.get('reported_status')),
            'rssi_dbm':station.get('rssi_dbm'),'snr_db':station.get('snr_db_reported'),
            'link_rx_phy_mbps':station.get('rx_link_mbps'),'link_tx_phy_mbps':station.get('tx_link_mbps'),
            'download_mbps':None,'upload_mbps':None,'latency_lan_ms':None,
            'interface':station.get('interface'),'ips':payload.get('ips',[]),
            'source':SOURCE,'quality':'reported','confidence':'reported',
            'measurement_semantics':'AP-reported RSSI and PHY; not Internet throughput'}

class Buckets:
    def __init__(self,start,end,keys):
        self.start=start.timestamp();self.end=end.timestamp();self.width=max(60,math.ceil((self.end-self.start)/360))
        self.keys=keys;self.buckets={};self.stats={k:{'count':0,'sum':0,'min':None,'max':None} for k in keys};self.count=0
    def add(self,point):
        ts=stamp(point['timestamp']);index=int((ts-self.start)//self.width)
        bucket=self.buckets.setdefault(index,{'timestamp':point['timestamp'],'timestamp_end':point['timestamp'],'sample_count':0,'values':{},'last_time':None,'max_gap_seconds':0})
        if bucket['last_time'] is not None:bucket['max_gap_seconds']=max(bucket['max_gap_seconds'],ts-bucket['last_time'])
        bucket['last_time']=ts;bucket['timestamp_end']=point['timestamp'];bucket['sample_count']+=1;self.count+=1
        for key in self.keys:
            value=point.get(key)
            if type(value) not in (int,float) or not math.isfinite(value):continue
            for target in (self.stats,bucket['values']):
                item=target.setdefault(key,{'count':0,'sum':0,'min':None,'max':None})
                item['count']+=1;item['sum']+=value
                item['min']=value if item['min'] is None else min(item['min'],value)
                item['max']=value if item['max'] is None else max(item['max'],value)
    def result(self):
        def finish(item):return {'sample_count':item['count'],'min':item['min'],'max':item['max'],'avg':item['sum']/item['count'] if item['count'] else None,'mean_semantics':'arithmetic_sample_mean','p95':None}
        points=[]
        for index,bucket in sorted(self.buckets.items()):
            values={k:finish(bucket['values'].get(k,{'count':0,'sum':0,'min':None,'max':None})) for k in self.keys}
            points.append({'timestamp':bucket['timestamp'],'timestamp_end':bucket['timestamp_end'],'sample_count':bucket['sample_count'],
                           'max_gap_seconds':bucket['max_gap_seconds'],'values':values,**{k:v['avg'] for k,v in values.items()}})
        return points,{k:finish(v) for k,v in self.stats.items()}

def device_history(identifier,period='24h'):
    mac=device_mac(identifier);start,end=window(period)
    keys=('rssi_dbm','snr_db','link_rx_phy_mbps','link_tx_phy_mbps','download_mbps','upload_mbps','latency_lan_ms','presence')
    buckets=Buckets(start,end,keys);online=0;known=0;segments=deque(maxlen=500);segment=None;previous=None;gap_count=0;latest=None
    identities=deque(maxlen=500);previous_identity=None;identity_count=0;segment_count=0;observed_duration=0
    def close_segment(item):
        nonlocal segment_count,observed_duration
        item['observed_duration_seconds']=max(0,stamp(item['last_observed_at'])-stamp(item['started_at']))
        observed_duration+=item['observed_duration_seconds'];segment_count+=1;segments.append(item)
    with core.connect() as db:
        identity=db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? ORDER BY ts DESC,id DESC LIMIT 1',(mac,)).fetchone()
        if identity is None:raise LookupError('Device not found')
        first=db.execute('SELECT MIN(ts) FROM router_client_samples WHERE mac=?',(mac,)).fetchone()[0]
        for row in db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? AND ts>=? AND ts<=? ORDER BY ts,id',(mac,start.isoformat(),end.isoformat())):
            payload=json.loads(row['payload']);point=sample(row['ts'],payload);latest=point
            identity_key=tuple(tuple(payload.get(k,[])) for k in ('names','ips','ports'))
            if identity_key!=previous_identity:
                identities.append({'collected_at':row['ts'],**{k:payload.get(k,[]) for k in ('names','ips','ports')}});identity_count+=1;previous_identity=identity_key
            point['presence']=100 if point['online'] is True else 0 if point['online'] is False else None
            buckets.add(point)
            if point['online'] is not None:known+=1
            if point['online'] is True:online+=1
            gap=previous is not None and stamp(row['ts'])-stamp(previous['timestamp'])>180
            if gap:gap_count+=1
            if segment and (gap or point['online'] is not True):
                segment['end_reason']='sample_gap' if gap else 'reported_state';close_segment(segment);segment=None
            if point['online'] is True:
                if segment is None:segment={'started_at':row['ts'],'last_observed_at':row['ts'],'confidence':'estimated_from_samples','source':SOURCE,'end_reason':'window_end'}
                segment['last_observed_at']=row['ts']
            previous=point
        if segment:close_segment(segment)
        events=[dict(r) for r in db.execute('SELECT * FROM events WHERE ts>=? AND ts<=? AND source=? AND instr(detail,?)>0 ORDER BY ts DESC LIMIT 1001',(start.isoformat(),end.isoformat(),SOURCE,mac))]
    points,stats=buckets.result();identity=json.loads(identity['payload'])|{'collected_at':identity['ts'],'first_seen':first,'id':identifier}
    age=end.timestamp()-stamp(identity['collected_at']);identity['quality']='ok' if -5<=age<=180 else 'stale'
    expected=math.ceil(PERIODS[period]/60)
    return {'device':identity,'period':{'key':period,'from':start.isoformat(),'to':end.isoformat(),'resolution_seconds':buckets.width},
            'source':SOURCE,'source_type':'router_gui_readonly','confidence':'reported','collected_at':latest['timestamp'] if latest else None,
            'sample_coverage':{'sample_count':buckets.count,'expected_count':expected,'coverage_percent':min(100,buckets.count/expected*100)},
            'measurement_semantics':{'presence':'estimated from reported states, not exact sessions','rssi_dbm':'AP-reported dBm','phy':'router RX/TX PHY in Mbit/s, not throughput','traffic':'unavailable'},
            'series':points,'stats':stats,'latest':latest,'sessions':list(segments),'session_count':segment_count,'sessions_truncated':segment_count>500,'identity_history':list(identities),'identity_history_truncated':identity_count>500,
            'presence':{'online_samples':online,'known_samples':known,'percent_of_known_samples':online/known*100 if known else None,
                        'observed_duration_seconds':observed_duration,'semantics':'estimated_contiguous_sample_spans_with_max_gap_180s; not exact association sessions'},
            'events':events[:1000],'events_truncated':len(events)>1000,
            'quality':{'sample_count':buckets.count,'expected_count':expected,'coverage_percent':min(100,buckets.count/expected*100),'sample_gaps':gap_count,'aggregation':'bucket_mean_with_min_max_envelope'},
            'capabilities':{'client_bytes':'unknown','client_traffic':'unsupported','client_rssi':'supported' if stats['rssi_dbm']['sample_count'] else 'unknown',
                            'phy_rate':'supported' if stats['link_rx_phy_mbps']['sample_count'] else 'unknown','client_probe':'not_configured','exact_sessions':'unsupported'}}

def overview_history(period='24h'):
    start,end=window(period)
    keys=('cpu_pct','memory_pct','optical_rx_dbm','optical_tx_dbm','wan_rx_bytes','wan_tx_bytes','online_clients','rssi_dbm')
    buckets=Buckets(start,end,keys);probes=Buckets(start,end,('router_ms','internet_ms','router_online','internet_online'))
    with core.connect() as db:
        for row in db.execute('SELECT ts,payload FROM huawei_samples WHERE ts>=? AND ts<=? ORDER BY ts,id',(start.isoformat(),end.isoformat())):
            payload=json.loads(row['payload']);p={'timestamp':row['ts'],**payload.get('metrics',{})}
            wan=next((k for k,v in payload.get('wan_states',{}).items() if 'Internet' in v.get('services',[])),None)
            counters=payload.get('interfaces',{}).get(wan,{})
            p.update(wan_rx_bytes=counters.get('rx_bytes'),wan_tx_bytes=counters.get('tx_bytes'))
            if 'clients' in payload:p['online_clients']=sum(c['reported_status']=='Online' for c in payload['clients'])
            values=[s['rssi_dbm'] for s in payload.get('stations',[]) if s.get('rssi_dbm') is not None]
            if values:p['rssi_dbm']=sum(values)/len(values)
            buckets.add(p)
        for row in db.execute('SELECT * FROM samples WHERE ts>=? AND ts<=? ORDER BY ts,id',(start.isoformat(),end.isoformat())):
            p=dict(row);p['timestamp']=p['ts'];probes.add(p)
        events=[dict(r) for r in db.execute('SELECT * FROM events WHERE ts>=? AND ts<=? ORDER BY ts DESC LIMIT 1001',(start.isoformat(),end.isoformat()))]
    points,stats=buckets.result();probe_points,probe_stats=probes.result()
    return {'period':{'key':period,'from':start.isoformat(),'to':end.isoformat(),'resolution_seconds':buckets.width},'series':points,'stats':stats,
            'probes':probe_points,'probe_stats':probe_stats,'events':events[:1000],'events_truncated':len(events)>1000,
            'source':SOURCE,'source_type':'router_gui_readonly','confidence':'reported','collected_at':points[-1]['timestamp_end'] if points else None,
            'sample_coverage':{'sample_count':buckets.count,'expected_count':math.ceil(PERIODS[period]/60),'coverage_percent':min(100,buckets.count/max(1,math.ceil(PERIODS[period]/60))*100)},
            'measurement_semantics':{'wan':'raw router counters; width/reset not validated; no throughput or consumption derived','wifi':'arithmetic RSSI mean of stations reported in each sample'},
            'quality':{'sample_count':buckets.count,'expected_count':math.ceil(PERIODS[period]/60),'coverage_percent':min(100,buckets.count/max(1,math.ceil(PERIODS[period]/60))*100),'aggregation':'bucket_mean_with_min_max_envelope'}}
