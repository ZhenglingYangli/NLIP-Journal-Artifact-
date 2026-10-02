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
# Set AIJ_RUNNER_DIR if submitting outside this directory.
cd "${AIJ_RUNNER_DIR:-${SLURM_SUBMIT_DIR:-$(dirname "$0")}}"
: "${AIJ_PYTHON:?Set AIJ_PYTHON to the configured experiment Python}"
: "${AIJ_OUTPUT:?Set AIJ_OUTPUT to a persistent result directory}"
# The allocation is a chunk, not the whole worst-case matrix. Resume on the same
# hardware/configuration; completed TIMEOUT/OOM results are retained.
"$AIJ_PYTHON" goSolver.py --config "${AIJ_CONFIG:-config.json}" \
  --matrix "${AIJ_MATRIX:-main}" --profile formal --workers "${SLURM_CPUS_PER_TASK:-7}" --execute \
  --output "$AIJ_OUTPUT" ${AIJ_RESUME:+--resume} &
batch_pid=$!
trap 'kill -TERM "$batch_pid" 2>/dev/null || true; wait "$batch_pid" || true; exit 143' TERM INT
wait "$batch_pid"
