"""Read-only historian views over the original, unlimited observation archive."""
import json
import math
import re
import threading
import time
from collections import OrderedDict
from collections import deque
from datetime import datetime, timezone, timedelta
from . import request_timing
from .metric_math import observation_coverage
from . import core, read_models
from .wifi_links import band_rssi, station_links
from .query_cache import QueryCache

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
    links=payload.get('wifi_links')
    links=links if isinstance(links,list) and links else station_links(stations,{})
    return {'timestamp':ts,'online':{'Online':True,'Offline':False}.get(payload.get('reported_status')),
            'rssi_dbm':station.get('rssi_dbm'),'snr_db':station.get('snr_db_reported'),
            'link_rx_phy_mbps':station.get('rx_link_mbps'),'link_tx_phy_mbps':station.get('tx_link_mbps'),
            'download_mbps':None,'upload_mbps':None,'latency_lan_ms':None,
            'interface':station.get('interface'),'wifi_links':links,'ips':payload.get('ips',[]),
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

class CounterPreview:
    """Bounded original observations; never average a wrapping byte counter."""
    def __init__(self,start,end):
        self.start=start;self.end=end;self.width=max(60,math.ceil((end-start).total_seconds()/360))
        self.points={};self.previous={};self.previous_timestamp=None;self.epochs={'wan_rx_bytes':0,'wan_tx_bytes':0}
        self.totals={k:0 for k in self.epochs};self.pairs={k:0 for k in self.epochs};self.excluded={k:0 for k in self.epochs}
    def add(self,ts,values):
        point={'timestamp':ts,'timestamp_end':ts,'sample_count':1,'max_gap_seconds':0}
        elapsed=stamp(ts)-self.previous_timestamp if self.previous_timestamp is not None else None
        if elapsed is not None and elapsed>180:
            for key in self.epochs:self.epochs[key]+=1
        self.previous_timestamp=stamp(ts)
        for key in self.epochs:
            value=values.get(key);old=self.previous.get(key)
            valid=type(value) in (int,float) and math.isfinite(value) and value>=0
            if old is not None and (not valid or value<old):self.epochs[key]+=1
            if old is not None and valid and elapsed is not None and 0<elapsed<=180 and value>=old:
                self.totals[key]+=value-old;self.pairs[key]+=1
            elif elapsed is not None:self.excluded[key]+=1
            point[key.replace('_bytes','_observed_bytes')]=self.totals[key] if valid and self.pairs[key] else None
            point[key]=value if valid else None;self.previous[key]=value if valid else None
        point['counter_epochs']=dict(self.epochs)
        point['observed_epochs']={k.replace('_bytes','_observed_bytes'):v for k,v in self.epochs.items()}
        index=int((stamp(ts)-self.start.timestamp())//self.width);self.points[index]=point
    def result(self):
        return [p for _,p in sorted(self.points.items())],{'key':next((k for k,v in PERIODS.items() if v==int((self.end-self.start).total_seconds())),None),'from':self.start.isoformat(),'to':self.end.isoformat(),
            'resolution_seconds':self.width,'sampled_preview':self.width>180,
            'observed_increments':{k:{'bytes':self.totals[k] if self.pairs[k] else None,'valid_pairs':self.pairs[k],'excluded_transitions':self.excluded[k]} for k in self.epochs},
            'semantics':'original_last_observation_per_bucket; known_resets_break_lines; not_throughput'}

def _device_history_uncached(identifier,period='24h'):
    mac=device_mac(identifier);start,end=window(period)
    keys=('rssi_dbm','snr_db','link_rx_phy_mbps','link_tx_phy_mbps','download_mbps','upload_mbps','latency_lan_ms','presence')
    buckets=Buckets(start,end,keys);online=0;known=0;segments=deque(maxlen=500);segment=None;previous=None;gap_count=0;latest=None
    identities=deque(maxlen=500);previous_identity=None;identity_count=0;segment_count=0;observed_duration=0
    wifi_history=deque(maxlen=500);wifi_change_count=0;previous_wifi=None
    def close_segment(item):
        nonlocal segment_count,observed_duration
        item['observed_duration_seconds']=max(0,stamp(item['last_observed_at'])-stamp(item['started_at']))
        observed_duration+=item['observed_duration_seconds'];segment_count+=1;segments.append(item)
    with core.connect() as db:
        db.execute('BEGIN')
        coverage=observation_coverage(db,'router_client_samples',start,end,mac)
        identity=db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? ORDER BY ts DESC,id DESC LIMIT 1',(mac,)).fetchone()
        if identity is None:raise LookupError('Device not found')
        first=db.execute('SELECT MIN(ts) FROM router_client_samples WHERE mac=?',(mac,)).fetchone()[0]
        for row in read_models.device_rows(db,mac,start.isoformat(),end.isoformat()):
            payload=json.loads(row['payload']);point=sample(row['ts'],payload);latest=point
            if point['online'] is True and point['wifi_links']:
                association=tuple((v.get('interface'),v.get('band'),v.get('channel')) for v in point['wifi_links'])
                if association!=previous_wifi:
                    wifi_change_count+=1
                    wifi_history.append({'observed_at':row['ts'],'links':point['wifi_links'],
                                         'semantics':'observed_wifi_interface_not_exact_roam_time'})
                    previous_wifi=association
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
            'sample_coverage':coverage,
            'measurement_semantics':{'presence':'estimated from reported states, not exact sessions','rssi_dbm':'AP-reported dBm','phy':'router RX/TX PHY in Mbit/s, not throughput','traffic':'unavailable'},
            'series':points,'stats':stats,'latest':latest,'sessions':list(segments),'session_count':segment_count,'sessions_truncated':segment_count>500,'identity_history':list(identities),'identity_history_truncated':identity_count>500,
            'wifi_history':list(wifi_history),'wifi_history_truncated':wifi_change_count>500,
            'presence':{'online_samples':online,'known_samples':known,'percent_of_known_samples':online/known*100 if known else None,
                        'observed_duration_seconds':observed_duration,'semantics':'estimated_contiguous_sample_spans_with_max_gap_180s; not exact association sessions'},
            'events':events[:1000],'events_truncated':len(events)>1000,
            'quality':{**coverage,'sample_gaps':gap_count,'aggregation':'bucket_mean_with_min_max_envelope'},
            'capabilities':{'client_bytes':'unknown','client_traffic':'unsupported','client_rssi':'supported' if stats['rssi_dbm']['sample_count'] else 'unknown',
                            'phy_rate':'supported' if stats['link_rx_phy_mbps']['sample_count'] else 'unknown','client_probe':'not_configured','exact_sessions':'unsupported'}}

_device_cache = QueryCache()


def device_history(identifier,period='24h'):
    device_mac(identifier)
    if period not in PERIODS:raise ValueError('Invalid period')
    def revision():
        with core.connect() as db:return read_models.router_revision(db)
    key=(str(core.DB_PATH.resolve()),identifier,period)
    return _device_cache.get(key,revision(),lambda:_device_history_uncached(identifier,period),revision)


def _overview_history_uncached(period='24h'):
    start,end=window(period)
    keys=('cpu_pct','memory_pct','optical_rx_dbm','optical_tx_dbm','wan_rx_bytes','wan_tx_bytes','online_clients','rssi_dbm','rssi_24_dbm','rssi_5_dbm')
    counters=CounterPreview(start,end)
    buckets=Buckets(start,end,keys);probes=Buckets(start,end,('router_ms','internet_ms','router_online','internet_online'))
    with core.connect() as db:
        db.execute('BEGIN')
        coverage=observation_coverage(db,'huawei_samples',start,end)
        for ts,point in read_models.overview_rows(db,start.isoformat(),end.isoformat()):
            buckets.add({'timestamp':ts,**point});counters.add(ts,point)
        for row in db.execute('SELECT * FROM samples WHERE ts>=? AND ts<=? ORDER BY ts,id',(start.isoformat(),end.isoformat())):
            p=dict(row);p['timestamp']=p['ts'];probes.add(p)
        events=[dict(r) for r in db.execute('SELECT * FROM events WHERE ts>=? AND ts<=? ORDER BY ts DESC LIMIT 1001',(start.isoformat(),end.isoformat()))]
    counter_points,counter_period=counters.result()
    points,stats=buckets.result();probe_points,probe_stats=probes.result()
    return {'period':{'key':period,'from':start.isoformat(),'to':end.isoformat(),'resolution_seconds':buckets.width},'series':points,'stats':stats,'counter_series':counter_points,'counter_period':counter_period,
            'probes':probe_points,'probe_stats':probe_stats,'events':events[:1000],'events_truncated':len(events)>1000,
            'source':SOURCE,'source_type':'router_gui_readonly','confidence':'reported','collected_at':points[-1]['timestamp_end'] if points else None,
            'sample_coverage':coverage,
            'measurement_semantics':{'wan':'raw router counters; width/reset not validated; no throughput or consumption derived','wifi':'arithmetic RSSI mean of stations reported in each sample; per-band average requires matching station/radio interface'},
            'quality':{**coverage,'aggregation':'bucket_mean_with_min_max_envelope'}}


# Memory-only cache; all original observations remain on the configured SQLite volume.
# Never reuse an aggregate after an INSERT, including historical backfill.
_OVERVIEW_TTL=20
_OVERVIEW_MAX=12
_overview_cache=OrderedDict()
_overview_locks={}
_overview_mutex=threading.Lock()
_overview_slots=threading.BoundedSemaphore(2)

def _revision(db):
    return tuple(db.execute('SELECT COALESCE(MAX(id),0) FROM '+table).fetchone()[0]
                 for table in ('huawei_samples','samples','events'))

def overview_summary(period='24h'):
    """Cheap home summary: exact coverage counts + sampled *observations* for sparklines.

    Summary series are NOT aggregates or replacement for detailed histories.
    Every represented value is a real stored observation, not an interpolated mean.
    """
    start,end=window(period)
    start_iso,end_iso=start.isoformat(),end.isoformat()
    span=PERIODS[period]
    bucket=max(60,math.ceil(span/96))
    with core.connect() as db:
        db.execute('BEGIN')
        coverage=observation_coverage(db,'huawei_samples',start,end)
        counter_start=max(start,end-timedelta(hours=1));counters=CounterPreview(counter_start,end)
        for ts,point in read_models.overview_rows(db,counter_start.isoformat(),end_iso):counters.add(ts,point)
        counter_points,counter_period=counters.result()
        # Both coverage and underlying original records remain exact.
        count=coverage['sample_count']
        # At most one original reading per summary bucket, using ID index on the second pass.
        ids=[row[0] for row in db.execute(
            "SELECT MAX(id) FROM huawei_samples WHERE ts>=? AND ts<=? "
            "GROUP BY CAST((CAST(strftime('%s',ts) AS INTEGER)-?)/? AS INTEGER)",
            (start_iso,end_iso,int(start.timestamp()),bucket))]
        series=[]
        if ids:
            for row in db.execute('SELECT ts,payload FROM huawei_samples WHERE id IN ('+
                                  ','.join('?' for _ in ids)+') ORDER BY ts,id',ids):
                payload=json.loads(row['payload'])
                p={'timestamp':row['ts'],'timestamp_end':row['ts'],'sample_count':1,
                   'max_gap_seconds':0}
                p.update(payload.get('metrics',{}))
                wan=next((name for name,value in payload.get('wan_states',{}).items()
                          if 'Internet' in value.get('services',[])),None)
                counters=payload.get('interfaces',{}).get(wan,{})
                p['wan_rx_bytes']=counters.get('rx_bytes');p['wan_tx_bytes']=counters.get('tx_bytes')
                if 'clients' in payload:
                    p['online_clients']=sum(c.get('reported_status')=='Online' for c in payload['clients'])
                signals=[v['rssi_dbm'] for v in payload.get('stations',[]) if v.get('rssi_dbm') is not None]
                p['rssi_dbm']=sum(signals)/len(signals) if signals else None
                p.update(band_rssi(payload))
                series.append(p)
        probe_ids=[row[0] for row in db.execute(
            "SELECT MAX(id) FROM samples WHERE ts>=? AND ts<=? "
            "GROUP BY CAST((CAST(strftime('%s',ts) AS INTEGER)-?)/? AS INTEGER)",
            (start_iso,end_iso,int(start.timestamp()),bucket))]
        probes=[]
        if probe_ids:
            for r in db.execute('SELECT * FROM samples WHERE id IN ('+
                                ','.join('?' for _ in probe_ids)+') ORDER BY ts,id',probe_ids):
                p=dict(r);p['timestamp']=p['ts'];p['timestamp_end']=p['ts'];p['sample_count']=1
                p['max_gap_seconds']=0
                probes.append(p)
        events=[dict(r) for r in db.execute('SELECT * FROM events WHERE ts>=? AND ts<=? '
                                            'ORDER BY ts DESC LIMIT 3',(start_iso,end_iso))]
    expected=max(1,math.ceil(span/60))
    return {'period':{'key':period,'from':start_iso,'to':end_iso,'resolution_seconds':bucket},
            'series':series,'probes':probes,'events':events,'counter_series':counter_points,'counter_period':counter_period,
            'quality':{**coverage,
                       'aggregation':'original_observations_sampled_for_preview'},
            'summary':{'sampled':True,'max_buckets':96,'raw_samples_retained':True,
                       'series_semantics':'one original stored observation per bucket',
                       'events_limited_to':3},
            'measurement_semantics':{'wan':'raw counters; decreases are discontinuities, not throughput; width and multiple wraps unvalidated','wan_rate_available':False},
            'source':SOURCE,'collected_at':series[-1]['timestamp_end'] if series else None}

def overview_history(period='24h',view='full'):
    if view not in ('full','summary'):raise ValueError('Invalid overview view')
    if period not in PERIODS:raise ValueError('Invalid period')
    key=(str(core.DB_PATH.resolve()),period,view)
    with core.connect() as db:revision=_revision(db)
    now=time.monotonic()
    with _overview_mutex:
        cached=_overview_cache.get(key)
        if cached and cached[1]==revision and now-cached[0]<_OVERVIEW_TTL:
            _overview_cache.move_to_end(key)
            # Immutable result by convention; serialization doesn't modify nested values.
            return cached[2]
        # Repeated requests for the same key share a lock, not a recalculation.
        lock=_overview_locks.setdefault(key,threading.Lock())
    with request_timing.acquire(lock):
        with core.connect() as db:revision=_revision(db)
        now=time.monotonic()
        with _overview_mutex:
            cached=_overview_cache.get(key)
            if cached and cached[1]==revision and now-cached[0]<_OVERVIEW_TTL:
                _overview_cache.move_to_end(key)
                return cached[2]
        # At most two distinct cache misses can read the SQLite volume concurrently.
        with request_timing.acquire(_overview_slots):
            result=overview_summary(period) if view=='summary' else _overview_history_uncached(period)
        with core.connect() as db:end_revision=_revision(db)
        # If a collector wrote during this read, don't cache an inconsistent version.
        if end_revision==revision:
            with _overview_mutex:
                _overview_cache[key]=(time.monotonic(),revision,result)
                _overview_cache.move_to_end(key)
                while len(_overview_cache)>_OVERVIEW_MAX:_overview_cache.popitem(last=False)
        return result
