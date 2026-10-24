import json
from io import StringIO
from unittest.mock import patch
from app.host_sources import collect, kernel_release
import tempfile
import unittest
from app.host_telemetry import HostMonitor

class DetailedHostTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=__import__('pathlib').Path(self.temp.name)
        self.monitor=HostMonitor(self.root/'observatory.db')
    def tearDown(self):self.temp.cleanup()
    def test_archive_is_lossless_paginated_and_keeps_old_records(self):
        s={'timestamp':'old','details':{'value':None,'counter':2**53+1}}
        with patch('app.host_telemetry.time.time',return_value=1):self.monitor.persist(s)
        with patch('app.host_telemetry.time.time',return_value=2):self.monitor.persist({'second':True})
        page=self.monitor.archive(limit=1)
        self.assertEqual(page['records'][0]['sample'],s)
        self.assertTrue(page['hasMore']);self.assertEqual(page['nextAfter'],1)
        self.assertEqual(self.monitor.archive(after=1,limit=1)['records'][0]['sample'],{'second':True})
        for after,limit in [('nan',1),(0,501),(-1,1),(0,'invalid')]:
            with self.assertRaises(ValueError):self.monitor.archive(after,limit)
    def test_sources_distinguish_denial_absence_and_real_zero(self):
        def files(path,**kwargs):
            if path=='/proc/meminfo':return StringIO('MemTotal: 4096 kB\nMemFree: 0 kB\n')
            if path=='/proc/self/status':return StringIO('Name: private\nUid: 123\nThreads: 2\nVmRSS: 40 kB\n')
            if path.endswith('/capacity'):return StringIO('0')
            if path.endswith('/temp'):raise PermissionError()
            raise FileNotFoundError()
        with patch('builtins.open',side_effect=files),patch('app.host_sources.os.cpu_count',return_value=0):s=collect()['metrics']
        self.assertEqual(s['battery.capacity']['value'],0)
        self.assertEqual(s['battery.temp']['status'],'denied')
        self.assertIsNone(s['battery.temp']['value'])
        self.assertEqual(s['pressure.cpu']['status'],'absent')
        self.assertEqual(s['process.status']['value'],{'Threads':2,'VmRSS':40})
        self.assertEqual(s['memory.meminfo']['value']['MemFree'],0)
    def test_catalog_has_provenance_without_copying_values(self):
        self.monitor.snapshot_data['details']={'metrics':{'x':{'value':123,'status':'ok','unit':'bytes','source':'test'}}}
        self.assertEqual(self.monitor.catalog()['sources']['x'],{'status':'ok','unit':'bytes','source':'test'})

    def test_android_os_version_is_not_reported_as_kernel_version(self):
        from types import SimpleNamespace
        with patch('app.host_sources.os.uname',return_value=SimpleNamespace(release='3.18.test'),create=True),patch('platform.release',return_value='8.0.0'):
            self.assertEqual(kernel_release(),'3.18.test')
        with patch('app.host_sources.os.uname',side_effect=OSError(),create=True):
            self.assertIsNone(kernel_release())
