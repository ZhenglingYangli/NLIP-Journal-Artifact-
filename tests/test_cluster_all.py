"""Exercise the automatic workflow with a local simulated Slurm environment."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = r'''import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]; action=sys.argv[1]
with (root/'actions').open('a') as f: f.write(' '.join(sys.argv[1:])+'\n')
def write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
if action=='data':
 for name in ['a.json','b.json']: write(root/'benchmarks/mipo'/name,{})
elif action=='configure': write(Path(os.environ['AIJ_CONFIG']),{'code_root':'codes','families':{'mipo':{'input_root':str(root/'benchmarks/mipo')}}})
elif action=='smoke':
 (root/'results/cluster-smoke-last-job.txt').write_text('101')
 folder=root/'results/cluster-smoke-101'; jobs=[]
 for i in range(61):
  name=str(i);jobs.append({'id':name,'smoke_expected':{'status':'OPTIMAL'}})
  write(folder/'jobs'/name/'result.json',{'verified':not bool(os.environ.get('FAIL_SMOKE')),'status':'OPTIMAL'})
 config=json.loads(Path(os.environ['AIJ_CONFIG']).read_text())
 write(folder/'run.json',{'plan':{'config':config,'code':{'commit':'fixed'},'execution_code':{'commit':'fixed'},'jobs':jobs}})
elif action.startswith('prepare'):
 batch=sys.argv[2];folder=root/'results'/batch
 config=json.loads(Path(os.environ['AIJ_CONFIG']).read_text())
 write(folder/'campaign.json',{'profile':'formal','matrix':'decomposition' if action.endswith('decomposition') else 'main','config_snapshot':config,'code_version':{'commit':'fixed'},'runner_version':{'commit':'fixed'},'tasks':[{'key':'config','job_ids':['job1']}]})
elif action in ['submit','resume','analyze']:
 folder=root/'results'/sys.argv[2]
 (folder/'array_job_id.txt').write_text('201')
 (folder/'analysis_job_id.txt').write_text('202')
 if action=='resume' or sys.argv[2]=='aij-decomposition':
  write(folder/'runs/config/jobs/job1/result.json',{'job_id':'job1','status':'TIMEOUT','witness':{'x':1}})
  write(folder/'runs/config/run.json',{'plan':{'python':sys.executable,'jobs':['job1']}})
 (folder/'analysis').mkdir(exist_ok=True);(folder/'analysis/report.md').write_text('report')
 (folder/'sumup').mkdir(exist_ok=True);(folder/'sumup/config.csv').write_text('status\nTIMEOUT\n')
'''
SUMMARIZE = r'''import json,sys,csv
from pathlib import Path
folder=Path(sys.argv[1]);p=folder/'runs/config/jobs/job1/result.json'
status=json.loads(p.read_text())['status'] if p.exists() else 'PENDING'
(folder/'results.csv').write_text('job_id,status\njob1,'+status+'\n')
(folder/'summary.json').write_text(json.dumps({'statuses':{status:1}}))
'''

class AutoWorkflowTests(unittest.TestCase):
    def test_automatic_resume_export_reentry_and_push(self):
        with tempfile.TemporaryDirectory(prefix='aij auto ') as temporary:
            root = Path(temporary)
            for folder in ['jobs', 'analysis', 'bin', 'benchmarks/manifests']:
                (root/folder).mkdir(parents=True)
            for name in ['jobs/run_cluster_all.sh', 'jobs/check_auto_state.py', 'analysis/export_results.py']:
                shutil.copy2(ROOT/name, root/name)
            (root/'jobs/goSolver.py').write_text("import json\nfrom pathlib import Path\nROOT=Path(__file__).parent\ndef git_identity(path):return {'commit':'fixed'}\ndef load_config(path):return json.loads(Path(path).read_text())\n")
            (root/'benchmarks/manifests/mipo_list.txt').write_text('a.json\nb.json\n')
            (root/'jobs/fake_pipeline.py').write_text(PIPELINE)
            (root/'jobs/run_cluster_pipeline.sh').write_text('#!/usr/bin/env bash\nexec "$AIJ_PYTHON" "$(dirname "$0")/fake_pipeline.py" "$@"\n')
            (root/'analysis/summarize_campaign.py').write_text(SUMMARIZE)
            (root/'jobs/push_results.sh').write_text('#!/usr/bin/env bash\nif [[ "$1" == export ]]; then\n "$AIJ_PYTHON" "$(dirname "$0")/../analysis/export_results.py" --campaign "results/$2" --output "deliveries/$2"\nelse\n echo "$2" >> pushes\nfi\n')
            for name, text in {
                'sbatch':'#!/usr/bin/env bash\nexit 0\n',
                'squeue':'#!/usr/bin/env bash\nexit 0\n',
                # Array accounting exposes child rows, not an array parent row.
                'sacct':'#!/usr/bin/env bash\nif [[ "$*" == *201* ]]; then echo "201_0|COMPLETED|0:0"; else echo "${4}|COMPLETED|0:0"; fi\n',
            }.items():
                p=root/'bin'/name;p.write_text(text);p.chmod(0o755)
            env=dict(os.environ, AIJ_PYTHON=sys.executable, AIJ_CONFIG=str(root/'jobs/config.cluster.json'), PATH=str(root/'bin')+':'+os.environ['PATH'])
            command=['bash',str(root/'jobs/run_cluster_all.sh'),'--push']
            first=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            actions=(root/'actions').read_text()
            self.assertEqual(actions.count('smoke\n'),1)
            self.assertIn('resume aij-main',actions)
            self.assertIn('TIMEOUT',(root/'deliveries/aij-main/results.csv').read_text())
            self.assertEqual((root/'pushes').read_text().splitlines(),['aij-main','aij-decomposition'])
            second=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(second.returncode,0,second.stdout+second.stderr)
            self.assertEqual((root/'actions').read_text(),actions)
            # Queue failures must not become permission to submit another batch.
            (root/'bin/squeue').write_text('#!/usr/bin/env bash\nexit 1\n')
            third=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(third.returncode,0)
            self.assertEqual((root/'actions').read_text(),actions)
            # Failed smoke must stop before another formal submission.
            (root/'bin/squeue').write_text('#!/usr/bin/env bash\nexit 0\n')
            shutil.rmtree(root/'deliveries')
            shutil.rmtree(root/'results')
            failed=subprocess.run(command,cwd=root,env=dict(env,FAIL_SMOKE='1'),capture_output=True,text=True,timeout=20)
            self.assertNotEqual(failed.returncode,0)
            new_actions=(root/'actions').read_text()[len(actions):]
            self.assertIn('smoke\n',new_actions)
            self.assertNotIn('submit',new_actions)
            self.assertNotIn('prepare',new_actions)

if __name__ == '__main__':
    unittest.main()
