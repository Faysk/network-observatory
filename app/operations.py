"""Passive, local Observatory health and configurable read-only alert evaluation.

No polling, router calls, remote delivery, mutation on GET or network access.
The JSON rules file (optional) is controlled by the S7 operator, never HTTP.
All outputs omit credentials, MACs, addresses, paths and unfiltered logs.
"""
import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from . import core

CONFIG_ENV = 'FNO_ALERT_RULES_FILE'
DEFAULTS = {
    'enabled': True,
    'collector_stale_minutes': 15,
    'host_stale_minutes': 5,
    'database_free_gib_warning': 2,
    'database_free_gib_critical': 1,
    'process_rss_mb_warning': 250,
    'sqlite_growth_mb_day_warning': 250,
    'change_window_minutes': 90,
    'change_sources': ['firewall_v4', 'firewall_v6', 'wan_acl', 'mac_policy', 'wps', 'file_services'],
}
LIMITS = {
    'collector_stale_minutes': (5, 1440),
    'host_stale_minutes': (3, 1440),
    'database_free_gib_warning': (0.5, 100),
    'database_free_gib_critical': (0.25, 100),
    'process_rss_mb_warning': (50, 4096),
    'sqlite_growth_mb_day_warning': (10, 10000),
    'change_window_minutes': (5, 1440),
}
VALID_CHANGE_SOURCES = frozenset(DEFAULTS['change_sources'] +
    ['upnp','band_steering','wifi_schedule','wan_nat','dlna','guest_limits','guest_network',
     'ipv6_lan','lan_settings','radio_settings','topology','wifi_backhaul','wifi_features','voice_schedule'])


def validate_rules(user):
    if not isinstance(user, dict) or set(user) - set(DEFAULTS):
        raise ValueError('Unknown configuration field')
    if 'enabled' in user and type(user['enabled']) is not bool:
        raise ValueError('enabled must be boolean')
    for name, (lo, hi) in LIMITS.items():
        if name in user:
            v = user[name]
            if type(v) not in (float, int) or not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError('Invalid threshold: ' + name)
    values = user.get('change_sources')
    if values is not None:
        if not isinstance(values,list) or len(values) > 20 or len(set(map(str,values))) != len(values):
            raise ValueError('Invalid change sources')
        if any(type(v) is not str or v not in VALID_CHANGE_SOURCES for v in values):
            raise ValueError('Unrecognized change source')
    config = {**DEFAULTS, **user}
    if config['database_free_gib_critical'] >= config['database_free_gib_warning']:
        raise ValueError('Critical reserve must be smaller than warning reserve')
    return config


def load_rules():
    path = os.environ.get(CONFIG_ENV)
    if not path:
        return dict(DEFAULTS), 'defaults'
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size > 8192:
            raise ValueError('configuration size')
        config = json.loads(p.read_text(encoding='utf-8'))
        return validate_rules(config), 'local_file'
    except (OSError, UnicodeError, ValueError, TypeError):
        # Fail safely: never silently operate with unknown customized rules.
        return {**DEFAULTS, 'enabled': False}, 'invalid_file_disabled'


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def age_minutes(stamp, now):
    if not isinstance(stamp, str):
        return None
    try:
        value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if value.tzinfo is None:
            return None
        minutes = (now - value.astimezone(timezone.utc)).total_seconds() / 60
        return round(max(0, minutes), 1) if minutes >= -2 else None
    except (ValueError, OverflowError):
        return None


def sizes_and_storage(path):
    """Stat only configured files/volume. Do not create missing directories."""
    file_info = {}
    for key, p in [('database',path), ('wal', Path(str(path)+'-wal'))]:
        try:
            file_info[key] = round(p.stat().st_size / 1048576, 2)
        except OSError:
            file_info[key] = None
    try:
        if not path.parent.is_dir():
            raise OSError('missing directory')
        st = os.statvfs(path.parent)
        free = st.f_bavail * st.f_frsize / 1073741824
        file_info['availableGiB'] = round(free,2)
        file_info['volumeAccessible'] = True
    except (OSError, AttributeError):
        file_info.update(availableGiB=None, volumeAccessible=False)
    return file_info


def history(host_db, now, limit=360):
    """Use only recent already archived host samples. Avoid full JSON archive scan."""
    if not host_db.is_file():
        return [], False
    cutoff = (now-timedelta(hours=24)).timestamp()
    try:
        with sqlite3.connect(host_db.resolve().as_uri()+'?mode=ro', uri=True, timeout=1) as db:
            rows = db.execute(
                'SELECT ts,payload FROM host_samples WHERE ts>=? AND ts<=? ORDER BY ts DESC LIMIT ?',
                (cutoff, now.timestamp()+60, limit+1)).fetchall()
        truncated = len(rows)>limit
        points = []
        for ts,raw in reversed(rows[:limit]):
            sample = json.loads(raw)
            diag = sample.get('diagnostics') or {}
            storage = next((s for s in sample.get('storage',[]) if s.get('id')=='sd'),None)
            points.append({
                'ts': datetime.fromtimestamp(ts,timezone.utc).isoformat(),
                'status': 'ok',
                'rss_mb': diag.get('processRssMB') if finite(diag.get('processRssMB')) else None,
                'database_mb': diag.get('databaseMB') if finite(diag.get('databaseMB')) else None,
                'api_p95_ms': diag.get('apiP95Ms') if finite(diag.get('apiP95Ms')) else None,
                'collector_ms': diag.get('routerCollectionMs') if finite(diag.get('routerCollectionMs')) else None,
                'sd_free_gib': round(storage['availableBytes']/1073741824,2) if storage and finite(storage.get('availableBytes')) else None,
            })
        return points,truncated
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return [],False


def alert(key, severity, title, detail, source, observed_at=None):
    return {'id':key,'severity':severity,'title':title,'detail':detail,
            'source':source,'observedAt':observed_at}


def read(now=None, host_snapshot=None, changes=None, rules=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('timezone-aware clock required')
    if rules is None:
        rules, rules_source = load_rules()
    else:
        rules = validate_rules(rules)
        rules_source = 'injected'
    from . import host_telemetry
    if host_snapshot is None:
        host_snapshot = host_telemetry._monitor.snapshot() if host_telemetry._monitor else {}
    if not isinstance(host_snapshot,dict):
        host_snapshot = {}
    diag = host_snapshot.get('diagnostics') or {}
    store = sizes_and_storage(core.DB_PATH)
    host_db = core.DB_PATH.parent/'host-telemetry.db'
    points, truncated = history(host_db,now)
    host_age = age_minutes(host_snapshot.get('timestamp'),now)
    collector = dict(core.COLLECTOR_STATE)
    collector_age = age_minutes(collector.get('last_success'),now)
    rss = diag.get('processRssMB') if finite(diag.get('processRssMB')) else None
    api95 = diag.get('apiP95Ms') if finite(diag.get('apiP95Ms')) else None
    out = []
    if rules['enabled']:
        if not store['volumeAccessible']:
            out.append(alert('storage_unavailable','critical','Volume de dados indisponível',
                             'Não foi possível consultar o volume configurado; confirmar a montagem antes de qualquer escrita.','system'))
        elif store['availableGiB'] is not None:
            free=store['availableGiB']
            level=('critical' if free < rules['database_free_gib_critical'] else
                   'warning' if free < rules['database_free_gib_warning'] else None)
            if level:
                out.append(alert('storage_reserve',level,'Pouco espaço no volume do arquivo',
                                 str(free)+' GiB disponíveis no volume configurado.','storage'))
        if collector.get('state') in ('auth_blocked','backoff'):
            out.append(alert('collector_state','warning','Coletor precisa de atenção',
                             'Estado reportado: '+collector['state']+'. Não assume falha na Internet.','collector'))
        if collector_age is not None and collector_age >= rules['collector_stale_minutes']:
            out.append(alert('collector_stale','warning','Recolha Huawei atrasada',
                             'Última recolha concluída há '+str(collector_age)+' minutos.','collector',
                             collector.get('last_success')))
        elif collector_age is None and collector.get('state') not in ('not_started',None):
            out.append(alert('collector_unverified','info','Sucesso de recolha não confirmado',
                             'Sem horário válido da última recolha nesta execução.','collector'))
        if host_age is not None and host_age >= rules['host_stale_minutes']:
            out.append(alert('host_stale','warning','Telemetria do S7 desatualizada',
                             'Última amostra do host há '+str(host_age)+' minutos.','host',host_snapshot.get('timestamp')))
        if rss is not None and rss >= rules['process_rss_mb_warning'] and host_age is not None and host_age < rules['host_stale_minutes']:
            out.append(alert('rss_high','warning','RAM do processo elevada',
                             str(round(rss,1))+' MB de RSS reportados pelo S7.','host'))
        # Use at least 6h of actual samples, not two very close points extrapolated to a day.
        db_points = [p for p in points if finite(p.get('database_mb'))]
        growth = None
        if len(db_points)>=2:
            span = (datetime.fromisoformat(db_points[-1]['ts'])-datetime.fromisoformat(db_points[0]['ts'])).total_seconds()/3600
            if span>=6 and db_points[-1]['database_mb']>=db_points[0]['database_mb']:
                growth=round((db_points[-1]['database_mb']-db_points[0]['database_mb'])*24/span,2)
        if growth is not None and growth>=rules['sqlite_growth_mb_day_warning']:
            out.append(alert('db_growth','warning','Crescimento elevado do SQLite',
                             str(growth)+' MB/dia estimados a partir de '+str(round(span,1))+' h observadas.','database'))
        if changes is None:
            changes=[]
            if store['volumeAccessible'] and core.DB_PATH.is_file():
                try:
                    with sqlite3.connect(core.DB_PATH.resolve().as_uri()+'?mode=ro',uri=True,timeout=1) as db:
                        cutoff=(now-timedelta(minutes=rules['change_window_minutes'])).isoformat()
                        changes=[dict(zip(('id','source','previous_at','observed_at','crosses_gap'),row))
                            for row in db.execute(
                            'SELECT id,source,previous_at,observed_at,crosses_gap FROM router_changes '
                            'WHERE observed_at>=? AND observed_at<=? ORDER BY observed_at DESC,id DESC LIMIT 40',
                            (cutoff,now.isoformat()))]
                except (OSError, sqlite3.Error):
                    changes=[]
        for item in (changes or [])[:40]:
            if item.get('source') not in rules['change_sources'] or item.get('crosses_gap'):
                continue
            delay=age_minutes(item.get('observed_at'),now)
            if delay is None or delay>rules['change_window_minutes']:
                continue
            if not item.get('previous_at') or age_minutes(item['previous_at'],now) is None:
                continue
            # Hash/ID are stable identifiers, no repeated notifications are sent.
            out.append(alert('config_'+str(item['id']),'info','Alteração de configuração observada',
                'Mudança reportada em '+str(item['source'])+'; comparar observações para avaliar o significado.',
                item['source'],item['observed_at']))
    summary={
        'processRssMB': rss if host_age is not None and host_age < rules['host_stale_minutes'] else None,
        'apiP95Ms': api95 if host_age is not None and host_age < rules['host_stale_minutes'] else None,
        'hostSampleAgeMinutes':host_age,
        'collectorSuccessAgeMinutes':collector_age,
        'collectorState':collector.get('state','unknown'),
        'databaseMB':store['database'],
        'walMB':store['wal'],
        'volumeFreeGiB':store['availableGiB'],
        'volumeAccessible':store['volumeAccessible'],
        'growthMBPerDay':growth if 'growth' in locals() else None,
    }
    return {
        'generatedAt':now.isoformat(),
        'health':summary,
        'alerts':out[:50],
        'alertCount':len(out),
        'rules':rules,
        'rulesSource':rules_source,
        'history':{'points':points,'truncated':truncated,'sampling':'existing S7 telemetry only, at most 360 most recent observations in 24 h',
                   'metrics':[{'key':'rss_mb','label':'RAM do processo','unit':'MB'},
                              {'key':'database_mb','label':'Tamanho SQLite principal','unit':'MB'},
                              {'key':'sd_free_gib','label':'MicroSD livre','unit':'GiB'},
                              {'key':'api_p95_ms','label':'API p95','unit':'ms'},
                              {'key':'collector_ms','label':'Tempo recolha Huawei','unit':'ms'}]},
        'semantics':{
            'notifications':'Passive read-only findings. No e-mail, push, remote reporting, acknowledgement or background writes.',
            'changes':'Only configured tracked sources, with two observed valid snapshots and no marked gap; not exact change time.',
            'unknown':'Missing values are null, never zeros. Health samples may be stale or unavailable.',
            'growth':'>= 6h of host samples required; estimated slope, never a forecast of disk exhaustion.',
        }
    }
