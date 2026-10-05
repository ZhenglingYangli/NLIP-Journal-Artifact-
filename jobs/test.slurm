#!/bin/bash
#SBATCH --job-name=nlip-test
#SBATCH --partition=bigmem-amd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread
#SBATCH --mem=2G
#SBATCH --time=00:05:00
#SBATCH --output=nlip-test-%j.log

cd "$SLURM_SUBMIT_DIR" || exit 1
echo "host=$(hostname) job=$SLURM_JOB_ID"
exec "$SLURM_SUBMIT_DIR/.venv/bin/python" -u jobs/goSolver.py test "$@"
