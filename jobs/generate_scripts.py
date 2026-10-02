"""Prepare disjoint family/method Slurm jobs. Never submits automatically."""
import argparse
import json
from math import ceil
from pathlib import Path
import shlex
from generate_slurm import write_submission
from goSolver import ROOT, load_config, methods, git_identity


def configuration_tasks(config, profile, matrix):
    tasks=[]
    for family, desc in config['families'].items():
        names=(Path(config['manifest_root'])/desc['manifest']).read_text().splitlines()
        names=[n.strip() for n in names if n.strip() and not n.startswith('#')]
        count=1 if profile=='smoke' else len(names)
        for method in methods(desc['task'],matrix,family):
            key=family+'-'+method['id']
            tasks.append({'key':key,'family':family,'method':method,
                          'job_ids':[f'{family}-{i:04d}-{method["id"]}' for i in range(1,count+1)]})
    ids=[j for t in tasks for j in t['job_ids']]
    if len(ids)!=len(set(ids)):
        raise ValueError('overlapping configuration tasks')
    return tasks


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',default=str(ROOT/'config.json'))
    ap.add_argument('--profile',choices=['formal','smoke'],default='formal')
    ap.add_argument('--matrix',choices=['main','decomposition'],default='main')
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--workers',type=int,default=7)
    ap.add_argument('--partition',choices=['normal','bigmem'],default='normal')
    ap.add_argument('--concurrent-jobs',type=int,default=3)
    ap.add_argument('--memory-gib',type=int,help='default 120 GiB for 7 formal workers; sized from worker budgets')
    a=ap.parse_args(); config=load_config(a.config)
    if a.memory_gib is None:
        a.memory_gib=460 if a.workers==28 else ceil((a.workers*config['profiles'][a.profile]['memory_gib']+.5)/10)*10
    if not 1<=a.workers<=28 or not 1<=a.concurrent_jobs<=4:
        raise ValueError('campaign supports 1..28 workers/job and 1..4 simultaneous exclusive nodes')
    memory_max=125 if a.partition=='normal' else 500
    if a.memory_gib < a.workers*config['profiles'][a.profile]['memory_gib']+.5 or a.memory_gib>memory_max:
        raise ValueError(f'memory must cover worker budgets plus runner reserve and be <={memory_max} GiB on {a.partition}')
    tasks=configuration_tasks(config,a.profile,a.matrix)
    limits=config['profiles'][a.profile]
    # Size the job from the largest configuration and the outer per-run cap.
    worst=max(ceil(len(t['job_ids'])/a.workers)*limits['outer_seconds'] for t in tasks)
    wall_hours=ceil(worst/3600)+2
    if wall_hours>360:
        raise ValueError('configuration exceeds the 15-day job limit; increase workers')
    plan={'config':str(Path(a.config).resolve()),'profile':a.profile,'matrix':a.matrix,
          'partition':a.partition,'workers':a.workers,'concurrent_jobs':a.concurrent_jobs,'memory_gib':a.memory_gib,
          'configuration_jobs':len(tasks),'instance_runs':sum(len(t['job_ids']) for t in tasks),'tasks':tasks}
    plan['code_version']=git_identity(config['code_root'])
    plan['config_snapshot']=config
    plan['limits']=limits
    plan['runner_version']=git_identity(str(ROOT))
    plan['manifests']={f:(Path(config['manifest_root'])/d['manifest']).read_text().splitlines()
                       for f,d in config['families'].items()}
    output=a.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    planpath=output/'campaign.json'
    if planpath.exists() and json.loads(planpath.read_text())!=plan:
        raise ValueError('existing campaign has different settings; keep its plan unchanged')
    planpath.write_text(json.dumps(plan,indent=2)+'\n')
    write_submission(plan, output, ROOT, wall_hours)
    print(json.dumps({k:plan[k] for k in ['profile','matrix','partition','workers','concurrent_jobs','memory_gib','configuration_jobs','instance_runs']},indent=2))
    print('Prepared only. Submit with: bash '+shlex.quote(str(output/'submit.sh')))

if __name__=='__main__': main()
