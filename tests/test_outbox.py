"""Synthetic-only tests: no router, network or production volume is accessed."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.outbox import Outbox
from app import core


class OutboxSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.outbox=Outbox(Path(self.temp.name)/'outbox')

    def tearDown(self):
        self.temp.cleanup()

    def test_corrupt_first_entry_is_preserved_and_does_not_block_next(self):
        invalid=self.outbox.path/'00-invalid.json'
        invalid.write_bytes(b'{"incomplete":')
        original=invalid.read_bytes()
        valid=self.outbox.path/'01-valid.json'
        valid.write_text(json.dumps({'sample':'synthetic-ok'}),encoding='utf-8')
        sent=[]
        with patch('app.outbox.validate_payload',return_value=None):
            self.assertEqual(self.outbox.flush(sent.append),1)
        self.assertEqual(sent,[{'sample':'synthetic-ok'}])
        self.assertFalse(valid.exists())
        self.assertFalse(invalid.exists())
        self.assertEqual((self.outbox.path/'quarantine'/invalid.name).read_bytes(),original)
        self.assertEqual(self.outbox.pending(),0)
        self.assertEqual(self.outbox.quarantined(),1)
        self.assertEqual(self.outbox.last_quarantined,1)
        self.assertEqual(self.outbox.flush(sent.append),0)
        self.assertEqual(self.outbox.quarantined(),1)

    def test_schema_invalid_payload_is_quarantined_but_valid_is_delivered(self):
        (self.outbox.path/'00-invalid.json').write_text('{"kind":"invalid"}')
        (self.outbox.path/'01-valid.json').write_text('{"kind":"valid"}')
        def validate(payload,require_recent=False):
            if payload['kind']=='invalid':raise ValueError('synthetic schema')
        seen=[]
        with patch('app.outbox.validate_payload',side_effect=validate):
            self.assertEqual(self.outbox.flush(seen.append),1)
        self.assertEqual(seen,[{'kind':'valid'}])
        self.assertEqual(self.outbox.quarantined(),1)

    def test_delivery_failure_never_acknowledges_or_quarantines_valid_data(self):
        target=self.outbox.path/'valid.json'
        target.write_text('{"test":1}')
        def failed(_payload):raise ConnectionError('synthetic delivery failure')
        with patch('app.outbox.validate_payload',return_value=None):
            with self.assertRaises(ConnectionError):self.outbox.flush(failed)
            self.assertEqual(self.outbox.pending(),1)
            self.assertEqual(self.outbox.quarantined(),0)
            captured=[]
            self.assertEqual(self.outbox.flush(captured.append),1)
        self.assertEqual(captured,[{'test':1}])
        self.assertFalse(target.exists())

    def test_invalid_utf8_is_kept_without_leaking_data_in_status(self):
        corrupted=self.outbox.path/'bad.json'
        corrupted.write_bytes(b'\\xff\\xfeprivate-unreadable')
        with patch('app.outbox.validate_payload',return_value=None):
            self.assertEqual(self.outbox.flush(lambda _p:None),0)
        self.assertEqual(self.outbox.quarantined(),1)
        old=core.DB_PATH
        try:
            core.DB_PATH=Path(self.temp.name)/'router.db'
            core.init_db()
            state=core.get_status()['recording']
            self.assertEqual(state['pending_samples'],0)
            self.assertEqual(state['quarantined_samples'],1)
            self.assertNotIn('private-unreadable',str(state))
        finally:
            core.DB_PATH=old


if __name__=='__main__':
    unittest.main()
