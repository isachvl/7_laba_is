import argparse,json,time
from pathlib import Path
import mlflow
ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trace-id',required=True);p.add_argument('--key',required=True);a=p.parse_args()
    mlflow.set_tracking_uri('sqlite:///'+(ROOT/'mlflow.db').as_posix());mlflow.flush_trace_async_logging();native=mlflow.get_trace(a.trace_id)
    assert native is not None
    original=json.loads(Path('traces',a.key+'.json').read_text(encoding='utf-8'))
    spans=native.data.spans;root=[s for s in spans if s.parent_id is None];assert len(root)==1 and root[0].span_type=='AGENT'
    events=[e for e in original['events'] if e['kind'] in ['model','tool']]
    children=sorted([s for s in spans if s.parent_id==root[0].span_id],key=lambda s:s.start_time_ns)
    assert len(children)==len(events),(len(children),len(events))
    for event,span in zip(events,children):
        assert event['span_id']==span.span_id
        if event['kind']=='model':
            assert span.span_type=='CHAT_MODEL';assert span.attributes['gen_ai.usage.input_tokens']==event['usage']['prompt_tokens'];assert span.attributes['gen_ai.usage.output_tokens']==event['usage']['completion_tokens']
        else:assert span.span_type=='TOOL' and span.name==event['name']
    check={'verified':True,'trace_id':a.trace_id,'key':a.key,'spans':len(spans),'model_calls':sum(e['kind']=='model' for e in events),'tool_calls':sum(e['kind']=='tool' for e in events),'root_status':str(root[0].status),'utility':original['utility']}
    Path('analysis/tracing_verified.json').write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(check,ensure_ascii=False))
