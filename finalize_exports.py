"""Export completed persisted native traces after async MLflow writes settle."""
import json,os
from pathlib import Path
os.environ['MLFLOW_DISABLE_AGENT_HINT']='1'
import mlflow

def main():
    mlflow.set_tracking_uri('sqlite:///'+Path('mlflow.db').resolve().as_posix())
    refreshed=[]
    for index,path in enumerate(sorted(Path('native_traces').glob('*.json')),1):
        old=json.loads(path.read_text(encoding='utf-8'));trace=mlflow.get_trace(old['info']['trace_id'],flush=True);assert trace is not None
        new=json.loads(trace.to_json());oldspans={s['span_id']:s for s in old['data']['spans']};newspans={s['span_id']:s for s in new['data']['spans']}
        assert oldspans.keys()<=newspans.keys(),path.name
        for key,span in oldspans.items():
            assert span['start_time_unix_nano']==newspans[key]['start_time_unix_nano']
            assert span['attributes'].get('mlflow.spanInputs')==newspans[key]['attributes'].get('mlflow.spanInputs')
        assert all(k in new['info']['tags'] for k in ['task','version','evaluation','run','utility']),path.name
        if old!=new:refreshed.append({'file':path.name,'early_span_count':len(oldspans),'complete_span_count':len(newspans)})
        path.write_text(trace.to_json(),encoding='utf-8')
        if index%100==0:print('Exported',index,flush=True)
    Path('analysis/export_finalization.json').write_text(json.dumps({'refreshed':refreshed,'method':'All 370 same persisted trace IDs read again after evaluator exit and async writer completion. Early snapshots can lack final spans/tags. Existing span IDs, start times and inputs verified unchanged. No generation or outcome changes.'},indent=2),encoding='utf-8');print('Finalized exports:',index,'updated snapshots:',len(refreshed))
if __name__=='__main__':main()
