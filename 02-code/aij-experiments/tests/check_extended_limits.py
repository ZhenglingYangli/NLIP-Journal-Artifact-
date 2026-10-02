"""Ensure every new dispatch route obeys the shared end-to-end deadline."""
from pathlib import Path
import argparse
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_batch import available_cpus, methods, load_config
from supervisor import supervise

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
args = parser.parse_args()
config = load_config(args.config)
routes = [(m, 'diverse') for m in methods('optimization', 'baselines', 'diverse')
          if m.get('encoding') in ('DW', 'IW') or m['solver'] == 'CVC5']
routes.append(({'id': 'cvc5-decision', 'solver': 'CVC5'}, 'smt'))
rows = []
for method, family in routes:
    with tempfile.TemporaryDirectory(prefix='aij-extended-deadline-') as folder:
        path = Path(folder)
        desc = config['families'][family]
        job = {'cpu': available_cpus()[0], 'code_root': str((ROOT/'../nlipsat-aij').resolve()),
               'method': method, 'family': family, 'task': desc['task'], 'k': desc.get('k'),
               'input': str(ROOT/'smoke'/desc['smoke_file']), 'solver_paths': config['solver_paths'],
               'solve_seconds': .02}
        (path/'job.json').write_text(json.dumps(job))
        result = supervise([config['python'], '-u', str(ROOT/'worker.py'), str(path/'job.json')], path,
                           {'solve_seconds': .02, 'verify_seconds': 5, 'memory_gib': 1, 'poll_seconds': .005})
        assert result['status'] == 'TIMEOUT', (method, result)
        rows.append({'method': method['id'], 'status': result['status'], 'wall_seconds': result['wall_seconds']})
output = args.output
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
