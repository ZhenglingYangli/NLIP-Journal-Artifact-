"""Targeted checks for missing-only setup and compact scientific result delivery."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

environment = load('environment', 'jobs/tools/check_environment.py')
delivery = load('delivery', 'analysis/export_results.py')

class EnvironmentTests(unittest.TestCase):
    def test_missing_and_site_api_are_distinct(self):
        def import_module(name):
            if name == 'cvc5':
                raise ModuleNotFoundError("No module named 'cvc5'", name='cvc5')
            return object()
        with patch.object(environment.metadata, 'version', side_effect=environment.metadata.PackageNotFoundError), \
             patch.object(environment.importlib, 'import_module', side_effect=import_module):
            missing, problems = environment.inspect([('cvc5', '1.3.4'), ('cplex', '22.1.2.1')])
        self.assertEqual(missing, ['cvc5==1.3.4'])
        self.assertEqual(len(problems), 1)
        self.assertIn('未自动替换', problems[0])

    def test_only_missing_package_is_installed(self):
        with patch.object(environment, 'inspect', side_effect=[(['cvc5==1.3.4'], []), ([], [])]), \
             patch.object(environment.subprocess, 'run') as run, \
             patch.object(sys, 'argv', ['check_environment.py', '--install-missing']):
            self.assertEqual(environment.main(), 0)
        self.assertEqual(run.call_args_list[0].args[0], [sys.executable, '-m', 'pip', 'install', 'cvc5==1.3.4'])

    def test_available_environment_is_not_reinstalled(self):
        with patch.object(environment, 'inspect', return_value=([], [])), \
             patch.object(environment.subprocess, 'run') as run, \
             patch.object(sys, 'argv', ['check_environment.py', '--install-missing']):
            self.assertEqual(environment.main(), 0)
        self.assertEqual(run.call_args.args[0], [sys.executable, '-m', 'pip', 'check'])

class DeliveryTests(unittest.TestCase):
    def test_preserves_failed_results_and_witnesses_without_raw_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'results/aij-main'
            target = Path(temporary) / 'deliveries/aij-main'
            job = source / 'runs/mipo-bin-rc2/jobs/job1'
            job.mkdir(parents=True)
            (source / 'sumup').mkdir()
            (source / 'analysis').mkdir()
            plan = {'profile': 'formal', 'matrix': 'main', 'tasks': [{'key': 'mipo-bin-rc2', 'job_ids': ['job1']}]}
            (source / 'campaign.json').write_text(json.dumps(plan))
            (source / 'summary.json').write_text(json.dumps({'statuses': {'TIMEOUT': 1}}))
            with (source / 'results.csv').open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['job_id', 'status'])
                writer.writeheader(); writer.writerow({'job_id': 'job1', 'status': 'TIMEOUT'})
            (job.parent.parent / 'run.json').write_text(json.dumps({'plan': {'python': '/project/python', 'jobs': ['job1']}}))
            (job / 'result.json').write_text(json.dumps({'status': 'TIMEOUT', 'witness': {'x': 2}}))
            (job / 'stdout.log').write_text('raw output')
            (job / 'encoding.wcnf').write_text('encoding')
            (source / 'sumup/config.csv').write_text('status\nTIMEOUT\n')
            (source / 'analysis/report.md').write_text('report')
            delivery.export(source, target)
            self.assertIn('TIMEOUT', (target / 'results.csv').read_text())
            self.assertFalse((target / 'runs').exists())
            self.assertNotIn('jobs', json.loads((target / 'environment.json').read_text())['mipo-bin-rc2']['plan'])
            with tarfile.open(source / 'verification-records.tar.gz') as archive:
                result = json.load(archive.extractfile('runs/mipo-bin-rc2/jobs/job1/result.json'))
                self.assertEqual(result['witness'], {'x': 2})
                self.assertFalse(any(name.endswith(('.log', '.wcnf')) for name in archive.getnames()))
            with self.assertRaisesRegex(ValueError, '已存在'):
                delivery.export(source, target)
            (source / 'summary.json').write_text(json.dumps({'statuses': {'PENDING': 1}}))
            (source / 'results.csv').write_text('job_id,status\njob1,PENDING\n')
            with self.assertRaisesRegex(ValueError, 'PENDING'):
                delivery.export(source, target.with_name('pending'))

if __name__ == '__main__':
    unittest.main()
