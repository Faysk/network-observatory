import csv
import io
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from datetime import datetime,timezone,timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from app import core,historian
from app.server import Handler

class HistorianTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(core,'DB_PATH',Path(self.temp.name)/'test.db');self.patch.start();core.init_db()
        self.mac='02:00:00:00:00:01';self.identifier=self.mac.replace(':','');self.now=datetime.now(timezone.utc)
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def seed(self,seconds,status='Online',rssi=-60,ip='192.168.1.50'):
        ts=(self.now-timedelta(seconds=seconds)).isoformat(timespec='seconds')
        payload={'mac':self.mac,'names':['Fixture phone'],'ips':[ip],'ports':['wlan1'],'reported_status':status,'stations':[]}
        if status=='Online':payload['stations']=[{'rssi_dbm':rssi,'snr_db_reported':40,'rx_link_mbps':144,'tx_link_mbps':72,'interface':'wlan1'}]
        with core.connect() as db:db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',(1,ts,self.mac,json.dumps(payload)))
        return payload
    def test_gaps_presence_identity_and_null_traffic(self):
        for seconds,status in ((900,'Online'),(840,'Online'),(780,'Offline'),(300,'Online'),(240,'Unknown')):self.seed(seconds,status,ip='192.168.1.51' if seconds<400 else '192.168.1.50')
        b=historian.device_history(self.identifier,'1h')
        self.assertEqual(b['quality']['sample_count'],5)
        self.assertEqual(b['quality']['sample_gaps'],1)
        self.assertEqual(b['session_count'],2)
        self.assertEqual(b['presence']['observed_duration_seconds'],60)
        self.assertEqual(b['presence']['percent_of_known_samples'],75)
        self.assertEqual(len(b['identity_history']),2)
        self.assertIsNone(b['stats']['download_mbps']['avg'])
        self.assertIsNone(b['latest']['latency_lan_ms'])
        self.assertEqual(b['capabilities']['client_probe'],'not_configured')
        self.assertEqual(b['device']['quality'],'stale')
        year=historian.device_history(self.identifier,'1y')
        self.assertEqual(year['quality']['sample_count'],5)
        self.assertLess(year['quality']['coverage_percent'],b['quality']['coverage_percent'])
        self.assertEqual(b['events'],[])
    def test_bucket_extrema_and_no_invented_data(self):
        self.seed(40,rssi=-80);self.seed(39,rssi=-40)
        b=historian.device_history(self.identifier,'1y')
        self.assertEqual(b['stats']['rssi_dbm']['min'],-80)
        self.assertEqual(b['stats']['rssi_dbm']['max'],-40)
        self.assertEqual(b['stats']['rssi_dbm']['avg'],-60)
        envelope=next(p['values']['rssi_dbm'] for p in b['series'] if p['values']['rssi_dbm']['sample_count'])
        self.assertEqual((envelope['min'],envelope['max']),(-80,-40))
        with self.assertRaises(ValueError):historian.device_history('../bad')
        with self.assertRaises(ValueError):historian.device_history(self.identifier,'bad')
        with self.assertRaises(LookupError):historian.device_history('020000000099')
        self.assertEqual(historian.overview_history()['series'],[])
    def test_http_export_all_observations_and_periods(self):
        payload=self.seed(1)
        with core.connect() as db:
            db.executemany('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',[(1,(self.now-timedelta(seconds=i+2)).isoformat(timespec='seconds'),self.mac,json.dumps(payload)) for i in range(2100)])
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{server.server_address[1]}/api/v1/devices/{self.identifier}'
        try:
            for period in historian.PERIODS:
                with urllib.request.urlopen(url+'?period='+period) as response:b=json.load(response)
                self.assertEqual(b['quality']['sample_count'],2101)
            with urllib.request.urlopen(url+'/export.json?period=1h') as response:export=json.load(response)
            self.assertEqual(len(export),2101)
            self.assertEqual(export[0]['observation']['mac'],self.mac)
            self.assertIsNone(export[0]['measurement']['download_mbps'])
            with urllib.request.urlopen(url+'/export.csv?period=1h') as response:rows=list(csv.DictReader(io.StringIO(response.read().decode('utf-8-sig'))))
            self.assertEqual(len(rows),2101)
            self.assertEqual(rows[0]['download_mbps'],'')
            self.assertEqual(json.loads(rows[0]['observation_json']),payload)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(url+'?period=invalid')
            self.assertEqual(error.exception.code,400)
        finally:server.shutdown();server.server_close();worker.join(3)

if __name__=='__main__':unittest.main()
