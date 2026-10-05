#!/usr/bin/env bash
#SBATCH --job-name=aij-analysis
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
set -euo pipefail
export AIJ_RUNNER_DIR="${AIJ_RUNNER_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../jobs" && pwd)}"
export AIJ_PYTHON="${AIJ_PYTHON:-$(command -v python3)}"
: "${AIJ_CAMPAIGN:?Set AIJ_CAMPAIGN}"
cd "$AIJ_RUNNER_DIR/../analysis"
export MPLBACKEND=Agg
"$AIJ_PYTHON" analyze_campaign.py "$AIJ_CAMPAIGN"
