"""Synthetic alert tests; no router, SD card or private LAN access."""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from app import operations, core


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'router.db'
        self.now=datetime(2026,10,26,20,0,tzinfo=timezone.utc)
        self.core=patch.object(core,'DB_PATH',self.db)
        self.core.start();self.addCleanup(self.core.stop)
        self.previous=dict(core.COLLECTOR_STATE)
        self.addCleanup(lambda: core.COLLECTOR_STATE.update(self.previous))
        core.COLLECTOR_STATE.update(state='ok',last_success=(self.now-timedelta(minutes=2)).isoformat())

    def host(self,minutes=1,rss=40):
        return {'timestamp':(self.now-timedelta(minutes=minutes)).isoformat(),
                'diagnostics':{'processRssMB':rss,'apiP95Ms':27.4}}

    def values(self,free=10):
        return {'database':20.0,'wal':0.6,'availableGiB':free,'volumeAccessible':True}

    def test_rules_validate_types_bounds_and_sources(self):
        self.assertTrue(operations.validate_rules({})['enabled'])
        self.assertEqual(operations.validate_rules({'collector_stale_minutes':20})['collector_stale_minutes'],20)
        for bad in ({'enabled':'yes'},{'no_such_rule':2},
                    {'change_sources':['unrecognized']},{'change_sources':['wps','wps']},
                    {'host_stale_minutes':False},{'database_free_gib_warning':0.1},
                    {'database_free_gib_critical':3,'database_free_gib_warning':2},
                    {'process_rss_mb_warning':float('nan')}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                operations.validate_rules(bad)

    def test_invalid_file_disables_custom_alerts_not_silently_defaults(self):
        p=Path(self.temp.name)/'invalid.json'
        p.write_text('{"enabled": "not a boolean"}')
        with patch.dict(os.environ,{operations.CONFIG_ENV:str(p)}):
            rules,source=operations.load_rules()
        self.assertEqual(source,'invalid_file_disabled')
        self.assertFalse(rules['enabled'])

    def test_passive_alert_state_and_no_guesses(self):
        with patch('app.operations.sizes_and_storage',return_value=self.values()):
            response=operations.read(now=self.now,host_snapshot=self.host(),changes=[])
        self.assertEqual(response['alerts'],[])
        self.assertEqual(response['health']['processRssMB'],40)
        self.assertIsNone(response['health']['growthMBPerDay'])
        self.assertEqual(response['health']['volumeFreeGiB'],10)
        self.assertEqual(response['rulesSource'],'defaults')

        core.COLLECTOR_STATE.update(state='auth_blocked',last_success=(self.now-timedelta(minutes=33)).isoformat())
        with patch('app.operations.sizes_and_storage',return_value=self.values(.8)):
            response=operations.read(now=self.now,host_snapshot=self.host(minutes=8,rss=300),
                                     changes=[],rules={'process_rss_mb_warning':200})
        alert_ids={x['id'] for x in response['alerts']}
        self.assertTrue({'storage_reserve','collector_state','collector_stale','host_stale'} <= alert_ids)
        self.assertNotIn('rss_high',alert_ids,'stale memory must not trigger a fresh usage alert')
        self.assertIsNone(response['health']['processRssMB'])
        self.assertEqual(response['health']['hostSampleAgeMinutes'],8)

    def test_changes_require_recent_non_gap_confirmed_observations(self):
        changes=[
          dict(id=1,source='wps',previous_at=(self.now-timedelta(minutes=10)).isoformat(),
               observed_at=(self.now-timedelta(minutes=5)).isoformat(),crosses_gap=False),
          dict(id=2,source='wps',previous_at=(self.now-timedelta(hours=2)).isoformat(),
               observed_at=(self.now-timedelta(minutes=5)).isoformat(),crosses_gap=True),
          dict(id=3,source='upnp',previous_at=(self.now-timedelta(minutes=10)).isoformat(),
               observed_at=(self.now-timedelta(minutes=5)).isoformat(),crosses_gap=False),
          dict(id=4,source='wps',previous_at=(self.now-timedelta(hours=3)).isoformat(),
               observed_at=(self.now-timedelta(hours=2)).isoformat(),crosses_gap=False),
        ]
        with patch('app.operations.sizes_and_storage',return_value=self.values()):
            a=operations.read(now=self.now,host_snapshot=self.host(),changes=changes)
            b=operations.read(now=self.now,host_snapshot=self.host(),changes=changes)
        ids=[x['id'] for x in a['alerts']]
        self.assertEqual(ids,['config_1'])
        self.assertEqual(ids,[x['id'] for x in b['alerts']])
        self.assertTrue(all('ip' not in json.dumps(x).lower() for x in a['alerts']))

    def test_existing_host_archive_supports_growth_calculation(self):
        with sqlite3.connect(Path(self.temp.name)/'host-telemetry.db') as db:
            db.execute('CREATE TABLE host_samples(ts REAL PRIMARY KEY,payload TEXT NOT NULL)')
            for hours,size in [(7,10),(0.1,100)]:
                when=self.now-timedelta(hours=hours)
                db.execute('INSERT INTO host_samples VALUES(?,?)',
                    (when.timestamp(),json.dumps({'diagnostics':{'databaseMB':size,'processRssMB':48,'apiP95Ms':40},
                     'storage':[{'id':'sd','availableBytes':10*1024**3}]})))
        with patch('app.operations.sizes_and_storage',return_value=self.values()):
            response=operations.read(now=self.now,host_snapshot=self.host(),changes=[],
                                     rules={'sqlite_growth_mb_day_warning':150})
        self.assertTrue(response['health']['growthMBPerDay']>150)
        self.assertIn('db_growth',[x['id'] for x in response['alerts']])
        self.assertEqual(len(response['history']['points']),2)
        self.assertEqual(response['history']['points'][0]['database_mb'],10)

    def test_missing_mount_or_no_host_does_not_report_green(self):
        core.COLLECTOR_STATE.update(state='not_started',last_success=None)
        with patch('app.operations.sizes_and_storage',return_value=self.values()|{'volumeAccessible':False,'availableGiB':None}):
            response=operations.read(now=self.now,host_snapshot={},changes=[])
        self.assertIn('storage_unavailable',[a['id'] for a in response['alerts']])
        self.assertIsNone(response['health']['processRssMB'])
        self.assertIsNone(response['health']['hostSampleAgeMinutes'])

    def test_source_queries_are_read_only(self):
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE router_changes(id INTEGER PRIMARY KEY,source TEXT,previous_at TEXT,observed_at TEXT,crosses_gap INTEGER)')
            db.execute('INSERT INTO router_changes VALUES(1,?,?,?,?)',
                 ('wps',(self.now-timedelta(minutes=4)).isoformat(),(self.now-timedelta(minutes=2)).isoformat(),0))
        before=self.db.stat().st_size
        with patch('app.operations.sizes_and_storage',return_value=self.values()):
            response=operations.read(now=self.now,host_snapshot=self.host())
        self.assertEqual([x['id'] for x in response['alerts']],['config_1'])
        self.assertEqual(self.db.stat().st_size,before)


if __name__ == '__main__':
    unittest.main()
