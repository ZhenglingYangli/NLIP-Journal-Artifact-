"""Configuration splitting must cover the frozen matrix exactly once."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from prepare_campaign import configuration_tasks
from run_batch import load_config, make_jobs, resume_compatible
from summarize_campaign import summarize

class Campaign(unittest.TestCase):
    def test_resume_on_equivalent_node(self):
        first={'host':'node1','cpus':[0,1],'cpu_model':['same CPU'],'platform':'Linux',
               'workers':2,'versions':{'solver':'1'},'jobs':['a','b']}
        second={**first,'host':'node2','cpus':[4,5]}
        self.assertTrue(resume_compatible(first,second))
        self.assertFalse(resume_compatible(first,{**second,'cpu_model':['different CPU']}))
        self.assertFalse(resume_compatible(first,{**second,'workers':3}))
        self.assertFalse(resume_compatible(first,{**second,'jobs':['a','c']}))

    def test_partition_matches_full_matrix(self):
        c=load_config(os.environ.get('AIJ_TEST_CONFIG', ROOT/'config.json'))
        main=configuration_tasks(c,'formal','main')
        ids=[j for t in main for j in t['job_ids']]
        expected=make_jobs(c,'formal','main',list(c['families']))
        self.assertEqual(len(main),61)
        self.assertEqual(len(ids),23335)
        self.assertEqual(len(set(ids)),len(ids))
        self.assertEqual(set(ids),{j['id'] for j in expected})
        extra=configuration_tasks(c,'formal','decomposition')
        other={j for t in extra for j in t['job_ids']}
        self.assertEqual(len(extra),2)
        self.assertEqual(len(other),1020)
        self.assertFalse(other.intersection(ids))
        self.assertTrue(all(not t['method']['options']['use_lrn'] for t in main+extra if 'encoding' in t['method']))

    def test_summary_preserves_missing_results(self):
        c=load_config(os.environ.get('AIJ_TEST_CONFIG', ROOT/'config.json'))
        tasks=configuration_tasks(c,'smoke','main')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'campaign.json').write_text(json.dumps({'tasks':tasks}))
            task=tasks[0]; job_id=task['job_ids'][0]
            out=root/'runs'/task['key']/'jobs'/job_id
            out.mkdir(parents=True)
            (out/'result.json').write_text(json.dumps({'job_id':job_id,'method':task['method'],'status':'OPTIMAL','verified':True}))
            result=summarize(root)
            self.assertEqual(result['planned'],61)
            self.assertEqual(result['statuses'],{'OPTIMAL':1,'PENDING':60})

if __name__=='__main__': unittest.main(verbosity=2)
