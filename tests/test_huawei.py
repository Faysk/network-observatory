import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock
import http.client
from app import core
from app.adapters import huawei_b7 as h

FIXTURES = Path(__file__).parent / 'fixtures'


def fixture(section):
    return (FIXTURES / f'huawei_b7_{section}.html').read_text(encoding='utf-8')


def payload():
    return {'firmware':h.FIRMWARE, 'collected_at':datetime.now(timezone.utc).isoformat(),
            'metrics':h.parse_optic(fixture('optic')),
            'interfaces':{**h.parse_wan(fixture('wan')), **h.parse_lan(fixture('lan'))}}


class HuaweiTests(unittest.TestCase):
    def test_private_inventory_merge_and_history(self):
        raw=fixture('stations')
        _,stations,_=h.parse_stations(raw)
        neighbor='new NeighInfo("domain","fd00::50","02:00:00:00:00:01","lan2","Stale");'
        clients=h.parse_clients(raw,stations,neighbor)
        wan_neighbor='new NeighInfo("domain","192.0.2.1","02:00:00:00:00:99","InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1","Reachable");'
        self.assertEqual(h.parse_clients(raw,stations,neighbor+wan_neighbor),clients)
        self.assertEqual(len(clients),1)
        self.assertEqual(clients[0]['ips'],['192.168.1.50','fd00::50'])
        self.assertEqual(clients[0]['mac'],'02:00:00:00:00:01')
        unusual=raw.replace('Fixture phone','Fixture (phone), desk')
        self.assertEqual(h.parse_stations(unusual)[1][0]['description'],'Fixture (phone), desk')
        p=payload();p.update(clients=clients,stations=stations)
        h.validate_payload(p)
        for field,value in (('password','secret'),('ips',['not-an-ip']),('mac','bad-mac')):
            bad=json.loads(json.dumps(p));bad['clients'][0][field]=value
            with self.assertRaises(ValueError):h.validate_payload(bad)
        with tempfile.TemporaryDirectory() as temp,patch.object(core,'DB_PATH',Path(temp)/'test.db'):
            core.init_db()
            p['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=120)).isoformat()
            core.put_huawei_sample(p)
            # Missing from the next snapshot must not manufacture a disconnect.
            missing=payload();missing['clients']=[]
            missing['collected_at']=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
            core.put_huawei_sample(missing)
            self.assertEqual(len(core.get_events()),0)
            p['collected_at']=datetime.now(timezone.utc).isoformat()
            p['clients'][0]['reported_status']='Offline';p['stations']=[]
            core.put_huawei_sample(p)
            self.assertEqual(len(core.get_events()),1)
            result=core.get_router_clients()['clients']
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['observations'],2)
            self.assertEqual(result[0]['reported_status'],'Offline')
            history=core.get_router_clients(clients[0]['mac'])['observations']
            self.assertEqual(history[1]['stations'][0]['rssi_dbm'],-62)
            self.assertEqual(history[0]['stations'],[])
            with core.connect() as db:
                db.execute('UPDATE huawei_samples SET ts=?',((datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat(),))
            self.assertEqual(core.get_status()['huawei']['clients'],[])
            with self.assertRaises(ValueError):core.get_router_clients("' OR 1=1")

    def test_extended_sources_privacy_and_validation(self):
        metrics,system,wifi=h.parse_system(fixture('system'))
        self.assertEqual(metrics['cpu_pct'],20)
        self.assertEqual(metrics['uptime_seconds'],123456)
        networks,stations,inventory=h.parse_stations(fixture('stations'))
        self.assertEqual(networks['wlan1']['client_limit'],128)
        self.assertEqual(len(stations),1)
        self.assertEqual(stations[0]['rssi_dbm'],-62)
        p=payload();p['metrics'].update(metrics)
        p.update(system=system,wifi=networks,stations=stations,inventory=inventory,
                 health=h.parse_health(fixture('optic')),wan_states=h.parse_wan_states(fixture('wan_states')),
                 voice=h.parse_voice(fixture('voice')),sections={'system':'ok'})
        h.validate_payload(p)
        self.assertNotIn('REDACTED',json.dumps(p))
        self.assertEqual(h.parse_wan_packets(fixture('wan_packets'))['wan1']['tx_unicast_packets'],100)
        for section in ('system','health','inventory'):
            bad=json.loads(json.dumps(p));bad[section]['serial']='secret'
            with self.assertRaises(ValueError):h.validate_payload(bad)
        for section,key in (('wifi','wlan1'),('wan_states','wan1'),('voice','line1')):
            bad=json.loads(json.dumps(p));bad[section][key]['mac']='secret'
            with self.assertRaises(ValueError):h.validate_payload(bad)
        bad=json.loads(json.dumps(p));bad['stations'][0]['password']='secret'
        with self.assertRaises(ValueError):h.validate_payload(bad)
        raw=fixture('stations')
        import re
        empty=re.sub(r'new stAssociatedDevice\([^;]+;', '',raw)
        self.assertEqual(h.parse_stations(empty)[1],[])
        with self.assertRaises(h.AdapterError):h.parse_stations('unsupported page')

    def test_optional_failure_preserves_baseline(self):
        adapter=h.HuaweiB7('192.168.1.1','test','test')
        pages={'/index.asp':fixture('index'),**{h.PATHS[k]:fixture(k) for k in h.PATHS}}
        def request(c,m,p,**kw):
            if p==h.PATHS['system']:raise h.AdapterError('schema_changed')
            return pages[p],[]
        with patch.object(adapter,'_request',side_effect=request):
            result=adapter._read_data(MagicMock())
        h.validate_payload(result)
        self.assertEqual(result['sections']['system'],'unavailable')
        self.assertNotIn('cpu_pct',result['metrics'])
        self.assertEqual(result['sections']['stations'],'ok')

    def test_idle_socket_reconnects_get_once_and_never_replays_login(self):
        adapter=h.HuaweiB7('192.168.1.1','fixture-user','fixture-password')
        conn=MagicMock()
        response=MagicMock()
        response.status=200
        response.read.return_value=b'fixture-response'
        response.getheaders.return_value=[]
        conn.getresponse.side_effect=[http.client.RemoteDisconnected(),response]
        self.assertEqual(adapter._request(conn,'GET','/index.asp')[0],'fixture-response')
        self.assertEqual(conn.request.call_count,2)
        conn.close.assert_called_once()
        conn.reset_mock()
        conn.getresponse.side_effect=[TimeoutError(),response]
        self.assertEqual(adapter._request(conn,'GET','/index.asp')[0],'fixture-response')
        self.assertEqual(conn.request.call_count,2)
        conn.reset_mock()
        conn.getresponse.side_effect=http.client.RemoteDisconnected()
        with self.assertRaises(http.client.RemoteDisconnected):
            adapter._request(conn,'POST','/login.cgi',body='synthetic')
        self.assertEqual(conn.request.call_count,1)

    def test_model_javascript_escaped_hyphen(self):
        self.assertEqual(h.parse_model(r'var productName="HG8247B7\x2d8N";'),'HG8247B7-8N')
        self.assertEqual(h.parse_model(r"var productName = 'HG8247B7\x2d8N';"),'HG8247B7-8N')
        with self.assertRaises(h.AdapterError): h.parse_model('var productName="other";')

    def test_credentials_file_formats_and_safe_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'credentials.txt'
            for text in ('Login\nfixture-user\nPass\nfixture-password',
                         'username=fixture-user\npassword=fixture-password',
                         'Login: fixture-user\nSenha: fixture-password'):
                path.write_text(text,encoding='utf-8-sig')
                self.assertEqual(h.load_credentials(path),('fixture-user','fixture-password'))
            path.write_text('sensitive-invalid-content',encoding='utf-8')
            with self.assertRaises(ValueError) as error: h.load_credentials(path)
            self.assertNotIn('sensitive-invalid-content',str(error.exception))

    def test_fixture_optic_allowlist(self):
        result = h.parse_optic(fixture('optic'))
        self.assertEqual(result['optical_rx_dbm'], -21.5)
        self.assertEqual(result['optical_temp_c'],34)
        self.assertEqual(set(result), set(h.OPTIC))
        self.assertNotIn('REDACTED',json.dumps(result))

    def test_counter_halves_and_link(self):
        result = h.parse_lan(fixture('lan'))['lan4']
        self.assertEqual(result['rx_bytes'], 2*2**32+10)
        self.assertEqual(result['tx_bytes'], 3*2**32+20)
        self.assertEqual(result['speed_mbps'],2500)
        self.assertEqual(result['duplex'],'full')
        self.assertEqual(h.parse_wan(fixture('wan'))['wan1']['rx_bytes'],9000)

    def test_absent_optical_value(self):
        result = h.parse_optic(fixture('optic').replace('"-21.5"','"--"'))
        self.assertNotIn('optical_rx_dbm',result)

    def test_expired_session_and_bad_schemas(self):
        for parser in (h.parse_optic,h.parse_wan,h.parse_lan):
            with self.assertRaises(h.AuthenticationError):
                parser('<input id="userpwd" type="password">')
            with self.assertRaises(h.AdapterError):
                parser('<html>No supported data</html>')
        with self.assertRaises(h.AdapterError):
            h.parse_optic(fixture('optic').replace('"2.5"','doSomething()'))

    def test_ingestion_rejects_sensitive_fields_nan_and_old_time(self):
        h.validate_payload(payload())
        for change in ('serial','nan','old','counter'):
            p=payload()
            if change=='serial': p['metrics']['serial']='REDACTED'
            if change=='nan': p['metrics']['optical_temp_c']=float('nan')
            if change=='old': p['collected_at']=(datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat()
            if change=='counter': p['interfaces']['wan1']['rx_bytes']=-1
            with self.assertRaises(ValueError): h.validate_payload(p)

    def test_persistence_stale_is_not_live(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(core,'DB_PATH',Path(temp)/'test.db'):
            core.init_db()
            self.assertEqual(core.get_status()['huawei']['quality'],'unavailable')
            p=payload();core.put_huawei_sample(p)
            self.assertEqual(core.get_status()['huawei']['quality'],'ok')
            with core.connect() as db:
                db.execute('UPDATE huawei_samples SET ts=?',((datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat(),))
            stale=core.get_status()['huawei']
            self.assertEqual(stale['quality'],'stale')
            self.assertEqual(stale['metrics'],{})
            self.assertEqual(stale['interfaces'],{})

    def test_collect_cache_allowlist_and_backoff(self):
        clock=[1000]
        adapter=h.HuaweiB7('192.168.1.1','test','test',clock=lambda:clock[0])
        adapter.cookie='synthetic-session'
        pages={'/':'var productName = "HG8247B7";', '/index.asp':fixture('index'), **{h.PATHS[k]:fixture(k) for k in h.PATHS}}
        with patch.object(adapter,'_request',side_effect=lambda c,m,p,**kw:(pages[p],[])) as request:
            result=adapter.collect()
            from app.router_observability import SOURCES
            initial_calls=10+len({v[0] for v in SOURCES.values()})
            self.assertEqual(request.call_count,initial_calls)
            self.assertIs(adapter.collect(),result)
            self.assertEqual(request.call_count,initial_calls)
            clock[0]+=61
            adapter.collect()
            self.assertEqual(request.call_count,initial_calls+9)
            self.assertEqual(len({id(c.args[0]) for c in request.call_args_list}),1)
        adapter.close()
        with self.assertRaises(h.AdapterError):
            adapter._request(None,'POST','/set.cgi')
        for expected in (120,240,900):
            clock[0]=adapter.next_attempt
            with patch.object(adapter,'_request',side_effect=OSError), self.assertRaises(h.AdapterError):
                adapter.collect()
            self.assertEqual(adapter.next_attempt-clock[0],expected)

    def test_no_public_target(self):
        with self.assertRaises(ValueError): h.HuaweiB7('8.8.8.8','test','test')

    def test_login_uses_same_connection_and_never_retries_bad_credentials(self):
        adapter=h.HuaweiB7('192.168.1.1','fixture-user','fixture-password')
        marker=object()
        replies=[('a'*32,[]),('',[('Set-Cookie','Cookie=synthetic-session; path=/')])]
        with patch.object(adapter,'_request',side_effect=replies) as request:
            adapter._login(marker)
        self.assertTrue(all(call.args[0] is marker for call in request.call_args_list))
        self.assertEqual(adapter.cookie,'Cookie=synthetic-session')
        adapter=h.HuaweiB7('192.168.1.1','fixture-user','fixture-password')
        with patch.object(adapter,'_request',return_value=('invalid challenge',[])) as request:
            with self.assertRaises(h.AuthenticationError): adapter._login(marker)
            self.assertEqual(request.call_count,1)

    def test_session_renewal_is_bounded_and_rate_limited(self):
        clock=[1000]
        adapter=h.HuaweiB7('192.168.1.1','fixture-user','fixture-password',clock=lambda:clock[0])
        adapter.verified_model='HG8247B7-8N'
        adapter.cookie='synthetic-session'
        adapter.cached=payload()
        adapter.last_login_attempt=939
        with patch.object(adapter,'_read_data',side_effect=[h.AuthenticationError('session_expired'),payload()]), patch.object(adapter,'_login') as login:
            adapter.collect()
            self.assertEqual(login.call_count,1)
            self.assertEqual(adapter.renewals,1)
        clock[0]+=61
        adapter.cookie='synthetic-renewed-session'
        with patch.object(adapter,'_read_data',side_effect=h.AuthenticationError('session_expired')) as read, patch.object(adapter,'_login') as login:
            with self.assertRaises(h.AuthenticationError): adapter.collect()
            self.assertEqual(login.call_count,1)
            self.assertEqual(read.call_count,2)
        adapter.last_login_attempt=clock[0]
        with patch.object(adapter,'_request') as request:
            with self.assertRaises(h.AuthenticationError): adapter._login(None)
            request.assert_not_called()
