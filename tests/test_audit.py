import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from datetime import datetime,timezone,timedelta
from app import core,audit
from app.adapters import huawei_b7 as h
from test_huawei import fixture

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(core,'DB_PATH',Path(self.temp.name)/'test.db');self.dbpatch.start();core.init_db()
    def tearDown(self):self.dbpatch.stop();self.temp.cleanup()
    def collect_fixture(self):
        pages={key:fixture(key) for key in h.PATHS};pages['index']=fixture('index')
        pages['lan']+='\nnew stPacketInfo("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1","1001","1002","1003","1004");\nnew stStats("InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Stats","2001","2002","2003","2004");'
        original=audit.rows(pages['wan_packets'],'WaninfoStats',11)[0]
        pages['wan_packets']='new WaninfoStats('+','.join(json.dumps(x) for x in [original[0]]+[str(i) for i in range(1001,1011)])+');'
        adapter=h.HuaweiB7('192.168.1.1','fixture-user','fixture-password')
        lookup={**{path:pages[key] for key,path in h.PATHS.items()},'/index.asp':pages['index']}
        with patch.object(adapter,'_request',side_effect=lambda c,m,p,**kw:(lookup[p],[])):
            result=adapter._read_data(MagicMock())
        return pages,result
    def test_independent_reference_checks_every_parsed_value(self):
        pages,payload=self.collect_fixture();h.validate_payload(payload)
        check=audit.source_check(pages,payload)
        self.assertEqual(check['mismatches'],[])
        self.assertGreater(check['checked_values'],100)
        self.assertEqual(payload['wan_packet_totals']['wan1']['tx_bytes'],1001)
        self.assertEqual(payload['wan_packet_totals']['wan1']['rx_bytes'],1002)
        self.assertEqual(payload['interfaces']['wan1']['rx_bytes'],9000)
        self.assertEqual(payload['interfaces']['wan1']['tx_unicast_packets'],1005)
        self.assertEqual(payload['wifi']['wlan1']['tx_bytes'],1001)
        self.assertEqual(payload['wifi']['wlan1']['rx_bytes'],1003)
        self.assertEqual(payload['wifi']['wlan1']['tx_errors'],2001)
        self.assertEqual(payload['wifi']['wlan1']['rx_errors'],2002)
        self.assertEqual(payload['wifi']['wlan1']['tx_drops'],2003)
        self.assertEqual(payload['wifi']['wlan1']['rx_drops'],2004)
        for path,value in audit.leaves(payload):
            if path.startswith('sections') or path=='collected_at' or isinstance(value,(dict,list)):continue
            broken=json.loads(json.dumps(payload));tokens=re.findall(r'[^.\[\]]+',path);node=broken
            for token in tokens[:-1]:node=node[int(token)] if isinstance(node,list) else node[token]
            token=int(tokens[-1]) if isinstance(node,list) else tokens[-1]
            node[token]=not value if type(value) is bool else value+1 if type(value) in (int,float) else 'corrupted' if value is None else value+'-corrupted'
            self.assertTrue(audit.source_check(pages,broken)['mismatches'],path)
        report=json.dumps(check)
        for secret in ('02:00:00:00:00:01','192.168.1.50','Fixture phone'):self.assertNotIn(secret,report)
    def test_every_value_survives_storage_and_duplicate_is_idempotent(self):
        _,payload=self.collect_fixture();payload['interfaces']['wan1']['tx_bytes']=2**64-1
        payload['interfaces']['lan4']['rx_bytes']=2**53+123
        payload['clients'][0]['names'].append('Câmara / Televisão ✓')
        core.put_huawei_sample(payload)
        self.assertEqual(audit.saved_check(payload)['mismatches'],[])
        core.put_huawei_sample(payload)
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM huawei_samples').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM router_client_samples').fetchone()[0],1)
            saved=json.loads(db.execute('SELECT payload FROM huawei_samples').fetchone()[0])
        self.assertEqual(saved,payload)
        self.assertEqual(saved['interfaces']['wan1']['tx_bytes'],18446744073709551615)
        changed=json.loads(json.dumps(payload));changed['metrics']['cpu_pct']=21
        with self.assertRaises(ValueError):core.put_huawei_sample(changed)
        with core.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM huawei_samples').fetchone()[0],1)
    def test_transaction_rolls_back_all_rows(self):
        _,first=self.collect_fixture();first['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat();core.put_huawei_sample(first)
        later=json.loads(json.dumps(first));later['collected_at']=datetime.now(timezone.utc).isoformat();later['clients'][0]['reported_status']='Offline';later['stations']=[]
        with patch.object(core,'emit',side_effect=RuntimeError('fixture-failure')):
            with self.assertRaises(RuntimeError):core.put_huawei_sample(later)
        with core.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM huawei_samples').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM router_client_samples').fetchone()[0],1)
    def test_exact_firmware_and_historical_validation(self):
        self.assertEqual(h.parse_identity(fixture('index')),h.FIRMWARE)
        with self.assertRaises(h.AdapterError):h.parse_identity(fixture('index').replace(h.FIRMWARE,'OTHER')+'<!-- '+h.FIRMWARE+' -->')
        _,payload=self.collect_fixture();payload['collected_at']='2000-01-01T00:00:00+00:00'
        h.validate_payload(payload,require_recent=False)
        with self.assertRaises(ValueError):h.validate_payload(payload)

    def test_outbox_survives_failure_restart_and_lost_acknowledgement(self):
        from app.outbox import Outbox
        folder=Path(self.temp.name)/'outbox';queue=Outbox(folder)
        _,payload=self.collect_fixture();queue.enqueue(payload)
        with self.assertRaises(OSError):queue.flush(MagicMock(side_effect=OSError('fixture')))
        self.assertEqual(Outbox(folder).pending(),1)
        def lost_acknowledgement(p):
            core.put_huawei_sample(p)
            raise OSError('acknowledgement lost')
        with self.assertRaises(OSError):Outbox(folder).flush(lost_acknowledgement)
        self.assertEqual(Outbox(folder).pending(),1)
        self.assertEqual(Outbox(folder).flush(core.put_huawei_sample),1)
        self.assertEqual(Outbox(folder).pending(),0)
        with core.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM huawei_samples').fetchone()[0],1)
        self.assertEqual(audit.saved_check(payload)['mismatches'],[])

    def test_delayed_delivery_keeps_current_state_and_original_time(self):
        _,current=self.collect_fixture();core.put_huawei_sample(current)
        old=json.loads(json.dumps(current));old['collected_at']='2000-01-01T00:00:00+00:00';old['clients'][0]['reported_status']='Offline';old['stations']=[]
        core.put_huawei_sample(old,historical=True)
        self.assertEqual(core.get_status()['huawei']['collected_at'],current['collected_at'])
        self.assertEqual(core.get_router_clients()['clients'][0]['reported_status'],'Online')
        self.assertEqual(core.get_router_clients(old['clients'][0]['mac'])['observations'][0]['collected_at'],current['collected_at'])
        self.assertEqual(core.get_events(),[])

    def test_probe_units_and_every_saved_probe_value(self):
        with patch.object(core.socket,'create_connection',return_value=MagicMock()),patch.object(core.time,'monotonic',side_effect=[100.0,100.012345]):
            self.assertEqual(core.tcp_probe('192.168.1.1'),(True,12.3))
        with patch.object(core,'tcp_probe',side_effect=[(True,12.3),(False,None)]):core.collect_once()
        with core.connect() as db:
            p=dict(db.execute('SELECT * FROM samples ORDER BY id DESC LIMIT 1').fetchone())
        self.assertEqual((p['router_online'],p['router_ms'],p['internet_online'],p['internet_ms']),(1,12.3,0,None))

if __name__=='__main__':unittest.main()

