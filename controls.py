import json,time
from functools import partial
from pathlib import Path
from reference_checks import GroundTruthAgent
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suites
from clock_control import environment_clock
from gate import gate

class DropLastRuntime(FunctionsRuntime):
    def __init__(self,functions,last,broken):super().__init__(functions);self.last=last;self.broken=broken;self.number=0
    def run_function(self,env,name,args,*a,**kw):
        self.number+=1;result,error=super().run_function(env,name,args,*a,**kw)
        return ('',error) if self.broken and self.number==self.last else (result,error)

def control():
    suite=get_suites('v1.2.2')['workspace'];ids=['user_task_'+str(i) for i in [1,2,3,7,9]];result={}
    for broken in [False,True]:
        records=[]
        for run in range(3):
            for name in ids:
                task=suite.get_user_task_by_id(name);env=task.init_environment(suite.load_and_inject_default_environment({}));n=len(task.ground_truth(env))
                start=time.perf_counter()
                with environment_clock():success,_=suite.run_task_with_pipeline(GroundTruthAgent(task),task,None,{},runtime_class=partial(DropLastRuntime,last=n,broken=broken))
                records.append({'task':name,'run':run,'utility':bool(success),'input_tokens':0,'output_tokens':0,'seconds':time.perf_counter()-start,'model_calls':0,'tool_calls':n,'trace_path':''})
        result['broken' if broken else 'base']={'manifest':{'kind':'scripted negative control','broken':broken},'benchmark':'v1.2.2','runs':3,'task_ids':ids,'records':records}
    verdict=gate(result['base'],result['broken']);assert verdict['status']=='FAIL';assert len(verdict['protected'])==5
    return result,verdict
if __name__=='__main__':
    data,verdict=control();Path('analysis/controls').mkdir(exist_ok=True)
    for name,s in data.items():Path('analysis/controls',name+'.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
    Path('analysis/controls/verdict.json').write_text(json.dumps(verdict,ensure_ascii=False,indent=2),encoding='utf-8');print('Negative control:',verdict['status'],verdict['lost'])
