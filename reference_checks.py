import hashlib,importlib.metadata,json
from pathlib import Path
from agentdojo.task_suite.load_suites import get_suites
from agentdojo.functions_runtime import FunctionsRuntime,FunctionCall
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.types import ChatAssistantMessage,ChatToolResultMessage,text_content_block_from_string as text
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def build_manifest():
    suite=get_suites('v1.2.2')['workspace']
    assert len(suite.tools)==24 and len(suite.user_tasks)==40
    tasks=[]
    for i in range(40):
        key=f'user_task_{i}';task=suite.get_user_task_by_id(key)
        env=task.init_environment(suite.load_and_inject_default_environment({}))
        before=env.model_dump_json();calls=task.ground_truth(env);runtime=FunctionsRuntime(suite.tools)
        for call in calls:
            _,error=runtime.run_function(env,call.function,call.args);assert error is None
        tasks.append(dict(id=key,split='dev' if i%4==0 else 'main',ground_truth_calls=len(calls),state_changing=before!=env.model_dump_json(),prompt=task.PROMPT))
    ids={s:[t['id'] for t in tasks if t['split']==s] for s in ('dev','main')}
    manifest={'agentdojo':importlib.metadata.version('agentdojo'),'benchmark':'v1.2.2','suite':'workspace','task_ids':ids,'task_list_sha256':hashlib.sha256(json.dumps(ids,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'tasks':tasks,'tools':[dict(name=f.name,description=f.description,parameters=f.parameters.model_json_schema()) for f in suite.tools]}
    save('manifest.json',manifest);return suite,manifest
class GroundTruthAgent(BasePipelineElement):
    name='scripted-ground-truth'
    def __init__(self,task):self.task=task
    def query(self,query,runtime,env,messages=(),extra_args={}):
        log=[];outputs=[]
        for i,c in enumerate(self.task.ground_truth(env)):
            call=FunctionCall(function=c.function,args=c.args,id=str(i))
            result,error=runtime.run_function(env,call.function,call.args)
            output=tool_result_to_str(result) if error is None else str(error);outputs.append(output)
            log.extend([ChatAssistantMessage(role='assistant',content=None,tool_calls=[call]),ChatToolResultMessage(role='tool',content=[text(output)],tool_call_id=call.id,tool_call=call,error=error)])
        log.append(ChatAssistantMessage(role='assistant',content=[text('\n'.join(outputs))],tool_calls=None))
        return query,runtime,env,log,extra_args
if __name__=='__main__':
    suite,manifest=build_manifest();results={}
    for key,task in suite.user_tasks.items():results[key]=bool(suite.run_task_with_pipeline(GroundTruthAgent(task),task,None,{})[0])
    save('checks/ground_truth.json',results);print('Ground truth successes',sum(results.values()),'/',len(results))
