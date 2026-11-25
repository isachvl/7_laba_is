import json
from pathlib import Path
from mlflow.entities import Trace
from mlflow.tracking import MlflowClient

def import_trace(path,experiment_id):
    source=Trace.from_json(Path(path).read_text(encoding='utf-8'));spans=source.data.spans
    root=next(s for s in spans if s.parent_id is None);client=MlflowClient()
    def attrs(span):return {**{k:v for k,v in span.attributes.items() if not k.startswith('mlflow.') or k=='mlflow.chat.tokenUsage'},'origin_span_id':span.span_id}
    tags={k:v for k,v in source.info.tags.items() if not k.startswith('mlflow.')};tags['origin_trace_id']=source.info.trace_id;tags['restored_from_saved_trace']='True'
    fresh=client.start_trace(name=root.name,span_type=root.span_type,inputs=root.inputs,attributes=attrs(root),tags=tags,experiment_id=experiment_id,start_time_ns=root.start_time_ns)
    mapping={root.span_id:fresh.span_id};pending=[s for s in sorted(spans,key=lambda s:s.start_time_ns) if s.parent_id is not None]
    while pending:
        remaining=[]
        for span in pending:
            if span.parent_id not in mapping:remaining.append(span);continue
            new=client.start_span(name=span.name,trace_id=fresh.trace_id,parent_id=mapping[span.parent_id],span_type=span.span_type,inputs=span.inputs,attributes=attrs(span),start_time_ns=span.start_time_ns)
            mapping[span.span_id]=new.span_id
        if len(remaining)==len(pending):raise ValueError('Invalid span hierarchy')
        pending=remaining
    for span in sorted([s for s in spans if s.parent_id is not None],key=lambda s:s.end_time_ns):
        client.end_span(trace_id=fresh.trace_id,span_id=mapping[span.span_id],outputs=span.outputs,status=span.status,end_time_ns=span.end_time_ns)
    client.end_trace(trace_id=fresh.trace_id,outputs=root.outputs,status=root.status,end_time_ns=root.end_time_ns)
    return fresh.trace_id
