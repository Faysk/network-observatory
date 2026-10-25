"""Synthetic MAC/OUI regression tests; no LAN/device access."""
import unittest
from unittest.mock import patch
from types import MappingProxyType
from app import device_identity as ident

class MacIdentityTests(unittest.TestCase):
    def test_eui48_normalization(self):
        self.assertEqual(ident.normalize_mac('00-11-22-33-44-55'),'00:11:22:33:44:55')
        self.assertEqual(ident.normalize_mac('001122334455'),'00:11:22:33:44:55')
        self.assertEqual(ident.normalize_mac(' 00:11:22:33:44:55 '),'00:11:22:33:44:55')
        for value in [None,42,'','hi','GG:11:22:33:44:55','00:11:22:33:44','00:11:22:33:44:55:66']:
            self.assertIsNone(ident.normalize_mac(value))
    def test_mac_type(self):
        cases={
            '00:11:22:33:44:55':'global',
            '02:00:00:00:00:01':'locally_administered',
            'F2:38:52:E7:B6:51':'locally_administered',
            '98:e2:55:83:13:fe':'global',
            '01:00:5e:00:00:01':'multicast',
            '00:00:00:00:00:00':'invalid',
            'ff:ff:ff:ff:ff:ff':'invalid',
            'bad':'invalid'}
        for mac,expected in cases.items():
            with self.subTest(mac=mac):self.assertEqual(ident.mac_type(mac),expected)
    def test_prefix_precedence_and_provenance(self):
        dataset=('fixture-v1',MappingProxyType({
            (24,'001122'):'Adapter group',
            (28,'0011223'):'Narrower group',
            (36,'001122334'):'Most specific registrant'
        }))
        r=ident.enrich_mac('00:11:22:33:44:55',dataset=dataset)
        self.assertEqual(r['oui_vendor'],'Most specific registrant')
        self.assertEqual(r['oui_prefix_bits'],36)
        self.assertEqual(r['sources'][0]['source'],'offline_ieee_assignment')
        self.assertEqual(r['oui_dataset_version'],'fixture-v1')
        self.assertEqual(ident.enrich_mac('00:11:22:AA:44:55',dataset=dataset)['oui_prefix_bits'],24)
    def test_local_not_matched_even_if_prefix_in_database(self):
        dataset=('fixture', {(24,'F23852'):'Misleading prefix'})
        r=ident.enrich_mac('f2:38:52:e7:b6:51',dataset=dataset)
        self.assertEqual(r['mac_type'],'locally_administered')
        self.assertIsNone(r['oui_vendor'])
        self.assertEqual(r['sources'],[])
    def test_unknown_dataset_and_unmatched_address(self):
        self.assertIsNone(ident.enrich_mac('00:11:22:33:44:55',dataset=(None,{}))['oui_vendor'])
        self.assertEqual(ident.enrich_mac('01:00:5e:00:00:01')['mac_type'],'multicast')
        self.assertIsNone(ident.enrich_mac(None)['oui_vendor'])
    def test_offline_import_and_1000_synthetic_addresses(self):
        import tempfile
        import json
        import time
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            local=Path(root)/'test-ieee.csv'
            local.write_text('Assignment,Organization Name\\n001122,Fixture Registrant\\n',encoding='utf-8')
            items=ident.load_ieee_csv(local,24)
            self.assertEqual(items,[{'prefix':'001122','prefix_bits':24,'registrant':'Fixture Registrant'}])
        table=('fixture', {(24,'001122'):'Fixture Registrant'})
        start=time.perf_counter()
        results=[ident.enrich_mac('00:11:22:%02x:%02x:%02x'%(i//65536,(i//256)%256,i%256),dataset=table) for i in range(1000)]
        elapsed=(time.perf_counter()-start)*1000
        self.assertEqual(len(results),1000)
        self.assertTrue(all(x['oui_vendor']=='Fixture Registrant' for x in results))
        print('Offline MAC lookup for 1000 fixture addresses:',round(elapsed,3),'ms')
    def test_memory_bounded(self):
        self.assertEqual(ident._dataset.cache_info().maxsize,1)

if __name__=='__main__':unittest.main()
