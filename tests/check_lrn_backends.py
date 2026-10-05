from pathlib import Path
import sys
_PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(_PROJECT/'jobs'),str(_PROJECT/'analysis'),str(_PROJECT/'codes'),str(_PROJECT/'codes/codes')]
"""One factor problem through each production encoding and MaxSAT backend."""
from pathlib import Path
import json
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1] / 'jobs'
sys.path.insert(0,str(ROOT))
from goSolver import load_config, methods, available_cpus
from internal.supervisor import supervise

config=load_config(ROOT/'config.ubuntu.json')
p={'variables':{'x':{'lb':-1,'ub':2},'y':{'lb':0,'ub':1}},'constraints':[],
   'objective':{'sense':'min','terms':[{'c':'1/2','vars':{}}],'factor_blocks':[{'residuals':[
       {'coefficients':{'x':2,'y':2},'constant':c,'weight':1} for c in [-2,0,2]]}]}}
rows=[]
with tempfile.TemporaryDirectory() as work:
    work=Path(work); source=work/'factor.json'; source.write_text(json.dumps(p))
    for method in methods('optimization','main','qplib'):
        if 'encoding' not in method: continue
        method['options'] = {**method.get('options', {}), 'use_lrn': True}
        folder=work/method['id']; folder.mkdir()
        job={'input':str(source),'task':'optimization','family':'qplib','method':method,'code_root':config['code_root'],
             'solver_paths':config['solver_paths'],'solve_seconds':20,'cpu':available_cpus()[0],
             'smoke_expected':{'status':'OPTIMAL','objective_exact':'17/2'}}
        path=folder/'job.json'; path.write_text(json.dumps(job))
        result=supervise([config['python'],str(ROOT/'internal/worker.py'),str(path)],folder,config['profiles']['smoke'])
        rows.append({'method':method['id'],'status':result['status'],'verified':result['verified'],
                     'objective':result.get('objective_exact'),'lrn':result.get('encoding_stats',{}).get('lrn')})
        assert result['status']=='OPTIMAL' and result['verified'],(method,result,(folder/'stdout.log').read_text())
print(json.dumps(rows,indent=2))
