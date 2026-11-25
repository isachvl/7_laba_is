"""One real exported tree, restored without generating an answer."""
import json
from pathlib import Path
import mlflow
from mlflow.entities import Trace
from portable_traces import import_trace

def canonical(trace):
    spans=trace.data.spans
    by_id={s.span_id:s for s in spans}
    def ancestry(s):
        return (() if s.parent_id is None else ancestry(by_id[s.parent_id]))+(s.name,)
    return [(ancestry(s),s.span_type,s.inputs,s.outputs,str(s.status),s.start_time_ns,s.end_time_ns) for s in sorted(spans,key=lambda x:(ancestry(x),x.start_time_ns))]

def main():
    source=Path('native_traces/overhead__on__user_task_0__r0__s42.json')
    original=Trace.from_json(source.read_text(encoding='utf-8'))
    Path('.restore_test').mkdir(exist_ok=True)
    mlflow.set_tracking_uri('sqlite:///'+str(Path('.restore_test/mlflow.db').resolve()).replace('\\','/'))
    experiment=mlflow.set_experiment('portability-check')
    trace_id=import_trace(source,experiment.experiment_id)
    mlflow.flush_trace_async_logging()
    restored=mlflow.get_trace(trace_id,flush=True)
    assert restored and canonical(original)==canonical(restored)
    result={'verified':True,'spans':len(original.data.spans),'original_trace_id':original.info.trace_id,'restored_trace_id':trace_id,'structure_inputs_outputs_status_and_times_match':True}
    Path('analysis/trace_restore_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result)
if __name__=='__main__':main()

