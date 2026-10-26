"""Synthetic backend regression tests: never connect to the S7 or external router."""
import concurrent.futures
import gzip
import json
import time
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime,timezone,timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import core,historian
from app.host_telemetry import HostMonitor,empty_snapshot
from app.server import Handler


class BackendOptimizations(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'fixture.db'
        self.patcher=patch.object(core,'DB_PATH',self.db)
        self.patcher.start()
        core.init_db()
        with historian._overview_mutex:
            historian._overview_cache.clear()
    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def seed_router(self):
        now=datetime.now(timezone.utc)
        with core.connect() as db:
            for i in range(127):
                ts=(now-timedelta(minutes=i)).isoformat()
                payload={'metrics':{'cpu_pct':0 if i%2==0 else 33,'memory_pct':None},
                         'wan_states':{'wan0':{'services':['Internet']}},
                         'interfaces':{'wan0':{'rx_bytes':1000+i,'tx_bytes':0}},
                         'clients':[],'stations':[]}
                db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)',
                           (ts,json.dumps(payload)))
                db.execute('INSERT INTO samples(ts,router_online,router_ms,internet_online,internet_ms) VALUES(?,?,?,?,?)',
                           (ts,1,0,1,None))
    def test_home_summary_exact_coverage_and_full_history_preserved(self):
        self.seed_router()
        summary=historian.overview_history('24h','summary')
        full=historian.overview_history('24h')
        self.assertEqual(summary['quality']['sample_count'],127)
        self.assertEqual(full['quality']['sample_count'],127)
        self.assertTrue(summary['summary']['raw_samples_retained'])
        self.assertLessEqual(len(summary['series']),97)
        self.assertGreater(len(full['series']),0)
        self.assertTrue(any(p['wan_tx_bytes']==0 for p in summary['series']))
        self.assertTrue(any(p.get('memory_pct') is None for p in summary['series']))
        # Stats and min/max on detailed history remain available.
        self.assertEqual(full['stats']['cpu_pct']['min'],0)
        self.assertEqual(full['stats']['wan_tx_bytes']['max'],0)
        self.assertIsNone(full['stats']['memory_pct']['avg'])
        with core.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM huawei_samples').fetchone()[0],127)
    def test_cache_invalidated_after_new_collection(self):
        self.seed_router()
        old=historian.overview_history('24h','summary')
        same=historian.overview_history('24h','summary')
        self.assertIs(old,same)
        now=datetime.now(timezone.utc).isoformat()
        with core.connect() as db:
            db.execute('INSERT INTO huawei_samples(ts,payload) VALUES(?,?)',
                       (now,json.dumps({'metrics':{'cpu_pct':71}})))
        new=historian.overview_history('24h','summary')
        self.assertIsNot(new,old)
        self.assertEqual(new['quality']['sample_count'],128)
        self.assertLessEqual(len(historian._overview_cache),historian._OVERVIEW_MAX)
        with self.assertRaises(ValueError):historian.overview_history('24h','private')
    def test_four_router_clients_share_one_full_aggregate(self):
        self.seed_router()
        with historian._overview_mutex:historian._overview_cache.clear()
        original=historian._overview_history_uncached
        calls=[]
        def aggregate(period):
            calls.append(period)
            time.sleep(.06)
            return original(period)
        with patch.object(historian,'_overview_history_uncached',side_effect=aggregate):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                jobs=[pool.submit(historian.overview_history,'24h','full') for _ in range(4)]
                result=[job.result() for job in jobs]
            self.assertEqual(len(calls),1)
            self.assertEqual([v['quality']['sample_count'] for v in result],[127]*4)

    def test_inventory_latest_timestamp_wins_over_backfilled_higher_id(self):
        mac='02:00:00:00:00:01';now=datetime.now(timezone.utc)
        observations=[(now,'Latest fixture'),(now-timedelta(days=1),'Backfilled fixture'),(now,'Latest tie fixture')]
        with core.connect() as db:
            for stamp,name in observations:
                payload={'mac':mac,'names':[name],'ports':['wifi:fixture'],'reported_status':'Online'}
                db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',(1,stamp.isoformat(),mac,json.dumps(payload)))
        result=core.get_router_clients()['clients']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['names'],['Latest tie fixture'])
        self.assertEqual(result[0]['observations'],3)
        self.assertEqual(result[0]['first_seen'],(now-timedelta(days=1)).isoformat())

    def test_different_chart_metrics_share_one_archive_scan(self):
        monitor=HostMonitor(Path(self.temp.name)/'fixture.db')
        sample=empty_snapshot();sample['cpu']['usagePercent']=0
        sample['memory'].update(totalMB=100,usedMB=25)
        sample['network'].update(rxMbps=1,txMbps=2)
        monitor.persist(sample)
        with patch.object(monitor,'query_history',wraps=monitor.query_history) as query:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                values=list(pool.map(lambda name:monitor.history(name,'7d'),['cpu','memory','rx','tx']))
            self.assertEqual(query.call_count,1)
            self.assertEqual([v[0]['value'] for v in values],[0,25,1,2])
            self.assertLessEqual(len(monitor.history_cache),56)

    def test_concurrent_identical_host_history_one_query_and_new_persist_invalidates(self):
        monitor=HostMonitor(Path(self.temp.name)/'fixture.db')
        sample=empty_snapshot()
        monitor.persist(sample)
        attempts=[]
        original=monitor.query_history
        def delayed(metric,span):
            attempts.append((metric,span))
            time.sleep(.06)
            return original(metric,span)
        with patch.object(monitor,'query_history',side_effect=delayed):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures=[pool.submit(monitor.history,'cpu','6h') for _ in range(4)]
                values=[future.result() for future in futures]
            self.assertEqual(len(attempts),1)
            self.assertEqual(len(values),4)
            self.assertIsNone(values[0][0]['value'])
            # Other metric uses independent key; cached identical query doesn't run again.
            self.assertEqual(monitor.history('cpu','6h'),values[0])
            self.assertEqual(len(attempts),1)
            monitor.persist(sample)
            monitor.history('cpu','6h')
            self.assertEqual(len(attempts),2)
        self.assertLessEqual(len(monitor.history_cache),56)


class SafeStaticHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.old=core.DB_PATH
        core.DB_PATH=Path(cls.temp.name)/'http-fixture.db'
        core.init_db()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.origin='http://127.0.0.1:'+str(cls.server.server_address[1])
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)
        core.DB_PATH=cls.old
        cls.temp.cleanup()
    def get(self,path,headers=None,method='GET'):
        request=urllib.request.Request(self.origin+path,headers=headers or {},method=method)
        try:
            with urllib.request.urlopen(request,timeout=4) as response:
                return response.status,response.read(),dict(response.headers)
        except urllib.error.HTTPError as error:
            if error.code==304:return error.code,error.read(),dict(error.headers)
            raise
    def test_code_gzip_etag_304_and_invalidation(self):
        status,packed,headers=self.get('/router/app.js',{'Accept-Encoding':'gzip'})
        self.assertEqual(status,200)
        self.assertEqual(headers.get('Content-Encoding'),'gzip')
        self.assertEqual(len(packed),int(headers['Content-Length']))
        self.assertIn(b'async function',gzip.decompress(packed))
        self.assertEqual(headers['Vary'],'Accept-Encoding')
        self.assertIn('private',headers['Cache-Control'])
        etag=headers['ETag']
        self.assertTrue(etag.startswith('"'))
        self.assertEqual(self.get('/router/app.js',{'If-None-Match':etag})[0],200)
        self.assertEqual(self.get('/router/app.js',{'If-None-Match':etag,'Accept-Encoding':'gzip'})[0],304)
        regular=self.get('/router/app.js')
        self.assertNotEqual(regular[2]['ETag'],etag)
        self.assertEqual(self.get('/router/app.js',{'If-None-Match':regular[2]['ETag']})[0],304)
        self.assertEqual(regular[0],200)
        self.assertNotIn('Content-Encoding',regular[2])
        self.assertEqual(self.get('/router/app.js',{'If-None-Match':'"stale"'} )[0],200)
        self.assertEqual(self.get('/router/app.js',{'Accept-Encoding':'gzip;q=0'})[2].get('Content-Encoding'),None)
        self.assertEqual(self.get('/router/app.js',method='HEAD')[1],b'')
        self.assertEqual(self.get('/router/app.js',{'If-Modified-Since':headers['Last-Modified']})[0],304)
    def test_modified_since_rounds_filesystem_subseconds_to_http_seconds(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            asset=Path(folder)/'app.js';asset.write_text('const synthetic = 1;')
            os.utime(asset,ns=(1700000000999999999,1700000000999999999))
            with patch('app.server.STATIC',Path(folder)):
                status,body,headers=self.get('/app.js')
                self.assertEqual(status,200)
                self.assertEqual(self.get('/app.js',{'If-Modified-Since':headers['Last-Modified']})[0],304)
                self.assertEqual(self.get('/app.js',{'If-Modified-Since':'Tue, 14 Nov 2023 22:13:19 GMT'})[0],200)

    def test_content_change_changes_etag_and_other_formats_do_not_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            asset=root/'app.js'
            asset.write_text('const assetVersion = "first";'+('x'*2400))
            (root/'photo.png').write_bytes(b'fixture image payload')
            (root/'data.json').write_text('{"private":true}')
            with patch('app.server.STATIC',root):
                _,_,first=self.get('/router/app.js')
                old_tag=first['ETag']
                # Revision changes bytes, not just a query-string version.
                asset.write_text('const assetVersion = "second";'+('x'*2400))
                import os
                os.utime(asset,(time.time()+2,time.time()+2))
                code,body,headers=self.get('/router/app.js',{'If-None-Match':old_tag})
                self.assertEqual(code,200)
                self.assertNotEqual(headers['ETag'],old_tag)
                self.assertIn(b'second',body)
                self.assertEqual(self.get('/router/app.js',{'If-None-Match':headers['ETag']})[0],304)
                for path in ('/photo.png','/data.json'):
                    code,_,head=self.get(path,{'Accept-Encoding':'gzip'})
                    self.assertEqual(code,200)
                    self.assertEqual(head['Cache-Control'],'no-store')
                    self.assertNotIn('ETag',head)
                    self.assertNotIn('Content-Encoding',head)

    def test_private_and_dynamic_not_cached(self):
        for path in ('/router/','/api/status','/api/v1/overview?period=24h&view=summary','/s7/'):
            code,_,headers=self.get(path)
            self.assertEqual(code,200)
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertNotIn('ETag',headers)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'index.html').write_text('<title>Private document</title>')
            (root/'user.js').write_text('const private = "fixture only";')
            with patch('app.server.VALT',root):
                code,_,headers=self.get('/valt/user.js',{'Accept-Encoding':'gzip'})
                self.assertEqual(code,200)
                self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertNotIn('ETag',headers)
                self.assertNotIn('Content-Encoding',headers)
