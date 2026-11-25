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

    def test_fixed_clock_serializes_write_results(self):
        from agentdojo.task_suite.load_suites import get_suites
        from agentdojo.functions_runtime import FunctionsRuntime
        from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
        from clock_control import environment_clock
        suite=get_suites('v1.2.2')['workspace'];env=suite.load_and_inject_default_environment({});runtime=FunctionsRuntime(suite.tools)
        operations=[('send_email',{'recipients':['test@example.com'],'subject':'Clock test','body':'Clock test'}),('append_to_file',{'file_id':'3','content':'Clock test'}),('create_file',{'filename':'clock-test.txt','content':'Clock test'})]
        with environment_clock():
            for name,args in operations:
                result,error=runtime.run_function(env,name,args)
                self.assertIsNone(error)
                output=tool_result_to_str(result)
                self.assertIn('2026-11-25 12:00:00',output)
