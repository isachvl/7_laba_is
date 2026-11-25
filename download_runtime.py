import hashlib,json,shutil,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MODEL='Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
MODEL_SHA='2fde00ce69dd4899c70d020845e2638353015bba0fdf161b3eb965f2bca4464e'
MODEL_URL='https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/resolve/ae44f08e1392f39c0e474af10c3ff8355c8b6688/'+MODEL

def download(url,path,expected):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        partial=path.with_suffix(path.suffix+'.part')
        subprocess.run(['curl.exe','-L','--fail','--retry','3','-o',str(partial),url],check=True)
        partial.replace(path)
    with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=expected:raise ValueError('Unexpected SHA-256: '+str(path))

if __name__=='__main__':
    for asset in json.loads((ROOT/'server_assets.json').read_text(encoding='utf-8')):
        archive=ROOT/'downloads'/asset['source'].split('/')[-1]
        download(asset['source'],archive,asset['sha256'])
        dest=(ROOT/'bin/llama').resolve()
        dest.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if not (dest/member.filename).resolve().is_relative_to(dest):raise ValueError('Unsafe archive member')
            z.extractall(dest)
    sibling=ROOT.parent/'lab1/models'/MODEL
    if sibling.exists():
        with sibling.open('rb') as f:
            assert hashlib.file_digest(f,'sha256').hexdigest()==MODEL_SHA
        print('Verified model in lab1:',sibling)
    else:download(MODEL_URL,ROOT/'models'/MODEL,MODEL_SHA)
    print('Runtime ready. Run start_server.py, then run.py dev.')

