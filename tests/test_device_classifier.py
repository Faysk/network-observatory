"""Synthetic, falsifiable device classification tests. No real device identity."""
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from app import core
from app.device_classifier import (
    CLASSIFICATION_VERSION, CATEGORIES, PLATFORMS, classify_client,
)


def classify(name=None, device_types=(), identity=None, ports=()):
    return classify_client({
        "names": [name] if name is not None else [],
        "device_types": list(device_types), "ports": list(ports),
        "mac": "00:11:22:33:44:55", "reported_status": "Offline",
    }, identity=identity)


class ClassifierRules(unittest.TestCase):
    def test_positive_category_and_platform_hints(self):
        examples = [
            ("PS5", "game_console", "unknown"),
            ("PlayStation-5", "game_console", "unknown"),
            ("Xbox-Series-X", "game_console", "unknown"),
            ("Nintendo-Switch", "game_console", "unknown"),
            ("iPhone-16", "smartphone", "ios"),
            ("iPad-Air", "tablet", "ios"),
            ("Galaxy-Tab-A7-Lite", "tablet", "android"),
            ("Redmi-Pad-5", "tablet", "android"),
            ("S23-de-Fixture", "smartphone", "android"),
            ("S26-Ultra-de-Fixture", "smartphone", "android"),
            ("Redmi-A5", "smartphone", "android"),
            ("REDMI-15C", "smartphone", "android"),
            ("Pixel-9-Pro", "smartphone", "android"),
            ("Roomba-TEST123", "robot_vacuum", "unknown"),
            ("Roborock-Test", "robot_vacuum", "unknown"),
            ("Smart-TV-Fixture", "smart_tv", "unknown"),
            ("Bravia-Test", "smart_tv", "unknown"),
            ("Chromecast-Dev", "streaming_box", "unknown"),
            ("Apple-TV-Dev", "streaming_box", "unknown"),
            ("LaserJet-Printer", "printer", "unknown"),
            ("IP-Camera-Test", "camera", "unknown"),
            ("WiFi-Repeater", "network_device", "unknown"),
            ("ESP32-Node", "iot", "unknown"),
            ("ThinkPad-Synthetic", "laptop", "unknown"),
            ("MacBook-Synthetic", "laptop", "macos"),
            ("Optiplex-Synthetic", "desktop", "unknown"),
            ("iMac-Synthetic", "desktop", "macos"),
            ("Generic-PC", "desktop", "unknown"),
        ]
        for name, category, platform in examples:
            with self.subTest(name=name):
                result=classify(name)
                self.assertEqual(result['category'],category)
                self.assertEqual(result['platform_family'],platform)
                self.assertIn(result['confidence'],('medium','low'))
                self.assertTrue(result['evidence'])
                self.assertEqual(result['classification_version'],CLASSIFICATION_VERSION)

    def test_weak_and_ambiguous_hints_never_force_os_or_type(self):
        cases = [
            ("MSFT 5.0", (), "unknown", "unknown"),
            ("wlan0", (), "unknown", "unknown"),
            ("Synthetic-Predator", (), "unknown", "unknown"),
            ("unknown", (), "unknown", "unknown"),
            ("00:11:22:33:44:55", (), "unknown", "unknown"),
            ("Ethernet", (), "unknown", "unknown"),
            ("Synthetic-Phone", ("MSFT 5.0",), "unknown", "unknown"),
        ]
        for name, hints, cat, platform in cases:
            with self.subTest(name=name):
                result=classify(name,hints)
                self.assertEqual(result['category'],cat)
                self.assertEqual(result['platform_family'],platform)
                self.assertEqual(result['confidence'],'unknown')
        self.assertTrue(any(e['rule']=='dhcp_msft_signature'
            for e in classify('Synthetic-PC',('MSFT 5.0',))['evidence']))
        self.assertEqual(classify('Synthetic-PC',('MSFT 5.0',))['platform_family'],'unknown')

    def test_contextual_computer_and_android_broad_category(self):
        # Anonymous placeholders: these are NOT real inventory values.
        computer=classify("Fixture-Predator", ("MSFT 5.0",))
        self.assertEqual(computer["category"], "computer")
        self.assertEqual(computer["confidence"], "medium")
        self.assertEqual(computer["platform_family"], "unknown")
        self.assertTrue(any(e["rule"]=="predator_computer_family_with_context"
                            for e in computer["evidence"]))
        acer=classify("Acer-Predator")
        self.assertEqual(acer["category"], "computer")
        # These names alone cannot distinguish a gaming PC from a nickname.
        self.assertEqual(classify("Fixture-Predator")["category"], "unknown")
        self.assertEqual(classify("Random-Predator", ("android-dhcp-12",))["category"], "android_device")
        self.assertEqual(classify("Fixture-Host", ("MSFT 5.0",))["category"], "unknown")
        # Android-DHCP identifies a platform hint, not phone/tablet model.
        for name in ("Fixture-S7", "TARS-Fixture", None):
            with self.subTest(name=name):
                result=classify(name, ("android-dhcp-8.0.0",))
                self.assertEqual(result["category"], "android_device")
                self.assertEqual(result["platform_family"], "android")
                self.assertEqual(result["confidence"], "low")
        self.assertEqual(classify("Galaxy-Tab-Fixture", ("android-dhcp-14",))["category"], "tablet")
        self.assertEqual(classify("Roomba-Fixture", ("android-dhcp-14",))["category"], "robot_vacuum")
        self.assertEqual(classify("PS5", ("android-dhcp-14",))["category"], "game_console")
        conflicting=classify("iPhone-16", ("android-dhcp-16",))
        self.assertEqual(conflicting["platform_family"], "unknown")
        self.assertEqual(conflicting["category"], "smartphone")

    def test_conflicting_categories_never_silently_pick_one(self):
        result=classify('PS5',('Roomba',))
        self.assertEqual(result['category'],'unknown')
        self.assertEqual(result['confidence'],'unknown')
        self.assertIn('conflicting_device_category_hints',result['conflicts'])

    def test_conflicting_platforms_explicitly_mark_unknown(self):
        result=classify('iPhone-16',('android-dhcp-16',))
        self.assertEqual(result['category'],'smartphone')
        self.assertEqual(result['platform_family'],'unknown')
        self.assertIn('conflicting_platform_hints',result['conflicts'])
        self.assertEqual(result['confidence'],'low')

    def test_mac_vendor_and_interface_never_prove_category(self):
        vendor = {'oui_vendor':'Example Electronics Inc.', 'mac_type':'global',
                  'oui_prefix_bits':24, 'oui_dataset_version':'fixture'}
        result=classify('wlan0',identity=vendor,ports=['wlan1'])
        self.assertEqual(result['category'],'unknown')
        self.assertEqual(result['platform_family'],'unknown')
        self.assertTrue(any(e['rule']=='ieee_block_assignee' for e in result['evidence']))
        self.assertEqual(result['confidence'],'unknown')
        result=classify('wlan0',identity={**vendor,'mac_type':'locally_administered'})
        self.assertFalse(any(e['rule']=='ieee_block_assignee' for e in result['evidence']))

    def test_same_category_twice_raises_qualitative_confidence(self):
        result=classify('PS5',('PS5',))
        self.assertEqual(result['category'],'game_console')
        self.assertEqual(result['confidence'],'high')
        self.assertFalse(result['conflicts'])

    def test_unicode_aliases_and_unknowns_are_bounded(self):
        result=classify('ＰＳ５')
        self.assertEqual(result['category'],'game_console')
        self.assertEqual(classify('x'*250_000)['category'],'unknown')
        self.assertEqual(classify(None)['display_name_suggestion'],None)
        self.assertEqual(classify('wlan0')['display_name_suggestion'],None)
        self.assertIsNone(classify('00:11:22:33:44:55')['display_name_suggestion'])
        self.assertEqual(classify('PS5')['display_name_suggestion'],'PS5')
        result=classify('PS5')
        self.assertTrue(all(set(e)=={'field','rule','source','confidence'} for e in result['evidence']))
        self.assertNotIn('PS5',repr(result['evidence']))

    def test_input_order_and_invalid_types_are_safe(self):
        b={'names':['PS5','PS5'],'device_types':None,'ports':['Ethernet']}
        first=classify_client(b)
        self.assertEqual(first,classify_client(b))
        self.assertEqual(first['category'],'game_console')
        self.assertEqual(len([e for e in first['evidence'] if e['rule']=='playstation']),1)
        self.assertEqual(classify_client([])['category'],'unknown')
        self.assertEqual(classify_client({'names':[12,{},None]})['category'],'unknown')
        self.assertTrue(all(x in CATEGORIES for x in [first['category'],'unknown']))
        self.assertTrue(all(x in PLATFORMS for x in [first['platform_family'],'unknown']))


class ClassifierInventoryIntegration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patcher=patch.object(core,'DB_PATH',Path(self.temp.name)/'test.db')
        self.patcher.start();core.init_db()
        self.mac='02:00:00:00:00:01'
        self.observation={'mac':self.mac,'names':['Roomba-Test'], 'ports':['wlan0'],
                          'device_types':['android-dhcp-14'], 'ips':['192.0.2.17'],
                          'reported_status':'Offline'}
        with core.connect() as db:
            db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)',
                       (1,datetime.now(timezone.utc).isoformat(),self.mac,json.dumps(self.observation)))
    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def test_json_contract_raw_client_unchanged(self):
        client=core.get_router_clients()['clients'][0]
        result=client['classification']
        self.assertEqual(result['category'],'robot_vacuum')
        self.assertEqual(result['platform_family'],'android')
        self.assertEqual(result['confidence'],'medium')
        self.assertEqual(client['identity']['mac_type'],'locally_administered')
        self.assertIsNone(client['identity']['oui_vendor'])
        self.assertEqual(core.get_router_clients(self.mac)['observations'][0]['names'],self.observation['names'])
        self.assertNotIn('classification',core.get_router_clients(self.mac)['observations'][0])
        with core.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT payload FROM router_client_samples').fetchone()[0]),self.observation)

if __name__ == '__main__': unittest.main()
