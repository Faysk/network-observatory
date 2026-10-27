"""Read-only network measurements, storage and optional metric ingestion.

All external observations carry a source; uncollected values remain None. The
router is not modified. No credentials, firmware hacks or hidden endpoints.
"""
from __future__ import annotations
import ipaddress
from contextlib import contextmanager
import json
import math
import os
import socket
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from . import request_timing

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("FNO_DB", str(ROOT / "data" / "observatory.db")))
ROUTER_IP = os.environ.get("FNO_ROUTER_IP", "192.168.1.1")
INTERVAL = max(30, int(os.environ.get("FNO_INTERVAL", "60")))
RETENTION_DAYS = max(0, int(os.environ.get("FNO_RETENTION_DAYS", "0")))
WRITE_TOKEN = os.environ.get("FNO_INGEST_TOKEN", "")
LOCK = threading.RLock()
# Budget network probes so 20+ unresponsive devices cannot turn a nominal
# 30-60s collection interval into minutes of serial timeout waits. Keep the
# Huawei collector independent; only explicitly registered targets are probed.
DEVICE_PROBE_BATCH = 16
_DEVICE_PROBE_CURSOR = 0
_DEVICE_PROBE_PROGRESS = {'sampled':0,'deferred':0,'tracked':0,'completed_at':None}
COLLECTOR_STATE={'state':'not_started','last_attempt':None,'last_success':None,'reason':None}


def set_collector_state(state,**fields):
    with LOCK:
        COLLECTOR_STATE.update(state=state,**fields)

ROUTER = {"model": "OptiXstar HG8247B7-8N", "vendor": "Huawei", "isp": None,
          "firmware": "V5R024C00S114", "hardware": None, "ip": ROUTER_IP,
          "note": "Modelo de referência do adaptador; confirme os metadados no seu equipamento."}

FIELDS = {"cpu_pct", "memory_pct", "uptime_seconds", "wan_rx_bytes_total", "wan_tx_bytes_total",
          "wan_rx_mbps", "wan_tx_mbps", "optical_rx_dbm", "optical_tx_dbm", "wifi_24_clients",
          "wifi_5_clients", "client_count", "temp_c", "pon_status", "firmware"}
NUMERIC_FIELDS = FIELDS - {"pon_status", "firmware"}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_lan_ip(ip):
    try:
        address = ipaddress.ip_address(ip)
        return isinstance(address, ipaddress.IPv4Address) and any(address in subnet for subnet in (ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16")))
    except ValueError:
        return False


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15, factory=request_timing.Connection)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=5000")
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with request_timing.acquire(LOCK), connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS samples (
          id INTEGER PRIMARY KEY, ts TEXT NOT NULL,
          router_online INTEGER, router_ms REAL, internet_online INTEGER, internet_ms REAL,
          source TEXT NOT NULL DEFAULT 'active-probe');
        CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);
        CREATE TABLE IF NOT EXISTS router_metrics (
          id INTEGER PRIMARY KEY, ts TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_router_metrics_ts ON router_metrics(ts);
        CREATE TABLE IF NOT EXISTS huawei_samples (
          id INTEGER PRIMARY KEY, ts TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_huawei_samples_ts ON huawei_samples(ts);
        CREATE TABLE IF NOT EXISTS router_client_samples (
          id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL, ts TEXT NOT NULL,
          mac TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_router_client_mac_ts ON router_client_samples(mac,ts);
        CREATE INDEX IF NOT EXISTS idx_router_client_ts ON router_client_samples(ts);
        CREATE TABLE IF NOT EXISTS devices (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, ip TEXT NOT NULL UNIQUE,
          type TEXT NOT NULL DEFAULT 'device', port INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS device_samples (
          id INTEGER PRIMARY KEY, ts TEXT NOT NULL, device_id INTEGER NOT NULL,
          online INTEGER NOT NULL, latency_ms REAL,
          FOREIGN KEY(device_id) REFERENCES devices(id));
        CREATE INDEX IF NOT EXISTS idx_device_samples_ts ON device_samples(ts);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, ts TEXT NOT NULL, severity TEXT NOT NULL,
          category TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL, source TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        CREATE TABLE IF NOT EXISTS device_group_members (
          mac TEXT PRIMARY KEY, group_id TEXT NOT NULL, source TEXT NOT NULL,
          updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_device_group ON device_group_members(group_id);
        CREATE TABLE IF NOT EXISTS device_presentation_overrides (
          mac TEXT PRIMARY KEY, nickname TEXT, category TEXT, icon TEXT, note TEXT,
          revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);

        """)
        from .read_models import init_router
        init_router(db)
        from .router_observability import init_db as init_observability
        init_observability(db)


def emit(db, severity, category, title, detail="", source="collector"):
    db.execute("INSERT INTO events(ts,severity,category,title,detail,source) VALUES(?,?,?,?,?,?)",
               (utcnow(), severity, category, title, detail, source))


def tcp_probe(ip, port=80, timeout=2.0):
    t0 = time.monotonic()
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            pass
        return True, round((time.monotonic() - t0) * 1000, 1)
    except (OSError, ValueError, OverflowError):
        return False, None


def ping_probe(ip, timeout=2):
    """ICMP via OS, never a shell string. Non-response != necessarily offline."""
    if not valid_lan_ip(ip):
        return False, None
    cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip] if sys.platform == "win32" else ["ping", "-c", "1", "-W", str(timeout), ip]
    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 2, check=False)
        if result.returncode == 0:
            return True, round((time.monotonic() - t0) * 1000, 1)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False, None


def probe_device(row):
    # Port 0 = ICMP; for devices that block ping, choose an explicit TCP port.
    if row["port"]:
        return tcp_probe(row["ip"], row["port"])
    return ping_probe(row["ip"])


def collect_once():
    # TCP/80 is a gateway web-management reachability probe, not a WAN test.
    router_up, router_ms = tcp_probe(ROUTER_IP, 80)
    # Remote TCP/443 measures a specific Internet path, NOT broadband speed.
    internet_up, internet_ms = tcp_probe("1.1.1.1", 443)
    # Never hold the global database lock (or a WAL transaction) during slow
    # network probes. Devices may be deleted while the probes are running.
    with request_timing.acquire(LOCK), connect() as db:
        devices = [dict(row) for row in db.execute("SELECT * FROM devices ORDER BY id")]
    # Round robin over *explicitly configured* devices. A skipped device keeps
    # its previous observation; we never fabricate an offline measurement.
    # The cursor is only advanced by the single active collector worker.
    global _DEVICE_PROBE_CURSOR
    count=len(devices)
    if count:
        offset=_DEVICE_PROBE_CURSOR % count
        selected=[devices[(offset+i)%count] for i in range(min(DEVICE_PROBE_BATCH,count))]
        _DEVICE_PROBE_CURSOR=(offset+len(selected))%count
    else:
        selected=[]
        _DEVICE_PROBE_CURSOR=0
    # Bounded fan-out: <= 4 simultaneous probes, <= 16 total per cycle.
    # Do not share a SQLite connection with any network worker.
    if selected:
        with ThreadPoolExecutor(max_workers=min(4,len(selected)),thread_name_prefix='fno-probe') as pool:
            outcomes=list(pool.map(probe_device,selected))
        observations=[(device,*outcome) for device,outcome in zip(selected,outcomes)]
    else:
        observations=[]
    # Timestamp reflects completion of probes, not their start, and therefore
    # cannot make a very slow cycle appear fresher than it really is.
    ts = utcnow()
    with request_timing.acquire(LOCK), connect() as db:
        prev = db.execute("SELECT router_online,internet_online FROM samples ORDER BY id DESC LIMIT 1").fetchone()
        db.execute("INSERT INTO samples(ts,router_online,router_ms,internet_online,internet_ms) VALUES(?,?,?,?,?)",
                   (ts, int(router_up), router_ms, int(internet_up), internet_ms))
        if prev is not None:
            for key, current, text in (("router_online", router_up, "Gateway Huawei"), ("internet_online", internet_up, "Sonda externa TCP")):
                if prev[key] != int(current):
                    emit(db, "info" if current else "critical", "connectivity",
                         f"{text}: {'recuperado' if current else 'indisponível'}",
                         "Mudança de estado confirmada numa recolha; falhas transitórias ainda podem ocorrer.")
        for d,up,ms in observations:
            # A removed device must not be resurrected by an in-flight probe.
            if db.execute("SELECT 1 FROM devices WHERE id=?", (d["id"],)).fetchone() is None:
                continue
            before = db.execute("SELECT online FROM device_samples WHERE device_id=? ORDER BY id DESC LIMIT 1", (d["id"],)).fetchone()
            db.execute("INSERT INTO device_samples(ts,device_id,online,latency_ms) VALUES(?,?,?,?)",
                       (ts, d["id"], int(up), ms))
            if before is not None and before["online"] != int(up):
                emit(db, "info" if up else "warning", "device",
                     f"{d['name']}: {'voltou a responder' if up else 'sem resposta'}",
                     f"Destino {d['ip']} · teste {'TCP/'+str(d['port']) if d['port'] else 'ICMP'}")
        prune_history(db)
    with LOCK:
        _DEVICE_PROBE_PROGRESS.update(sampled=len(observations),
                                      deferred=count-len(observations),
                                      tracked=count,completed_at=ts)
    return {"router_online": router_up, "internet_online": internet_up}


def collector_loop(stop_event):
    # Fixed start-to-start cadence, measured with a monotonic clock. A slow
    # scan does not add another full INTERVAL to the next scheduled cycle.
    # After an overrun skip missed slots; never create catch-up probe storms.
    next_due=time.monotonic()+INTERVAL
    try:
        collect_once()
    except Exception as exc:
        print(f"Collector first cycle: {exc}", file=sys.stderr)
    while not stop_event.wait(max(0,next_due-time.monotonic())):
        try:
            collect_once()
        except Exception as exc:
            print(f"Collector cycle: {exc}", file=sys.stderr)
        next_due+=INTERVAL
        now=time.monotonic()
        if next_due<=now:
            next_due+=INTERVAL*(int((now-next_due)//INTERVAL)+1)


def put_router_metrics(data, source):
    """The only trusted way to fill Huawei-specific metrics in v0.1.
    An external approved collector calls this after parsing authenticated data.
    """
    if not isinstance(data, dict):
        raise ValueError("JSON object expected")
    fields = {k:v for k,v in data.items() if k in FIELDS}
    if not fields:
        raise ValueError("No recognized metrics")
    for key, value in fields.items():
        if key in NUMERIC_FIELDS:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e18:
                raise ValueError(f"Bad numeric metric: {key}")
            if key in {"cpu_pct", "memory_pct"} and not 0 <= value <= 100:
                raise ValueError(f"Invalid percent: {key}")
        elif not isinstance(value, str) or len(value) > 100:
            raise ValueError(f"Bad text metric: {key}")
    if len(source) > 64:
        raise ValueError("Source too long")
    with request_timing.acquire(LOCK), connect() as db:
        db.execute("INSERT INTO router_metrics(ts,source,payload) VALUES(?,?,?)", (utcnow(), source, json.dumps(fields)))
        emit(db, "info", "integration", "Novas métricas Huawei recebidas", ", ".join(sorted(fields)), source)
    return fields


def latest_router(db):
    row = db.execute("SELECT ts,source,payload FROM router_metrics ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return {"ts": None, "source": None, "metrics": {}}
    return {"ts": row["ts"], "source": row["source"], "metrics": json.loads(row["payload"])}


def list_devices(db):
    rows = db.execute("""SELECT d.*, s.ts AS sampled_at, s.online, s.latency_ms
        FROM devices d LEFT JOIN device_samples s ON s.id=(
          SELECT id FROM device_samples WHERE device_id=d.id ORDER BY id DESC LIMIT 1)
        ORDER BY d.id""").fetchall()
    return [dict(r) for r in rows]


def put_huawei_sample(data, historical=False):
    from .adapters.huawei_b7 import validate_payload
    validate_payload(data,require_recent=not historical)
    with request_timing.acquire(LOCK), connect() as db:
        previous_sample=db.execute('SELECT payload FROM huawei_samples WHERE ts=? LIMIT 1',(data['collected_at'],)).fetchone()
        if previous_sample is not None:
            if json.loads(previous_sample['payload'])!=data:
                raise ValueError('Conflicting telemetry for the same timestamp')
            return
        sample_id=db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)',
                   (data['collected_at'], json.dumps(data, allow_nan=False))).lastrowid
        from .router_observability import persist
        persist(db,data.get('observability',{}),historical=historical)
        from .read_models import project_overview, project_client, safe_project
        safe_project(db,project_overview,sample_id,data['collected_at'],data)
        for client in data.get('clients',[]):
            previous=db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? AND ts<? ORDER BY ts DESC,id DESC LIMIT 1',(client['mac'],data['collected_at'])).fetchone()
            observation={**client,'stations':[s for s in data.get('stations',[]) if s.get('mac')==client['mac']]}
            observation_id=db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',
                       (sample_id,data['collected_at'],client['mac'],json.dumps(observation,allow_nan=False))).lastrowid
            safe_project(db,project_client,observation_id,data['collected_at'],client['mac'],observation,data.get('wifi',{}))
            if previous and not historical:
                old=json.loads(previous['payload']).get('reported_status','Unknown')
                gap=(datetime.fromisoformat(data['collected_at'])-datetime.fromisoformat(previous['ts'])).total_seconds()
                new=client['reported_status']
                if 0<gap<=180 and old in ('Online','Offline') and new in ('Online','Offline') and old!=new:
                    emit(db,'info','router-client','Estado do aparelho alterado',f"{client['mac']} · {old} → {new}",'huawei-b7-http')
        prune_history(db)


ARCHIVE_TABLES={'huawei':'huawei_samples','clients':'router_client_samples','probes':'samples',
                'router':'router_metrics','devices':'device_samples','events':'events'}


def prune_history(db):
    """Zero means unlimited: never delete observations automatically."""
    if RETENTION_DAYS==0:return
    cutoff=datetime.fromtimestamp(time.time()-RETENTION_DAYS*86400,tz=timezone.utc).isoformat(timespec='seconds')
    for table in ARCHIVE_TABLES.values():
        db.execute(f'DELETE FROM {table} WHERE ts < ?',(cutoff,))
    db.execute('DELETE FROM router_observations WHERE ts < ?',(cutoff,))
    db.execute('DELETE FROM router_changes WHERE observed_at < ?',(cutoff,))


def get_archive(kind='huawei',after=0,limit=1000):
    """Lossless pages over all retained rows, including samples outside chart windows."""
    if kind not in ARCHIVE_TABLES:raise ValueError('Invalid archive kind')
    after=int(after);limit=int(limit)
    if after<0 or not 1<=limit<=2000:raise ValueError('Invalid archive page')
    with request_timing.acquire(LOCK),connect() as db:
        rows=db.execute(f'SELECT * FROM {ARCHIVE_TABLES[kind]} WHERE id>? ORDER BY id LIMIT ?',
                        (after,limit+1)).fetchall()
    more=len(rows)>limit
    result=[]
    for row in rows[:limit]:
        item=dict(row)
        if 'payload' in item:item['payload']=json.loads(item['payload'])
        result.append(item)
    return {'kind':kind,'rows':result,'next_after':result[-1]['id'] if result else after,
            'has_more':more,'downsampled':False}


def get_router_clients(mac=None, limit=120):
    """Retained client observations; absence is never inferred as offline."""
    from .adapters.huawei_b7 import normalise_mac,is_lan_client
    from .device_identity import get_registry, inspect_mac
    from .device_classifier import classify_client, meaningful_name
    from .device_history_hints import hints
    from .device_preferences import read_presentation
    # One lazy, immutable registry per response; no lookup HTTP or database writes.
    # Configured main database is expected to live on microSD in S7 deployments.
    registry = get_registry(DB_PATH.parent) if mac is None else None
    with request_timing.acquire(LOCK),connect() as db:
        if mac is not None:
            if normalise_mac(mac)!=mac or mac is None:raise ValueError('Invalid MAC')
            rows=db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? ORDER BY ts DESC,id DESC LIMIT ?',
                            (mac,max(1,min(2000,int(limit))))).fetchall()
            return {'mac':mac,'source':'huawei-b7-http','observations':[dict(json.loads(r['payload']),collected_at=r['ts']) for r in rows]}
        # Count on the narrow MAC/ts index, then read only the latest payload per MAC.
        # A backfilled older timestamp must not win just because its ID is newer.
        rows=db.execute('''WITH summary AS (
                          SELECT mac,MIN(ts) AS first_seen,COUNT(*) AS observations
                          FROM router_client_samples GROUP BY mac)
                          SELECT r.ts,r.payload,g.first_seen,g.observations FROM summary g
                          JOIN router_client_samples r ON r.id=(
                            SELECT id FROM router_client_samples c WHERE c.mac=g.mac
                            ORDER BY c.ts DESC,c.id DESC LIMIT 1)
                          ORDER BY r.ts DESC,r.mac''').fetchall()
        result=[]
        for row in rows:
            item=json.loads(row['payload'])
            if not is_lan_client(item):continue
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['ts'])).total_seconds()
            item.update(first_seen=row['first_seen'],last_seen=row['ts'],observations=row['observations'],
                        quality='ok' if -5<=age<=180 else 'stale')
            # Read-only API enrichment: the original observation JSON is untouched.
            item['identity'] = inspect_mac(item.get('mac'), registry=registry)
            item['classification'] = classify_client(item, identity=item['identity'])
            if item['quality']=='ok' and item.get('reported_status')=='Online' and item['classification']['category'] in ('unknown','android_device') and not any(meaningful_name(v) for v in item.get('names',[])):
                item['classification']=classify_client(item,identity=item['identity'],history=hints(db,DB_PATH,item.get('mac')))
            item['presentation'] = read_presentation(db, item.get('mac'))
            result.append(item)
        from .device_groups import enrich
        enrich(db, result)
        return {'manual_group_count':len({c['association']['group_id'] for c in result if c['association']['group_id']}),'source':'huawei-b7-http','clients':result,'retention_days':RETENTION_DAYS,'retention_unlimited':RETENTION_DAYS==0}


def latest_huawei(db):
    row = db.execute('SELECT ts,payload FROM huawei_samples ORDER BY ts DESC,id DESC LIMIT 1').fetchone()
    if row is None:
        return {'source': 'huawei-b7-http', 'quality': 'unavailable', 'collected_at': None,
                'metrics': {}, 'interfaces': {}}
    result = json.loads(row['payload'])
    # Additional sources have their own cadence/API; keep the baseline status small.
    result.pop('observability',None)
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(row['ts'])).total_seconds()
    result.update(source='huawei-b7-http', age_seconds=max(0, int(age)),
                  quality='ok' if -5 <= age <= 180 else 'stale')
    if result['quality'] == 'stale':
        result['metrics'] = {}
        result['interfaces'] = {}
        for section in ('system','wifi','wan_states','wan_packet_totals','inventory','voice','health'):
            result[section] = {}
        result['stations'] = []
        result['clients'] = []
    return result


def get_status():
    with request_timing.acquire(LOCK), connect() as db:
        last = db.execute("SELECT * FROM samples ORDER BY id DESC LIMIT 1").fetchone()
        counts = db.execute("SELECT count(*) AS c FROM events").fetchone()["c"]
        result = {"router": ROUTER, "probe": dict(last) if last else None,
                  "metrics": latest_router(db), "devices": list_devices(db),
                  "huawei": latest_huawei(db),
                  "collector": dict(COLLECTOR_STATE),
                  "probe_cycle": dict(_DEVICE_PROBE_PROGRESS),
                  "event_count": counts, "server_time": utcnow(),
                  "poll_interval_seconds": INTERVAL, "retention_days": RETENTION_DAYS, "retention_unlimited": RETENTION_DAYS==0,
                  "methodology": {"router": "TCP/80 para a interface web", "internet": "TCP/443 para 1.1.1.1", "device": "ICMP ou porta TCP configurada"}}
    # Filesystem enumeration can take arbitrarily long with a large backlog.
    # It is independent of the SQLite snapshot: never hold the global writer
    # lock (or DB transaction) while traversing the microSD queue folders.
    result["recording"] = {
        "pending_samples":sum(1 for _ in (DB_PATH.parent/"outbox").glob("*.json")),
        "quarantined_samples":sum(1 for _ in (DB_PATH.parent/"outbox"/"quarantine").rglob("*.json")),
        "durable_queue":True,
    }
    return result


def get_history(hours=24, limit=450):
    cutoff = datetime.fromtimestamp(time.time() - hours*3600, tz=timezone.utc).isoformat(timespec="seconds")
    with request_timing.acquire(LOCK), connect() as db:
        rows = db.execute("SELECT * FROM samples WHERE ts>=? ORDER BY ts DESC,id DESC LIMIT 5001", (cutoff,)).fetchall()
        metrics = db.execute("SELECT * FROM router_metrics WHERE ts>=? ORDER BY ts DESC,id DESC LIMIT 5001", (cutoff,)).fetchall()
        huawei = db.execute('SELECT payload FROM huawei_samples WHERE ts>=? ORDER BY ts DESC,id DESC LIMIT 5001', (cutoff,)).fetchall()
    # Legacy endpoint retains the bounded window, but always declares data loss.
    truncated = {'probes':len(rows)>5000,'router':len(metrics)>5000,'huawei':len(huawei)>5000}
    rows = list(reversed(rows[:5000]));metrics = list(reversed(metrics[:5000]))
    huawei = list(reversed(huawei[:5000]))
    def downsample(data):
        if len(data) <= limit: return data
        stride = max(1, (len(data)+limit-1)//limit)
        return data[::stride] + ([data[-1]] if data[-1] is not data[::stride][-1] else [])
    return {"probes": [dict(r) for r in downsample(rows)],
            "router": [{"ts": r["ts"], "source":r["source"], **json.loads(r["payload"])} for r in downsample(metrics)],
            "huawei": [json.loads(r['payload']) for r in downsample(huawei)],
            "truncated":truncated,
            "bounded_to_last":5000,
            "downsampled":{kind:count>limit for kind,count in (
                ('probes',len(rows)),('router',len(metrics)),('huawei',len(huawei)))},
            "semantics":"bounded legacy preview; /api/archive pages preserve all retained observations"}


def get_events(limit=120):
    with request_timing.acquire(LOCK), connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]


def add_device(data):
    ip = str(data.get("ip", "")).strip()
    name = str(data.get("name", "")).strip()
    kind = str(data.get("type", "device"))[:24]
    try: port = int(data.get("port", 0))
    except (TypeError, ValueError): port = -1
    if not valid_lan_ip(ip): raise ValueError("Usa um endereço IPv4 privado da tua rede")
    if not name or len(name) > 64: raise ValueError("Nome obrigatório (até 64 caracteres)")
    if not 0 <= port <= 65535: raise ValueError("Porta TCP inválida")
    with request_timing.acquire(LOCK), connect() as db:
        try:
            db.execute("INSERT INTO devices(name,ip,type,port,created_at) VALUES(?,?,?,?,?)", (name,ip,kind,port,utcnow()))
        except sqlite3.IntegrityError:
            raise ValueError("Este IP já está registado") from None
        emit(db,"info","inventory",f"Dispositivo adicionado: {name}",f"{ip} · {'TCP/'+str(port) if port else 'ICMP'}","dashboard")
    return True


def delete_device(device_id):
    with request_timing.acquire(LOCK), connect() as db:
        row = db.execute("SELECT name FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row: raise ValueError("Dispositivo não encontrado")
        db.execute("DELETE FROM device_samples WHERE device_id=?", (device_id,))
        db.execute("DELETE FROM devices WHERE id=?", (device_id,))
        emit(db,"info","inventory",f"Dispositivo removido: {row['name']}","", "dashboard")


def passive_neighbors():
    """Read only OS neighbor cache: never scans subnets, never guarantees completeness."""
    cmd = ["arp", "-a"] if sys.platform == "win32" else (["ip", "neigh"] if sys.platform.startswith("linux") else ["arp", "-a"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        if result.returncode != 0: return {"source":"OS cache", "entries":[], "warning":"Comando indisponível no host"}
        import re
        ips = sorted({x for x in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", result.stdout) if valid_lan_ip(x)})
        return {"source":"OS neighbor cache", "entries":[{"ip": x} for x in ips],
                "warning":"Cache parcial e transitória, não é uma descoberta completa."}
    except (OSError, subprocess.TimeoutExpired):
        return {"source":"OS cache", "entries":[], "warning":"Sem acesso à tabela ARP do host"}


def metrics_text():
    status = get_status(); probe = status["probe"] or {}
    router = status["metrics"];mt = router["metrics"]
    def fresh(ts):
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(ts)).total_seconds()
            return -5<=age<=180
        except (ValueError,TypeError,OverflowError):return False
    lines = ["# HELP fno_router_reachable Gateway web port TCP reachability",
             "# TYPE fno_router_reachable gauge",
             "# HELP fno_external_probe_reachable External TCP/443 target reachability",
             "# TYPE fno_external_probe_reachable gauge"]
    if fresh(probe.get('ts')):
        for source,target in (('router_online','fno_router_reachable'),('internet_online','fno_external_probe_reachable')):
            if probe.get(source) in (0,1) and type(probe[source]) is int:
                lines.append(f"{target} {probe[source]}")
    if fresh(probe.get('ts')):
        for source, target in (("router_ms", "fno_router_tcp_latency_ms"),("internet_ms", "fno_external_tcp_latency_ms")):
            if type(probe.get(source)) in (int,float) and math.isfinite(probe[source]):
                lines.extend((f"# TYPE {target} gauge", f"{target} {probe[source]}"))
    if fresh(router.get('ts')):
        for source, target in (("cpu_pct","fno_huawei_cpu_percent"),("memory_pct","fno_huawei_memory_percent"),
                               ("uptime_seconds","fno_huawei_uptime_seconds"),("optical_rx_dbm","fno_huawei_optical_rx_dbm"),
                               ("wan_rx_bytes_total","fno_huawei_wan_rx_bytes_total"),("wan_tx_bytes_total","fno_huawei_wan_tx_bytes_total")):
            if type(mt.get(source)) in (int, float) and math.isfinite(mt[source]):
                lines.extend((f"# TYPE {target} gauge", f"{target} {mt[source]}"))
    for d in status["devices"]:
        if d["online"] in (0,1) and type(d["online"]) is int and fresh(d.get('sampled_at')):
            label = d["ip"].replace('\\','\\\\').replace('"','\\"')
            lines.append(f'fno_device_reachable{{ip="{label}"}} {d["online"]}')
    return "\n".join(lines)+"\n"
