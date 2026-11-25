import unittest
from controls import control
from instrumented import transform
class ControlTests(unittest.TestCase):
    def test_actual_scripted_negative_control(self):
        data,result=control();self.assertEqual(result['status'],'FAIL');self.assertGreaterEqual(len(result['lost']),1)
    def test_truncation_and_marker_keep_budget(self):
        raw='x'*3500
        self.assertEqual(transform(raw,'base'),(raw,False))
        for version in ['candidate','fix']:
            out,truncated=transform(raw,version);self.assertEqual(len(out),2000);self.assertTrue(truncated)
        self.assertTrue(transform(raw,'fix')[0].startswith('[TRUNCATED TOOL RESULT'))
