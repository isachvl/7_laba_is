import argparse,json,subprocess,sys,time
from pathlib import Path
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',choices=['aa','candidate','fix'],required=True);a=p.parse_args();root=Path(__file__).resolve().parent;folder=root/'analysis/ci_logs';folder.mkdir(exist_ok=True)
    log=folder/(a.candidate+'.log');status=[]
    commands=[[sys.executable,'-X','utf8','-m','unittest','discover','-s','tests','-v'],[sys.executable,'-X','utf8','gate.py','eval/base/summary.json','eval/'+a.candidate+'/summary.json','--report','analysis/dashboards/ci_'+a.candidate+'.html']]
    with log.open('w',encoding='utf-8') as f:
        f.write('Local execution of the same check commands configured in .github/workflows/regression.yml. No GitHub-hosted execution is claimed.\n')
        for cmd in commands:
            f.write('\nCOMMAND: '+' '.join(cmd)+'\n');f.flush();r=subprocess.run(cmd,cwd=root,stdout=f,stderr=subprocess.STDOUT);status.append({'command':cmd,'returncode':r.returncode})
            f.write('EXIT CODE: '+str(r.returncode)+'\n');f.flush()
            if r.returncode:break
    result={'kind':'local equivalent of configured GitHub Actions steps','candidate':a.candidate,'checks':status,'exit_code':next((r['returncode'] for r in status if r['returncode']),0)}
    log.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));sys.exit(result['exit_code'])
