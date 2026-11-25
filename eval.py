import argparse,hashlib,json,os,statistics,time
from contextlib import nullcontext
from pathlib import Path
os.environ['MLFLOW_DISABLE_AGENT_HINT']='1'
import mlflow
from agentdojo.task_suite.load_suites import get_suites
from instrumented import Agent
from clock_control import environment_clock,FIXED_TIME
ROOT=Path(__file__).resolve().parent

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def setup():
    mlflow.set_tracking_uri('sqlite:///'+(ROOT/'mlflow.db').as_posix());exp=mlflow.set_experiment('lr7')
    return exp.experiment_id

def frozen_check():
    for name,value in read('frozen.json')['hashes'].items():assert digest(name)==value,name

def episode(suite,task_id,version,run,tracing,key,experiment_id):
    config=read('config.json');path=Path('traces')/(key+'.json')
    if path.exists():raise RuntimeError('Partial episode requires review before retry: '+key)
    agent=Agent(config,path,'base' if version in ['base','aa','off','on'] else version,tracing)
    agent.trace.update(key=key,version=version,task=task_id,run=run,temperature=0,seed=42)
    agent.save();trace_id=None;error=None
    started=time.perf_counter()
    context=mlflow.start_span(name=f'episode {task_id}',span_type='AGENT') if tracing else nullcontext(None)
    with context as root:
        if root:
            trace_id=root.trace_id;agent.trace['mlflow_trace_id']=trace_id;agent.save()
            root.set_inputs({'task':task_id,'prompt':suite.get_user_task_by_id(task_id).PROMPT})
            mlflow.update_current_trace(tags={'task':task_id,'version':'base' if version=='aa' else version,'evaluation':version,'run':str(run),'episode_key':key})
        try:
            with environment_clock():utility,_=suite.run_task_with_pipeline(agent,suite.get_user_task_by_id(task_id),None,{})
        except Exception as exc:
            utility=False;error=repr(exc);agent.trace.update(reason='evaluation_error',evaluation_error=error)
        finally:agent.client.close();agent.http.close()
        if root:
            root.set_outputs({'utility':bool(utility),'reason':agent.trace['reason'],'answer':agent.trace.get('answer','')})
            mlflow.update_current_trace(tags={'utility':str(bool(utility)),'stop_reason':agent.trace['reason']})
    seconds=time.perf_counter()-started
    agent.trace.update(utility=bool(utility),wall_episode_seconds=seconds);agent.save()
    events=agent.trace['events'];models=[e for e in events if e['kind']=='model'];tools=[e for e in events if e['kind']=='tool']
    row={'key':key,'task':task_id,'run':run,'version':version,'utility':bool(utility),'reason':agent.trace['reason'],
         **{k:agent.trace[k] for k in ['model_calls','tool_calls','input_tokens','output_tokens']},'seconds':seconds,
         'max_input_tokens':max((e['usage']['prompt_tokens'] for e in models),default=0),'tool_errors':sum(bool(e.get('error')) for e in tools),
         'truncated_tools':sum(e.get('truncated',False) for e in tools),'trace_id':trace_id,'trace_path':str(path),
         'trace_url':f'http://127.0.0.1:5006/#/experiments/{experiment_id}/traces?selectedTraceId={trace_id}' if trace_id else None,'evaluation_error':error}
    if trace_id:
        native=mlflow.get_trace(trace_id,flush=True)
        if native is None:raise RuntimeError('Trace export missing; saved ID '+trace_id)
        Path('native_traces').mkdir(exist_ok=True);Path('native_traces',key+'.json').write_text(native.to_json(),encoding='utf-8')
    return row

def signals(records):
    return {'latency':{'median_seconds':statistics.median(r['seconds'] for r in records)},
            'traffic':{'model_calls':sum(r['model_calls'] for r in records),'tool_calls':sum(r['tool_calls'] for r in records)},
            'errors':{'tool_errors':sum(r['tool_errors'] for r in records),'limit_stops':sum(r['reason'] in ['max_tools','max_calls','context_limit'] for r in records)},
            'saturation':{'input_tokens':sum(r['input_tokens'] for r in records),'output_tokens':sum(r['output_tokens'] for r in records),'max_context_fraction':max(r['max_input_tokens']/16384 for r in records)}}

def run(version,runs,phase='main',limit=None):
    frozen_check();exp_id=setup();config=read('config.json');suite=get_suites(config['benchmark'])['workspace'];manifest=read('reference/lr5_manifest.json')
    folder=Path('eval')/(version if phase=='main' else 'overhead');folder.mkdir(exist_ok=True)
    file=folder/'results.jsonl';records=[json.loads(l) for l in file.read_text(encoding='utf-8').splitlines()] if file.exists() else []
    complete={r['key'] for r in records}
    if phase=='overhead':
        ids=manifest['ids']['workspace_dev'];jobs=[(i,v,0,v=='on') for i in ids for v in ['off','on']]
    else:
        ids=manifest['ids']['workspace_main'];jobs=[(i,version,r,True) for r in range(runs) for i in ids]
    if limit:jobs=jobs[:limit]
    for number,(task,v,index,tracing) in enumerate(jobs,1):
        key=f'{phase}__{v}__{task}__r{index}__s42'
        if key in complete:continue
        row=episode(suite,task,v,index,tracing,key,exp_id)
        with file.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
        records.append(row);complete.add(key);print(number,len(jobs),key,row['utility'],row['reason'],flush=True)
    if phase=='main':
        assert len(records)==30*runs
        save(folder/'summary.json',{'schema':1,'evaluation':version,'version':'base' if version=='aa' else version,'manifest':read('versions/'+('base' if version=='aa' else version)+'.json'),
            'benchmark':config['benchmark'],'runs':runs,'task_ids':ids,'records':records,'signals':signals(records)})
    else:save(folder/'summary.json',{'records':records,'task_ids':ids,'signals':signals(records)})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--version',choices=['base','aa','candidate','fix'],default='base');p.add_argument('--runs',type=int,default=3);p.add_argument('--phase',choices=['main','overhead'],default='main');p.add_argument('--limit',type=int);a=p.parse_args();run(a.version,a.runs,a.phase,a.limit)
