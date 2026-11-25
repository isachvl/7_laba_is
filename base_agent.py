import json,time
from pathlib import Path
import httpx
from openai import OpenAI
from jsonschema import validate
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.functions_runtime import EmptyEnv,FunctionCall
from agentdojo.types import ChatAssistantMessage,ChatSystemMessage,ChatUserMessage,ChatToolResultMessage,text_content_block_from_string as text

class StopEpisode(Exception):
    pass

def to_tool(f):
    return {'type':'function','function':{'name':f.name,'description':f.description,'parameters':f.parameters.model_json_schema()}}

class Agent(BasePipelineElement):
    def __init__(self,config,mode,path,scripted=None):
        self.name='local-qwen3-4b-'+mode
        self.config=config
        self.mode=mode
        self.path=Path(path)
        self.scripted=scripted
        self.client=OpenAI(base_url=config['base_url'],api_key='none',max_retries=0,timeout=600)
        self.http=httpx.Client(base_url=config['base_url'].removesuffix('/v1'),timeout=120)
        self.trace={'mode':mode,'events':[],'model_calls':0,'tool_calls':0,'input_tokens':0,'output_tokens':0,'reason':'answer'}

    def record(self,event):
        self.trace['events'].append(event)
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(json.dumps(self.trace,ensure_ascii=False,indent=2),encoding='utf-8')

    def model(self,chat,tools=None,schema=None):
        if self.trace['tool_calls']>=self.config['max_tools']:raise StopEpisode('max_tools')
        if self.trace['model_calls']>=self.config['max_calls']:raise StopEpisode('max_calls')
        request={'model':self.config['model'],'messages':chat,'temperature':0,'seed':42,'max_tokens':1024,
                 'extra_body':{'cache_prompt':True}}
        template={'messages':chat}
        if tools:request['tools']=tools;template['tools']=tools
        if schema:request['response_format']=schema
        r=self.http.post('/apply-template',json=template);r.raise_for_status()
        prompt=r.json()['prompt']
        r=self.http.post('/tokenize',json={'content':prompt,'add_special':False,'parse_special':True});r.raise_for_status()
        count=len(r.json()['tokens'])
        if count+1024>self.config['context']:raise StopEpisode('context_limit')
        self.trace['model_calls']+=1
        start=time.perf_counter()
        if self.scripted is not None:
            result=self.scripted.pop(0)
            usage={'prompt_tokens':count,'completion_tokens':0}
        else:
            response=self.client.chat.completions.create(**request)
            result=response.choices[0].message.model_dump(exclude_none=True)
            usage=response.usage.model_dump()
            if usage['prompt_tokens']+1024>self.config['context']:raise StopEpisode('context_limit')
        self.trace['input_tokens']+=usage['prompt_tokens']
        self.trace['output_tokens']+=usage['completion_tokens']
        self.record({'kind':'model','messages':chat.copy(),'tools':tools,'response_format':schema,
                     'message_count':len(chat),'counted_input_tokens':count,'response':result,'usage':usage,'seconds':time.perf_counter()-start})
        return result

    def execute(self,call,runtime,env,chat,log,allowed=None):
        if self.trace['tool_calls']>=self.config['max_tools']:raise StopEpisode('max_tools')
        self.trace['tool_calls']+=1
        name=call['function']['name']
        raw=call['function']['arguments']
        start=time.perf_counter()
        try:
            args=json.loads(raw)
            if not isinstance(args,dict):raise ValueError('Arguments must be an object')
        except (ValueError,TypeError) as exc:
            args={};output='Invalid JSON arguments: '+str(exc);error=output
        else:
            if allowed is not None and name!=allowed:
                output='Wrong tool for fixed plan step: '+name;error=output
            else:
                result,error=runtime.run_function(env,name,args)
                output=tool_result_to_str(result) if error is None else str(error)
        fc=FunctionCall(function=name,args=args,id=call['id'])
        log.extend([ChatAssistantMessage(role='assistant',content=None,tool_calls=[fc]),
                    ChatToolResultMessage(role='tool',content=[text(output)],tool_call_id=fc.id,tool_call=fc,error=error)])
        chat.append({'role':'tool','content':output,'tool_call_id':call['id']})
        self.record({'kind':'tool','name':name,'arguments_raw':raw,'arguments':args,'output':output,'error':error,
                     'allowed_tool':allowed,'seconds':time.perf_counter()-start})

    def query(self,query,runtime,env=EmptyEnv(),messages=(),extra_args={}):
        start=time.perf_counter()
        system=Path('prompts/system.txt').read_text(encoding='utf-8')
        tools=[to_tool(f) for f in runtime.functions.values()]
        chat=[{'role':'system','content':system},{'role':'user','content':query}]
        log=[ChatSystemMessage(role='system',content=[text(system)]),ChatUserMessage(role='user',content=[text(query)])]
        self.trace['query']=query
        answer=''
        try:
            if self.mode=='react':
                while True:
                    result=self.model(chat,tools)
                    calls=result.get('tool_calls',[])
                    if not calls:
                        answer=result.get('content') or 'Unable to complete the task.'
                        break
                    chat.append({k:v for k,v in result.items() if k in ('role','content','tool_calls')})
                    for call in calls:self.execute(call,runtime,env,chat,log)
            else:
                plan_schema={'type':'object','additionalProperties':False,'required':['steps'],'properties':{'steps':{'type':'array','minItems':1,'maxItems':8,'items':{'type':'object','additionalProperties':False,'required':['tool','purpose'],'properties':{'tool':{'type':'string','enum':[t['function']['name'] for t in tools]},'purpose':{'type':'string'}}}}}}
                prompt=Path('prompts/plan.txt').read_text(encoding='utf-8')
                plan_chat=chat+[{'role':'user','content':prompt+'\nAvailable tools:\n'+json.dumps(tools)}]
                result=self.model(plan_chat,schema={'type':'json_schema','json_schema':{'name':'plan','strict':True,'schema':plan_schema}})
                try:
                    plan=json.loads(result.get('content',''));validate(plan,plan_schema)
                except Exception as exc:
                    self.record({'kind':'plan_error','error':repr(exc)})
                    raise StopEpisode('plan_invalid')
                self.trace['plan']=plan
                chat.append({'role':'assistant','content':'Fixed plan: '+json.dumps(plan)})
                for step in plan['steps']:
                    chat.append({'role':'user','content':'Execute this fixed step using its tool: '+json.dumps(step)})
                    available=[t for t in tools if t['function']['name']==step['tool']]
                    result=self.model(chat,available)
                    calls=result.get('tool_calls',[])
                    if not calls:
                        chat.append({'role':'assistant','content':result.get('content') or 'Step failed.'})
                        self.record({'kind':'step_failed','step':step,'response':result})
                        continue
                    # A plan step executes at most one tool call.
                    call=calls[0]
                    chat.append({'role':'assistant','content':result.get('content'),'tool_calls':[call]})
                    self.execute(call,runtime,env,chat,log,allowed=step['tool'])
                chat.append({'role':'user','content':'Give the final concise answer based on the completed steps.'})
                result=self.model(chat)
                answer=result.get('content') or 'Unable to complete the task.'
        except StopEpisode as exc:
            self.trace['reason']=str(exc);answer='Stopped: '+str(exc)
        except Exception as exc:
            self.trace['reason']='runtime_error';answer='Unable to complete the task: '+type(exc).__name__
            self.record({'kind':'exception','error':repr(exc)})
        log.append(ChatAssistantMessage(role='assistant',content=[text(answer)],tool_calls=None))
        self.trace.update(answer=answer,seconds=time.perf_counter()-start)
        self.save()
        return query,runtime,env,log,extra_args
