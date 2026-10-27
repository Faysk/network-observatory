import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from app import core

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = core.DB_PATH
        core.DB_PATH = Path(self.temp.name) / 'test.db'
        core.init_db()

    def tearDown(self):
        core.DB_PATH = self.old
        self.temp.cleanup()

    def test_initial_metrics_are_unknown(self):
        s = core.get_status()
        self.assertIsNone(s['metrics']['ts'])
        self.assertEqual(s['metrics']['metrics'], {})
        self.assertIsNone(s['probe'])

    def test_unlimited_retention_and_lossless_archive(self):
        old='2000-01-01T00:00:00+00:00'
        with core.connect() as db:
            db.execute('INSERT INTO samples(ts) VALUES(?)',(old,))
            db.execute('INSERT INTO router_metrics(ts,source,payload) VALUES(?,?,?)',(old,'fixture','{}'))
            db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)',(old,'{}'))
            db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',(1,old,'02:00:00:00:00:01','{}'))
            db.execute('INSERT INTO device_samples(ts,device_id,online) VALUES(?,?,?)',(old,1,1))
            db.execute('INSERT INTO events(ts,severity,category,title,detail,source) VALUES(?,?,?,?,?,?)',(old,'info','fixture','fixture','','fixture'))
            with patch.object(core,'RETENTION_DAYS',0):core.prune_history(db)
        for kind in core.ARCHIVE_TABLES:
            self.assertEqual(len(core.get_archive(kind)['rows']),1)
        with core.connect() as db:
            db.executemany('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)',[(old,json.dumps({'sequence':i})) for i in range(5010)])
        seen=[];after=0
        while True:
            page=core.get_archive('huawei',after,1000)
            seen.extend(r['id'] for r in page['rows'])
            if not page['has_more']:break
            self.assertGreater(page['next_after'],after)
            after=page['next_after']
        self.assertEqual(len(seen),5011)
        self.assertEqual(len(set(seen)),5011)
        with patch.object(core,'RETENTION_DAYS',30),core.connect() as db:core.prune_history(db)
        for kind in core.ARCHIVE_TABLES:self.assertEqual(core.get_archive(kind)['rows'],[])
        with self.assertRaises(ValueError):core.get_archive('not-a-table')
        with self.assertRaises(ValueError):core.get_archive(after=-1)
        with self.assertRaises(ValueError):core.get_archive(limit=2001)

    def test_network_address_filter(self):
        self.assertTrue(core.valid_lan_ip('192.168.1.20'))
        self.assertFalse(core.valid_lan_ip('8.8.8.8'))
        self.assertFalse(core.valid_lan_ip('127.0.0.1'))
        self.assertFalse(core.valid_lan_ip('169.254.1.1'))
        self.assertFalse(core.valid_lan_ip('192.168.1.999'))

    def test_router_metric_ingest_validation(self):
        with self.assertRaises(ValueError): core.put_router_metrics({'cpu_pct': 200}, 'test')
        with self.assertRaises(ValueError): core.put_router_metrics({'cpu_pct': True}, 'test')
        for bad in (float('nan'),float('inf'),float('-inf')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                core.put_router_metrics({'memory_pct':bad}, 'test')
        with self.assertRaises(ValueError): core.put_router_metrics({'garbage': 8}, 'test')
        row = core.put_router_metrics({'cpu_pct': 37, 'memory_pct': 13}, 'manual-authorized')
        self.assertEqual(row['cpu_pct'], 37)
        s = core.get_status()
        self.assertEqual(s['metrics']['source'], 'manual-authorized')
        self.assertEqual(s['metrics']['metrics']['memory_pct'], 13)

    def test_devices_lifecycle(self):
        with self.assertRaises(ValueError): core.add_device({'name':'bad','ip':'1.1.1.1'})
        core.add_device({'name':'TCL C7K','ip':'192.168.1.120','type':'tv','port':443})
        with self.assertRaises(ValueError): core.add_device({'name':'duplicate','ip':'192.168.1.120'})
        devices=core.get_status()['devices']; self.assertEqual(len(devices),1)
        self.assertIsNone(devices[0]['online'])
        core.delete_device(devices[0]['id'])
        self.assertEqual(core.get_status()['devices'], [])

    def test_collect_and_events_transition(self):
        values=[(True,1.0),(True,15.0)]
        with patch.object(core,'tcp_probe',side_effect=values):
            core.collect_once()
        status=core.get_status()
        self.assertEqual(status['probe']['router_online'], 1)
        self.assertEqual(len(core.get_history(24)['probes']),1)
        with patch.object(core,'tcp_probe',side_effect=[(False,None),(True,25.0)]):
            core.collect_once()
        event=core.get_events()[0]
        self.assertEqual(event['severity'],'critical')
        self.assertIn('Gateway',event['title'])

    def test_prometheus_omits_missing_router(self):
        result=core.metrics_text()
        self.assertIn('# TYPE fno_router_reachable gauge',result)
        self.assertNotIn('fno_router_reachable 0',result)
        self.assertNotIn('fno_huawei_cpu_percent',result)

    def test_prometheus_only_exports_fresh_observed_values(self):
        current=datetime.now(timezone.utc).isoformat()
        old=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        with core.connect() as db:
            db.execute('INSERT INTO samples(ts,router_online,router_ms,internet_online,internet_ms) VALUES(?,?,?,?,?)',
                       (old,0,None,1,4.5))
            db.execute('INSERT INTO router_metrics(ts,source,payload) VALUES(?,?,?)',
                       (old,'test',json.dumps({'cpu_pct':70})))
        outdated=core.metrics_text()
        self.assertNotIn('fno_router_reachable 0',outdated)
        self.assertNotIn('fno_external_probe_reachable 1',outdated)
        self.assertNotIn('fno_huawei_cpu_percent 70',outdated)
        with core.connect() as db:
            db.execute('INSERT INTO samples(ts,router_online,router_ms,internet_online,internet_ms) VALUES(?,?,?,?,?)',
                       (current,0,12.0,1,4.5))
            db.execute('INSERT INTO router_metrics(ts,source,payload) VALUES(?,?,?)',
                       (current,'test',json.dumps({'cpu_pct':70})))
        fresh=core.metrics_text()
        self.assertIn('fno_router_reachable 0',fresh)
        self.assertIn('fno_external_probe_reachable 1',fresh)
        self.assertIn('fno_huawei_cpu_percent 70',fresh)

    def test_slow_device_probe_does_not_lock_queries_or_resurrect_deleted_device(self):
        core.add_device({'name':'Slow fixture','ip':'192.168.1.190','port':443})
        entered=threading.Event();release=threading.Event();errors=[]
        def slow_device(_row):
            entered.set()
            if not release.wait(3):raise TimeoutError('synthetic test timeout')
            return True,5.0
        def collect():
            try:core.collect_once()
            except Exception as exc:errors.append(exc)
        with patch.object(core,'tcp_probe',side_effect=[(True,1.0),(True,3.0)]), \
             patch.object(core,'probe_device',side_effect=slow_device):
            worker=threading.Thread(target=collect)
            worker.start()
            try:
                self.assertTrue(entered.wait(2),'synthetic probe was never entered')
                query_done=threading.Event()
                reader=threading.Thread(target=lambda:(core.get_status(),query_done.set()),daemon=True)
                reader.start()
                self.assertTrue(query_done.wait(1),'read API blocked behind slow probe')
                core.delete_device(1)
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors,[])
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM device_samples').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],1)

    def test_device_probes_run_with_bounded_parallelism_and_finish_timestamp(self):
        import time
        for i in range(7):
            core.add_device({'name':'Synthetic '+str(i),
                             'ip':'192.168.1.'+str(i+10),'port':443})
        guard=threading.Lock()
        active=0;peak=0
        def simulated(_device):
            nonlocal active,peak
            with guard:
                active+=1;peak=max(peak,active)
            time.sleep(.035)
            with guard:active-=1
            return True,1.5
        completed_at='2026-10-27T12:59:00+00:00'
        with patch.object(core,'tcp_probe',side_effect=[(True,1.0),(True,2.0)]), \
             patch.object(core,'probe_device',side_effect=simulated), \
             patch.object(core,'utcnow',return_value=completed_at):
            core.collect_once()
        self.assertGreater(peak,1,'seven probes should not run serially')
        self.assertLessEqual(peak,4,'probe fan-out must not exceed four workers')
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM device_samples').fetchone()[0],7)
            self.assertEqual(db.execute('SELECT COUNT(DISTINCT ts) FROM device_samples').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT ts FROM samples ORDER BY id DESC LIMIT 1').fetchone()[0],
                             completed_at)

    def test_round_robin_budget_never_converts_deferred_device_to_offline(self):
        for n in range(23):
            core.add_device({'name':'Synthetic '+str(n),
                             'ip':'192.168.77.'+str(n+11),'port':443})
        called=[]
        def unreachable(device):
            called.append(device['id'])
            return False,None
        with patch.object(core,'_DEVICE_PROBE_CURSOR',0), \
             patch.object(core,'tcp_probe',side_effect=[(True,1.0),(True,2.0)]*3), \
             patch.object(core,'probe_device',side_effect=unreachable):
            core.collect_once()
            first=list(called)
            state=core.get_status()
            self.assertEqual(state['probe_cycle']['sampled'],16)
            self.assertEqual(state['probe_cycle']['tracked'],23)
            self.assertEqual(state['probe_cycle']['deferred'],7)
            with core.connect() as db:
                observed={row['device_id'] for row in db.execute('SELECT device_id FROM device_samples')}
                self.assertEqual(len(observed),16)
                self.assertEqual({r['id'] for r in state['devices'] if r['online'] is None},
                                 set(range(1,24))-observed)
            core.collect_once()
            second=called[len(first):]
        self.assertEqual(len(first),16)
        self.assertEqual(len(second),16)
        self.assertEqual(len(set(first)),16)
        self.assertEqual(len(set(second)),16)
        self.assertEqual(set(first)|set(second),set(range(1,24)))
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM device_samples').fetchone()[0],32)
        self.assertEqual(core.get_status()['probe_cycle']['deferred'],7)

    def test_slow_outbox_scan_never_blocks_sqlite_writes(self):
        entered=threading.Event();release=threading.Event()
        finished=threading.Event();written=threading.Event();failures=[]
        original_glob=Path.glob
        def slow_glob(path,pattern):
            if path.name=='outbox' and pattern=='*.json':
                entered.set()
                if not release.wait(3):
                    raise TimeoutError('synthetic slow queue scan')
            return original_glob(path,pattern)
        def reader():
            try:core.get_status()
            except Exception as exc:failures.append(exc)
            finally:finished.set()
        def writer():
            try:core.put_router_metrics({'cpu_pct':31},'synthetic-lock-audit')
            except Exception as exc:failures.append(exc)
            finally:written.set()
        with patch.object(Path,'glob',new=slow_glob):
            thread=threading.Thread(target=reader,daemon=True)
            thread.start()
            try:
                self.assertTrue(entered.wait(2),'status did not scan the queue')
                writer_thread=threading.Thread(target=writer,daemon=True)
                writer_thread.start()
                self.assertTrue(written.wait(1),'a slow queue scan held the SQLite lock')
            finally:
                release.set()
                thread.join(3)
                if 'writer_thread' in locals():writer_thread.join(3)
        self.assertTrue(finished.is_set())
        self.assertEqual(failures,[])
        self.assertEqual(core.get_status()['metrics']['metrics']['cpu_pct'],31)

    def test_legacy_history_marks_truncation_and_downsampling(self):
        now=datetime.now(timezone.utc).isoformat()
        with core.connect() as db:
            db.executemany('INSERT INTO samples(ts) VALUES(?)',[(now,)]*5002)
        result=core.get_history(24,limit=9)
        self.assertTrue(result['truncated']['probes'])
        self.assertEqual(result['bounded_to_last'],5000)
        self.assertTrue(result['downsampled']['probes'])
        self.assertLessEqual(len(result['probes']),10)
        self.assertEqual(result['router'],[])
        self.assertFalse(result['truncated']['router'])

if __name__ == '__main__': unittest.main()
