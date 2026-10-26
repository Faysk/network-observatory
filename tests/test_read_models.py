"""Projection correctness over synthetic raw archives, including partial rebuilds."""
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app import core, historian, read_models
from app.host_telemetry import HostMonitor, empty_snapshot
from tools.build_read_models import rebuild


class HostProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.monitor = HostMonitor(Path(self.tmp.name)/'router.db')
        self.now = (int(time.time())//3600)*3600-1800
        with closing(sqlite3.connect(self.monitor.path)) as db, db:
            db.execute('CREATE TABLE host_samples(ts REAL PRIMARY KEY,payload TEXT NOT NULL)')
            for i in range(5):
                s = empty_snapshot()
                s['cpu']['usagePercent'] = [0, 25, None, 75, 100][i]
                s['memory'].update(totalMB=100 if i != 2 else 0, usedMB=25)
                s['network'].update(rxMbps=i, txMbps=None if i == 2 else 0)
                s['storage'] = [{'id':'internal','usedGB': 0, 'totalGB': 64}]
                db.execute('INSERT INTO host_samples VALUES(?,?)', (self.now-1000+i*60, json.dumps(s)))

    def tearDown(self):
        self.tmp.cleanup()

    def query(self):
        with closing(sqlite3.connect(self.monitor.path)) as db:
            return read_models.query_host(db, self.now-2000, 3600)

    def test_exact_aggregation_after_partial_full_and_repeated_rebuild(self):
        legacy = self.query()
        self.assertEqual(legacy[0][1], 50)
        self.assertEqual(legacy[0][2], 25)
        self.assertEqual(legacy[0][4], 0)
        with closing(sqlite3.connect(self.monitor.path)) as db, db:
            read_models.backfill_host(db, 2)
        self.assertEqual(self.query(), legacy)
        self.assertEqual(rebuild(self.monitor.path, 'host', 2), 3)
        self.assertEqual(self.query(), legacy)
        self.assertEqual(rebuild(self.monitor.path, 'host'), 0)

    def test_storage_identifies_internal_and_legacy_projection_falls_back(self):
        with closing(sqlite3.connect(self.monitor.path)) as db,db:
            db.execute('DELETE FROM host_samples')
            sample=empty_snapshot();sample['storage']=[{'id':'sd','usedGB':60,'totalGB':64},{'id':'internal','usedGB':10,'totalGB':20}]
            db.execute('INSERT INTO host_samples VALUES(?,?)',(self.now,json.dumps(sample)))
            columns=','.join('"'+k+'"' for k in read_models.HOST_EXPRESSIONS)
            db.execute('CREATE TABLE host_chart_points(ts REAL PRIMARY KEY,'+columns+') WITHOUT ROWID')
            db.execute('INSERT INTO host_chart_points(ts,storage) VALUES(?,99)',(self.now,))
            before=db.execute('SELECT payload FROM host_samples').fetchone()[0]
            self.assertEqual(read_models.query_host(db,self.now-1,60)[0][-1],50)
            read_models.init_host(db)
            self.assertEqual(read_models.query_host(db,self.now-1,60)[0][-1],50)
            self.assertEqual(read_models.backfill_host(db),1)
            self.assertEqual(read_models.query_host(db,self.now-1,60)[0][-1],50)
            self.assertEqual(db.execute('SELECT payload FROM host_samples').fetchone()[0],before)
            self.assertEqual(read_models.query_host(db,self.now-1,60,until=self.now-0.5),[])
            db.execute('UPDATE host_samples SET payload=?',(json.dumps({'storage':[{'id':'sd','usedGB':60,'totalGB':64}]}),))
            self.assertIsNone(read_models.query_host(db,self.now-1,60)[0][-1])

    def test_updates_deletes_and_backfill_are_not_hidden_by_projection(self):
        rebuild(self.monitor.path, 'host')
        with closing(sqlite3.connect(self.monitor.path)) as db, db:
            db.execute("UPDATE host_samples SET payload=json_set(payload,'$.cpu.usagePercent',50) WHERE ts=?", (self.now-1000,))
            db.execute('DELETE FROM host_samples WHERE ts=?', (self.now-1000+60,))
        self.assertEqual(self.query()[0][1], 75)
        self.assertEqual(rebuild(self.monitor.path, 'host'), 1)
        self.assertEqual(self.query()[0][1], 75)

    def test_projection_failure_retains_raw_and_falls_back(self):
        self.monitor.persist(empty_snapshot())
        with closing(sqlite3.connect(self.monitor.path)) as db:
            before = db.execute('SELECT COUNT(*) FROM host_samples').fetchone()[0]
            projected = db.execute('SELECT COUNT(*) FROM host_chart_points').fetchone()[0]
        with patch.object(read_models, 'project_host', side_effect=OSError('synthetic full disk')):
            with self.assertWarns(RuntimeWarning):
                self.monitor.persist(empty_snapshot())
        with closing(sqlite3.connect(self.monitor.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM host_samples').fetchone()[0], before+1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM host_chart_points').fetchone()[0], projected)
        self.assertEqual(self.monitor.projection_error,'OSError')
        self.assertTrue(self.monitor.history('cpu','24h'))

    def test_no_internal_or_missing_volume_fallback(self):
        missing = Path(self.tmp.name)/'absent-sd'/'new.db'
        with self.assertRaises(ValueError):
            rebuild(missing, 'host')
        self.assertFalse(missing.parent.exists())


class RouterProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'sd.db'
        self.patch = patch.object(core, 'DB_PATH', self.path)
        self.patch.start()
        core.init_db()
        self.end = datetime.now(timezone.utc)
        self.start = self.end-timedelta(days=1)
        self.mac = '02:00:00:00:00:01'
        with core.connect() as db:
            for i, age in enumerate([1000, 940, 880, 400, 340]):
                ts = (self.end-timedelta(seconds=age)).isoformat()
                payload = {'mac': self.mac, 'names': ['Fixture <name>'], 'ips': ['192.0.2.'+str(i+1)],
                           'ports': ['wlan0'], 'reported_status': 'Offline' if i == 2 else 'Online',
                           'stations': [{'rssi_dbm': 0 if i == 0 else -60, 'rx_link_mbps': 0, 'tx_link_mbps': None,
                                         'snr_db_reported': 25, 'interface': 'wlan0', 'unneeded_field': 'x'*4000}]}
                db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)', (1, ts, self.mac, json.dumps(payload)))
                sample = {'metrics': {'cpu_pct': i, 'memory_pct': None}, 'clients': [payload],
                          'wan_states': {'wan0': {'services': ['Internet']}},
                          'interfaces': {'wan0': {'rx_bytes': 0, 'tx_bytes': 123}}, 'stations': payload['stations']}
                db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)', (ts, json.dumps(sample)))

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def bundles(self):
        with patch.object(historian, 'window', return_value=(self.start, self.end)):
            return historian._device_history_uncached(self.mac.replace(':', '')), historian._overview_history_uncached()

    def test_lossless_semantics_during_partial_full_and_repeated_rebuild(self):
        before = self.bundles()
        with core.connect() as db:
            raw = [r[0] for r in db.execute('SELECT payload FROM router_client_samples ORDER BY id')]
            read_models.backfill_router(db, 2)
        self.assertEqual(self.bundles(), before)
        self.assertEqual(rebuild(self.path, 'router', 2), 6)
        self.assertEqual(self.bundles(), before)
        self.assertEqual(rebuild(self.path, 'router'), 0)
        with core.connect() as db:
            self.assertEqual(raw, [r[0] for r in db.execute('SELECT payload FROM router_client_samples ORDER BY id')])
            self.assertNotIn('unneeded_field', db.execute('SELECT payload FROM client_chart_points LIMIT 1').fetchone()[0])
        self.assertEqual(before[0]['quality']['sample_gaps'], 1)

    def test_raw_update_invalidates_and_falls_back_without_missing_rows(self):
        rebuild(self.path, 'router')
        with core.connect() as db:
            db.execute("UPDATE router_client_samples SET payload=json_set(payload,'$.reported_status','Offline') WHERE id=1")
        self.assertEqual(self.bundles()[0]['presence']['online_samples'], 3)

        self.assertEqual(rebuild(self.path, 'router'), 1)
        self.assertEqual(self.bundles()[0]['presence']['online_samples'], 3)

    def test_device_cache_revision_tracks_updates_not_only_max_id(self):
        identifier=self.mac.replace(':','')
        before=historian.device_history(identifier)['presence']['online_samples']
        with core.connect() as db:
            db.execute("UPDATE router_client_samples SET payload=json_set(payload,'$.reported_status','Offline') WHERE id=1")
        self.assertEqual(historian.device_history(identifier)['presence']['online_samples'], before-1)


class MirrorTests(unittest.TestCase):
    def test_integrated_frontend_matches_reviewed_standalone_release(self):
        import hashlib
        root=Path(__file__).resolve().parents[1]
        metadata=json.loads((root/'docs/INTEGRATED_S7.json').read_text(encoding='utf-8'))
        self.assertEqual(set(metadata['sha256']),{'js/app.js','css/styles.css','index.html'})
        for name,expected in metadata['sha256'].items():
            content=(root/'app/static/s7'/name).read_bytes().replace(b'\r\n',b'\n')
            self.assertEqual(hashlib.sha256(content).hexdigest(),expected,name+' mirror drift')
