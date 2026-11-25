import copy,unittest
from gate import gate

def summary(n=6):
    ids=['user_task_'+str(i) for i in range(n)]
    return {'manifest':{'system':'test'},'benchmark':'v1.2.2','runs':3,'task_ids':ids,'records':[{'task':i,'run':r,'utility':True,'input_tokens':100,'output_tokens':10,'seconds':1} for i in ids for r in range(3)]}
class GateTests(unittest.TestCase):
    def test_loss_not_compensated_by_improvement(self):
        a=summary(7);b=copy.deepcopy(a)
        for r in a['records']:
            if r['task']=='user_task_6':r['utility']=False
        for r in b['records']:
            if r['task']=='user_task_0':r['utility']=False
        self.assertEqual(gate(a,b)['status'],'FAIL')
    def test_only_three_protected_review(self):self.assertEqual(gate(summary(3),summary(3))['status'],'REVIEW')
    def test_missing_run_error(self):
        a=summary();b=copy.deepcopy(a);b['records'].pop();self.assertEqual(gate(a,b)['status'],'ERROR')
    def test_benchmark_mismatch_error(self):
        a=summary();b=copy.deepcopy(a);b['benchmark']='other';self.assertEqual(gate(a,b)['status'],'ERROR')
    def test_one_failure_tolerated_only_by_majority(self):
        a=summary();b=copy.deepcopy(a);b['records'][0]['utility']=False
        self.assertEqual(gate(a,b)['status'],'PASS');self.assertEqual(gate(a,b,strict=True)['status'],'FAIL')
    def test_cost_review(self):
        a=summary();b=copy.deepcopy(a)
        for r in b['records']:r['input_tokens']=200
        self.assertEqual(gate(a,b)['status'],'REVIEW')
    def test_tests_failure_is_fail(self):self.assertEqual(gate(summary(),summary(),tests_ok=False)['status'],'FAIL')
    def test_identical_pass(self):self.assertEqual(gate(summary(),summary())['status'],'PASS')
