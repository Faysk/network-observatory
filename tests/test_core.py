import json
import tempfile
import unittest
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
        self.assertIn('fno_router_reachable',result)
        self.assertNotIn('fno_huawei_cpu_percent',result)

if __name__ == '__main__': unittest.main()
