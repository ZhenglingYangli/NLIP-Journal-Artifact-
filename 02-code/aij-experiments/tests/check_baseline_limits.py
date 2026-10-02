"""Exercise a genuine nonoptimal nonlinear incumbent and outer deadlines."""
from pathlib import Path
import argparse
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent/'nlipsat-aij'/'codes'))
import scip_baseline as baseline
from pyscipopt import SCIP_PARAMSETTING
from supervisor import supervise
from run_batch import available_cpus, load_config

problem = {'variables':{'x':{'lb':0,'ub':2}},'constraints':[],
           'objective':{'sense':'max','terms':[{'c':1,'vars':{'x':2}}]}}
build = baseline.build_model
def with_incumbent(*args,**kwargs):
    model,original,stats = build(*args,**kwargs)
    model.setPresolve(SCIP_PARAMSETTING.OFF)
    model.setHeuristics(SCIP_PARAMSETTING.OFF)
    model.setLongintParam('limits/nodes',0)
    sol = model.createSol()
    model.setSolVal(sol, original['x'],1)
    objective_var = next(v for v in model.getVars() if v.name=='objective_value')
    model.setSolVal(sol,objective_var,0)
    assert model.addSol(sol)
    return model,original,stats
baseline.build_model = with_incumbent
result = baseline.solve(problem,'native',5)
baseline.build_model = build
assert result['status']=='FEASIBLE' and result['verified'],result
assert result['objective_exact']=='1' and result['encoded_incumbent_objective']==0,result
records = [{'check':'native-nonoptimal-slack','status':result['status'],
            'original_objective':result['objective_exact'],'encoded_objective':result['encoded_incumbent_objective']}]
parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
args = parser.parse_args()
config = load_config(args.config)
for solver in ['SCIP-MILP','SCIP-NATIVE']:
    with tempfile.TemporaryDirectory(prefix='aij-baseline-deadline-') as folder:
        path = Path(folder)
        job = {'cpu':available_cpus()[0],'code_root':str((ROOT/'../nlipsat-aij').resolve()),
               'method':{'id':solver.lower(),'solver':solver},'task':'optimization',
               'input':str(ROOT/'smoke/cross.qplib'),'solver_paths':{},'solve_seconds':.02}
        (path/'job.json').write_text(json.dumps(job))
        answer = supervise([config['python'],'-u',str(ROOT/'worker.py'),str(path/'job.json')],path,
                           {'solve_seconds':.02,'verify_seconds':5,'memory_gib':1,'poll_seconds':.005})
        assert answer['status']=='TIMEOUT',answer
        records.append({'check':solver+'-outer-deadline','status':answer['status'],'wall_seconds':answer['wall_seconds']})
output = args.output;output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(records,indent=2))
print(json.dumps(records,indent=2))
