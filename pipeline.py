import json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent;os.chdir(ROOT);os.environ['MLFLOW_DISABLE_AGENT_HINT']='1'
STATUS=Path('analysis/pipeline_status.json')
def status(stage,state='running',**kw):STATUS.write_text(json.dumps({'stage':stage,'state':state,'updated_epoch':time.time(),**kw},ensure_ascii=False,indent=2),encoding='utf-8')
def execute(label,args):
    status(label);print('STAGE',label,flush=True)
    subprocess.run([sys.executable,'-X','utf8',*args],check=True)
try:
    assert json.loads(Path('analysis/tracing_verified.json').read_text())['verified']
    execute('overhead',['eval.py','--phase','overhead'])
    for name in ['base','aa','candidate']:execute(name,['eval.py','--version',name,'--runs','3'])
    from gate import read,gate,dashboard
    Path('analysis/dashboards').mkdir(exist_ok=True)
    base=read('eval/base/summary.json')
    for name in ['aa','candidate']:
        cand=read('eval/'+name+'/summary.json');v=gate(base,cand);dashboard(base,cand,v,'analysis/dashboards/'+name+'.html');Path('analysis/dashboards',name+'.json').write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');print('GATE',name,v['status'],v['lost'],flush=True)
    candidate=gate(base,read('eval/candidate/summary.json'))
    if not candidate['lost']:
        status('candidate','needs_second_change',reason='No protected losses; assignment requires a second realistic change.');sys.exit(0)
    execute('fix',['eval.py','--version','fix','--runs','3'])
    fixed=read('eval/fix/summary.json');v=gate(base,fixed);dashboard(base,fixed,v,'analysis/dashboards/fix.html');Path('analysis/dashboards/fix.json').write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');print('GATE fix',v['status'],v['lost'],flush=True)
    status('complete','complete')
except BaseException as exc:
    if isinstance(exc,SystemExit) and exc.code==0:raise
    status('failed','error',error=repr(exc));traceback.print_exc();raise
