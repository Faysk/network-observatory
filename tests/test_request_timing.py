import sqlite3
import unittest
from app import request_timing as timing

class TimingTests(unittest.TestCase):
    def test_sql_results_and_scope_isolation(self):
        self.assertIsNone(timing.header())
        with timing.request_scope() as values:
            with sqlite3.connect(':memory:',factory=timing.Connection) as db:
                db.execute('CREATE TABLE example(value)')
                db.executemany('INSERT INTO example VALUES(?)',[(0,),(None,),(2,)])
                self.assertEqual(db.execute('SELECT value FROM example').fetchall(),[(0,),(None,),(2,)])
                self.assertEqual(list(db.execute('SELECT value FROM example')),[(0,),(None,),(2,)])
            self.assertGreater(values['db'],0)
            self.assertIn('db;dur=',timing.header())
        self.assertIsNone(timing.header())
        with timing.request_scope() as values:self.assertEqual(values['db'],0)

    def test_wait_measures_acquisition_not_protected_work(self):
        class Lock:
            def acquire(self):self.locked=True
            def release(self):self.locked=False
        lock=Lock()
        with timing.request_scope() as values:
            with self.assertRaises(ValueError):
                with timing.acquire(lock):
                    acquired=values['wait']
                    self.assertTrue(lock.locked)
                    raise ValueError('fixture')
            self.assertFalse(lock.locked)
            self.assertEqual(values['wait'],acquired)
