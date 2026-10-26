import concurrent.futures
import threading
import time
import unittest
from app.query_cache import QueryCache


class CacheTests(unittest.TestCase):
    def test_four_consumers_share_one_query_and_cannot_mutate_cached_result(self):
        cache = QueryCache()
        calls = []
        def compute():
            calls.append(1)
            time.sleep(.04)
            return {'series': [0, None, 25]}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: cache.get('range', 1, compute, lambda: 1), range(4)))
        self.assertEqual(len(calls), 1)
        values[0]['series'][0] = 999
        self.assertEqual(values[1]['series'][0], 0)
        self.assertEqual(cache.get('range', 1, compute, lambda: 1)['series'][0], 0)
        self.assertFalse(cache.flights)

    def test_revision_change_failed_query_and_memory_budget(self):
        cache = QueryCache(entries=2, byte_limit=100)
        for key in range(5):
            cache.get(key, 1, lambda: {'text': 'x'*40}, lambda: 1)
        self.assertLessEqual(cache.bytes, 100)
        self.assertLessEqual(len(cache.cache), 2)
        self.assertEqual(cache.get('version', 1, lambda: [1], lambda: 1), [1])
        self.assertEqual(cache.get('version', 2, lambda: [2], lambda: 2), [2])
        def bad():
            raise OSError('Synthetic read error')
        with self.assertRaises(OSError):
            cache.get('failed', 1, bad, lambda: 1)
        self.assertEqual(cache.get('failed', 1, lambda: [0], lambda: 1), [0])
        cache.get('oversize', 1, lambda: 'x'*200, lambda: 1)
        self.assertNotIn('oversize', cache.cache)
        self.assertFalse(cache.flights)

    def test_writing_during_calculation_does_not_cache_old_revision(self):
        cache = QueryCache()
        self.assertEqual(cache.get('range', 1, lambda: [1], lambda: 2), [1])
        self.assertFalse(cache.cache)
