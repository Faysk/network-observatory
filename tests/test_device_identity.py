"""MAC/OUI identity tests: ONLY synthetic fixtures, never a live router."""
import concurrent.futures
import csv
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import core
from app.device_identity import (
    DEFAULT_FILENAME, MAX_REGISTRY_BYTES, OuiRegistry, get_registry,
    inspect_mac, mac_address_type, normalize_mac,
)
from tools.import_ieee_oui import build, parse_registry, save_atomic


def sample_registry(path):
    path.write_text(
        "# version=synthetic-testing-only\n"
        "24\t001122\tFixture Interface Lab\n"
        "28\t0011223\tFixture Medium Block\n"
        "36\t001122334\tFixture Small Block\n",
        encoding="utf-8",
    )
    return OuiRegistry.from_file(path)


class NormalizeMacTests(unittest.TestCase):
    def test_formats_strictly_eui48(self):
        for value in (
            "00:11:22:33:44:55", "00-11-22-33-44-55",
            "0011.2233.4455", "001122334455", " 00:11:22:33:44:55 ",
        ):
            self.assertEqual(normalize_mac(value), "00:11:22:33:44:55")
        for value in ("00:11:22:33:44", "00:11:22:33:44:55:66:77",
                      "00:11-22:33:44:55", "００１１２２３３４４５５", "00:11:22:gg:44:55",
                      "", None, 123, {}, "00:11:22:33:44:55\nother"):
            self.assertIsNone(normalize_mac(value), value)

    def test_global_local_multicast_invalid_and_unknown(self):
        for mac, expected in (
            ("00:11:22:33:44:55", "global"),
            ("02:00:00:00:00:01", "locally_administered"),
            ("06:ab:cd:00:00:01", "locally_administered"),
            ("f2:00:00:00:00:02", "locally_administered"),
            ("01:00:5e:00:00:01", "multicast"),
            ("03:11:22:33:44:55", "multicast"),
            ("00:00:00:00:00:00", "invalid"),
            ("ff:ff:ff:ff:ff:ff", "invalid"),
            ("bogus", "invalid"), (None, "unknown"), ("", "unknown"),
        ):
            with self.subTest(mac=mac):self.assertEqual(mac_address_type(mac), expected)

    def test_global_oui_longest_prefix_and_local_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            reg=sample_registry(Path(directory)/DEFAULT_FILENAME)
            hit=inspect_mac("00:11:22:33:44:55",registry=reg)
            self.assertEqual(hit['oui_vendor'],"Fixture Small Block")
            self.assertEqual(hit['oui_prefix_bits'],36)
            self.assertEqual(hit['oui_dataset_version'],"synthetic-testing-only")
            self.assertIn('ieee_public_assignment',hit['sources'])
            self.assertIn('not_device_model',hit['vendor_semantics'])
            self.assertEqual(inspect_mac("00:11:22:3f:44:55",registry=reg)['oui_prefix_bits'],28)
            self.assertEqual(inspect_mac("00:11:22:fe:44:55",registry=reg)['oui_prefix_bits'],24)
            no_vendor=inspect_mac("02:11:22:33:44:55",registry=reg)
            self.assertEqual(no_vendor['mac_type'],'locally_administered')
            self.assertIsNone(no_vendor['oui_vendor'])
            self.assertIsNone(no_vendor['oui_prefix_bits'])
            self.assertEqual(inspect_mac("01:11:22:33:44:55",registry=reg)['oui_vendor'],None)

    def test_unknown_missing_or_corrupt_registry_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(inspect_mac("00:11:22:33:44:55",registry=get_registry(directory))['oui_vendor'])
            file=Path(directory)/DEFAULT_FILENAME
            file.write_text("not\ta\tvalid\n",encoding="utf-8")
            self.assertIsNone(inspect_mac("00:11:22:33:44:55",registry=get_registry(directory))['oui_vendor'])
            file.write_text("# version=test\n24\t001122\tFixture Vendor\n",encoding="utf-8")
            os.utime(file,ns=(time.time_ns(),time.time_ns()))
            self.assertEqual(inspect_mac("00:11:22:33:44:55",registry=get_registry(directory))['oui_vendor'],"Fixture Vendor")
            file.open('wb').close()
            with file.open('wb') as out:out.truncate(MAX_REGISTRY_BYTES+1)
            with self.assertRaises(ValueError):OuiRegistry.from_file(file)

    def test_1000_mac_enrichments_bounded_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            reg=sample_registry(Path(directory)/DEFAULT_FILENAME)
            start=time.perf_counter()
            observations=[inspect_mac(f"00:11:22:{i//65536:02x}:{i//256%256:02x}:{i%256:02x}",registry=reg) for i in range(1000)]
            elapsed=round((time.perf_counter()-start)*1000,2)
            self.assertEqual(len(observations),1000)
            self.assertEqual(len(set(x['normalized_mac'] for x in observations)),1000)
            self.assertEqual(observations[0],inspect_mac("00:11:22:00:00:00",registry=reg))
            self.assertEqual(len(reg.entries),3)
            print(f"Synthetic MAC benchmark: 1000 local lookups in {elapsed} ms; 3 fixture OUI entries; no LAN or real MACs")


class ImporterTests(unittest.TestCase):
    def make_file(self,directory,filename,kind,prefix,vendor):
        path=Path(directory)/filename
        with path.open("w",encoding="utf-8",newline="") as output:
            writer=csv.writer(output)
            writer.writerow(["Registry","Assignment","Organization Name","Organization Address"])
            writer.writerow([kind,prefix,vendor,"Synthetic testing address"])
        return path

    def test_compile_and_atomic_install_three_ieee_registry_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs={
                "MA-L":self.make_file(directory,'oui.csv','MA-L','001122','Fixture Lab'),
                "MA-M":self.make_file(directory,'mam.csv','MA-M','0011223','Fixture Medium'),
                "MA-S":self.make_file(directory,'oui36.csv','MA-S','001122334','Fixture Small')
            }
            content,n,digest=build(inputs)
            self.assertEqual(n,3)
            self.assertTrue(digest)
            file=Path(directory)/DEFAULT_FILENAME
            save_atomic(file,content)
            reg=OuiRegistry.from_file(file)
            self.assertEqual(reg.lookup("00:11:22:33:44:55"),("Fixture Small",36))
            self.assertEqual(reg.lookup("00:11:22:30:00:01"),("Fixture Medium",28))
            with self.assertRaises(FileExistsError):save_atomic(file,content)
            save_atomic(file,content.replace("Fixture Lab","Fixture Renamed"),replace=True)
            self.assertEqual(OuiRegistry.from_file(file).entries[(24,"001122")],"Fixture Renamed")
            self.assertFalse(list(Path(directory).glob(".oui-import-*.tmp")))

    def test_reject_invalid_csv_and_destination_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            valid=self.make_file(directory,"oui.csv","MA-L","001122","Fixture")
            wrong=self.make_file(directory,"wrong.csv","MA-L","badprefix","Fixture")
            with self.assertRaises(ValueError):build({"MA-L":wrong})
            with self.assertRaises(ValueError):build({"MA-S":valid})
            with self.assertRaises(ValueError):save_atomic(Path(directory)/'missing-parent'/DEFAULT_FILENAME,"value")
            corrupt=Path(directory)/"corrupt.csv"
            corrupt.write_text("not,official,header\n1,2,3\n")
            with self.assertRaises(ValueError):parse_registry(corrupt,"MA-L")


class RouterInventoryIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'observatory.db'
        self.patcher=patch.object(core,'DB_PATH',self.db)
        self.patcher.start()
        core.init_db()
        self.registry=sample_registry(Path(self.tmp.name)/DEFAULT_FILENAME)
        self.mac="00:11:22:33:44:55"
        self.original={"mac":self.mac,"names":["Synthetic fixture computer"],"ips":["192.0.2.12"],
                       "device_types":["MSFT 5.0"],"ports":["eth:1"],
                       "reported_status":"Online","stations":[]}
        from datetime import datetime,timezone
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds")
        with core.connect() as db:
            db.execute("INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(?,?,?,?)",
                       (1,timestamp,self.mac,json.dumps(self.original)))
    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_read_only_enrichment_retains_original_history_and_status(self):
        b=core.get_router_clients()
        self.assertEqual(len(b['clients']),1)
        c=b['clients'][0]
        self.assertEqual(c['identity']['oui_vendor'],"Fixture Small Block")
        self.assertEqual(c['identity']['mac_type'],"global")
        self.assertEqual(c['reported_status'],"Online")
        self.assertEqual(c['names'],self.original['names'])
        self.assertEqual(c['mac'],self.mac)
        raw=core.get_router_clients(mac=self.mac)
        self.assertEqual(len(raw['observations']),1)
        for key,value in self.original.items():
            self.assertEqual(raw['observations'][0][key],value)
        self.assertNotIn("identity",raw['observations'][0])
        with core.connect() as db:
            payload=json.loads(db.execute('SELECT payload FROM router_client_samples').fetchone()[0])
            self.assertEqual(payload,self.original)
