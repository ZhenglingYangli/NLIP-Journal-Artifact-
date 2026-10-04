#!/usr/bin/env bash
#SBATCH --job-name=aij-main
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --partition=normal
#SBATCH --exclusive
#SBATCH --cpus-per-task=7
#SBATCH --hint=nomultithread
#SBATCH --mem=120G
#SBATCH --time=10-01:00:00
#SBATCH --output=aij-%j.log
#SBATCH --signal=B:TERM@60
set -euo pipefail
# Single-batch compatibility entry. The default multi-job workflow is
# generate_scripts.py -> generated submit.sh -> run_config_array.sh.
# AIJ_RUNNER_DIR can override the agreed MatriCS installation directory.
export AIJ_RUNNER_DIR="${AIJ_RUNNER_DIR:-/scratch/scherif/NLIP/NLIP-AIJ/jobs}"
export AIJ_PYTHON="${AIJ_PYTHON:-$AIJ_RUNNER_DIR/.venv/bin/python}"
cd "$AIJ_RUNNER_DIR"
: "${AIJ_OUTPUT:?Set AIJ_OUTPUT to a persistent result directory}"
# The allocation is a chunk, not the whole worst-case matrix. Resume on the same
# hardware/configuration; completed TIMEOUT/OOM results are retained.
"$AIJ_PYTHON" goSolver.py --config "${AIJ_CONFIG:-config.cluster.json}" \
  --matrix "${AIJ_MATRIX:-main}" --profile formal --workers "${SLURM_CPUS_PER_TASK:-7}" --execute \
  --output "$AIJ_OUTPUT" ${AIJ_RESUME:+--resume} &
batch_pid=$!
trap 'kill -TERM "$batch_pid" 2>/dev/null || true; wait "$batch_pid" || true; exit 143' TERM INT
wait "$batch_pid"
