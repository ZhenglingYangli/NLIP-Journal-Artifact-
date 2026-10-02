"""Success, missing-run and budget semantics of the published analysis tables."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_campaign import analyze, success


class Analysis(unittest.TestCase):
    def test_success_requires_budget_and_verified_witness(self):
        row = {'family':'qplib','status':'OPTIMAL','verified':True,'solve_wall_seconds':2}
        self.assertTrue(success(row, 3600))
        for changes in [{'verified':False}, {'status':'FEASIBLE'}, {'solve_wall_seconds':3601}, {'solve_wall_seconds':''}]:
            self.assertFalse(success({**row, **changes}, 3600))
        self.assertTrue(success({**row,'family':'smt','status':'UNSAT','verified':False},3600))
        self.assertFalse(success({**row,'family':'smt','status':'SAT','verified':False},3600))

    def test_pending_and_unsuccessful_results_remain_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            methods=[{'id':'bin-rc2','solver':'RC2','encoding':'BIN'}, {'id':'scip-native','solver':'SCIP-NATIVE'}]
            tasks=[{'key':'qplib-'+m['id'],'family':'qplib','method':m,
                    'job_ids':[f'qplib-{i:04d}-{m["id"]}' for i in range(1,4)]} for m in methods]
            (root/'campaign.json').write_text(json.dumps({'profile':'formal','matrix':'main','limits':{'solve_seconds':3600},'tasks':tasks}))
            for task, records in zip(tasks, [[('OPTIMAL',True,2),('TIMEOUT',False,3600)], [('OPTIMAL',True,3),('UNSUPPORTED',False,1),('FEASIBLE',True,3600)]]):
                for job_id,(status,verified,elapsed) in zip(task['job_ids'],records):
                    path=root/'runs'/task['key']/'jobs'/job_id
                    path.mkdir(parents=True)
                    (path/'result.json').write_text(json.dumps({'job_id':job_id,'method':task['method'],'status':status,
                        'verified':verified,'solve_wall_seconds':elapsed,'solve_budget_seconds':3600,'termination':'TIMEOUT' if status=='TIMEOUT' else '',
                        'formula':{'variables':7,'hard':8,'soft':9}}))
            summary=analyze(root,plots=False)
            rows={r['method']:r for r in summary}
            self.assertEqual(rows['bin-rc2']['pending'],1)
            self.assertEqual(rows['bin-rc2']['solved'],1)
            self.assertEqual(rows['bin-rc2']['par2_seconds'],'')
            self.assertEqual(rows['scip-native']['par2_seconds'],4801)
            self.assertEqual(rows['scip-native']['verified_feasible'],1)
            with (root/'results.csv').open() as f:
                raw=list(csv.DictReader(f))
            self.assertEqual(len(raw),6)
            self.assertEqual(raw[0]['num_variables'],'7')
            self.assertEqual(raw[1]['termination'],'TIMEOUT')
            with (root/'analysis/pairwise.csv').open() as f:
                pair=next(csv.DictReader(f))
            self.assertEqual(pair['completed_common'],'2')
            self.assertEqual(pair['a_faster_on_both'],'1')


if __name__=='__main__': unittest.main()
