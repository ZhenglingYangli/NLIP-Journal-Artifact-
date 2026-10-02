#!/usr/bin/env bash
#SBATCH --job-name=aij-config
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --hint=nomultithread
#SBATCH --signal=B:TERM@60
set -euo pipefail
: "${AIJ_PYTHON:?Set AIJ_PYTHON}"
: "${AIJ_RUNNER_DIR:?Set AIJ_RUNNER_DIR}"
: "${AIJ_CAMPAIGN:?Set AIJ_CAMPAIGN}"
: "${SLURM_ARRAY_TASK_ID:?Submit the generated array script}"
cd "$AIJ_RUNNER_DIR"
"$AIJ_PYTHON" run_campaign_task.py --campaign "$AIJ_CAMPAIGN" --index "$SLURM_ARRAY_TASK_ID" &
batch_pid=$!
trap 'kill -TERM "$batch_pid" 2>/dev/null || true; wait "$batch_pid" || true; exit 143' TERM INT
wait "$batch_pid"
