import argparse,html,json,statistics,sys
from pathlib import Path

DEFAULT={'minimum_protected':5,'cost_growth':.25,'time_growth':.25,'remaining_drop_tasks':1}

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def summarize(summary):
    records=summary['records'];by={i:[] for i in summary['task_ids']}
    for r in records:by[r['task']].append(r)
    return by

def validate(s):
    if not isinstance(s,dict) or not s.get('task_ids') or len(set(s['task_ids']))!=len(s['task_ids']):return 'Invalid task list'
    if not s.get('benchmark') or not s.get('manifest') or s.get('runs')!=3:return 'Missing manifest, benchmark or three-run declaration'
    by=summarize(s)
    if any(len(v)!=3 or {r['run'] for r in v}!={0,1,2} for v in by.values()):return 'Missing or duplicate task repetition'
    if len(s['records'])!=3*len(by):return 'Extra task records'
    for r in s['records']:
        if type(r.get('utility')) is not bool:return 'Invalid utility'
        for k in ['input_tokens','output_tokens','seconds']:
            if not isinstance(r.get(k),(int,float)) or r[k]<0:return 'Missing or invalid cost/time'
    return None

def gate(base,candidate,tests_ok=True,strict=False,thresholds=None):
    limits=thresholds or DEFAULT
    try:
        problem=validate(base) or validate(candidate)
        if problem:return {'status':'ERROR','reason':[problem],'protected':[],'lost':[],'new':[]}
        if set(base['task_ids'])!=set(candidate['task_ids']) or base['benchmark']!=candidate['benchmark']:return {'status':'ERROR','reason':['Task list or benchmark mismatch'],'protected':[],'lost':[],'new':[]}
        a=summarize(base);b=summarize(candidate)
    except (KeyError,TypeError,ValueError):return {'status':'ERROR','reason':['Malformed summary'],'protected':[],'lost':[],'new':[]}
    protected=[i for i in a if all(r['utility'] for r in a[i])]
    lost=[i for i in protected if sum(r['utility'] for r in b[i])<(3 if strict else 2)]
    new=[i for i in a if sum(r['utility'] for r in a[i])<2 and sum(r['utility'] for r in b[i])>=2]
    reasons=[];status='PASS'
    if not tests_ok:status='FAIL';reasons.append('Tests without model failed')
    if lost:status='FAIL';reasons.append('Protected task lost')
    remaining=[i for i in a if i not in protected]
    drop=(sum(r['utility'] for i in remaining for r in a[i])-sum(r['utility'] for i in remaining for r in b[i]))/3
    def median(s,k):return statistics.median((r['input_tokens']+r['output_tokens']) if k=='tokens' else r[k] for r in s['records'])
    costs={n:{'successes':sum(r['utility'] for r in s['records']),'episodes':len(s['records']),'mean_success':sum(r['utility'] for r in s['records'])/len(s['records']),
               'median_tokens':median(s,'tokens'),'median_seconds':median(s,'seconds')} for n,s in [('base',base),('candidate',candidate)]}
    for metric,threshold in [('median_tokens',limits['cost_growth']),('median_seconds',limits['time_growth'])]:
        first=costs['base'][metric];second=costs['candidate'][metric]
        ratio=second/first if first else (1 if second==0 else float('inf'))
        if ratio>1+threshold:reasons.append(metric+' increased by more than 25%');status='REVIEW' if status=='PASS' else status
    if len(protected)<limits['minimum_protected']:reasons.append('Fewer than five protected tasks');status='REVIEW' if status=='PASS' else status
    if drop>=limits['remaining_drop_tasks']:reasons.append('Mean remaining successes dropped by at least one task');status='REVIEW' if status=='PASS' else status
    return {'status':status,'reason':reasons or ['No rejection or review condition'],'protected':protected,'lost':lost,'new':new,'remaining_drop_tasks':drop,'costs':costs,'strict':strict}

def dashboard(base,candidate,result,path):
    a=summarize(base) if validate(base) is None else {};b=summarize(candidate) if validate(candidate) is None else {}
    rows=[]
    for i in sorted(set(a)&set(b),key=lambda s:int(s.split('_')[-1])):
        ar=sorted(a[i],key=lambda r:r['run']);br=sorted(b[i],key=lambda r:r['run'])
        def links(rs):return ' '.join('<a href="'+html.escape(r.get('trace_url') or r.get('trace_path',''))+'">'+str(r['run']+1)+'</a>' for r in rs)
        rows.append('<tr><td>'+i+'</td><td>'+str(sum(r['utility'] for r in ar))+'/3</td><td>'+str(sum(r['utility'] for r in br))+'/3</td><td>'+str(i in result['protected'])+'</td><td>'+str(i in result['lost'])+'</td><td>'+links(ar)+'</td><td>'+links(br)+'</td></tr>')
    content='<!doctype html><html lang="ru"><meta charset="utf-8"><title>LR7 regression gate</title><style>body{font:15px Arial;max-width:1150px;margin:30px auto;color:#172339}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccd5df}th{background:#e5effa}pre{white-space:pre-wrap;background:#f3f5f8;padding:12px}a{color:#165cbd}</style>'
    content+='<h1>Регрессионный гейт: '+result['status']+'</h1><p>'+html.escape('; '.join(result['reason']))+'</p><h2>Версии и манифесты</h2><pre>'+html.escape(json.dumps({'base':base.get('manifest'),'candidate':candidate.get('manifest'),'benchmark':base.get('benchmark')},ensure_ascii=False,indent=2))+'</pre>'
    content+='<h2>Итоги</h2><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre><h2>Исходы и ссылки на трейсы</h2><table><tr><th>Задача</th><th>База</th><th>Кандидат</th><th>Защищена</th><th>Потеряна</th><th>Трейсы базы</th><th>Трейсы кандидата</th></tr>'+''.join(rows)+'</table>'
    content+='<h2>Четыре сигнала</h2><pre>'+html.escape(json.dumps({'base':base.get('signals'),'candidate':candidate.get('signals')},ensure_ascii=False,indent=2))+'</pre></html>'
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(content,encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('base');p.add_argument('candidate');p.add_argument('--report',default='gate_report.html');p.add_argument('--strict',action='store_true');p.add_argument('--tests-failed',action='store_true');args=p.parse_args()
    try:base=read(args.base);cand=read(args.candidate)
    except (OSError,ValueError) as exc:print(json.dumps({'status':'ERROR','reason':str(exc)}));return 2
    result=gate(base,cand,not args.tests_failed,args.strict);dashboard(base,cand,result,args.report)
    Path(args.report).with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 1 if result['status']=='FAIL' else 2 if result['status']=='ERROR' else 0
if __name__=='__main__':sys.exit(main())
