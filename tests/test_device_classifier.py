"""Pure synthetic categorization contract. No identifiable real LAN values."""
import unittest
from app.device_classifier import classify_client

class CategoryTests(unittest.TestCase):
    def classify(self,names=(),types=(),mac='02:00:00:00:00:01'):
        return classify_client({'names':list(names),'device_types':list(types),'mac':mac})
    def test_strong_device_classes(self):
        cases=[
            (['Fixture-PS5'],[],'game_console'),
            (['Roomba-TEST'],[],'robot_vacuum'),
            (['Galaxy-Tab-Fixture'],[],'tablet'),
            (['S23-de-Teste'],['android-dhcp-16'],'smartphone'),
            (['Fixture-Predator'],['MSFT 5.0'],'laptop'),
            (['Fixture-PC'],['MSFT 5.0'],'desktop'),
            (['Fixture-Printer'],[],'printer'),
            (['Fixture-Access-Point'],[],'network_device'),
            (['Fixture-Smart-TV'],[],'smart_tv'),
            (['Fixture-Chromecast'],[],'streaming_box')
        ]
        for names,types,expected in cases:
            with self.subTest(names=names):
                r=self.classify(names,types)
                self.assertEqual(r['category'],expected)
                self.assertTrue(r['evidence'])
                self.assertFalse(r['confirmed'])
    def test_protocol_signature_is_not_os_or_class_proof(self):
        r=self.classify(['fixture-host'],['MSFT 5.0'])
        self.assertEqual(r['category'],'unknown')
        self.assertEqual(r['platform_family'],'unknown')
        r=self.classify(['fixture-host'],['android-dhcp-16'])
        self.assertEqual(r['category'],'unknown')
        self.assertEqual(r['platform_family'],'android')
    def test_mac_and_interface_alone_cannot_classify(self):
        for mac in ('02:00:00:00:00:01','00:11:22:33:44:55'):
            r=self.classify(['wlan0'],[],mac)
            self.assertEqual(r['category'],'unknown')
            self.assertEqual(r['confidence'],'unknown')
    def test_conflict_downgrades_to_unknown(self):
        r=self.classify(['Fixture-Roomba','Fixture-PS5'])
        self.assertEqual(r['category'],'unknown')
        self.assertEqual(r['conflicts'],['game_console','robot_vacuum'])
    def test_reproducible_and_preserves_unknowns(self):
        data={'names':['unknown-fixture'],'device_types':[],'mac':'00:11:22:33:44:55'}
        self.assertEqual(classify_client(data),classify_client(data))
        self.assertIsNone(classify_client(data)['display_name_suggestion'] if not data['names'] else None)
        self.assertEqual(classify_client({})['platform_family'],'unknown')
    def test_taxonomy_and_version(self):
        r=self.classify(['Roomba-fixture'])
        self.assertEqual(r['category'],'robot_vacuum')
        self.assertNotEqual(r['classification_version'],'')
        self.assertIn(r['confidence'],('high','medium','low','unknown'))

if __name__=='__main__':unittest.main()
