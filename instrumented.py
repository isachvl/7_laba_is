import json,time
from contextlib import nullcontext
from types import SimpleNamespace
from base_agent import Agent as BaseAgent
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str

MARKER='[TRUNCATED TOOL RESULT: output limited to 2000 characters. Use a narrower query or read a specific object.]\n'

def transform(value,version):
    if version not in ('candidate','fix') or len(value)<=2000:return value,False
    if version=='candidate':return value[:2000],True
    return MARKER+value[:2000-len(MARKER)],True

class ClientProxy:
    def __init__(self,real,owner):
        self.real=real;self.owner=owner;self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def close(self):self.real.close()
    def create(self,**kwargs):
        a=self.owner
        if not a.tracing:return self.real.chat.completions.create(**kwargs)
        import mlflow
        with mlflow.start_span(name='chat',span_type='CHAT_MODEL') as span:
            span.set_inputs({'model':kwargs['model'],'messages':kwargs['messages'],'tools':kwargs.get('tools')})
            span.set_attribute('gen_ai.request.model',kwargs['model'])
            result=self.real.chat.completions.create(**kwargs)
            u=result.usage.model_dump();span.set_outputs(result.choices[0].message.model_dump(exclude_none=True))
            span.set_attributes({'gen_ai.usage.input_tokens':u['prompt_tokens'],'gen_ai.usage.output_tokens':u['completion_tokens'],
                'mlflow.chat.tokenUsage':{'input_tokens':u['prompt_tokens'],'output_tokens':u['completion_tokens'],'total_tokens':u['total_tokens']}})
            a.last_model_span=span.span_id
            return result

class RuntimeProxy:
    def __init__(self,runtime,owner):self.runtime=runtime;self.owner=owner;self.functions=runtime.functions
    def run_function(self,env,name,args,*extra,**kw):
        a=self.owner
        if a.tracing:
            import mlflow
            context=mlflow.start_span(name=name,span_type='TOOL')
        else:context=nullcontext(None)
        with context as span:
            if span:span.set_inputs({'name':name,'arguments':args})
            result,error=self.runtime.run_function(env,name,args,*extra,**kw)
            raw=tool_result_to_str(result) if error is None else str(error)
            visible,truncated=transform(raw,a.version) if error is None else (raw,False)
            meta={'raw_output':raw,'raw_chars':len(raw),'visible_chars':len(visible),'truncated':truncated,'span_id':span.span_id if span else None}
            a.last_tool_meta=meta
            if span:
                span.set_outputs({'raw':raw,'visible':visible,'raw_chars':len(raw),'visible_chars':len(visible),'truncated':truncated,'error':error})
                span.set_attributes({'tool.name':name,'tool.output_chars':len(visible),'tool.error':error or ''})
                if error:span.set_status('ERROR')
            return (visible if truncated else result),error

class Agent(BaseAgent):
    def __init__(self,config,path,version='base',tracing=True):
        super().__init__(config,'react',path);self.version=version;self.tracing=tracing
        self.last_model_span=None;self.last_tool_meta={};self.client=ClientProxy(self.client,self)
    def record(self,event):
        if event['kind']=='model':event['span_id']=self.last_model_span
        elif event['kind']=='tool':event.update(self.last_tool_meta);self.last_tool_meta={}
        super().record(event)
    def query(self,query,runtime,env,messages=(),extra_args={}):
        return super().query(query,RuntimeProxy(runtime,self),env,messages,extra_args)
