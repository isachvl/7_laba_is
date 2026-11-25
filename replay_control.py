import copy,json,os,statistics,time
from pathlib import Path
from types import SimpleNamespace
from base_agent import StopEpisode
from instrumented import Agent,ClientProxy
from clock_control import environment_clock

class FixedProvider:
    def __init__(self,owner):self.owner=owner;self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def close(self):pass
    def create(self,**kwargs):
        event=self.owner.current
        return SimpleNamespace(usage=SimpleNamespace(model_dump=lambda:copy.deepcopy(event['usage'])),choices=[SimpleNamespace(message=SimpleNamespace(model_dump=lambda **kw:copy.deepcopy(event['response'])))])

class ReplayAgent(Agent):
    def __init__(self,config,path,source,tracing):
        super().__init__(config,path,'base',tracing);self.source=source;self.remaining=[e for e in source['events'] if e['kind']=='model'];self.client.close();self.client=ClientProxy(FixedProvider(self),self)
    def model(self,chat,tools=None,schema=None):
        if not self.remaining:raise StopEpisode(self.source['reason'])
        if self.trace['tool_calls']>=self.config['max_tools']:raise StopEpisode('max_tools')
        if self.trace['model_calls']>=self.config['max_calls']:raise StopEpisode('max_calls')
        event=self.remaining.pop(0)
        assert chat==event['messages'],'Replayed tool state or messages diverged from source'
        assert tools==event['tools']
        self.current=event;self.trace['model_calls']+=1;started=time.perf_counter()
        result=self.client.chat.completions.create(model=self.config['model'],messages=chat,tools=tools,temperature=0,seed=42,max_tokens=1024,extra_body={'cache_prompt':True})
        usage=result.usage.model_dump();response=result.choices[0].message.model_dump()
        self.trace['input_tokens']+=usage['prompt_tokens'];self.trace['output_tokens']+=usage['completion_tokens']
        self.record({'kind':'model','messages':chat.copy(),'tools':tools,'response':response,'usage':usage,'seconds':time.perf_counter()-started,'fixed_response_replay':True})
        return response

def main():
    import mlflow
    from agentdojo.task_suite.load_suites import get_suites
    root=Path(__file__).resolve().parent;os.chdir(root);os.environ['MLFLOW_DISABLE_AGENT_HINT']='1';folder=root/'.replay';folder.mkdir(exist_ok=True)
    os.chdir(folder);mlflow.set_tracking_uri('sqlite:///'+(folder/'mlflow.db').as_posix());mlflow.set_experiment('fixed_response_control');os.chdir(root)
    source=[json.loads(l) for l in Path('eval/overhead/results.jsonl').read_text(encoding='utf-8').splitlines() if json.loads(l)['version']=='off'];assert len(source)==10
    config=json.loads(Path('config.json').read_text());suite=get_suites(config['benchmark'])['workspace'];records=[]
    for row in source:
        original=json.loads(Path(row['trace_path']).read_text(encoding='utf-8'))
        for traced in [False,True]:
            path=folder/'traces'/(row['task']+'_'+str(traced)+'.json');agent=ReplayAgent(config,path,original,traced)
            context=mlflow.start_span(name='fixed replay '+row['task'],span_type='AGENT') if traced else __import__('contextlib').nullcontext(None)
            started=time.perf_counter()
            try:
                with context as span:
                    with environment_clock():utility,_=suite.run_task_with_pipeline(agent,suite.get_user_task_by_id(row['task']),None,{})
                    if span:span.set_outputs({'utility':bool(utility),'fixed_response_control':True})
                elapsed=time.perf_counter()-started
                records.append({'task':row['task'],'tracing':traced,'utility':bool(utility),'seconds':elapsed,**{k:agent.trace[k] for k in ['model_calls','tool_calls','input_tokens','output_tokens']}})
            finally:agent.client.close();agent.http.close()
    a={r['task']:r for r in records if not r['tracing']};b={r['task']:r for r in records if r['tracing']}
    keys=['utility','model_calls','tool_calls','input_tokens','output_tokens']
    assert all(all(a[i][k]==b[i][k] for k in keys) for i in a)
    result={'kind':'Fixed recorded SDK responses with real tool execution; no fresh model inference. Does not replace the fresh-model overhead experiment.','n':10,'all_utility_calls_tokens_match':True,'off_median_seconds':statistics.median(r['seconds'] for r in a.values()),'on_median_seconds':statistics.median(r['seconds'] for r in b.values()),'records':records}
    result['difference_seconds']=result['on_median_seconds']-result['off_median_seconds'];Path('analysis/replay_control.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');mlflow.flush_trace_async_logging();print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False))
if __name__=='__main__':main()
