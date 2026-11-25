import csv,json,statistics
from pathlib import Path
from gate import gate,read,dashboard

def save(p,v):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def stats(records,key):
    values=[r[key] for r in records]
    return {'median':statistics.median(values),'min':min(values),'max':max(values),'sum':sum(values)}
def canonical(e):
    if e['kind']=='model':
        response=e['response'];calls=[]
        for c in response.get('tool_calls',[]):
            raw=c['function']['arguments']
            try:args=json.loads(raw)
            except ValueError:args=raw
            calls.append({'name':c['function']['name'],'arguments':args})
        return {'kind':'model','content':response.get('content'),'tool_calls':calls}
    if e['kind']=='tool':return {k:e.get(k) for k in ['kind','name','arguments','output','error']}
    return None

def divergence(first,second):
    a=[e for e in read(first['trace_path'])['events'] if canonical(e) is not None];b=[e for e in read(second['trace_path'])['events'] if canonical(e) is not None]
    for index in range(max(len(a),len(b))):
        x=a[index] if index<len(a) else None;y=b[index] if index<len(b) else None
        if x is None or y is None or canonical(x)!=canonical(y):
            return {'event':index+1,'base':x,'candidate':y,'base_trace_id':first['trace_id'],'candidate_trace_id':second['trace_id'],'base_trace':first['trace_path'],'candidate_trace':second['trace_path']}
    return None

def main():
    systems={n:read('eval/'+n+'/summary.json') for n in ['base','aa','candidate','fix']}
    # Normalize presentation-only URLs to the installed MLflow UI query parameter.
    for name,system in systems.items():
        for row in system['records']:
            if row.get('trace_url'):row['trace_url']=row['trace_url'].replace('selectedTraceId=','traceId=')
        save('eval/'+name+'/summary.json',system)
    records=[r for n in systems.values() for r in n['records']]
    assert len(records)==360 and len({r['key'] for r in records})==360
    overhead_summary=read('eval/overhead/summary.json')
    overhead_summary.update(manifest=read('versions/base.json'),benchmark=systems['base']['benchmark'],runs_per_condition=1,tracing_conditions=['off','on'])
    save('eval/overhead/summary.json',overhead_summary)
    overhead=overhead_summary['records'];assert len(overhead)==20
    off={r['task']:r for r in overhead if r['version']=='off'};on={r['task']:r for r in overhead if r['version']=='on'}
    timing={'off':stats(list(off.values()),'seconds'),'on':stats(list(on.values()),'seconds')}
    parity={'n':10,'utility_equal':sum(off[i]['utility']==on[i]['utility'] for i in off),
            'token_equal':sum(all(off[i][k]==on[i][k] for k in ['input_tokens','output_tokens']) for i in off),
            'calls_equal':sum(all(off[i][k]==on[i][k] for k in ['model_calls','tool_calls']) for i in off),
            'mismatch_tasks':[i for i in off if any(off[i][k]!=on[i][k] for k in ['utility','input_tokens','output_tokens','model_calls','tool_calls'])],
            'timing':timing,'observed_time_ratio':timing['on']['median']/timing['off']['median']}
    equal_work=[i for i in off if all(off[i][k]==on[i][k] for k in ['input_tokens','output_tokens','model_calls','tool_calls'])]
    parity['equal_work_tasks']=equal_work
    if equal_work:parity['equal_work_time']={n:stats([d[i] for i in equal_work],'seconds') for n,d in [('off',off),('on',on)]}
    metrics={}
    for name,system in systems.items():
        data=system['records'];metrics[name]={'successes':sum(r['utility'] for r in data),'n':90,'success':sum(r['utility'] for r in data)/90,
            'per_run_successes':[sum(r['utility'] for r in data if r['run']==k) for k in range(3)],
            **{k:stats(data,k) for k in ['model_calls','tool_calls','input_tokens','output_tokens','seconds','max_input_tokens']},
            'tool_errors':sum(r['tool_errors'] for r in data),'limit_stops':sum(r['reason'] in ['max_calls','max_tools','context_limit'] for r in data),'truncations':sum(r['truncated_tools'] for r in data)}
    for name,system in systems.items():
        totals=[r['input_tokens']+r['output_tokens'] for r in system['records']]
        metrics[name]['total_tokens']={'median':statistics.median(totals),'min':min(totals),'max':max(totals),'sum':sum(totals)}
    verdicts={n:gate(systems['base'],systems[n]) for n in ['aa','candidate','fix']}
    strict=gate(systems['base'],systems['aa'],strict=True)
    comparisons=[]
    for name in ['candidate','fix']:
        lost=verdicts[name]['lost']
        if not lost:
            by_a={r['task']:[] for r in systems['base']['records']};by_b={r['task']:[] for r in systems[name]['records']}
            for r in systems['base']['records']:by_a[r['task']].append(r)
            for r in systems[name]['records']:by_b[r['task']].append(r)
            selected=max(by_a,key=lambda i:sum(r['input_tokens']+r['output_tokens'] for r in by_b[i])-sum(r['input_tokens']+r['output_tokens'] for r in by_a[i]));lost=[selected]
        for task in lost:
            b=sorted([r for r in systems[name]['records'] if r['task']==task],key=lambda r:r['run']);chosen=next((r for r in b if not r['utility']),b[0]);original=next(r for r in systems['base']['records'] if r['task']==task and r['run']==chosen['run'])
            difference=divergence(original,chosen)
            truncated=[e for e in read(chosen['trace_path'])['events'] if e['kind']=='tool' and e.get('truncated')]
            comparisons.append({'version':name,'task':task,'lost':task in verdicts[name]['lost'],'candidate_runs':[r['utility'] for r in b],
                'first_difference':difference,'first_truncation':truncated[0] if truncated else None,'base_record':original,'candidate_record':chosen})
    semantic_example=None
    for r in sorted(systems['candidate']['records'],key=lambda r:(r['task']!='user_task_35',r['run']))+systems['base']['records']:
        if r['utility'] or r['reason']!='answer':continue
        native=read('native_traces/'+r['key']+'.json')
        root=next(s for s in native['data']['spans'] if not s.get('parent_span_id'))
        if native['info']['state']=='OK':
            semantic_example={'record':r,'root_status':root['status'],'answer':read(r['trace_path'])['answer'],'query':read(r['trace_path'])['query']};break
    summary={'overhead':parity,'metrics':metrics,'gates':verdicts,'strict_aa':strict,'comparisons':comparisons,'semantic_example':semantic_example,
             'episodes':380,'native_traces':len(list(Path('native_traces').glob('*.json'))),'controls':read('analysis/controls/verdict.json')}
    save('analysis/summary.json',summary);save('analysis/divergence_candidates.json',comparisons)
    for name,v in verdicts.items():dashboard(systems['base'],systems[name],v,'analysis/dashboards/'+name+'.html');save('analysis/dashboards/'+name+'.json',v)
    dashboard(systems['base'],systems['aa'],strict,'analysis/dashboards/aa_strict.html');save('analysis/dashboards/aa_strict.json',strict)
    with Path('analysis/version_metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['version','successes','episodes','median_input','median_output','median_total_tokens','median_seconds','median_model_calls','max_context','gate_status']);w.writeheader()
        for n,m in metrics.items():w.writerow({'version':n,'successes':m['successes'],'episodes':90,'median_input':m['input_tokens']['median'],'median_output':m['output_tokens']['median'],'median_total_tokens':m['total_tokens']['median'],'median_seconds':m['seconds']['median'],'median_model_calls':m['model_calls']['median'],'max_context':m['max_input_tokens']['max'],'gate_status':'BASE' if n=='base' else verdicts[n]['status']})
    with Path('analysis/overhead.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['task','off_success','on_success','off_input','on_input','off_output','on_output','off_seconds','on_seconds']);w.writeheader()
        for i in off:w.writerow({'task':i,'off_success':off[i]['utility'],'on_success':on[i]['utility'],'off_input':off[i]['input_tokens'],'on_input':on[i]['input_tokens'],'off_output':off[i]['output_tokens'],'on_output':on[i]['output_tokens'],'off_seconds':off[i]['seconds'],'on_seconds':on[i]['seconds']})
    plots(summary);print('Analysis complete:',{n:v['status'] for n,v in verdicts.items()},'AA strict:',strict['status'])

def plots(s):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names=list(s['metrics']);data=s['metrics'];colors=['#64748b','#0f8d78','#c05028','#2563eb']
    fig,axes=plt.subplots(1,3,figsize=(12,3.3),layout='constrained')
    for ax,key,title,label in [(axes[0],'success','Успешность','%'),(axes[1],'tokens','Медиана суммы входа и выхода','Токены'),(axes[2],'seconds','Медиана времени','Секунды')]:
        values=[100*data[n]['success'] if key=='success' else data[n]['total_tokens']['median'] if key=='tokens' else data[n]['seconds']['median'] for n in names]
        bars=ax.bar(names,values,color=colors);ax.bar_label(bars,fmt='%.1f',padding=3);ax.set(title=title,ylabel=label,ylim=(0,max(values)*1.3));ax.tick_params(axis='x',labelsize=8)
    fig.savefig('analysis/versions.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(8,3),layout='constrained')
    values=[s['overhead']['timing'][n]['median'] for n in ['off','on']]
    bars=axes[0].bar(['Без трейсинга','С трейсингом'],values,color=['#64748b','#2563eb']);axes[0].bar_label(bars,fmt='%.2f',padding=3);axes[0].set(title='Наблюдаемая медиана времени',ylabel='Секунды',ylim=(0,max(values)*1.3))
    gates=s['gates'];labels=['A/A','Изменение','Исправление'];values=[len(gates[n]['lost']) for n in ['aa','candidate','fix']]
    bars=axes[1].bar(labels,values,color=['#0f8d78','#c05028','#2563eb']);axes[1].bar_label(bars,padding=3);axes[1].set(title='Потерянные защищаемые задачи',ylabel='Задач',ylim=(0,max(max(values)*1.3,1)))
    fig.savefig('analysis/gates.png',dpi=170);plt.close(fig)
if __name__=='__main__':main()
