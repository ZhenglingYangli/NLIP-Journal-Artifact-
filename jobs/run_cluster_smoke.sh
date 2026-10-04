#!/usr/bin/env bash
#SBATCH --job-name=aij-smoke
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:45:00
#SBATCH --hint=nomultithread
#SBATCH --output=aij-smoke-%j.log
set -euo pipefail
export AIJ_RUNNER_DIR="${AIJ_RUNNER_DIR:-/scratch/scherif/NLIP/NLIP-AIJ/jobs}"
export AIJ_PYTHON="${AIJ_PYTHON:-$AIJ_RUNNER_DIR/.venv/bin/python}"
cd "$AIJ_RUNNER_DIR"
"$AIJ_PYTHON" -c 'from goSolver import check_cplex_license; import sys; check_cplex_license(sys.executable)'
out="../results/cluster-smoke-${SLURM_JOB_ID}"
"$AIJ_PYTHON" goSolver.py --config "${AIJ_CONFIG:-config.cluster.json}" --profile smoke --workers 1 --execute --output "$out" &
pid=$!
trap 'kill -TERM "$pid" 2>/dev/null || true; wait "$pid" || true; exit 1' TERM INT
wait "$pid"
"$AIJ_PYTHON" - "$out" <<'PY'
import json, sys
from pathlib import Path
folder = Path(sys.argv[1])
plan = json.loads((folder/'run.json').read_text())['plan']
failures = []
for job in plan['jobs']:
    path = folder/'jobs'/job['id']/'result.json'
    if not path.exists():
        failures.append((job['id'], 'MISSING'))
        continue
    result = json.loads(path.read_text())
    expected = job['smoke_expected']
    if not result.get('verified') or any(result.get(key) != value for key, value in expected.items()):
        failures.append((job['id'], result.get('status')))
print(json.dumps({'planned': len(plan['jobs']), 'failures': failures}, indent=2))
if failures or len(plan['jobs']) != 61:
    raise SystemExit('Cluster smoke did not pass; inspect results before formal submission.')
PY
