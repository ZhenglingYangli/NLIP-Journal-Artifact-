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
    ap.add_argument('--index',required=True,type=int)
    a=ap.parse_args(); folder=a.campaign.resolve()
    plan=json.loads((folder/'campaign.json').read_text())
    if not 0<=a.index<len(plan['tasks']): raise ValueError('invalid configuration index')
    task=plan['tasks'][a.index]
    config=load_config(plan['config']); desc=config['families'][task['family']]
    if 'config_snapshot' in plan and config!=plan['config_snapshot']:
        raise ValueError('site configuration changed after preparing campaign')
    if git_identity(config['code_root'])!=plan['code_version'] or git_identity(str(ROOT))!=plan['runner_version']:
        raise ValueError('execution code changed after preparing campaign')
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
