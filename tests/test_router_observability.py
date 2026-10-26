import json
import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import MagicMock,patch
from app import core,router_observability as o
from app.adapters import huawei_b7 as h
from test_huawei import fixture,payload


def js(name,*values):return 'function '+name+'(){};new '+name+'('+','.join(json.dumps(str(v)) for v in values)+');'
def bundle(source,data,seconds=0,status='ok'):
    return {source:{'collected_at':(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(),'status':status,'reason':None if status=='ok' else 'transport','data':data}}


class ObservationTests(unittest.TestCase):
    def test_every_confirmed_contract_and_private_projection(self):
        domain='InternetGatewayDevice.LANDevice.1.WLANConfiguration.1'
        wifi=[domain,'Private network name','1','Private SSID','0','11ax','36','80','PT','1','3','1','0','1','1','0','9','-70','1','0','0','1','0','0','0','WPA2','AES','AES','AES','AES','1','3600']
        examples={
            'radio_settings':js('stWlanWifi',*wifi)+js('stWlanAdv',domain,1,100,2347,2346)+js('stAttachConf',domain,1,0,1,'Long'),
            'guest_limits':js('stGuestLimitInfo','guest',100,200),
            'guest_network':js('stGuestIpInfo','guest','192.168.10.20','192.168.10.200','domain'),
            'client_modes':js('stWifiWorkingMode','domain','11ax','192.168.1.50','02:00:00:00:00:01'),
            'upnp':js('stUpnpPortMapping',1,3600,'198.51.100.1',1234,1234,'TCP','192.168.1.50','Fixture mapping'),
            'firewall_v4':js('stPortFilter','domain',1,0,2),'firewall_v6':js('stPortFilter','domain',1,0,2),
            'wan_acl':js('WanAccessItemClass','domain',0,'HTTP','Private WAN name','198.51.100.0/24'),
            'dhcp':js('DHCPInfo','domain','Fixture phone','192.168.1.50','02:00:00:00:00:01',300,'phone','WiFi','DHCP',100),
            'client_details':js('USERDevice','domain','192.168.1.50','02:00:00:00:00:01','SSID1','IPv4','phone','Online','WiFi',120,'Fixture phone',1,1,'phone','Fixture alias','phone',300),
            'ipv6':js('IPv6WanInfo','domain','IP','Connected','IPoE','02:00:00:00:00:01',10,0,'2001:db8::53','private.example','2001:db8::1','2001:db8::2',100)+js('IPv6AddressInfo','domain','Preferred','DHCPv6','2001:db8::3',100,200,150)+js('IPv6PrefixInfo','domain','DHCPv6','2001:db8:1::/64',100,200,150),
            'wps':js('stWpsPin',domain,0,'PBC'),'wifi_features':"var mloEnable='0';var password='DO_NOT_STORE';",
            'usb_voice':js('stPhysicalMedium','domain','Private USB label','Present',0)+js('stLine','domain','+351000000000','line','Up','Idle','0')+"var wlanChipType2G='QCN6224';",
            'lan_settings':js('stMainDhcpInfo','domain',1,'192.168.1.20','192.168.1.200',86400,'private.example','192.168.1.1')+js('stLanHostInfo','domain',1,'192.168.1.1','255.255.255.0')+js('stDhcpStaticInfo','domain','192.168.1.50','02:00:00:00:00:01'),
            'ipv6_lan':js('stRouterAdver','domain',1,1,1)+js('stIpv6DNSConfig','domain','Auto','2001:db8::53'),
            'topology':js('LanInfoClass','domain','Private LAN',1,'Bridge',10,0,0),
            'radios':js('stRadio','domain','5GHz',1),
            'band_steering':js('stDisallowSta','domain','Fixture phone','02:00:00:00:00:01'),
            'wifi_schedule':js('stDuration','domain','08:00','22:00','12345',1,'3','Private schedule'),
            'mac_policy':js('stMacFilterArr','domain',1,0,1,0),
            'file_services':js('stFtpSrvCfg','domain',0,'Private username',21,'/private/path',1,0)+js('stSftpSrvCfg','domain',0,22,0),
            'dlna':js('stDlnaService','domain',0,0,'Private alias'),
            'wan_nat':js('stWANInfo','domain','Private WAN','INTERNET',1,'198.51.100.7',1,'IP_Routed'),
            'voice_schedule':js('stRingSchedule','domain',0,1),
            'wifi_backhaul':js('stAttachConf',domain,1,'0'),
            'client_addresses':js('stUserDevInfoPTVDF','Fixture phone','phone','192.168.1.50','02:00:00:00:00:01','Online','SSID1',100,300,'domain','DO_NOT_STORE','DO_NOT_STORE','DO_NOT_STORE'),
            'station_details':js('stAssociatedDevice',domain,'02:00:00:00:00:01',100,1000,900,-50,-90,40,80,'11ax',1,0,1,'192.168.1.50','Fixture phone','2*2',1,1,1,1,'0',1,1,1,1,1,1,1,1),
        }
        self.assertEqual(set(examples),set(o.SOURCES))
        for source,raw in examples.items():
            with self.subTest(source=source):
                data=o.parse(source,raw);self.assertTrue(data);o.validate(bundle(source,data))
                encoded=json.dumps(data)
                for secret in ('Private network','Private SSID','Private WAN','198.51.100.','2001:db8','private.example','+351','Private USB','Private username','/private/path','DO_NOT_STORE'):
                    self.assertNotIn(secret,encoded)
                with self.assertRaises(ValueError):o.parse(source,'unsupported page')
        radio=o.parse('radio_settings',examples['radio_settings'])[0]
        self.assertEqual((radio['channel_reported'],radio['power_pct'],radio['width_policy_code'],radio['rssi_threshold_setting']),(36,80,3,-70))
        self.assertEqual(o.parse('dhcp',examples['dhcp'])[0]['lease_elapsed_reported_seconds'],100)
        # The two inventory branches must agree before deduplication.
        self.assertEqual(len(o.parse('client_details',examples['client_details']+examples['client_details'])),1)
        conflicting=o.parse('client_details',examples['client_details']+examples['client_details'].replace('Fixture phone','Other phone'))[0]
        self.assertIsNone(conflicting['name']);self.assertEqual(conflicting['conflicting_fields'],['name']);self.assertEqual(conflicting['reported_rows'],2)
        self.assertEqual(conflicting['mac'],'02:00:00:00:00:01')
        sentinel=examples['station_details'].replace('"-50"','"4294967295"').replace('"80"','"4294967295"')
        station=o.parse('station_details',sentinel)[0]
        self.assertIsNone(station['rssi_dbm']);self.assertIsNone(station['signal_quality_reported']);self.assertEqual(station['rx_link_mbps'],1000)
        bare=examples['station_details'].split(';',1)[1]
        self.assertEqual(o.parse('station_details',bare),o.parse('station_details',examples['station_details']))

    def test_source_trends_are_bounded_indexed_and_private(self):
        db=sqlite3.connect(':memory:')
        db.row_factory=sqlite3.Row
        try:
            o.init_db(db)
            anchor=datetime.now(timezone.utc)-timedelta(minutes=18)
            for i in range(6):
                ts=(anchor+timedelta(minutes=i*3)).isoformat()
                status='ok' if i!=2 else 'unavailable'
                values=[
                    {'mac':'02:00:00:00:00:01','ip':'192.0.2.99',
                     'rssi_dbm':-60+i,'snr_db_reported':30+i},
                    {'mac':'02:00:00:00:00:02','ip':'192.0.2.98',
                     'rssi_dbm':None,'snr_db_reported':None},
                ]
                db.execute("INSERT INTO router_observations(source,ts,status,reason,payload) VALUES(?,?,?,?,?)",
                           ('station_details',ts,status,None,json.dumps(values) if status=='ok' else None))
            small=o.trend(db,'station_details',24,3)
            self.assertTrue(small['truncated'])
            self.assertEqual(len(small['points']),3)
            self.assertEqual(small['points'][0]['record_count'],2)
            self.assertIn('rssi_mean_dbm',small['points'][0])
            self.assertNotIn('mac',json.dumps(small))
            self.assertNotIn('192.0.2',json.dumps(small))
            all_points=o.trend(db,'station_details',24)
            self.assertFalse(all_points['truncated'])
            self.assertEqual(len(all_points['points']),6)
            self.assertIsNone(all_points['points'][2]['record_count'])
            self.assertIsNone(all_points['points'][2].get('rssi_mean_dbm'))
            self.assertEqual(all_points['points'][0]['rssi_mean_dbm'],-60)
            self.assertEqual(all_points['metrics'][1]['unit'],'dBm')
            self.assertEqual(o.trend(db,'upnp',24)['points'],[])
            for source,hours,limit in [('unknown',24,400),('upnp',float('nan'),400),
                                       ('upnp',0,400),('upnp',24,401),('upnp',24,0)]:
                with self.assertRaises(ValueError):
                    o.trend(db,source,hours,limit)
        finally:
            db.close()

    def test_empty_upnp_is_distinct_from_failed_schema(self):
        self.assertEqual(o.parse('upnp',js('stUpnpPortMapping',0,0,'',0,0,'','0.0.0.0','')),[])
        self.assertEqual(o.parse('upnp','function stUpnpPortMapping(){};'),[])
        with self.assertRaises(ValueError):o.parse('upnp','login required')
        with self.assertRaises(ValueError):o.parse('upnp',js('stUpnpPortMapping',1,'bad'))
        self.assertIsNone(o.private_ip('8.8.8.8'))

    def test_strict_ingestion_and_history_semantics(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(core,'DB_PATH',Path(temp)/'test.db'):
            core.init_db()
            def store(data,age,status='ok',historical=False):
                p=payload();p['collected_at']=(datetime.now(timezone.utc)+timedelta(seconds=age)).isoformat();p['observability']=bundle('upnp',data,age,status);core.put_huawei_sample(p,historical=historical)
            mapping={'enabled':True,'external_port':1234,'internal_port':1234,'protocol':'TCP','client_ip':'192.168.1.50','lease_seconds_reported':300}
            store([mapping],-1200,historical=True)
            store([dict(mapping,lease_seconds_reported=100)],-900,historical=True)
            store(None,-600,'unavailable',True)
            store([],0)
            with core.connect() as db:
                result=o.read(db);change=result['changes'][0]
                self.assertEqual(len(result['changes']),1);self.assertTrue(change['crosses_gap'])
                self.assertEqual(change['detail']['removed'],1)
                self.assertEqual(change['detail']['before_count'],1)
                self.assertEqual(change['detail']['after_count'],0)
                self.assertIn('external_port',change['detail']['changed_fields'])
                comparison=o.read_change(db,change['id'])
                self.assertEqual(comparison['before'][0]['external_port'],1234)
                self.assertEqual(comparison['after'],[])
                self.assertIsNone(o.read_change(db,999999))
                arch=o.archive(db,'upnp',limit=2);self.assertTrue(arch['has_more']);self.assertEqual(len(o.archive(db,'upnp',arch['next_after'])['records']),2)
                self.assertEqual(next(s for s in result['sources'] if s['id']=='upnp')['data'],[])
                p=payload();p['observability']=bundle('upnp',[dict(mapping,password='secret')])
                with self.assertRaises(ValueError):h.validate_payload(p)
                with self.assertRaises(ValueError):o.read(db,float('nan'))
                with self.assertRaises(ValueError):o.archive(db,'unknown')
                snapshot=bundle('upnp',[],0);o.persist(db,snapshot)
                snapshot['upnp']['data']=[mapping]
                with self.assertRaises(ValueError):o.persist(db,snapshot)
                self.assertEqual(o.stable([mapping],'upnp'),o.stable([dict(mapping,lease_seconds_reported=1)],'upnp'))

    def test_shared_connection_cadence_and_original_timestamps(self):
        clock=[1000];adapter=h.HuaweiB7('192.168.1.1','fixture','fixture',clock=lambda:clock[0]);adapter.cookie='synthetic'
        conn=MagicMock()
        with patch.object(adapter,'_request',return_value=('unsupported',[])) as request:
            first=o.collect(adapter,conn);count=request.call_count
            self.assertEqual(count,len({v[0] for v in o.SOURCES.values()}))
            self.assertTrue(all(c.args[0] is conn and c.kwargs['cookie']=='synthetic' for c in request.call_args_list))
            clock[0]+=61;self.assertEqual(o.collect(adapter,conn),first);self.assertEqual(request.call_count,count)
            clock[0]+=300;o.collect(adapter,conn);self.assertEqual(request.call_count,count*2)
        adapter.next_observation_attempt=0
        with patch.object(adapter,'_request',side_effect=h.AuthenticationError('expired')):
            with self.assertRaises(h.AuthenticationError):o.collect(adapter,conn)

    def test_authentication_failure_preserves_server_without_retry(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(core,'DB_PATH',Path(temp)/'test.db'):
            adapter=MagicMock();adapter.collect.side_effect=h.AuthenticationError('expired')
            with patch('app.adapters.huawei_b7.time.sleep',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):h.run_collector(adapter,12345,'x'*32,True,keep_serving_on_auth_error=True)
            self.assertEqual(adapter.collect.call_count,1)
            self.assertEqual(core.COLLECTOR_STATE['state'],'auth_blocked')
            adapter.close.assert_called_once()

    def test_optional_auth_failure_must_reach_session_manager(self):
        adapter=h.HuaweiB7('192.168.1.1','fixture','fixture')
        pages={'/index.asp':fixture('index'),**{h.PATHS[k]:fixture(k) for k in h.PATHS}}
        def request(c,m,p,**kwargs):
            if p==h.PATHS['system']:raise h.AuthenticationError('expired')
            return pages[p],[]
        with patch.object(adapter,'_request',side_effect=request):
            with self.assertRaises(h.AuthenticationError):adapter._read_data(MagicMock())


if __name__=='__main__':unittest.main()
