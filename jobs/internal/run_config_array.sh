#!/usr/bin/env bash
#SBATCH --job-name=aij-config
#SBATCH --partition=bigmem-amd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --exclusive
#SBATCH --hint=nomultithread
#SBATCH --signal=B:TERM@60
set -euo pipefail
export AIJ_RUNNER_DIR="${AIJ_RUNNER_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
export AIJ_PYTHON="${AIJ_PYTHON:-$(command -v python3)}"
: "${AIJ_CAMPAIGN:?Set AIJ_CAMPAIGN}"
: "${SLURM_ARRAY_TASK_ID:?Submit the generated array script}"
cd "$AIJ_RUNNER_DIR"
echo "host=$(hostname) job=$SLURM_JOB_ID configuration=$SLURM_ARRAY_TASK_ID"
exec "$AIJ_PYTHON" internal/run_campaign_task.py --campaign "$AIJ_CAMPAIGN" --index "$SLURM_ARRAY_TASK_ID"
