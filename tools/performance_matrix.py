"""Individual functional + performance checks. Synthetic by default; no collectors.

Reports contain metrics only. Live mode requires explicit operator opt-in and
never starts a source, changes configuration or records response bodies.
"""
import gzip
import argparse
import concurrent.futures
import csv
import fnmatch
import hashlib
import io
import json
import math
import os
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.parse
from contextlib import ExitStack, closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import core, historian, host_telemetry
from app.host_telemetry import HostMonitor, empty_snapshot
from app.query_cache import QueryCache
from app.read_models import backfill_host, backfill_router
from app.server import Handler

SCHEMA = 1
MAC = '02:00:00:00:00:01'
EXPECTED = {'cpu': 0, 'memory': 25, 'rx': 0, 'tx': 2, 'battery': 80,
            'temp': 30, 'latency': None, 'storage': 0}


@dataclass
class Case:
    id: str
    transport: str
    invoke: object
    validate: object


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def series(value, expected='contract'):
    require(isinstance(value, list), 'Expected series array')
    require(len(value) <= 361, 'Series exceeds documented bucket bound')
    for point in value:
        require(isinstance(point, dict) and 'time' in point and 'value' in point, 'Invalid point contract')
        v = point['value']
        require(v is None or type(v) in (int, float) and math.isfinite(v), 'Invalid numeric value')
        if expected != 'contract':
            require(v == expected, 'Fixture value changed; zero/null must be preserved')


def bundle(value, device=False):
    require(isinstance(value, dict), 'Expected history object')
    require(isinstance(value.get('series'), list), 'Missing series')
    require(len(value['series']) <= 361, 'Unbounded chart series')
    require(isinstance(value.get('quality', {}).get('sample_count'), int), 'Missing coverage count')
    require('period' in value and 'from' in value['period'] and 'to' in value['period'], 'Missing window')
    if device:
        require(value.get('presence', {}).get('known_samples', -1) >= 0, 'Missing presence semantics')
        require(value.get('capabilities', {}).get('client_traffic') == 'unsupported', 'Invented traffic capability')


def snapshot(value, synthetic=False):
    require(isinstance(value, dict) and 'quality' in value and 'diagnostics' in value, 'Invalid host snapshot')
    require(value['quality'] in ('starting', 'ok', 'stale'), 'Unexpected host quality')
    if synthetic:
        require(value.get('cpu',{}).get('usagePercent')==0, 'Snapshot lost CPU zero')
        require(value.get('memory',{}).get('usedMB')==25, 'Snapshot changed memory value')
        require(value.get('network',{}).get('latencyMs') is None, 'Snapshot invented latency')


def catalog(value, synthetic=False):
    require(isinstance(value,dict) and value.get('schemaVersion')==2 and isinstance(value.get('sources'),dict), 'Invalid catalog provenance')
    if synthetic:
        require(value['sources'].get('fixture.cpu',{}).get('status')=='ok', 'Catalog lost fixture provenance')
        require('value' not in value['sources']['fixture.cpu'], 'Catalog exposed metric value')


def archive(value, synthetic=False):
    require(isinstance(value, dict) and isinstance(value.get('records'), list), 'Invalid archive page')
    require(len(value['records']) <= 10, 'Archive page exceeded requested limit')
    require('hasMore' in value and 'nextAfter' in value, 'Missing pagination contract')
    if synthetic:
        require(bool(value['records']), 'Archive lost original records')
        require(all('synthetic_padding' in r.get('sample',{}) for r in value['records']), 'Archive substituted compact data for raw snapshot')


def inventory(value, expected=None):
    require(isinstance(value, dict) and isinstance(value.get('clients'), list), 'Invalid inventory')
    for client in value['clients']:
        require(all(k in client for k in ('identity', 'classification', 'presentation')), 'Missing enrichment contract')
    if expected is not None:
        require(len(value['clients'])==expected, 'Inventory count changed')


def stats(samples):
    if not samples:
        return {'n': 0, 'median_ms': None, 'p95_ms': None}
    values = sorted(samples)
    return {'n': len(values), 'median_ms': round(statistics.median(values), 3),
            'min_ms': round(values[0], 3), 'max_ms': round(values[-1], 3),
            'stdev_ms': round(statistics.stdev(values), 3) if len(values) > 1 else 0,
            'p95_ms': round(values[math.ceil(.95*len(values))-1], 3) if len(values) >= 20 else None}


def error_description(exc):
    if isinstance(exc, AssertionError):
        return 'Contract: '+str(exc)  # validators use only constant, non-payload messages
    if isinstance(exc, urllib.error.HTTPError):
        return 'HTTP '+str(exc.code)
    return type(exc).__name__  # never include a live URL, payload or identifier


def measured(case):
    started = time.perf_counter()
    cpu = time.thread_time()
    value, wire_bytes, extra = case.invoke()
    received = time.perf_counter()
    if wire_bytes is None:
        wire_bytes = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
    serialized = time.perf_counter()
    case.validate(value)
    finished = time.perf_counter()
    return {'total_ms': (finished-started)*1000, 'query_or_http_ms': (received-started)*1000,
            'serialize_ms': (serialized-received)*1000, 'validate_ms': (finished-serialized)*1000,
            'thread_cpu_ms': (time.thread_time()-cpu)*1000, 'bytes': wire_bytes, **extra}


def summarize(case, mode, samples, errors):
    row = {'id': case.id+'/'+mode, 'case': case.id, 'transport': case.transport, 'mode': mode,
           'functional': not errors, 'errors': errors, **stats([x['total_ms'] for x in samples])}
    for field in ('query_or_http_ms', 'serialize_ms', 'validate_ms', 'thread_cpu_ms', 'ttfb_ms', 'body_ms', 'parse_ms',
                  'server_db_ms','server_wait_ms','server_app_ms','server_serialize_ms','server_compress_ms','server_total_ms'):
        values = [x[field] for x in samples if field in x]
        if values:
            row[field+'_median'] = round(statistics.median(values), 3)
    row['bytes_max'] = max((x['bytes'] for x in samples), default=0)
    return row


def run_case(case, trials, concurrency, reset=None):
    rows = []
    modes = ['uncached', 'cached', 'concurrent'] if reset else ['first_observed', 'repeat', 'concurrent']
    for mode in modes:
        samples, errors = [], []
        try:
            if mode in ('cached',):
                measured(case)  # prime application cache, excluded from timing samples
            if mode == 'concurrent':
                if reset:
                    reset()  # sharing a miss, rather than just four warm hits
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(measured, case) for _ in range(concurrency)]
                    for future in futures:
                        try:
                            samples.append(future.result())
                        except Exception as exc:
                            errors.append(error_description(exc))
            else:
                for _ in range(1 if mode == 'first_observed' else trials):
                    if mode == 'uncached':
                        reset()
                    try:
                        samples.append(measured(case))
                    except Exception as exc:
                        errors.append(error_description(exc))
        except Exception as exc:
            errors.append(error_description(exc))
        rows.append(summarize(case, mode, samples, errors))
    return rows


def clear_caches(monitor):
    with historian._overview_mutex:
        historian._overview_cache.clear()
    historian._device_cache = QueryCache()
    with monitor.history_lock:
        monitor.history_cache.clear()


def seed(directory, days, per_day, devices, padding):
    """All observations invented; no adapter, sampling, file from a device or network."""
    core.init_db()
    anchor = datetime.now(timezone.utc)-timedelta(seconds=5)
    host = HostMonitor(Path(directory)/'observatory.db')
    sample = empty_snapshot()
    sample['timestamp'] = anchor.isoformat()
    sample['quality'] = 'ok'
    sample['cpu']['usagePercent'] = 0
    sample['memory'].update(usedMB=25, totalMB=100)
    sample['network'].update(rxMbps=0, txMbps=2)
    sample['battery'].update(levelPercent=80, temperatureC=30)
    sample['storage'] = [{'usedGB': 0, 'totalGB': 64}]
    sample['synthetic_padding'] = 'x'*padding
    sample['details']={'metrics':{'fixture.cpu':{'status':'ok','value':0,'source':'synthetic'}},'measuredAt':anchor.isoformat()}
    host.snapshot_data = sample
    with core.connect() as db, closing(sqlite3.connect(host.path)) as hd, hd:
        hd.execute('CREATE TABLE host_samples(ts REAL PRIMARY KEY,payload TEXT NOT NULL)')
        for i in range(days*per_day):
            stamp = anchor-timedelta(seconds=i*86400/per_day)
            clients = []
            for j in range(devices):
                mac = '02:00:00:'+f'{j+1:06x}'[0:2]+':'+f'{j+1:06x}'[2:4]+':'+f'{j+1:06x}'[4:6]
                client = {'mac': mac, 'names': ['Fixture phone '+str(j)], 'ips': ['192.0.2.'+str(j+1)],
                          'ports': ['wlan0'], 'reported_status': 'Online',
                          'stations': [{'rssi_dbm': -60, 'rx_link_mbps': 0, 'tx_link_mbps': None, 'interface': 'wlan0'}]}
                clients.append(client)
                db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',
                           (i+1, stamp.isoformat(), mac, json.dumps(client)))
            payload = {'metrics': {'cpu_pct': 0, 'memory_pct': None}, 'clients': clients,
                       'stations': [], 'wan_states': {'wan0': {'services': ['Internet']}},
                       'interfaces': {'wan0': {'rx_bytes': 0, 'tx_bytes': 1000+i}}, 'synthetic_padding': 'x'*padding}
            db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)', (stamp.isoformat(), json.dumps(payload)))
            db.execute('INSERT INTO samples(ts,router_online,router_ms,internet_online,internet_ms) VALUES(?,?,?,?,?)',
                       (stamp.isoformat(), 1, 0, 1, None))
            hd.execute('INSERT INTO host_samples VALUES(?,?)', (stamp.timestamp(), json.dumps(sample)))
    with core.connect() as db:
        while backfill_router(db, 128):
            pass
    with closing(sqlite3.connect(host.path)) as db, db:
        db.row_factory = sqlite3.Row
        while backfill_host(db, 128):
            pass
    return host


def backend_cases(monitor, periods, devices=None):
    cases = []
    wrap = lambda fn: lambda: (fn(), None, {})
    cases += [Case('router/status', 'backend', wrap(core.get_status), lambda v: require('huawei' in v, 'Missing source')),
              Case('router/inventory', 'backend', wrap(core.get_router_clients), lambda v:inventory(v,devices)),
              Case('s7/snapshot', 'backend', wrap(monitor.snapshot), lambda v:snapshot(v,True)),
              Case('s7/catalog', 'backend', wrap(monitor.catalog), lambda v:catalog(v,True)),
              Case('s7/archive/page10', 'backend', wrap(lambda: monitor.archive(0, 10)), lambda v:archive(v,True))]
    for period in periods:
        for view in ('summary', 'full'):
            cases.append(Case(f'router/overview/{view}/{period}', 'backend',
                              wrap(lambda p=period, v=view: historian.overview_history(p, v)), bundle))
        cases.append(Case('router/device/'+period, 'backend', wrap(lambda p=period: historian.device_history(MAC.replace(':', ''), p)),
                          lambda v: bundle(v, True)))
        host_range = {'1m': '30d', '1y': '1a'}.get(period, period)
        for metric in host_telemetry.METRICS:
            cases.append(Case(f's7/history/{metric}/{host_range}', 'backend',
                              wrap(lambda m=metric, p=host_range: monitor.history(m, p)),
                              lambda v, expected=EXPECTED[metric]: series(v, expected)))
    return cases


def http_cases(url, device, periods, exports, max_bytes, timeout, synthetic=False, devices=None, compressed=False, flows=False):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path, kind='json'):
        def call():
            started = time.perf_counter()
            req=urllib.request.Request(url.rstrip('/')+path,headers={'Accept-Encoding':'gzip' if compressed else 'identity'})
            with opener.open(req, timeout=timeout) as response:
                headers_at = time.perf_counter()
                require(response.status == 200, 'HTTP status failure')
                body = response.read(max_bytes+1)
                require(len(body) <= max_bytes, 'Response size cap exceeded')
                wire_bytes=len(body)
                server={}
                for item in response.headers.get('Server-Timing','').split(','):
                    name,_,parameter=item.strip().partition(';dur=')
                    if name in ('db','wait','app','serialize','compress','total'):
                        try:
                            duration=float(parameter)
                            if math.isfinite(duration) and duration>=0:server['server_'+name+'_ms']=duration
                        except ValueError:pass
                encoding=response.headers.get('Content-Encoding')
            body_at = time.perf_counter()
            if encoding=='gzip':
                with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:body=stream.read(max_bytes+1)
                require(len(body)<=max_bytes,'Decoded response size cap exceeded')
            value = json.loads(body) if kind == 'json' else list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
            parsed = time.perf_counter()
            return value, wire_bytes, {**server, 'ttfb_ms': (headers_at-started)*1000, 'body_ms': (body_at-headers_at)*1000,
                                      'parse_ms': (parsed-body_at)*1000}
        return call
    cases = [Case('router/status', 'http', request('/api/status'), lambda v: require('huawei' in v, 'Missing source')),
             Case('router/inventory', 'http', request('/api/router/clients'), lambda v:inventory(v,devices)),
             Case('s7/snapshot', 'http', request('/api/host/snapshot'), lambda v:snapshot(v,synthetic)),
             Case('s7/catalog', 'http', request('/api/host/catalog'), lambda v:catalog(v,synthetic)),
             Case('s7/archive/page10', 'http', request('/api/host/archive?limit=10'), lambda v:archive(v,synthetic))]
    for period in periods:
        for view in ('summary', 'full'):
            cases.append(Case(f'router/overview/{view}/{period}', 'http', request(f'/api/v1/overview?period={period}&view={view}'), bundle))
        if device:
            base='/api/v1/devices/'+device
            cases.append(Case('router/device/'+period, 'http', request(base+'?period='+period), lambda v: bundle(v, True)))
            if exports:
                for kind in ('json', 'csv'):
                    def validate(value, fmt=kind, p=period):
                        require(isinstance(value, list), 'Expected export observations')
                        if synthetic:
                            require(bool(value), 'Synthetic export lost all observations')
                            start,end=historian.window(p)
                            with core.connect() as db:
                                expected=db.execute('SELECT COUNT(*) FROM router_client_samples WHERE mac=? AND ts>=? AND ts<=?',
                                                    (historian.device_mac(device),start.isoformat(),end.isoformat())).fetchone()[0]
                            require(len(value)==expected, 'Export truncated original observations')
                        for row in value:
                            require(('observation' in row and 'measurement' in row) if fmt == 'json' else 'observation_json' in row,
                                    'Export lost original observation')
                    cases.append(Case(f'router/export/{kind}/{period}', 'http', request(base+'/export.'+kind+'?period='+period, kind), validate))
        host_range = {'1m': '30d', '1y': '1a'}.get(period, period)
        for metric in host_telemetry.METRICS:
            cases.append(Case(f's7/history/{metric}/{host_range}', 'http', request('/api/host/history?metric='+metric+'&range='+host_range),
                              lambda v, m=metric: series(v, EXPECTED[m] if synthetic else 'contract')))
    if flows:
        # Representative mixed endpoint batches; not a browser rendering benchmark.
        groups={'router/page/24h':['router/status','router/inventory','router/overview/summary/24h'],
                's7/page/network/24h':['s7/snapshot','s7/history/rx/24h','s7/history/tx/24h','s7/history/latency/24h']}
        lookup={case.id:case for case in cases}
        for name,ids in groups.items():
            if not all(key in lookup for key in ids):continue
            members=[lookup[key] for key in ids]
            def batch(selected=members):
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected)) as pool:
                    rows=list(pool.map(lambda case:case.invoke(),selected))
                for case,row in zip(selected,rows):case.validate(row[0])
                return None,sum(row[1] for row in rows),{}
            cases.append(Case(name,'http',batch,lambda v:None))
    return cases


def compare(report, baseline, percent=25, noise_ms=5):
    if report['profile']['kind']=='live' or baseline.get('profile',{}).get('kind')=='live':
        return {'compatible':False,'regressions':[],'reason':'Live data/cache/load are uncontrolled; no automatic regression verdict. Use fixed synthetic fixtures for gating.'}
    if report['comparison_fingerprint'] != baseline.get('comparison_fingerprint'):
        return {'compatible': False, 'regressions': [], 'reason': 'Environment, transport or fixture differ; no automatic performance verdict'}
    previous = {x['id']: x for x in baseline['results']}
    regressions = []
    for row in report['results']:
        old = previous.get(row['id'])
        if old and row['functional'] and old['functional'] and old['median_ms'] is not None and row['median_ms'] is not None:
            threshold = old['median_ms']*(1+percent/100)+noise_ms
            if row['median_ms'] > threshold:
                regressions.append({'id': row['id'], 'before_ms': old['median_ms'], 'after_ms': row['median_ms'], 'threshold_ms': round(threshold, 3)})
    current = {x['id'] for x in report['results']}
    return {'compatible': True, 'regressions': regressions, 'missing_cases': sorted(set(previous)-current),
            'new_cases': sorted(current-set(previous)), 'relative_percent': percent, 'noise_floor_ms': noise_ms}


def markdown(report):
    lines = ['# Matriz de funcionalidade e desempenho', '', report['warning'], '',
             f"Casos: {len(report['results'])} · Falhas funcionais: {sum(not r['functional'] for r in report['results'])}", '',
             '| Caso / cenário | Estado | Mediana ms | Máximo ms | Bytes |', '|---|---|---:|---:|---:|']
    for row in sorted(report['results'], key=lambda r: r['median_ms'] or 0, reverse=True):
        lines.append(f"| {row['id']} | {'OK' if row['functional'] else 'FALHA'} | {row['median_ms']} | {row.get('max_ms')} | {row['bytes_max']} |")
    if 'comparison' in report:
        lines += ['', '## Comparação', '', '```json', json.dumps(report['comparison'], ensure_ascii=False, indent=2), '```']
    if 'budgets' in report:
        lines += ['', '## Orçamentos', '', '```json', json.dumps(report['budgets'], ensure_ascii=False, indent=2), '```']
    return '\n'.join(lines)+'\n'


def budgets(report, settings):
    violations, unmatched = [], []
    for rule in settings['rules']:
        matches=[row for row in report['results'] if fnmatch.fnmatchcase(row['id'],rule['pattern'])]
        if not matches:
            unmatched.append(rule['pattern'])
        for row in matches:
            for field in ('median_ms','p95_ms','bytes_max'):
                if field in rule and (row.get(field) is None or row[field]>rule[field]):
                    violations.append({'id':row['id'],'metric':field,'actual':row.get(field),
                                       'maximum':rule[field],'reason':'insufficient_samples' if row.get(field) is None else 'over_budget'})
    return {'violations':violations,'unmatched_rules':unmatched}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport', choices=('backend', 'http'), default='backend')
    p.add_argument('--live-url', help='Explicit already-authorized application origin; never the Huawei admin GUI')
    p.add_argument('--allow-live', action='store_true')
    p.add_argument('--device-id', help='Private optional 12-hex device ID; not stored in reports')
    p.add_argument('--environment-label', default='local-synthetic')
    p.add_argument('--build-label', default='unspecified')
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--samples-per-day', type=int, default=24)
    p.add_argument('--devices', type=int, default=19)
    p.add_argument('--payload-kib', type=int, default=4)
    p.add_argument('--fixture-budget-mib', type=int, default=256, help='Conservative fixture+WAL budget, max 1024 MiB')
    p.add_argument('--periods', nargs='+', choices=list(historian.PERIODS), default=list(historian.PERIODS))
    p.add_argument('--trials', type=int, default=5)
    p.add_argument('--concurrent', type=int, default=4)
    p.add_argument('--include-flows',action='store_true',help='Mixed endpoint page batches (HTTP only)')
    p.add_argument('--gzip',action='store_true',help='Negotiate compressed API responses (HTTP only)')
    p.add_argument('--include-exports', action='store_true', help='Opt-in potentially large read-only exports')
    p.add_argument('--timeout', type=float, default=30)
    p.add_argument('--max-response-mib', type=int, default=32)
    p.add_argument('--work-dir', type=Path, help='Existing volume for disposable synthetic files; set to SD when running on S7')
    p.add_argument('--output', required=True, type=Path, help='JSON report; Markdown is saved alongside it. Never contains payloads')
    p.add_argument('--baseline', type=Path)
    p.add_argument('--regression-percent', type=float, default=25)
    p.add_argument('--noise-floor-ms', type=float, default=5)
    p.add_argument('--fail-regressions', action='store_true')
    p.add_argument('--budgets', type=Path, help='Explicit environment-specific JSON rules; no universal timing thresholds')
    p.add_argument('--fail-budgets', action='store_true')
    p.add_argument('--case', action='append', dest='case_patterns', help='Select individual case IDs or glob patterns; repeatable')
    args = p.parse_args(argv)
    if args.fail_regressions and not args.baseline:
        p.error('--fail-regressions requires --baseline; no silent disabled gate')
    if args.fail_budgets and not args.budgets:
        p.error('--fail-budgets requires --budgets; no silent disabled gate')
    if (args.include_exports or args.include_flows or args.gzip) and args.transport!='http':
        p.error('Full exports are HTTP cases; select --transport http explicitly')
    if not (1 <= args.days <= 366 and 1 <= args.samples_per_day <= 1440 and 1 <= args.devices <= 100 and 0 <= args.payload_kib <= 128):
        p.error('Invalid bounded fixture dimensions')
    if not (1 <= args.trials <= 100 and 1 <= args.concurrent <= 4 and 1 <= args.max_response_mib <= 128 and 0 < args.timeout <= 120):
        p.error('Invalid trials, concurrency, timeout or response cap')
    if args.live_url and (not args.allow_live or args.transport != 'http'):
        p.error('Live measurements require --transport http --allow-live and operator authorization')
    if args.live_url:
        origin=urllib.parse.urlsplit(args.live_url)
        if origin.scheme not in ('http','https') or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('','/'):
            p.error('Use a plain application HTTP(S) origin, without credentials, query or path')
        if args.environment_label=='local-synthetic':
            p.error('Give the live measurement an explicit --environment-label')
    if args.device_id and (len(args.device_id) != 12 or any(c not in '0123456789abcdef' for c in args.device_id)):
        p.error('Device ID must be 12 lowercase hexadecimal characters')
    if args.work_dir and not args.work_dir.is_dir():
        p.error('--work-dir must already exist on the selected volume')
    if not args.output.parent.is_dir():
        p.error('Output parent must already exist')
    if args.output.exists() or args.output.with_suffix('.md').exists():
        p.error('Do not overwrite prior measurements; use a unique output path')
    if not 1 <= args.fixture_budget_mib <= 1024 or args.regression_percent < 0 or args.noise_floor_ms < 0:
        p.error('Invalid fixture budget or regression threshold')
    android=os.environ.get('PREFIX','').startswith('/data/data/com.termux/')
    if android:
        if not args.live_url and (not args.work_dir or not str(args.work_dir.resolve()).startswith('/storage/')):
            p.error('On S7/Termux, use an existing microSD --work-dir; no internal fallback')
        if not str(args.output.resolve()).startswith('/storage/'):
            p.error('On S7/Termux, reports must stay on microSD')
        if shutil.disk_usage('/data/data/com.termux/files/home').free < 2147483648:
            p.error('Internal reserve below 2 GiB; defer benchmark work')
    estimated=args.days*args.samples_per_day*(2*args.payload_kib*1024+4096+args.devices*1024)*3
    if not args.live_url:
        if estimated > args.fixture_budget_mib*1024**2:
            p.error('Fixture exceeds its disk budget; reduce dimensions or explicitly raise --fixture-budget-mib')
        if shutil.disk_usage(args.work_dir or tempfile.gettempdir()).free < estimated+256*1024**2:
            p.error('Insufficient space for fixture, WAL and safety margin')
    environment = {'label': args.environment_label, 'system': platform.system(), 'machine': platform.machine(),
                   'processor':platform.processor(),'cpu_count':os.cpu_count(),
                   'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version}
    profile = {'kind': 'live' if args.live_url else 'synthetic', 'transport': args.transport,
               'days': args.days, 'samples_per_day': args.samples_per_day, 'devices': args.devices,
               'payload_kib': args.payload_kib, 'trials': args.trials, 'concurrent': args.concurrent,
               'include_exports': args.include_exports, 'include_flows':args.include_flows, 'gzip':args.gzip, 'periods': args.periods, 'fixture_schema': SCHEMA,
               'live_device_selected': bool(args.device_id)}
    profile['case_patterns']=args.case_patterns
    if args.live_url:
        for field in ('days','samples_per_day','devices','payload_kib','fixture_schema'):
            profile[field]=None  # the live archive dimensions are not controlled by this tool
    report = {'schema': SCHEMA, 'created_at': datetime.now(timezone.utc).isoformat(), 'environment': environment,
              'profile': profile, 'build': args.build_label,
              'warning': 'Synthetic checks are not S7 LAN/Android performance. Application-cache reset is not a cold OS/SD cache. Live checks validate contracts, not sensor truth. p95 requires at least 20 observations.',
              'not_measured': ['browser paint/INP/LCP/FPS', 'individual collector/sysfs sensor reads', 'Huawei authentication or collection'],
              'results': []}
    report['comparison_fingerprint'] = hashlib.sha256(json.dumps({'environment': environment, 'profile': profile}, sort_keys=True).encode()).hexdigest()
    with ExitStack() as stack:
        reset = None
        if args.live_url:
            cases = http_cases(args.live_url, args.device_id, args.periods, args.include_exports, args.max_response_mib*1024**2, args.timeout, compressed=args.gzip, flows=args.include_flows)
        else:
            folder = stack.enter_context(tempfile.TemporaryDirectory(prefix='synthetic-perf-matrix-', dir=args.work_dir))
            stack.enter_context(patch.object(core, 'DB_PATH', Path(folder)/'observatory.db'))
            monitor = seed(folder, args.days, args.samples_per_day, args.devices, args.payload_kib*1024)
            reset = lambda: clear_caches(monitor)
            report['fixture_bytes'] = sum(x.stat().st_size for x in Path(folder).glob('*.db'))
            if args.transport == 'backend':
                cases = backend_cases(monitor, args.periods, args.devices)
            else:
                stack.enter_context(patch.object(host_telemetry, '_monitor', monitor))
                class QuietHandler(Handler):
                    def log_message(self, *args):
                        pass
                server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
                server.daemon_threads = True
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                stack.callback(server.server_close)
                stack.callback(server.shutdown)
                cases = http_cases(f'http://127.0.0.1:{server.server_address[1]}', MAC.replace(':', ''), args.periods,
                                   args.include_exports, args.max_response_mib*1024**2, args.timeout, synthetic=True, devices=args.devices, compressed=args.gzip, flows=args.include_flows)
        if args.case_patterns:
            cases=[case for case in cases if any(fnmatch.fnmatchcase(case.id,pattern) for pattern in args.case_patterns)]
            if not cases:
                p.error('No cases matched the explicit selection')
        groups={}
        for case in cases:
            group='/'.join(case.id.split('/')[:2])
            groups[group]=groups.get(group,0)+1
        report['coverage']={'individual_queries':len(cases),'groups':groups}
        for index, case in enumerate(cases, 1):
            report['results'] += run_case(case, args.trials, args.concurrent, reset)
            print(f'{index}/{len(cases)} {case.id}', flush=True)
    if args.baseline:
        report['comparison'] = compare(report, json.loads(args.baseline.read_text(encoding='utf-8')), args.regression_percent, args.noise_floor_ms)
    if args.budgets:
        report['budgets']=budgets(report,json.loads(args.budgets.read_text(encoding='utf-8')))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    failures = sum(not r['functional'] for r in report['results'])
    print(f"Report: {len(report['results'])} scenarios, {failures} functional failures; no response bodies stored")
    comparison = report.get('comparison', {})
    failed_comparison = comparison and (not comparison['compatible'] or comparison['regressions'] or comparison.get('missing_cases'))
    failed_budgets=report.get('budgets',{}).get('violations') or report.get('budgets',{}).get('unmatched_rules')
    return 1 if failures or args.fail_regressions and failed_comparison or args.fail_budgets and failed_budgets else 0


if __name__ == '__main__':
    raise SystemExit(main())
