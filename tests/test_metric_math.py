import sqlite3,unittest
from datetime import datetime,timedelta,timezone
from app.metric_math import observation_coverage,percentile

class MeasurementMathTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('CREATE TABLE huawei_samples(id INTEGER PRIMARY KEY,ts TEXT)')
        self.start=datetime(2026,1,1,tzinfo=timezone.utc)
    def tearDown(self):self.db.close()
    def add(self,seconds):self.db.execute('INSERT INTO huawei_samples(ts) VALUES(?)',((self.start+timedelta(seconds=seconds)).isoformat(),))
    def coverage(self,seconds):return observation_coverage(self.db,'huawei_samples',self.start,self.start+timedelta(seconds=seconds))
    def test_processing_overhead_is_not_mislabeled_packet_loss(self):
        for second in range(0,1000,67):self.add(second)
        r=self.coverage(1000)
        self.assertEqual(r['coverage_percent'],100);self.assertLess(r['nominal_sample_percent'],100)
        self.assertEqual(r['observed_interval_mean_seconds'],67)
    def test_outage_and_duplicates_cannot_make_healthy_coverage(self):
        for second in [0,0,1800]:self.add(second)
        self.assertEqual(self.coverage(3600)['coverage_percent'],10)
        self.assertEqual(self.coverage(3600)['covered_seconds'],360)
    def test_context_and_future_are_clipped(self):
        self.add(-60);self.add(200)
        r=self.coverage(100);self.assertEqual(r['coverage_percent'],100);self.assertEqual(r['sample_count'],0)
    def test_percentile_nearest_rank_and_small_window(self):
        self.assertEqual(percentile(range(1,21)),19)
        self.assertEqual(percentile([0]),0);self.assertIsNone(percentile([]))
        self.assertEqual(percentile([float('nan'),1,2]),2)
