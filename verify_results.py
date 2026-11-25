import base64,hashlib,json
from collections import Counter
from pathlib import Path
from gate import gate,read

def decode_attrs(span):
    result={}
    for key,value in span['attributes'].items():
        try:result[key]=json.loads(value)
        except (TypeError,ValueError):result[key]=value
    return result

def main():
    frozen=read('frozen.json')
    for name,digest in frozen['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    systems={name:read('eval/'+name+'/summary.json') for name in ['base','aa','candidate','fix']}
    for name,summary in systems.items():
        assert len(summary['records'])==90 and len(summary['task_ids'])==30 and summary['runs']==3
        manifest=summary['manifest'].copy();expected=manifest.pop('system_sha256');assert hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()==expected
        for i in summary['task_ids']:assert {r['run'] for r in summary['records'] if r['task']==i}=={0,1,2}
        assert gate(systems['base'],summary)['status']!='ERROR'
    assert systems['base']['manifest']==systems['aa']['manifest']
    overhead=read('eval/overhead/summary.json')['records'];assert len(overhead)==20
    records=[r for s in systems.values() for r in s['records']]+overhead
    assert len(records)==380 and len({r['key'] for r in records})==380
    traced=0
    for row in records:
        t=read(row['trace_path']);models=[e for e in t['events'] if e['kind']=='model'];tools=[e for e in t['events'] if e['kind']=='tool']
        assert t['utility']==row['utility'];assert row['model_calls']<=15 and row['tool_calls']<=15
        assert sum(e['usage']['prompt_tokens'] for e in models)==row['input_tokens']
        assert sum(e['usage']['completion_tokens'] for e in models)==row['output_tokens']
        assert all(e['usage']['prompt_tokens']+1024<=16384 for e in models)
        if row['version'] in ['candidate','fix']:assert all(e.get('visible_chars',len(e['output']))<=2000 for e in tools if not e.get('error'))
        if row['trace_id'] is None:assert row['version']=='off';continue
        traced+=1;native=read('native_traces/'+row['key']+'.json');assert native['info']['trace_id']==row['trace_id']
        assert native['info']['tags']['utility']==str(row['utility'])
        spans=native['data']['spans'];roots=[s for s in spans if not s['parent_span_id']];assert len(roots)==1
        assert decode_attrs(roots[0])['mlflow.spanType']=='AGENT'
        children=[s for s in spans if s['parent_span_id']==roots[0]['span_id']]
        native_models=[s for s in children if decode_attrs(s)['mlflow.spanType']=='CHAT_MODEL']
        assert len(native_models)==row['model_calls']
        assert sum(decode_attrs(s).get('gen_ai.usage.input_tokens',0) for s in native_models)==row['input_tokens']
        assert sum(decode_attrs(s).get('gen_ai.usage.output_tokens',0) for s in native_models)==row['output_tokens']
        lookup={base64.b64decode(s['span_id']).hex():s for s in children}
        for event in models+tools:
            if event.get('span_id'):assert event['span_id'] in lookup
    assert traced==370 and len(list(Path('native_traces').glob('*.json')))==370
    assert read('analysis/tracing_verified.json')['verified'];assert read('analysis/trace_restore_check.json')['verified'];assert read('analysis/replay_control.json')['all_utility_calls_tokens_match']
    assert read('analysis/controls/verdict.json')['status']=='FAIL'
    print('PASS: 380 measured episodes, 370 real native traces, complete 3-run summaries, system manifests, token accounting and span links verified. No fresh model calls.')
if __name__=='__main__':main()
