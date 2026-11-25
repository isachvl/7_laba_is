import copy,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
from instrumented import ClientProxy

class DummySpan:
    span_id='synthetic-unit-span'
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def set_inputs(self,*args):pass
    def set_outputs(self,*args):pass
    def set_attribute(self,*args):pass
    def set_attributes(self,*args):pass

class TransparencyTests(unittest.TestCase):
    def test_fixed_sdk_response_and_request_are_unchanged(self):
        response=SimpleNamespace(usage=SimpleNamespace(model_dump=lambda:{'prompt_tokens':100,'completion_tokens':12,'total_tokens':112}),
            choices=[SimpleNamespace(message=SimpleNamespace(model_dump=lambda **kw:{'role':'assistant','content':'Fixed unit response'}))])
        observed=[]
        def create(**kwargs):observed.append(copy.deepcopy(kwargs));return response
        real=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        request={'model':'test','messages':[{'role':'user','content':'Fixed unit request'}],'temperature':0,'seed':42,'max_tokens':1024,'extra_body':{'cache_prompt':True}}
        fake_mlflow=SimpleNamespace(start_span=lambda **kw:DummySpan())
        with patch.dict(sys.modules,{'mlflow':fake_mlflow}):
            for traced in [False,True]:
                proxy=ClientProxy(real,SimpleNamespace(tracing=traced,last_model_span=None))
                self.assertIs(proxy.create(**copy.deepcopy(request)),response)
        self.assertEqual(observed,[request,request])
