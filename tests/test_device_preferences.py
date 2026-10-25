"""Synthetic, local SQLite presentation settings. Never opens production DB."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import core
from app import device_preferences as p

class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.storage=Path(self.temp.name)/'mounted-sd-fixture.db'
        self.patch=patch.object(core,'DB_PATH',self.storage)
        self.patch.start()
        core.init_db()
        self.mac='02:00:00:00:00:01'
    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()
    def test_persistence_and_reset(self):
        with core.connect() as db:
            self.assertEqual(p.read_presentation(db,self.mac)['source'],'none')
            rev=p.save(db,self.mac,nickname='Fixture Test',category='smartphone',icon='tablet',note='private-only')
            self.assertEqual(rev,1)
        with core.connect() as db:
            record=p.read_presentation(db,self.mac)
            self.assertEqual(record['category'],'smartphone')
            self.assertEqual(record['icon'],'tablet')
            self.assertEqual(record['nickname'],'Fixture Test')
            self.assertNotIn('note',record)
            self.assertEqual(p.save(db,self.mac,nickname='Second test',expected_revision=1),2)
            with self.assertRaises(ValueError):p.save(db,self.mac,nickname='Unexpected',expected_revision=1)
            with self.assertRaises(ValueError):p.delete(db,self.mac,expected_revision=1)
            self.assertEqual(p.delete(db,self.mac,expected_revision=2),1)
            self.assertEqual(p.read_presentation(db,self.mac)['source'],'none')
    def test_reject_bad_values(self):
        with core.connect() as db:
            for value in ('<script>','a'*1000,'bad\nline'):
                with self.assertRaises(ValueError):p.save(db,self.mac,nickname=value if len(value)>50 or '\n' in value else None,category='not-a-category')
            for mac in ('bad','ff:ff:ff:ff:ff:ff'):
                with self.assertRaises(ValueError):p.save(db,mac,nickname='fixture')
            with self.assertRaises(ValueError):p.save(db,self.mac)
            with self.assertRaises(ValueError):p.save(db,self.mac,icon='remote-svg')
    def test_no_archive_mutations(self):
        with core.connect() as db:
            before=db.execute('SELECT COUNT(*) FROM router_client_samples').fetchone()[0]
            p.save(db,self.mac,nickname='No historian modification')
            after=db.execute('SELECT COUNT(*) FROM router_client_samples').fetchone()[0]
            self.assertEqual(before,after)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM device_presentation_overrides').fetchone()[0],1)

if __name__=='__main__':unittest.main()
