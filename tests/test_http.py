import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from app import core
from app.server import Handler

HTTP_TIMEOUT=float(os.environ.get('FNO_TEST_HTTP_TIMEOUT','3'))

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.old=core.DB_PATH
        core.DB_PATH=Path(cls.temp.name)/'test-http.db'
        core.init_db()
        cls.oldtoken=core.WRITE_TOKEN
        core.WRITE_TOKEN='integration-test-token'
        cls.srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.url=f'http://127.0.0.1:{cls.srv.server_address[1]}'
        cls.thread=threading.Thread(target=cls.srv.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown();cls.srv.server_close();cls.thread.join(3)
        core.WRITE_TOKEN=cls.oldtoken
        core.DB_PATH=cls.old
        cls.temp.cleanup()

    def request(self,path,data=None,token=None):
        encoded=json.dumps(data).encode() if data is not None else None
        headers={'Content-Type':'application/json'}
        if token is not None:headers['X-API-Key']=token
        req=urllib.request.Request(self.url+path,data=encoded,headers=headers)
        with urllib.request.urlopen(req,timeout=HTTP_TIMEOUT) as res:return res.status,res.read(),dict(res.headers)

    def test_absolute_request_target_is_not_a_proxy(self):
        import http.client
        conn=http.client.HTTPConnection('127.0.0.1',self.srv.server_address[1],timeout=HTTP_TIMEOUT)
        try:
            conn.request('GET','http://example.invalid/router/')
            res=conn.getresponse()
            self.assertEqual(res.status,403)
            self.assertIn(b'Proxy requests are not supported',res.read())
        finally:conn.close()

    def test_api_timing_and_gzip_preserve_contract(self):
        import gzip
        fixture={'clients':[{'name':'synthetic repeated value','value':0} for _ in range(1500)]}
        with patch('app.core.get_router_clients',return_value=fixture):
            plain=self.request('/api/router/clients')
            req=urllib.request.Request(self.url+'/api/router/clients',headers={'Accept-Encoding':'gzip'})
            with urllib.request.urlopen(req,timeout=HTTP_TIMEOUT) as res:
                packed=res.read();headers=dict(res.headers)
            self.assertEqual(json.loads(gzip.decompress(packed)),fixture)
            self.assertLess(len(packed),len(plain[1])//2)
            self.assertEqual(headers['Content-Encoding'],'gzip')
            self.assertEqual(headers['Cache-Control'],'no-store')
            durations=dict(item.strip().split(';dur=') for item in headers['Server-Timing'].split(','))
            self.assertEqual(set(durations),{'db','wait','app','serialize','compress','total'})
            self.assertTrue(all(float(value)>=0 for value in durations.values()))
            self.assertNotIn('synthetic',headers['Server-Timing'])
        self.assertNotIn('Server-Timing',self.request('/router/')[2])

    def test_s7_shared_assets_resolve_from_server_root(self):
        html=self.request('/s7/')[1].decode()
        for asset in ('workspace.css','finish.css','finish.js','loading.css'):
            self.assertIn('"/'+asset,html)
            self.assertEqual(self.request('/'+asset)[0],200)
        self.assertNotIn('href="workspace.css',html)

    def test_host_namespace_partial_and_static_isolation(self):
        from app.host_telemetry import HostMonitor, empty_snapshot
        m=HostMonitor(Path(self.temp.name)/'observatory.db')
        m.snapshot_data=empty_snapshot()
        with patch('app.host_telemetry._monitor',m):
            code,body,_=self.request('/api/host/snapshot')
            self.assertEqual(code,200);self.assertIsNone(json.loads(body)['battery']['levelPercent'])
            code,body,_=self.request('/api/host/history?metric=cpu&range=1h')
            self.assertEqual(json.loads(body),[])
            with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/host/history?metric=bad')
            self.assertEqual(error.exception.code,400)
        code,body,_=self.request('/s7/')
        self.assertEqual(code,200);self.assertIn(b'js/app.js',body)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/config/login.txt')
        self.assertEqual(error.exception.code,404)

    def test_host_full_archive_and_catalog(self):
        from app.host_telemetry import HostMonitor, empty_snapshot
        m=HostMonitor(Path(self.temp.name)/'host-archive-test'/'observatory.db')
        m.path.parent.mkdir(exist_ok=True)
        sample=empty_snapshot();sample['details']={'metrics':{'test':{'value':None,'source':'fixture','status':'denied','unit':'bytes'}}}
        m.snapshot_data=sample;m.persist(sample)
        with patch('app.host_telemetry._monitor',m):
            page=json.loads(self.request('/api/host/archive?limit=1')[1])
            self.assertEqual(page['records'][0]['sample'],sample)
            self.assertEqual(json.loads(self.request('/api/host/catalog')[1])['sources']['test']['status'],'denied')
            for query in ('limit=501','after=nan','after=-1'):
                with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/host/archive?'+query)
                self.assertEqual(error.exception.code,400)

    def test_project_routes_and_switcher(self):
        for path in ('/', '/router', '/router/', '/s7', '/s7/'):
            code,body,_=self.request(path)
            self.assertEqual(code,200)
            self.assertIn(b'class="project-switch"',body)
            self.assertIn(b'href="/router/"',body)
            self.assertIn(b'href="/s7/"',body)
        for path in ('/router/styles.css','/router/app.js','/workspace.css','/s7/js/app.js'):
            code,_,_=self.request(path);self.assertEqual(code,200)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/router/../config/login.txt')
        self.assertIn(error.exception.code,(403,404))

    def test_valt_static_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'index.html').write_text('<title>Vault fixture</title>')
            (root/'documento com espaço.pdf').write_bytes(b'%PDF-fixture')
            with patch('app.server.VALT',root):
                code,body,headers=self.request('/valt')
                self.assertEqual(code,200);self.assertIn(b'Vault fixture',body)
                self.assertEqual(headers['X-Frame-Options'],'SAMEORIGIN')
                self.assertIn("frame-ancestors 'self'",headers['Content-Security-Policy'])
                self.assertEqual(self.request('/valt/documento%20com%20espa%C3%A7o.pdf')[1],b'%PDF-fixture')
                for path in ('/valt/%2e%2e/index.html','/valt/%5c..%5cconfig/login.txt','/valt/missing'):
                    with self.assertRaises(urllib.error.HTTPError) as error:self.request(path)
                    self.assertIn(error.exception.code,(403,404))
        self.assertEqual(self.request('/router/')[2]['X-Frame-Options'],'DENY')

    def test_basic_assets_and_api(self):
        code,body,_=self.request('/api/status');self.assertEqual(code,200)
        self.assertIn('router',json.loads(body))
        code,body,headers=self.request('/');self.assertEqual(code,200)
        self.assertIn(b'Faysk',body)
        self.assertIn('Content-Security-Policy',headers)
        self.assertEqual(self.request('/metrics')[0],200)

    def test_archive_endpoint(self):
        result=json.loads(self.request('/api/archive?kind=huawei&after=0&limit=1')[1])
        self.assertFalse(result['downsampled'])
        self.assertIn('next_after',result)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/archive?kind=invalid')
        self.assertEqual(error.exception.code,400)

    def test_observability_api(self):
        data=json.loads(self.request('/api/router/observability?hours=24')[1])
        self.assertEqual(data['poll_seconds'],300)
        self.assertGreater(len(data['sources']),20)
        self.assertIn('wifi_logs',data['unsupported'])
        self.assertEqual(json.loads(self.request('/api/router/observability/archive?source=upnp')[1])['records'],[])
        for path in ('/api/router/observability?hours=nan','/api/router/observability?hours=999999','/api/router/observability/archive?source=bad','/api/router/observability/archive?source=upnp&limit=501'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(path)
            self.assertEqual(error.exception.code,400)

    def test_write_requires_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request('/api/devices',{'name':'Test','ip':'192.168.1.90'})
        self.assertEqual(e.exception.code,401)
        self.assertEqual(self.request('/api/devices',{'name':'Test','ip':'192.168.1.90'},'integration-test-token')[0],201)

    def test_rejects_unknown_path(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/bad-path')
        self.assertEqual(e.exception.code,404)

    def test_huawei_ingestion_roundtrip_and_privacy(self):
        from test_huawei import payload
        token='fixture-token-with-more-than-32-characters'
        with patch.object(core,'WRITE_TOKEN',token):
            p=payload()
            self.assertEqual(self.request('/api/ingest/huawei',p,token)[0],201)
            status=json.loads(self.request('/api/status')[1])
            self.assertEqual(status['huawei']['metrics']['optical_rx_dbm'],-21.5)
            p['metrics']['serial']='REDACTED'
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/ingest/huawei',p,token)
            self.assertEqual(error.exception.code,400)

    def test_huawei_short_token_disabled(self):
        from test_huawei import payload
        with patch.object(core,'WRITE_TOKEN','short'):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/ingest/huawei',payload(),'short')
            self.assertEqual(error.exception.code,403)

    def test_huawei_queued_old_sample_requires_token_and_backfill_header(self):
        from test_huawei import payload
        p=payload();p['collected_at']='2001-01-01T00:00:00+00:00'
        token='fixture-token-with-more-than-32-characters'
        with patch.object(core,'WRITE_TOKEN',token):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/ingest/huawei',p,token)
            self.assertEqual(error.exception.code,400)
            req=urllib.request.Request(self.url+'/api/ingest/huawei',data=json.dumps(p).encode(),headers={'Content-Type':'application/json','X-API-Key':token,'X-FNO-Backfill':'1'})
            with urllib.request.urlopen(req,timeout=HTTP_TIMEOUT) as response:self.assertEqual(response.status,201)
            req=urllib.request.Request(self.url+'/api/ingest/huawei',data=json.dumps(p).encode(),headers={'Content-Type':'application/json','X-FNO-Backfill':'1'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req,timeout=HTTP_TIMEOUT)
            self.assertEqual(error.exception.code,401)

    def test_private_client_endpoint(self):
        from test_huawei import payload,fixture
        from app.adapters import huawei_b7 as h
        p=payload();_,p['stations'],_=h.parse_stations(fixture('stations'))
        p['clients']=h.parse_clients(fixture('stations'),p['stations'])
        core.put_huawei_sample(p)
        result=json.loads(self.request('/api/router/clients')[1])
        self.assertEqual(result['clients'][0]['mac'],'02:00:00:00:00:01')
        history=json.loads(self.request('/api/router/clients?mac=02%3A00%3A00%3A00%3A00%3A01&limit=1')[1])
        self.assertEqual(len(history['observations']),1)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/router/clients?mac=invalid')
        self.assertEqual(error.exception.code,400)

if __name__ == '__main__': unittest.main()
