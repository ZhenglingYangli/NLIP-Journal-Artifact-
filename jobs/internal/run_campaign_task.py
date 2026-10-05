"""Execute one configuration from a prepared campaign."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from goSolver import ROOT, load_config, methods, git_identity

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--campaign',required=True,type=Path)
    ap.add_argument('--index',type=int)
    ap.add_argument('--check-code',action='store_true',help='check the prepared version on the login node before submitting')
    a=ap.parse_args(); folder=a.campaign.resolve()
    plan=json.loads((folder/'campaign.json').read_text())
    config=load_config(plan['config'])
    if 'config_snapshot' in plan and config!=plan['config_snapshot']:
        raise ValueError('site configuration changed after preparing campaign')
    if a.check_code:
        if git_identity(config['code_root'], config['git'])!=plan['code_version'] or git_identity(str(ROOT), config['git'])!=plan['runner_version']:
            raise ValueError('execution code changed after preparing campaign')
        if plan['profile']=='formal' and (plan['code_version']['dirty'] or plan['runner_version']['dirty']):
            raise ValueError('commit the solver and runner code before preparing a formal campaign')
        return
    if a.index is None or not 0<=a.index<len(plan['tasks']): raise ValueError('invalid configuration index')
    task=plan['tasks'][a.index]; desc=config['families'][task['family']]
    os.environ['AIJ_CODE_VERSION']=json.dumps(plan['code_version'])
    os.environ['AIJ_RUNNER_VERSION']=json.dumps(plan['runner_version'])
    current=next(m for m in methods(desc['task'],plan['matrix'],task['family']) if m['id']==task['method']['id'])
    if current!=task['method']: raise ValueError('method changed after preparing campaign')
    names=(Path(config['manifest_root'])/desc['manifest']).read_text().splitlines()
    if names!=plan['manifests'][task['family']]: raise ValueError('manifest changed after preparing campaign')
    count=1 if plan['profile']=='smoke' else sum(bool(n.strip()) and not n.startswith('#') for n in names)
    if task['job_ids']!=[f'{task["family"]}-{i:04d}-{current["id"]}' for i in range(1,count+1)]:
        raise ValueError('manifest count changed after preparation')
    output=folder/'runs'/task['key']
    command=[sys.executable,str(ROOT/'goSolver.py'),'--config',plan['config'],'--profile',plan['profile'],
             '--matrix',plan['matrix'],'--families',task['family'],'--methods',current['id'],
             '--workers',str(plan['workers']),'--output',str(output),'--execute']
    if (output/'run.json').exists(): command.append('--resume')
    os.execv(sys.executable,command)

if __name__=='__main__': main()
