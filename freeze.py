import hashlib,importlib.metadata,json,platform,subprocess,sys
from pathlib import Path
from clock_control import FIXED_TIME

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
    from agentdojo.task_suite.load_suites import get_suites
    from base_agent import to_tool
    old=read('reference/lr5_frozen.json');assert sha('base_agent.py')==old['hashes']['base_agent.py']
    config=read('config.json');suite=get_suites(config['benchmark'])['workspace']
    tools=[to_tool(f) for f in suite.tools];save('reference/tools.json',tools)
    names=['base_agent.py','instrumented.py','clock_control.py','eval.py','config.json','gate.py','hypothesis.md','prompts/system.txt','prompts/plan.txt','reference/tools.json']
    frozen={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'hashes':{n:sha(n) for n in names},'model':{'name':config['model'],'revision':'ae44f08e1392f39c0e474af10c3ff8355c8b6688','quantization':'Q4_K_M','weights_sha256':old['source_model']},'server':read('server_command.json'),'benchmark':config['benchmark'],'generation':{'temperature':0,'seed':42,'max_tokens':1024},'limits':{k:config[k] for k in ['context','max_calls','max_tools']},'environment_tool_clock':FIXED_TIME,'python':sys.version,'executable':sys.executable,'packages':{n:importlib.metadata.version(n) for n in ['agentdojo','mlflow','openai','httpx']}}
    with Path(frozen['server'][frozen['server'].index('-m')+1]).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==old['source_model']
    save('frozen.json',frozen)
    for name,policy in [('base','unchanged result'),('candidate','first 2000 characters'),('fix','maximum 2000 characters including explicit truncation marker')]:
        version={**frozen,'name':name,'result_policy':policy};version['system_sha256']=hashlib.sha256(json.dumps(version,sort_keys=True).encode()).hexdigest();save('versions/'+name+'.json',version)
    print('Frozen system:',frozen['commit'])
