#!/usr/bin/env bash
# Collaborator entry point. Solver code stays in codes; analysis stays in analysis.
set -euo pipefail
JOBS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$JOBS_DIR/.." && pwd)"
export NLIP_LEGACY_ROOT="${NLIP_LEGACY_ROOT:-/scratch/scherif/NLIP/NLIP}"
export AIJ_RUNNER_DIR="$JOBS_DIR"
export AIJ_PYTHON="${AIJ_PYTHON:-$JOBS_DIR/.venv/bin/python}"
export AIJ_CONFIG="${AIJ_CONFIG:-$JOBS_DIR/config.cluster.json}"
action="${1:-help}"
if (($#)); then shift; fi

help_text() {
  cat <<'HELP'
用法：bash jobs/run_cluster_pipeline.sh <操作> [参数]
  setup                     检查选定环境，只补装缺少的依赖（无环境则创建）
  env-check                 只检查 Python 依赖，不安装
  data [--archive 文件]      下载或读取 MIPO 原包，转换固定 870 个实例
  configure                 按 NLIP_* 环境变量定位集群数据和外部求解器
  check                     检查依赖、正式输入、外部程序与 Slurm 命令
  smoke                     提交计算节点环境/许可证/61 配置小实例测试
  smoke-status              查看最近一次小实例测试状态和日志
  prepare [批次名]          准备主实验，默认批次 aij-main（不提交）
  prepare-decomposition [名] 准备已确定的分解对照，默认 aij-decomposition
  submit [批次名]           提交已准备的批次，同时安排后续分析
  resume [批次名]           重交已停止批次，跳过已有结果；运行中拒绝重复提交
  status [批次名]           查看队列与已有结果计数
  analyze [批次名]          提交独立汇总/画图作业

顺序：setup → data → configure → check → smoke → smoke-status
小实例全部通过后：prepare → submit → status；结束后自动分析。
默认 normal / 每作业 7 路 / 120G / 同时 3 作业。未指定操作只显示帮助。
AIJ_PYTHON 可指定已有环境；AIJ_CONFIG 可指定已有配置。
结果默认位于仓库 results/；批次参数也可直接使用绝对路径。
MatriCS 新项目目录：/scratch/scherif/NLIP/NLIP-AIJ
旧数据和求解器根目录：/scratch/scherif/NLIP/NLIP
HELP
  printf '当前代码目录：%s\n当前结果目录：%s/results\n' "$PROJECT_DIR" "$PROJECT_DIR"
}
python_ready() {
  [[ -x "$AIJ_PYTHON" ]] || { echo "Python 不可用：$AIJ_PYTHON；先运行 setup 或设置 AIJ_PYTHON。" >&2; exit 1; }
}
config_ready() {
  python_ready
  [[ -f "$AIJ_CONFIG" ]] || { echo "缺少配置：$AIJ_CONFIG；先运行 configure。" >&2; exit 1; }
}
need_slurm() {
  command -v "$1" >/dev/null || { echo "找不到 $1；请在集群登录环境执行。" >&2; exit 1; }
}
campaign_path() {
  local name="${1:-aij-main}"
  if [[ "$name" = /* ]]; then printf '%s\n' "$name"; else printf '%s/results/%s\n' "$PROJECT_DIR" "$name"; fi
}
cd "$JOBS_DIR"
case "$action" in
  help|-h|--help) help_text ;;
  setup)
    if [[ ! -x "$AIJ_PYTHON" ]]; then
      [[ "$AIJ_PYTHON" == "$JOBS_DIR/.venv/bin/python" ]] || { echo "指定的 AIJ_PYTHON 不存在。" >&2; exit 1; }
      "${PYTHON:-python3.9}" -m venv "$JOBS_DIR/.venv"
    fi
    "$AIJ_PYTHON" "$JOBS_DIR/check_environment.py" --install-missing
    echo "环境已检查并补齐缺少的依赖。CPLEX 完整许可证将在计算节点 smoke 中检查。"
    ;;
  env-check) python_ready; "$AIJ_PYTHON" "$JOBS_DIR/check_environment.py" ;;
  data) python_ready; "$AIJ_PYTHON" "$JOBS_DIR/prepare_mipo.py" "$@" ;;
  configure) python_ready; "$AIJ_PYTHON" "$JOBS_DIR/configure_cluster.py" ;;
  check)
    config_ready
    "$AIJ_PYTHON" - "$AIJ_CONFIG" <<'PY'
import importlib.metadata as metadata
import json, os, sys
from pathlib import Path
from goSolver import load_config, make_jobs
import psutil, pysat, pypblib, z3, pyscipopt, highspy, cvc5, cplex, matplotlib
config=load_config(sys.argv[1])
jobs=make_jobs(config,'formal','main',list(config['families']))
for name,path in config['solver_paths'].items():
    if not Path(path).is_file() or not os.access(path,os.X_OK):
        raise SystemExit(f'{name} 不可执行：{path}')
print(json.dumps({'python':sys.executable,'configuration':sys.argv[1],
  'runs':len(jobs),'instances':len({(j['family'],j['input']) for j in jobs}),
  'versions':{p:metadata.version(p) for p in ['python-sat','pypblib','z3-solver','psutil','pyscipopt','highspy','cvc5','cplex','matplotlib']}},indent=2))
PY
    for cmd in sbatch squeue sacct; do need_slurm "$cmd"; done
    echo "登录节点检查通过；求解、完整许可证和动态库仍由 smoke 在计算节点测试。"
    ;;
  smoke)
    config_ready; need_slurm sbatch
    mkdir -p "$PROJECT_DIR/results"
    id=$(sbatch --parsable --chdir="$JOBS_DIR" --export=ALL --output="$PROJECT_DIR/results/cluster-smoke-%j.log" "$JOBS_DIR/run_cluster_smoke.sh")
    id="${id%%;*}"
    printf '%s\n' "$id" > "$PROJECT_DIR/results/cluster-smoke-last-job.txt"
    echo "小实例测试作业：$id；用 smoke-status 查看结果。"
    ;;
  smoke-status)
    need_slurm sacct
    id=$(cat "$PROJECT_DIR/results/cluster-smoke-last-job.txt")
    sacct -j "$id" --format=JobID,State,ExitCode,Elapsed,MaxRSS
    log="$PROJECT_DIR/results/cluster-smoke-$id.log"
    if [[ -f "$log" ]]; then tail -n 35 "$log"; else echo "日志尚未生成：$log"; fi
    echo "通过标准：作业 COMPLETED、ExitCode 0:0，且最后 planned=61、failures=[]。"
    ;;
  prepare|prepare-decomposition)
    config_ready
    matrix=main; default_name=aij-main
    if [[ "$action" == prepare-decomposition ]]; then matrix=decomposition; default_name=aij-decomposition; fi
    campaign=$(campaign_path "${1:-$default_name}")
    "$AIJ_PYTHON" "$JOBS_DIR/generate_scripts.py" --config "$AIJ_CONFIG" --matrix "$matrix" --partition normal --workers 7 --memory-gib 120 --concurrent-jobs 3 --output "$campaign"
    ;;
  submit|resume)
    python_ready; need_slurm sbatch; need_slurm squeue
    campaign=$(campaign_path "${1:-aij-main}")
    [[ -f "$campaign/submit.sh" ]] || { echo "没有提交脚本；请先 prepare：$campaign" >&2; exit 1; }
    if [[ -f "$campaign/array_job_id.txt" ]]; then
      id=$(cat "$campaign/array_job_id.txt")
      running=$(squeue --noheader --user="$(id -un)" --format='%i %T' | awk -v id="$id" '$1 == id || index($1, id "_") == 1')
      [[ -z "$running" ]] || { echo "该批次仍在队列中，未重复提交：$running" >&2; exit 1; }
    fi
    bash "$campaign/submit.sh" | tee -a "$campaign/submissions.log"
    ;;
  status)
    python_ready; need_slurm squeue
    campaign=$(campaign_path "${1:-aij-main}")
    squeue -u "$(id -un)" --format='%.18i %.10P %.24j %.10T %.12M %.6D %R'
    if [[ -f "$campaign/campaign.json" ]]; then
      "$AIJ_PYTHON" "$PROJECT_DIR/analysis/summarize_campaign.py" "$campaign"
      echo "本批结果：$campaign"
    fi
    ;;
  analyze)
    python_ready; need_slurm sbatch
    export AIJ_CAMPAIGN
    AIJ_CAMPAIGN=$(campaign_path "${1:-aij-main}")
    [[ -f "$AIJ_CAMPAIGN/campaign.json" ]] || { echo "找不到实验计划：$AIJ_CAMPAIGN" >&2; exit 1; }
    sbatch --chdir="$JOBS_DIR" --export=ALL --output="$AIJ_CAMPAIGN/analysis-%j.log" "$PROJECT_DIR/analysis/run_campaign_analysis.sh"
    ;;
  *) help_text; exit 2 ;;
esac
