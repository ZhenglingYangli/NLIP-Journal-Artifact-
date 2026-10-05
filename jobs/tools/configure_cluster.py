"""Resolve known cluster paths and check all selected inputs before submission."""
import json
import os
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from goSolver import ROOT, load_config, make_jobs


def select(label, candidates, executable=False):
    for value in candidates:
        if value and (os.access(value, os.X_OK) and Path(value).is_file() if executable else Path(value).is_dir()):
            return str(Path(value).resolve())
    raise SystemExit(label + ' not found; checked: ' + ', '.join(str(p) for p in candidates if p))


def main():
    config = json.loads((ROOT / 'config.json').read_text())
    legacy = os.environ.get('NLIP_LEGACY_ROOT', '/scratch/scherif/NLIP/NLIP')
    config['benchmark_root'] = select('NLIP_BENCHMARK_ROOT', [os.environ.get('NLIP_BENCHMARK_ROOT'), legacy + '/benchmarks'])
    shared = '/users/scherif/ComputeSpace/solvers/'
    for key, name in [('MAXHS', 'maxhs'), ('WMAXCDCL', 'wmaxcdcl'), ('OPENWBO', 'openwbo')]:
        config['solver_paths'][key] = select('NLIP_' + key, [os.environ.get('NLIP_' + key),
            legacy + '/solvers/maxsat/' + name, shared + ('wmaxcdcl_24' if key == 'WMAXCDCL' else name)], True)
    if os.environ.get('NLIP_DIVERSE_ROOT'):
        config['families']['diverse']['input_root'] = os.environ['NLIP_DIVERSE_ROOT']
    if os.environ.get('NLIP_MIPO_ROOT'):
        config['families']['mipo']['input_root'] = os.environ['NLIP_MIPO_ROOT']
    # Only the resolved site config is local; committed source stays clean.
    destination = ROOT / 'config.cluster.json'
    destination.write_text(json.dumps(config, indent=2) + '\n')
    resolved = load_config(destination)
    jobs = make_jobs(resolved, 'formal', 'main', list(resolved['families']))
    print(json.dumps({'config': str(destination), 'benchmark_root': resolved['benchmark_root'],
        'solver_paths': resolved['solver_paths'], 'mipo_root': resolved['families']['mipo']['input_root'],
        'runs': len(jobs), 'by_family': dict(Counter(j['family'] for j in jobs))}, indent=2))


if __name__ == '__main__':
    main()
