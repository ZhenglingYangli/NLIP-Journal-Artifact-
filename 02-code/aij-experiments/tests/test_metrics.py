import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metrics import problem_features, quality
from supervisor import supervise
from result_table import row_for


class Metrics(unittest.TestCase):
    def test_original_scale_bounds_and_gap(self):
        q=quality({'objective_scale':10,'objective_divisor':2,'objective_constant':-30},20,10,.5,7)
        self.assertEqual(q['primal_bound_original'],1)
        self.assertEqual(q['dual_bound_original'],-1)
        self.assertEqual(q['absolute_gap_original'],2)
        self.assertEqual(q['normalized_gap_original'],2)
        self.assertEqual(q['search_nodes'],7)
        self.assertIsNone(quality({},None,float('inf'))['normalized_gap_original'])

    def test_model_features(self):
        p={'variables':{'x':{'lb':0,'ub':1},'y':{'lb':-2,'ub':2}},
           'objective':{'sense':'min','terms':[{'c':'1/2','vars':{'y':4}}]},
           'constraints':[{'terms':[{'c':1,'vars':{'x':1,'y':1}}]}]}
        f=problem_features(p)
        self.assertEqual((f['variables'],f['boolean_variables'],f['domain_size_max']),(2,1,5))
        self.assertEqual((f['objective_degree'],f['nonlinear_constraint_atoms']),(4,1))

    def test_timeout_and_oom_keep_completed_stage_metrics(self):
        for tail,limits,status in [('time.sleep(5)',{'solve_seconds':.3,'memory_gib':.2},'TIMEOUT'),
                                   ('blob=bytearray(100*1024*1024);time.sleep(5)',{'solve_seconds':3,'memory_gib':.06},'OOM')]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);child=folder/'child.py'
                child.write_text("import json,time\nprint('AIJ_PROGRESS '+json.dumps({'phase':'solve','at':time.monotonic(),'metrics':{'read_seconds':.02,'formula':{'variables':123,'hard':456},'top_weight':9}}),flush=True)\n"+tail)
                r=supervise([sys.executable,str(child)],folder,dict(limits,verify_seconds=1,poll_seconds=.01,outer_seconds=4))
                self.assertEqual(r['status'],status)
                self.assertEqual(r['termination_phase'],'solve')
                self.assertEqual(r['formula']['variables'],123)
                self.assertEqual(json.loads((folder/'progress.json').read_text())['metrics']['top_weight'],9)
                row=row_for({'id':'x','family':'qplib','method':{'id':'bin-rc2','solver':'RC2','encoding':'BIN'}},r)
                self.assertEqual(row['num_variables'],123)
                self.assertEqual(row['read_seconds'],.02)


if __name__=='__main__': unittest.main()
