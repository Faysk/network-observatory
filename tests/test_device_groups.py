"""Synthetic associations, privacy and compatibility; no real device access."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import core, device_groups, device_preferences


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch.object(core, 'DB_PATH', Path(self.tmp.name)/'sd.db')
        self.patcher.start()
        core.init_db()
        self.macs = ['02:00:00:00:00:01', '02:00:00:00:00:02']
        self.stamp = core.utcnow()
        with core.connect() as db:
            for mac in self.macs:
                payload = {'mac': mac, 'names': ['Fixture-console'], 'ips': ['192.0.2.1'],
                           'ports': ['LAN1'], 'reported_status': 'Online', 'stations': []}
                db.execute('INSERT INTO router_client_samples(sample_id,ts,mac,payload) VALUES(1,?,?,?)',
                           (self.stamp, mac, json.dumps(payload)))

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_suggestions_never_merge_and_manual_link_is_reversible(self):
        before = core.get_router_clients()
        self.assertEqual(len(before['clients']), 2)
        self.assertEqual(before['manual_group_count'], 0)
        self.assertTrue(before['clients'][0]['possible_relations'])
        with core.connect() as db:
            original = list(db.execute('SELECT payload FROM router_client_samples'))
            group = device_groups.associate(db, self.macs)
        after = core.get_router_clients()
        self.assertEqual(after['manual_group_count'], 1)
        self.assertEqual(len(after['clients']), 2)
        self.assertEqual({x['association']['group_id'] for x in after['clients']}, {group})
        with core.connect() as db:
            self.assertEqual([x[0] for x in original], [x[0] for x in db.execute('SELECT payload FROM router_client_samples')])
            self.assertEqual(device_groups.dissociate(db, self.macs[0]), 1)
        self.assertEqual(core.get_router_clients()['manual_group_count'], 0)

    def test_conflicting_names_stay_unconfirmed_and_bounded(self):
        clients = [{'mac': f'02:00:00:00:01:{i:02x}', 'names': ['Fixture-shared'],
                    'classification': {'category': 'tablet' if i%2 else 'smartphone'}} for i in range(100)]
        with core.connect() as db:
            device_groups.enrich(db, clients)
        for item in clients:
            self.assertLessEqual(len(item['possible_relations']), 3)
            self.assertIsNone(item['association']['group_id'])
            self.assertTrue(all(x['confirmed'] is False for x in item['possible_relations']))
        self.assertTrue(clients[0]['possible_relations'][0]['conflict'])

    def test_reject_unobserved_and_multicast_and_preserve_notes(self):
        with core.connect() as db:
            for bad in (['02:00:00:00:ff:01', self.macs[0]], [self.macs[0]], ['01:00:00:00:00:01', self.macs[0]]):
                with self.assertRaises(ValueError):
                    device_groups.associate(db, bad)
            device_preferences.save(db, self.macs[0], nickname='<script>fixture</script>', category='tablet', note='private note')
        response = core.get_router_clients()
        self.assertNotIn('private note', json.dumps(response))
        with core.connect() as db:
            # A consistent backup can be restored with the separate metadata intact.
            copy = sqlite3.connect(':memory:')
            db.backup(copy)
            self.assertEqual(copy.execute('SELECT COUNT(*) FROM device_presentation_overrides').fetchone()[0], 1)
            self.assertEqual(copy.execute('SELECT COUNT(*) FROM router_client_samples').fetchone()[0], 2)
            copy.close()
        core.init_db()  # idempotent migration
        self.assertEqual(len(core.get_router_clients()['clients']), 2)
