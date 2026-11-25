import copy,json,os,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    os.chdir(ROOT);os.environ['MLFLOW_DISABLE_AGENT_HINT']='1'
    import mlflow
    from mlflow.tracking import MlflowClient
    from portable_traces import import_trace
    from gate import gate,dashboard
    mlflow.set_tracking_uri('sqlite:///'+(ROOT/'mlflow.db').as_posix());exp=mlflow.set_experiment('lr7');client=MlflowClient()
    mapping=read('.laptop/trace_map.json') if Path('.laptop/trace_map.json').exists() else {}
    sources=sorted(Path('native_traces').glob('*.json'))
    for index,path in enumerate(sources,1):
        raw=read(path);old=raw['info']['trace_id'];known=mapping.get(old,old)
        if mlflow.get_trace(known,silent=True) is None:
            known=import_trace(path,exp.experiment_id);mlflow.flush_trace_async_logging()
        mapping[old]=known
        save('.laptop/trace_map.json',mapping)
        if index%50==0:print('Traces restored:',index,'/',len(sources),flush=True)
    copied={}
    for name in ['base','aa','candidate','fix']:
        summary=read('eval/'+name+'/summary.json');local=copy.deepcopy(summary)
        for row in local['records']:
            row['trace_id']=mapping[row['trace_id']];row['trace_url']=f"http://127.0.0.1:5006/#/experiments/{exp.experiment_id}/traces?selectedTraceId={row['trace_id']}"
        copied[name]=local;save('.laptop/eval/'+name+'.json',local)
        existing=client.search_runs([exp.experiment_id],filter_string=f"tags.configuration = '{name}'")
        verdict=gate(copied.get('base',local),local)
        with mlflow.start_run(run_id=existing[0].info.run_id if existing else None,run_name=name,log_system_metrics=False):
            mlflow.set_tag('configuration',name);mlflow.log_params({'benchmark':summary['benchmark'],'tasks':30,'runs_per_task':3,'temperature':0})
            metrics={'success':sum(r['utility'] for r in local['records'])/90,'median_total_tokens':statistics.median(r['input_tokens']+r['output_tokens'] for r in local['records']),
                'median_seconds':statistics.median(r['seconds'] for r in local['records']),'protected_lost':len(verdict['lost'])}
            oldmetrics=existing[0].data.metrics if existing else {};pending={k:v for k,v in metrics.items() if oldmetrics.get(k)!=v}
            if pending:mlflow.log_metrics(pending)
            mlflow.set_tag('gate_status',verdict['status']);mlflow.log_artifact('eval/'+name+'/summary.json','evaluation');mlflow.log_artifact('versions/'+('base' if name=='aa' else name)+'.json','version')
            if name=='base':
                for path in Path('analysis').glob('*'):
                    if path.is_file() and path.suffix in ['.json','.png','.csv']:mlflow.log_artifact(str(path),'analysis')
                mlflow.log_artifact('report.pdf','report')
    for name in ['aa','candidate','fix']:
        result=gate(copied['base'],copied[name]);dashboard(copied['base'],copied[name],result,'.laptop/dashboards/'+name+'.html')
    links=''.join('<li><a href=".laptop/dashboards/'+n+'.html">'+n+'</a></li>' for n in ['aa','candidate','fix'])
    Path('dashboard.local.html').write_text('<!doctype html><meta charset="utf-8"><h1>ЛР7: регрессионные дашборды</h1><ul>'+links+'</ul><p><a href="http://127.0.0.1:5006">MLflow: Traces</a></p>',encoding='utf-8')
    print('Ready: lr7, 4 evaluation runs and',len(sources),'native traces. Open dashboard.local.html and MLflow Traces. Saved timestamps are preserved; clear the time filter if needed.')
if __name__=='__main__':main()
