import json
from contextlib import closing
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from app.host_telemetry import HostMonitor, empty_snapshot
from app import host_telemetry

class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.monitor=HostMonitor(self.root/'observatory.db')
    def tearDown(self):self.temp.cleanup()
    def test_cpu_deltas_first_sample_unknown(self):
        with patch('app.host_telemetry.read',return_value='cpu 10 0 10 80 0 0 0 0\ncpu0 10 0 10 80 0 0 0 0'):
            self.assertEqual(self.monitor.cpu(),(None,[None]))
        with patch('app.host_telemetry.read',return_value='cpu 20 0 20 160 0 0 0 0\ncpu0 20 0 20 160 0 0 0 0'):
            self.assertEqual(self.monitor.cpu(),(20.0,[20.0]))
    def test_absent_sensors_are_null_not_zero(self):
        with patch('app.host_telemetry.read',return_value=None),patch('app.host_telemetry.shutil.which',return_value=None):
            self.assertIsNone(self.monitor.battery()['levelPercent'])
            self.assertIsNone(self.monitor.network()['rxMbps'])
    def test_history_preserves_null_and_rejects_injection(self):
        s=empty_snapshot();self.monitor.persist(s)
        result=self.monitor.history('cpu','24h')
        self.assertEqual(len(result),1);self.assertIsNone(result[0]['value'])
        with self.assertRaises(ValueError):self.monitor.history("cpu');DROP TABLE host_samples;--",'24h')
        with self.assertRaises(ValueError):self.monitor.history('cpu','invalid')
    def test_retention_and_aggregation_bounded(self):
        import sqlite3
        self.monitor.persist(empty_snapshot())
        with closing(sqlite3.connect(self.monitor.path)) as db, db:
            db.execute('INSERT INTO host_samples VALUES (?,?)',(time.time()-32*86400,json.dumps(empty_snapshot())))
        self.monitor.persist(empty_snapshot())
        with closing(sqlite3.connect(self.monitor.path)) as db, db:self.assertEqual(db.execute('select count(*) from host_samples').fetchone()[0],3)
        self.assertLessEqual(len(self.monitor.history('memory','1a')),361)
    def test_cache_and_stale_never_substitute_demo(self):
        s=empty_snapshot();s['timestamp']='2020-01-01T00:00:00+00:00';self.monitor.snapshot_data=s
        with patch.object(self.monitor,'sample',side_effect=AssertionError('HTTP must not sample')):
            result=self.monitor.snapshot()
        self.assertEqual(result['quality'],'stale');self.assertIsNone(result['battery']['levelPercent'])
        result['memory']['totalMB']=999
        self.assertIsNone(self.monitor.snapshot_data['memory']['totalMB'])
    def test_timing_window_bounded_and_excludes_host(self):
        self.monitor.record_api('/api/host/snapshot',10)
        for i in range(200):self.monitor.record_api('/api/status',i)
        self.assertEqual(len(self.monitor.api),128)
        self.assertTrue(all(p=='/api/status' for p,_ in self.monitor.api))
    def test_missing_sd_does_not_create_fallback(self):
        self.monitor.path=self.root/'missing-volume/host.db'
        with self.assertRaises(OSError):self.monitor.persist(empty_snapshot())
        self.assertFalse(self.monitor.path.parent.exists())


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.monitor=HostMonitor(self.root/'observatory.db')
        self.path=self.root/'adb-cpu.snapshot'
        self.clock=patch.object(host_telemetry.time,'clock_gettime',return_value=101,create=True)
        self.constant=patch.object(host_telemetry.time,'CLOCK_BOOTTIME',7,create=True)
        self.clock.start();self.constant.start()
    def tearDown(self):self.clock.stop();self.constant.stop();self.temp.cleanup()
    def payload(self,nonce=None,after=101,before=100):
        return f"S7CPU1 {nonce or self.monitor.agent_nonce}\nbefore {before}\ncpu 10 0 10 80 0 0 0 0\ncpu0 10 0 10 80 0 0 0 0\nafter {after}\ncpu 20 0 20 160 0 0 0 0\ncpu0 20 0 20 160 0 0 0 0\n"
    def test_agent_numeric_sample_and_offline_cores(self):
        self.path.write_text(self.payload())
        with patch('app.host_telemetry.os.cpu_count',return_value=2),patch('app.host_telemetry.cpu_ids',return_value=list(range(8))):r=self.monitor.agent_cpu()
        self.assertEqual(r['status'],'ok');self.assertEqual(r['usagePercent'],20)
        self.assertEqual(r['coresPercent'],[20.0]+[None]*7)
        self.assertEqual((self.root/'adb-agent.request').read_text().strip(),self.monitor.agent_nonce)
    def test_previous_session_is_rejected(self):
        self.path.write_text(self.payload('0'*32));r=self.monitor.agent_cpu()
        self.assertEqual(r['status'],'waiting-new-session');self.assertNotIn('usagePercent',r)
    def test_old_and_future_readings_are_rejected(self):
        for after in (-100,105):
            self.path.write_text(self.payload(after=after,before=after-1))
            self.assertEqual(self.monitor.agent_cpu()['status'],'stale')
    def test_invalid_sample_cannot_become_zero(self):
        for text in ['bad',self.payload().replace('20 0 20 160','-1 0 20 160'),self.payload(after=100),self.payload().replace('cpu 20 0 20 160','cpu 10 0 10 80'),'x'*17000]:
            self.path.write_text(text);r=self.monitor.agent_cpu()
            self.assertNotEqual(r['status'],'ok');self.assertNotIn('usagePercent',r)
    def test_extra_counters_are_numeric_bounded_and_preserved(self):
        self.path.write_text(self.payload()+'vmstat pgfault 123\nloadavg 0.1 0.2 0.3\ndisk mmcblk1 1 2 3 4 5 6 7 8 9 10 11\nstat ctxt 456\n')
        result=self.monitor.agent_cpu()
        self.assertEqual(result['extraCounters']['vmstat']['pgfault'],123)
        self.assertEqual(result['extraCounters']['disk']['mmcblk1'][2],3)
        self.assertIn('cpu',result['rawFrames']['before'])
        for extra in ['vmstat pgfault -1','loadavg nan 0 0','disk private 1 2 3','stat ctxt 99999999999999999999999']:
            self.path.write_text(self.payload()+extra+'\n')
            self.assertEqual(self.monitor.agent_cpu()['status'],'unavailable')
    def test_missing_sample_is_unavailable(self):
        self.assertEqual(self.monitor.agent_cpu()['status'],'unavailable')
