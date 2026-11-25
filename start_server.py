import json,subprocess,time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parent
MODEL='Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
if __name__=='__main__':
    model=ROOT/'models'/MODEL
    if not model.exists():model=ROOT.parent/'lab1/models'/MODEL
    exe=ROOT/'bin/llama/llama-server.exe'
    if not exe.exists():exe=ROOT.parent/'lab4/bin/llama/llama-server.exe'
    if not exe.exists() or not model.exists():raise SystemExit('Run download_runtime.py first')
    cmd=json.loads((ROOT/'server_command.json').read_text(encoding='utf-8'))
    cmd[0]=str(exe);cmd[cmd.index('-m')+1]=str(model)
    with (ROOT/'server.log').open('a',encoding='utf-8') as log:
        process=subprocess.Popen(cmd,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/'server.pid').write_text(str(process.pid))
    for i in range(180):
        if process.poll() is not None:raise RuntimeError('Server stopped. See server.log and Windows security events.')
        try:
            if httpx.get('http://127.0.0.1:8084/health',timeout=2).status_code==200:
                print('Server ready at http://127.0.0.1:8084/v1; PID',process.pid);break
        except httpx.TransportError:pass
        time.sleep(1)
    else:raise TimeoutError('Server startup')
