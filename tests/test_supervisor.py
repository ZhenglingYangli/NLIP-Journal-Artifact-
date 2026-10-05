from pathlib import Path
import sys
_PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(_PROJECT/'jobs'),str(_PROJECT/'analysis'),str(_PROJECT/'codes'),str(_PROJECT/'codes/codes')]
import json
from pathlib import Path
import sys
import tempfile
import unittest
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from internal.supervisor import supervise


class Supervision(unittest.TestCase):
    def run_child(self, source, **limits):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        script = folder / 'child.py'
        script.write_text('import time,json,subprocess,sys,os\n' + source)
        settings = dict(solve_seconds=1, verify_seconds=1, memory_gib=.25, poll_seconds=.01)
        settings.update(limits)
        return supervise([sys.executable, str(script)], folder, settings), folder

    def test_completed_result(self):
        result, _ = self.run_child("print('AIJ_RESULT '+json.dumps({'status':'UNSAT','verified':False}),flush=True)")
        self.assertEqual(result['status'], 'UNSAT')

    def test_timeout_kills_descendants(self):
        result, folder = self.run_child("p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\nopen('pid','w').write(str(p.pid))\ntime.sleep(30)", solve_seconds=.25)
        self.assertEqual(result['status'], 'TIMEOUT')
        pid = int((folder / 'pid').read_text())
        try:
            status = psutil.Process(pid).status()
        except psutil.NoSuchProcess:
            return
        self.assertEqual(status, psutil.STATUS_ZOMBIE)

    def test_verification_has_separate_budget(self):
        source = "print('AIJ_PHASE '+json.dumps({'phase':'verify','at':time.monotonic()}),flush=True)\ntime.sleep(.4)\nprint('AIJ_RESULT '+json.dumps({'status':'OPTIMAL','verified':True}),flush=True)"
        result, _ = self.run_child(source, solve_seconds=.25, verify_seconds=1)
        self.assertEqual(result['status'], 'OPTIMAL')
        self.assertGreater(result['verify_wall_seconds'], .35)

    def test_verification_timeout_is_not_a_success(self):
        result, _ = self.run_child("print('AIJ_PHASE '+json.dumps({'phase':'verify','at':time.monotonic()}),flush=True)\ntime.sleep(30)", verify_seconds=.15)
        self.assertEqual(result['status'], 'INVALID')
        self.assertEqual(result['termination'], 'VERIFY_TIMEOUT')

    def test_tree_memory_limit(self):
        result, _ = self.run_child("data=bytearray(100*1024*1024)\ntime.sleep(30)", memory_gib=.06)
        self.assertEqual(result['status'], 'OOM')

    def test_outer_budget_does_not_extend_solving(self):
        result, _ = self.run_child("time.sleep(2)\nprint('AIJ_RESULT '+json.dumps({'status':'OPTIMAL','verified':True}),flush=True)", solve_seconds=.2, outer_seconds=1)
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertLess(result['wall_seconds'], .8)

    def test_outer_cap_also_covers_verification(self):
        result, _ = self.run_child("print('AIJ_PHASE '+json.dumps({'phase':'verify','at':time.monotonic()}),flush=True)\ntime.sleep(2)", solve_seconds=1, verify_seconds=2, outer_seconds=.3)
        self.assertEqual(result['status'], 'OUTER_TIMEOUT')


if __name__ == '__main__':
    unittest.main(verbosity=2)
