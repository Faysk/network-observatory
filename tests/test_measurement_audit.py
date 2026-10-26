import copy,unittest
from tools.audit_measurements import audit

class AuditTests(unittest.TestCase):
    def inputs(self):
        host={'cpu':{'usagePercent':0,'coresPercent':[0,None]},'memory':{'totalMB':100,'usedMB':25,'availableMB':75},'battery':{'levelPercent':0},'network':{'rxMbps':0,'txMbps':None},'details':{'metrics':{'memory.meminfo':{'value':{'MemTotal':102400},'unit':'KiB','source':'fixture','status':'ok'}}}}
        status={'huawei':{'metrics':{'cpu_pct':0,'memory_pct':0}},'probe':{'router_ms':0,'internet_ms':None}}
        overview={'quality':{'window_seconds':1000,'covered_seconds':1000,'coverage_percent':100,'coverage_semantics':'time_with_stored_observation_no_older_than_180_seconds'},'measurement_semantics':{'wan_rate_available':False}}
        return host,status,overview,{'clients':[]}
    def test_zero_unknown_and_consistency_are_distinct(self):
        result=audit(*self.inputs());self.assertEqual(result['summary']['fail'],0)
        by_name={r['name']:r['status'] for r in result['checks']}
        self.assertEqual(by_name['host.cpu.percent'],'pass');self.assertEqual(by_name['host.network.rxMbps'],'pass');self.assertEqual(by_name['host.network.txMbps'],'unknown')
        self.assertNotIn('MemTotal',str(result))
    def test_bad_formula_and_false_precision_fail(self):
        host,status,overview,inventory=self.inputs();host['memory']['usedMB']=30;overview['quality']['coverage_percent']=89;overview['measurement_semantics']['wan_rate_available']=True
        result=audit(host,status,overview,inventory);self.assertEqual(result['summary']['fail'],3)
