import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools import s7_preflight as preflight


class S7PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/'router.db'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE synthetic_readings(id INTEGER PRIMARY KEY, value TEXT)')
            db.execute('INSERT INTO synthetic_readings(value) VALUES(?)',('private-mac-02:00:00',))

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_probe_read_only_and_no_private_values_reported(self):
        before=hashlib.sha256(self.db.read_bytes()).digest()
        check=preflight.sqlite_readonly(self.db)
        self.assertEqual(check['status'],'ok')
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).digest(),before)
        with patch.object(preflight,'local_status',
                          return_value={'router':{},'collector':{'state':'ok'}}):
            report=preflight.run_preflight(str(self.db),str(self.db),self.root,
                                           min_free_mib=0)
        self.assertEqual(report['result'],'incomplete')  # same-volume warning
        self.assertNotIn('private-mac',json.dumps(report))
        self.assertNotIn(str(self.root),json.dumps(report))
        self.assertEqual(next(x for x in report['checks'] if x['name']=='local_api')['status'],'ok')

    def test_missing_database_and_unavailable_api_are_not_green(self):
        with patch.object(preflight,'local_status',side_effect=ValueError('secret')):
            report=preflight.run_preflight(str(self.root/'missing.db'),
                                           internal_dir=self.root,min_free_mib=0)
        self.assertEqual(report['result'],'fail')
        text=json.dumps(report)
        self.assertNotIn('secret',text)
        self.assertNotIn(str(self.root),text)

    def test_external_origins_and_credentials_are_rejected_before_any_http(self):
        for origin in ('https://127.0.0.1:8765','http://8.8.8.8:8765',
                       'http://bad:pass@localhost:8765',
                       'http://localhost:8765/other','http://localhost:8765',
                       'http://127.0.0.1:8765?redirect=1'):
            with self.subTest(origin=origin),patch.object(
                    preflight.urllib.request,'build_opener') as opener:
                with self.assertRaises(ValueError):
                    preflight.local_status(origin)
                opener.assert_not_called()

    def test_auth_blocked_and_missing_host_db_are_visible(self):
        with patch.object(preflight,'local_status',
                          return_value={'router':{},'collector':{'state':'auth_blocked'}}):
            report=preflight.run_preflight(str(self.db),internal_dir=self.root,
                                           min_free_mib=0)
        self.assertEqual(report['result'],'fail')
        self.assertIn('host_sqlite',[r['name'] for r in report['checks']])
        self.assertEqual(next(x for x in report['checks'] if x['name']=='collector')['status'],'fail')

    def test_cli_exit_codes_never_print_paths(self):
        import io
        from contextlib import redirect_stdout
        sink=io.StringIO()
        with patch.object(preflight,'local_status',
                          return_value={'router':{},'collector':{'state':'ok'}}),redirect_stdout(sink):
            code=preflight.main(['--router-db',str(self.db),'--internal-dir',str(self.root),
                                '--min-internal-free-mib','0','--host-db',str(self.db)])
        self.assertEqual(code,2)
        self.assertNotIn(str(self.root),sink.getvalue())
        self.assertEqual(json.loads(sink.getvalue())['result'],'incomplete')


if __name__=='__main__':
    unittest.main()
