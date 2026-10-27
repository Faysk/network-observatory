"""Rebuildable chart projections on the SAME volume as the lossless archive.

No retention changes, network calls, internal cache or approximated aggregates.
Projections retain each observation; aggregation still happens for the requested
window. Missing/invalidated rows fall back to original payloads during migration.
"""
import json
import math
import sqlite3
import warnings

HOST_EXPRESSIONS = {
    'cpu': "CASE WHEN json_type(payload,'$.cpu.usagePercent') IN ('integer','real') AND json_extract(payload,'$.cpu.usagePercent') BETWEEN 0 AND 100 THEN json_extract(payload,'$.cpu.usagePercent') END",
    'memory': "CASE WHEN json_type(payload,'$.memory.usedMB') IN ('integer','real') AND json_type(payload,'$.memory.totalMB') IN ('integer','real') AND json_extract(payload,'$.memory.usedMB') BETWEEN 0 AND json_extract(payload,'$.memory.totalMB') THEN 100.0*json_extract(payload,'$.memory.usedMB')/nullif(json_extract(payload,'$.memory.totalMB'),0) END",
    'rx': "CASE WHEN json_type(payload,'$.network.rxMbps') IN ('integer','real') AND json_extract(payload,'$.network.rxMbps')>=0 THEN json_extract(payload,'$.network.rxMbps') END",
    'tx': "CASE WHEN json_type(payload,'$.network.txMbps') IN ('integer','real') AND json_extract(payload,'$.network.txMbps')>=0 THEN json_extract(payload,'$.network.txMbps') END",
    'battery': "CASE WHEN json_type(payload,'$.battery.levelPercent') IN ('integer','real') AND json_extract(payload,'$.battery.levelPercent') BETWEEN 0 AND 100 THEN json_extract(payload,'$.battery.levelPercent') END",
    # SQLite AVG(text) silently coerces nonnumeric strings to 0. Keep invalid
    # sensor readings NULL; do not fabricate zero degrees or milliseconds.
    'temp': "CASE WHEN json_type(payload,'$.battery.temperatureC') IN ('integer','real') AND json_extract(payload,'$.battery.temperatureC') BETWEEN -100 AND 200 THEN json_extract(payload,'$.battery.temperatureC') END",
    'latency': "CASE WHEN json_type(payload,'$.network.latencyMs') IN ('integer','real') AND json_extract(payload,'$.network.latencyMs') BETWEEN 0 AND 1000000 THEN json_extract(payload,'$.network.latencyMs') END",
    'storage': "(SELECT 100.0*json_extract(v.value,'$.usedGB')/nullif(json_extract(v.value,'$.totalGB'),0) FROM json_each(payload,'$.storage') v WHERE json_extract(v.value,'$.id')='internal' AND json_type(v.value,'$.usedGB') IN ('integer','real') AND json_type(v.value,'$.totalGB') IN ('integer','real') AND json_extract(v.value,'$.usedGB') BETWEEN 0 AND json_extract(v.value,'$.totalGB') LIMIT 1)",
}


def safe_project(db, fn, *args):
    """A rebuildable projection must not prevent a valid raw observation commit.

    If SQLite has rolled back the whole transaction (for example ENOSPC), raise:
    only a surviving raw transaction can be reported as successfully recorded.
    """
    db.execute('SAVEPOINT chart_projection')
    try:
        fn(db, *args)
    except (sqlite3.Error, OSError, ValueError) as exc:
        if not db.in_transaction:
            raise
        db.execute('ROLLBACK TO chart_projection')
        db.execute('RELEASE chart_projection')
        warnings.warn('Chart projection failed; raw transaction retained and history uses fallback', RuntimeWarning)
        return type(exc).__name__
    db.execute('RELEASE chart_projection')
    return None


def exists(db, table):
    return db.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?', (table,)).fetchone() is not None


def init_host(db):
    objects = ('host_chart_points', 'host_chart_invalidate_delete', 'host_chart_invalidate_update')
    if db.execute('SELECT COUNT(*) FROM sqlite_master WHERE name IN (?,?,?)', objects).fetchone()[0] == 3 and any(row[1]=='projection_version' for row in db.execute('PRAGMA table_info(host_chart_points)')):
        return
    # No REAL affinity: preserve JSON number/text/null semantics for SQLite AVG.
    columns = ','.join('"'+name+'"' for name in HOST_EXPRESSIONS)
    db.execute('SAVEPOINT chart_schema')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS host_chart_points(ts REAL PRIMARY KEY,'+columns+',projection_version INTEGER NOT NULL DEFAULT 3) WITHOUT ROWID')
        if not any(row[1]=='projection_version' for row in db.execute('PRAGMA table_info(host_chart_points)')):
            db.execute('ALTER TABLE host_chart_points ADD COLUMN projection_version INTEGER NOT NULL DEFAULT 1')
        for operation in ('DELETE', 'UPDATE'):
            db.execute(f'CREATE TRIGGER IF NOT EXISTS host_chart_invalidate_{operation.lower()} AFTER {operation} ON host_samples '
                       'BEGIN DELETE FROM host_chart_points WHERE ts=OLD.ts; END')
        db.execute('RELEASE chart_schema')
    except BaseException:
        db.execute('ROLLBACK TO chart_schema');db.execute('RELEASE chart_schema')
        raise


def project_host(db, stamp):
    columns = ','.join('"'+name+'"' for name in HOST_EXPRESSIONS)
    db.execute('INSERT OR REPLACE INTO host_chart_points(ts,'+columns+',projection_version) SELECT ts,'+
               ','.join(HOST_EXPRESSIONS.values())+',3 FROM host_samples WHERE ts=?', (stamp,))


def query_host(db, cutoff, bucket, until=None):
    until = float('inf') if until is None else until
    names = list(HOST_EXPRESSIONS)
    values = ','.join('"'+name+'"' for name in names)
    averages = ','.join('AVG("'+name+'")' for name in names)
    if exists(db, 'host_chart_points') and any(row[1]=='projection_version' for row in db.execute('PRAGMA table_info(host_chart_points)')):
        source = ('SELECT ts,'+values+' FROM host_chart_points WHERE ts>=? AND ts<=? AND projection_version=3 UNION ALL '
                  'SELECT ts,'+','.join(HOST_EXPRESSIONS.values())+' FROM host_samples r '
                  'WHERE ts>=? AND ts<=? AND NOT EXISTS(SELECT 1 FROM host_chart_points p WHERE p.ts=r.ts AND p.projection_version=3)')
        parameters = (cutoff, until, cutoff, until, bucket)
    else:
        source = ('SELECT ts,'+','.join(expression+' AS "'+name+'"' for name, expression in HOST_EXPRESSIONS.items())+
                  ' FROM host_samples WHERE ts>=? AND ts<=?')
        parameters = (cutoff, until, bucket)
    return db.execute('SELECT MIN(ts),'+averages+' FROM ('+source+
                      ') GROUP BY CAST(ts/? AS INTEGER) ORDER BY MIN(ts)', parameters).fetchall()


def init_router(db):
    objects = ['history_versions', 'router_chart_points', 'client_chart_points',
               'idx_router_chart_points_id', 'idx_client_chart_points_id']
    objects += ['history_version_'+source+'_'+op for source in ('clients', 'overview', 'events') for op in ('insert', 'update', 'delete')]
    objects += [table+'_invalidate_'+op for table in ('router_chart_points', 'client_chart_points') for op in ('delete', 'update')]
    if db.execute('SELECT COUNT(*) FROM sqlite_master WHERE name IN ('+','.join('?' for _ in objects)+')', objects).fetchone()[0] == len(objects):
        return
    db.execute('SAVEPOINT chart_schema')
    try:
        _init_router_schema(db)
        db.execute('RELEASE chart_schema')
    except BaseException:
        db.execute('ROLLBACK TO chart_schema');db.execute('RELEASE chart_schema')
        raise


def _init_router_schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS history_versions(source TEXT PRIMARY KEY,revision INTEGER NOT NULL) WITHOUT ROWID')
    for raw, source in [('router_client_samples', 'clients'), ('huawei_samples', 'overview'), ('events', 'events')]:
        db.execute('INSERT OR IGNORE INTO history_versions VALUES(?,0)', (source,))
        for operation in ('INSERT', 'UPDATE', 'DELETE'):
            db.execute(f'CREATE TRIGGER IF NOT EXISTS history_version_{source}_{operation.lower()} AFTER {operation} ON {raw} '
                       f"BEGIN UPDATE history_versions SET revision=revision+1 WHERE source='{source}'; END")
    for raw, table, key in (
        ('huawei_samples', 'router_chart_points', 'ts,id'),
        ('router_client_samples', 'client_chart_points', 'mac,ts,id'),
    ):
        fields = 'mac TEXT NOT NULL,' if raw == 'router_client_samples' else ''
        db.execute(f'CREATE TABLE IF NOT EXISTS {table}({fields}ts TEXT NOT NULL,id INTEGER NOT NULL,'
                   f'payload TEXT NOT NULL,PRIMARY KEY({key})) WITHOUT ROWID')
        db.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_id ON {table}(id)')
        for operation in ('DELETE', 'UPDATE'):
            db.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_invalidate_{operation.lower()} AFTER {operation} ON {raw} '
                       f'BEGIN DELETE FROM {table} WHERE id=OLD.id; END')

def router_revision(db):
    if exists(db, 'history_versions'):
        return tuple(db.execute('SELECT revision FROM history_versions WHERE source=?', (name,)).fetchone()[0]
                     for name in ('clients', 'events'))
    return tuple(db.execute('SELECT COALESCE(MAX(id),0) FROM '+name).fetchone()[0]
                 for name in ('router_client_samples', 'events'))


def overview_point(payload):
    from .wifi_links import band_rssi
    point = dict(payload.get('metrics', {}))
    wan = next((k for k, v in payload.get('wan_states', {}).items() if 'Internet' in v.get('services', [])), None)
    counters = payload.get('interfaces', {}).get(wan, {})
    point.update(wan_rx_bytes=counters.get('rx_bytes'), wan_tx_bytes=counters.get('tx_bytes'))
    if 'clients' in payload:
        point['online_clients'] = sum(c.get('reported_status') == 'Online' for c in payload['clients'])
    # Compute a sample mean only from plausible, finite AP-reported signal
    # readings. Booleans/text (including "unknown") must not become 1 or 0,
    # and malformed legacy rows must not crash the historical projection.
    stations=payload.get('stations')
    stations=stations if isinstance(stations,list) else []
    values=[v for station in stations[:128] if isinstance(station,dict)
            for v in [station.get('rssi_dbm')]
            if type(v) in (int,float) and math.isfinite(v) and -200<=v<=0]
    point['rssi_dbm']=sum(values)/len(values) if values else None
    point.update(band_rssi(payload))
    # Old compact rows may have accepted invalid station RSSI during an
    # arithmetic mean. Mark the corrected calculation to force raw fallback.
    point['_signal_calc_version']=1
    return point


def client_point(payload, wifi=None):
    point = {k: payload[k] for k in ('names', 'ips', 'ports', 'reported_status') if k in payload}
    stations = payload.get('stations', [])
    point['stations'] = [{k: stations[0][k] for k in
                          ('rssi_dbm', 'snr_db_reported', 'rx_link_mbps', 'tx_link_mbps', 'interface')
                          if k in stations[0]}] if stations else []
    from .wifi_links import station_links
    point['wifi_links'] = station_links(stations, wifi)
    return point


def project_overview(db, observation_id, stamp, payload):
    db.execute('INSERT OR REPLACE INTO router_chart_points(ts,id,payload) VALUES(?,?,?)',
               (stamp, observation_id, json.dumps(overview_point(payload), allow_nan=False, separators=(',', ':'))))


def project_client(db, observation_id, stamp, mac, payload, wifi=None):
    db.execute('INSERT OR REPLACE INTO client_chart_points(mac,ts,id,payload) VALUES(?,?,?,?)',
               (mac, stamp, observation_id, json.dumps(client_point(payload, wifi), allow_nan=False, separators=(',', ':'))))


def device_rows(db, mac, start, end):
    if not exists(db, 'client_chart_points'):
        return db.execute('SELECT ts,payload FROM router_client_samples WHERE mac=? AND ts>=? AND ts<=? ORDER BY ts,id',
                          (mac, start, end))
    return db.execute('SELECT ts,payload FROM ('
                      'SELECT ts,id,payload FROM client_chart_points WHERE mac=? AND ts>=? AND ts<=? UNION ALL '
                      'SELECT ts,id,payload FROM router_client_samples r WHERE mac=? AND ts>=? AND ts<=? '
                      'AND NOT EXISTS(SELECT 1 FROM client_chart_points p WHERE p.id=r.id)) ORDER BY ts,id',
                      (mac, start, end, mac, start, end))


def overview_rows(db, start, end):
    if not exists(db, 'router_chart_points'):
        for row in db.execute('SELECT ts,payload FROM huawei_samples WHERE ts>=? AND ts<=? ORDER BY ts,id', (start, end)):
            yield row['ts'], overview_point(json.loads(row['payload']))
        return
    rows = db.execute('SELECT ts,payload,compact FROM ('
                      'SELECT ts,id,payload,1 AS compact FROM router_chart_points WHERE ts>=? AND ts<=? '
                      "AND json_extract(payload,'$._signal_calc_version')=1 UNION ALL "
                      'SELECT ts,id,payload,0 AS compact FROM huawei_samples r WHERE ts>=? AND ts<=? '
                      'AND NOT EXISTS(SELECT 1 FROM router_chart_points p WHERE p.id=r.id '
                      "AND json_extract(p.payload,'$._signal_calc_version')=1)) ORDER BY ts,id",
                      (start, end, start, end))
    for row in rows:
        payload = json.loads(row['payload'])
        yield row['ts'], payload if row['compact'] else overview_point(payload)


def refresh_wifi_context(db, batch=64, cursors=None):
    """Rebuild only old compact rows lacking Wi-Fi keys; never edit raw archive.

    Called explicitly by the offline read-model builder, not by a live GET.
    """
    init_router(db)
    cursors = cursors if cursors is not None else {}
    total = 0
    for table, raw, prefix in (('router_chart_points', 'huawei_samples', 'wifi_overview'),
                               ('client_chart_points', 'router_client_samples', 'wifi_client')):
        after = cursors.get(prefix, 0)
        marker = '$.rssi_24_dbm' if prefix == 'wifi_overview' else '$.wifi_links'
        # Correct existing overview compact rows as well as absent Wi-Fi band
        # metadata; old RSSI means may contain coerced boolean/invalid values.
        mismatch=(" OR COALESCE(json_extract(p.payload,'$._signal_calc_version'),0)<>1"
                  if prefix=='wifi_overview' else "")
        rows = db.execute(
            f"SELECT r.* FROM {table} p JOIN {raw} r ON r.id=p.id "
            "WHERE p.id>? AND (json_type(p.payload,?) IS NULL"+mismatch+") "
            "ORDER BY p.id LIMIT ?",
            (after, marker, batch)).fetchall()
        parent_wifi = {}
        for row in rows:
            payload = json.loads(row['payload'])
            if prefix == 'wifi_overview':
                project_overview(db, row['id'], row['ts'], payload)
            else:
                if row['sample_id'] not in parent_wifi:
                    parent = db.execute('SELECT payload FROM huawei_samples WHERE id=?', (row['sample_id'],)).fetchone()
                    parent_wifi[row['sample_id']] = json.loads(parent['payload']).get('wifi', {}) if parent else {}
                project_client(db, row['id'], row['ts'], row['mac'], payload, parent_wifi[row['sample_id']])
        total += len(rows)
        if rows:
            cursors[prefix] = rows[-1]['id']
    return total


def backfill_router(db, batch=64, cursors=None):
    """One bounded transaction, resumable, idempotent, including older backfill."""
    init_router(db)
    total = 0
    for raw, table, project in (
        ('huawei_samples', 'router_chart_points', project_overview),
        ('router_client_samples', 'client_chart_points', project_client),
    ):
        after = cursors.get(raw, 0) if cursors is not None else 0
        rows = db.execute(f'SELECT * FROM {raw} r WHERE id>? AND NOT EXISTS(SELECT 1 FROM {table} p WHERE p.id=r.id) ORDER BY id LIMIT ?', (after, batch)).fetchall()
        parent_wifi = {}
        for row in rows:
            payload = json.loads(row['payload'])
            if raw == 'huawei_samples':
                project(db, row['id'], row['ts'], payload)
            else:
                if row['sample_id'] not in parent_wifi:
                    parent = db.execute('SELECT payload FROM huawei_samples WHERE id=?', (row['sample_id'],)).fetchone()
                    parent_wifi[row['sample_id']] = json.loads(parent['payload']).get('wifi', {}) if parent else {}
                project(db, row['id'], row['ts'], row['mac'], payload, parent_wifi[row['sample_id']])
        total += len(rows)
        if rows and cursors is not None:
            cursors[raw] = rows[-1]['id']
    return total


def backfill_host(db, batch=32, cursors=None):
    init_host(db)
    after = cursors.get('host', -1e300) if cursors is not None else -1e300
    rows = db.execute('SELECT ts FROM host_samples r WHERE ts>? AND NOT EXISTS('
                      'SELECT 1 FROM host_chart_points p WHERE p.ts=r.ts AND p.projection_version=3) ORDER BY ts LIMIT ?', (after, batch)).fetchall()
    for row in rows:
        project_host(db, row[0])
    if rows and cursors is not None:
        cursors['host'] = rows[-1][0]
    return len(rows)
