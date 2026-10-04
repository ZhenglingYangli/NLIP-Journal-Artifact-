"""Test first clone, an older checkout update, and frozen-plan preservation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class BootstrapTests(unittest.TestCase):
    def test_clone_update_and_freeze(self):
        with tempfile.TemporaryDirectory(prefix='aij bootstrap ') as tmp:
            root=Path(tmp);author=root/'author';author.mkdir();(author/'jobs').mkdir()
            def git(folder,*args):
                return subprocess.run(['git','-C',str(folder),*args],check=True,capture_output=True,text=True)
            git(author,'init','-b','main');git(author,'config','user.name','test');git(author,'config','user.email','test@example.invalid')
            (author/'jobs/run_cluster_all.sh').write_text('#!/usr/bin/env bash\ncat "$(dirname "$0")/../version.txt"\nprintf "%s\\n" "$@"\n')
            (author/'version.txt').write_text('version one\n');git(author,'add','.');git(author,'commit','-m','one')
            origin=root/'origin.git';subprocess.run(['git','init','--bare',str(origin)],check=True,capture_output=True)
            git(author,'remote','add','origin',str(origin));git(author,'push','origin','main')
            fake=root/'bin';fake.mkdir();queue=fake/'squeue';queue.write_text('#!/usr/bin/env bash\nexit 0\n');queue.chmod(0o755)
            checkout=root/'cluster checkout'
            env=dict(os.environ,NLIP_WORKDIR=str(checkout),AIJ_REPO_URL=str(origin),PATH=str(fake)+':'+os.environ['PATH'])
            command=['bash',str(ROOT/'jobs/start_cluster.sh'),'--push']
            def run():return subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            first=run();self.assertEqual(first.returncode,0,first.stderr);self.assertIn('version one',first.stdout);self.assertIn('--push',first.stdout)
            (author/'version.txt').write_text('version two\n');git(author,'commit','-am','two');git(author,'push','origin','main')
            second=run();self.assertEqual(second.returncode,0,second.stderr);self.assertIn('version two',second.stdout)
            frozen=checkout/'results/batch/campaign.json';frozen.parent.mkdir(parents=True);frozen.write_text('{}')
            (author/'version.txt').write_text('version three\n');git(author,'commit','-am','three');git(author,'push','origin','main')
            third=run();self.assertEqual(third.returncode,0,third.stderr);self.assertIn('version two',third.stdout)
            frozen.unlink();(checkout/'version.txt').write_text('local modification\n')
            dirty=run();self.assertNotEqual(dirty.returncode,0);self.assertEqual((checkout/'version.txt').read_text(),'local modification\n')

if __name__=='__main__':
    unittest.main()
