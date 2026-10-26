import contextlib
import copy
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from tools import performance_matrix as matrix


class MatrixTests(unittest.TestCase):
    def test_individual_contract_failure_is_reported(self):
        bad=matrix.Case('fixture/metric','backend',lambda:([{'time':'fixture','value':999}],None,{}),lambda v:matrix.series(v,0))
        rows=matrix.run_case(bad,1,2,lambda:None)
        self.assertEqual(len(rows),3)
        self.assertTrue(all(not row['functional'] for row in rows))
        self.assertTrue(all(row['errors'] for row in rows))

    def test_small_samples_do_not_claim_p95(self):
        self.assertIsNone(matrix.stats([1,2,3,4])['p95_ms'])
        self.assertEqual(matrix.stats(list(range(1,21)))['p95_ms'],19)

    def test_regressions_noise_and_coverage(self):
        before={'comparison_fingerprint':'same','profile':{'kind':'synthetic'},'results':[
            {'id':'cpu/uncached','median_ms':100,'functional':True},
            {'id':'memory/uncached','median_ms':100,'functional':True}]}
        after=copy.deepcopy(before)
        after['results']=[{'id':'cpu/uncached','median_ms':131,'functional':True}]
        result=matrix.compare(after,before)
        self.assertEqual(len(result['regressions']),1)
        self.assertEqual(result['missing_cases'],['memory/uncached'])
        after['results'][0]['median_ms']=129
        self.assertFalse(matrix.compare(after,before)['regressions'])
        after['comparison_fingerprint']='different'
        self.assertFalse(matrix.compare(after,before)['compatible'])
        after['profile']['kind']='live'
        self.assertFalse(matrix.compare(after,before)['compatible'])

    def test_latency_budget_missing_p95_and_typo_are_not_green(self):
        report={'results':[{'id':'s7/cpu/repeat','median_ms':10,'p95_ms':None,'bytes_max':100}]}
        rules={'rules':[{'pattern':'s7/*','median_ms':5,'p95_ms':20},{'pattern':'typo','bytes_max':10}]}
        result=matrix.budgets(report,rules)
        self.assertEqual(len(result['violations']),2)
        self.assertEqual(result['unmatched_rules'],['typo'])

    def test_synthetic_backend_and_http_reports_are_private_and_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            for transport in ('backend','http'):
                output=Path(folder)/(transport+'.json')
                with contextlib.redirect_stdout(io.StringIO()):
                    code=matrix.main(['--transport',transport,'--days','1','--samples-per-day','2','--devices','2',
                                      '--payload-kib','0','--trials','1','--periods','1h','7d',
                                      '--include-exports','--output',str(output)])
                self.assertEqual(code,0)
                data=json.loads(output.read_text(encoding='utf-8'))
                self.assertTrue(all(row['functional'] for row in data['results']))
                for metric in matrix.EXPECTED:
                    self.assertTrue(any(row['case']=='s7/history/'+metric+'/7d' for row in data['results']))
                serialized=json.dumps(data)
                self.assertNotIn(matrix.MAC,serialized)
                self.assertNotIn('Fixture phone',serialized)
                self.assertNotIn('192.0.2.',serialized)
                self.assertTrue(output.with_suffix('.md').is_file())

    def test_live_requires_opt_in_and_fixture_disk_budget_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            for args in (['--live-url','http://127.0.0.1:1'],
                         ['--days','366','--samples-per-day','1440','--devices','100','--payload-kib','128']):
                with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                    matrix.main(args+['--output',str(Path(folder)/'unused.json')])
            self.assertFalse(list(Path(folder).iterdir()))
        error=urllib.error.HTTPError('http://private/identifier',500,'secret response',{},None)
        self.assertEqual(matrix.error_description(error),'HTTP 500')
