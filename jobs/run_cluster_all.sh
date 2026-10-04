#!/usr/bin/env bash
# Resume the approved workflow using existing scripts and Slurm records.
set -euo pipefail
JOBS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$JOBS_DIR/.." && pwd)"
export AIJ_PYTHON="${AIJ_PYTHON:-$JOBS_DIR/.venv/bin/python}"
export AIJ_CONFIG="${AIJ_CONFIG:-$JOBS_DIR/config.cluster.json}"
push=false
main=aij-main
decomposition=aij-decomposition
for arg in "$@"; do
  case "$arg" in
    --push) push=true ;;
    --help|-h)
      echo '用法：bash jobs/run_cluster_all.sh [--push]'
      echo '自动补齐准备 → 小实例测试 → 主实验 → 分解对照 → 分析 → 导出。'
      echo '--push：全部结束后自动推送两个结果分支；默认只导出。'
      echo '可设置 AIJ_MAIN_BATCH、AIJ_DECOMPOSITION_BATCH、AIJ_MIPO_ARCHIVE。'
      echo '可中断并重开此入口，已提交的 Slurm 作业继续运行。'
      exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done
main="${AIJ_MAIN_BATCH:-$main}"
decomposition="${AIJ_DECOMPOSITION_BATCH:-$decomposition}"
for batch in "$main" "$decomposition"; do
  [[ "$batch" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]] || { echo '批次名只能包含字母、数字、点、下划线和短横线。' >&2; exit 1; }
done
[[ "$main" != "$decomposition" ]] || { echo '主实验和分解对照必须使用不同批次名。' >&2; exit 1; }
cd "$PROJECT_DIR"
for cmd in sbatch squeue sacct flock; do
  command -v "$cmd" >/dev/null || { echo "缺少 $cmd，请在集群登录环境运行。" >&2; exit 1; }
done
mkdir -p results
exec 9>results/.cluster-all.lock
flock -n 9 || { echo '这个项目已有总入口运行中，请查看它的日志。' >&2; exit 1; }
trap 'echo "流程停在第 $LINENO 行。查看上方错误，修复后重开同一入口；已提交的作业不会被取消。" >&2' ERR
pipeline() { bash "$JOBS_DIR/run_cluster_pipeline.sh" "$@"; }
active() {
  local queued
  queued=$(squeue --noheader --user="$(id -un)" --format='%i') || { echo '队列查询失败，停止自动操作。' >&2; exit 1; }
  awk -v id="$1" '$1 == id || index($1,id "_")==1 {found=1} END {exit !found}' <<< "$queued"
}
wait_job() {
  local job="$1" record state code
  echo "等待作业 $job；入口会每 30 秒查看一次，不重复提交。"
  while true; do
    if active "$job"; then sleep 30; continue; fi
    record=$(sacct -n -P -j "$job" --format=JobIDRaw,State,ExitCode | awk -F'|' -v id="$job" '
      $1==id || (index($1,id "_")==1 && index($1,".")==0) {
        found=1; if ($2!="COMPLETED" || $3!="0:0") {bad=$2 "|" $3}
      } END {if(found) print bad ? bad : "COMPLETED|0:0"}')
    if [[ -z "$record" ]]; then
      echo "作业 $job 暂无记账结果，请稍后重开入口核实；未重复提交。" >&2
      return 1
    fi
    IFS='|' read -r state code <<< "$record"
    state="${state%% *}"
    echo "作业 $job：$state，退出码 $code"
    [[ "$state" == COMPLETED && "$code" == 0:0 ]]
    return
  done
}
# Wait before changing dependencies or site configuration used by another batch.
for record in results/*/array_job_id.txt results/*/analysis_job_id.txt results/cluster-smoke-last-job.txt; do
  [[ -f "$record" ]] || continue
  job=$(cat "$record")
  if active "$job"; then wait_job "$job" || true; fi
done
# A retry after Git authentication failure must not rerun completed experiments.
if [[ -x "$AIJ_PYTHON" && -d "deliveries/$main" && -d "deliveries/$decomposition" ]]; then
  "$AIJ_PYTHON" "$JOBS_DIR/check_auto_state.py" delivery "$PROJECT_DIR/results/$main" "$PROJECT_DIR/deliveries/$main"
  "$AIJ_PYTHON" "$JOBS_DIR/check_auto_state.py" delivery "$PROJECT_DIR/results/$decomposition" "$PROJECT_DIR/deliveries/$decomposition"
  if $push; then
    bash "$JOBS_DIR/push_results.sh" push "$main"
    bash "$JOBS_DIR/push_results.sh" push "$decomposition"
  fi
  echo '两个批次已经完成且交付与当前结果一致，无需重新准备或求解。'
  exit 0
fi
if [[ -f "results/$main/array_job_id.txt" || -f "results/$decomposition/array_job_id.txt" ]]; then
  pipeline env-check
else
  pipeline setup
fi
if ! "$AIJ_PYTHON" - "$AIJ_CONFIG" "$JOBS_DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from goSolver import load_config
root=Path(sys.argv[2]).parent
config=load_config(sys.argv[1]) if Path(sys.argv[1]).exists() else None
data=Path(config['families']['mipo']['input_root']) if config else root/'benchmarks/mipo'
names=(root/'benchmarks/manifests/mipo_list.txt').read_text().splitlines()
missing=[name for name in names if not (data/name).is_file()]
print(f'MIPO：{len(names)-len(missing)}/{len(names)} 个文件就绪，目录 {data}')
sys.exit(bool(missing))
PY
then
  data_args=()
  if [[ -n "${AIJ_MIPO_ARCHIVE:-}" ]]; then data_args=(--archive "$AIJ_MIPO_ARCHIVE"); fi
  if [[ -f "$AIJ_CONFIG" ]]; then
    mipo_root=$(cd "$JOBS_DIR"; "$AIJ_PYTHON" -c 'import sys;from goSolver import load_config;print(load_config(sys.argv[1])["families"]["mipo"]["input_root"])' "$AIJ_CONFIG")
    data_args+=(--output "$mipo_root")
  fi
  pipeline data "${data_args[@]}"
fi
if [[ ! -f "$AIJ_CONFIG" ]]; then
  [[ "$AIJ_CONFIG" == "$JOBS_DIR/config.cluster.json" ]] || { echo '自定义配置不存在，请提供实际配置路径。' >&2; exit 1; }
  pipeline configure
fi
pipeline check
smoke_ok() {
  [[ -f results/cluster-smoke-last-job.txt ]] || return 1
  local job
  job=$(cat results/cluster-smoke-last-job.txt)
  "$AIJ_PYTHON" "$JOBS_DIR/check_auto_state.py" smoke "$PROJECT_DIR/results/cluster-smoke-$job" "$AIJ_CONFIG"
}
if ! smoke_ok; then
  pipeline smoke
  job=$(cat results/cluster-smoke-last-job.txt)
  if ! wait_job "$job"; then pipeline smoke-status; exit 1; fi
  smoke_ok || { pipeline smoke-status; exit 1; }
fi
run_batch() {
  local batch="$1" matrix="$2" folder="$PROJECT_DIR/results/$1" attempt pending
  if [[ ! -f "$folder/campaign.json" ]]; then
    if [[ "$matrix" == main ]]; then pipeline prepare "$batch"; else pipeline prepare-decomposition "$batch"; fi
  fi
  "$AIJ_PYTHON" "$JOBS_DIR/check_auto_state.py" campaign "$folder" "$AIJ_CONFIG" "$matrix"
  for attempt in 1 2; do
    "$AIJ_PYTHON" "$PROJECT_DIR/analysis/summarize_campaign.py" "$folder"
    pending=$("$AIJ_PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1]))["statuses"].get("PENDING",0))' "$folder/summary.json")
    if [[ "$pending" == 0 ]]; then break; fi
    if [[ -f "$folder/array_job_id.txt" ]]; then pipeline resume "$batch"; else pipeline submit "$batch"; fi
    wait_job "$(cat "$folder/array_job_id.txt")" || true
    if [[ -f "$folder/analysis_job_id.txt" ]]; then wait_job "$(cat "$folder/analysis_job_id.txt")" || true; fi
  done
  "$AIJ_PYTHON" "$PROJECT_DIR/analysis/summarize_campaign.py" "$folder"
  "$AIJ_PYTHON" - "$folder/summary.json" <<'PY'
import json,sys
summary=json.load(open(sys.argv[1]))
if summary['statuses'].get('PENDING',0):
    raise SystemExit('续跑后仍有 PENDING，请查看作业日志解决问题；不再自动重复提交。')
PY
  # The last submitted analysis must succeed; a missing/failed one is submitted once.
  if [[ ! -f "$folder/analysis/report.md" ]] || [[ ! -f "$folder/analysis_job_id.txt" ]] || ! wait_job "$(cat "$folder/analysis_job_id.txt")"; then
    pipeline analyze "$batch"
    wait_job "$(cat "$folder/analysis_job_id.txt")"
  fi
  if [[ ! -d "deliveries/$batch" ]]; then
    bash "$JOBS_DIR/push_results.sh" export "$batch"
  else
    "$AIJ_PYTHON" "$JOBS_DIR/check_auto_state.py" delivery "$folder" "$PROJECT_DIR/deliveries/$batch"
  fi
}
run_batch "$main" main
run_batch "$decomposition" decomposition
if $push; then
  bash "$JOBS_DIR/push_results.sh" push "$main"
  bash "$JOBS_DIR/push_results.sh" push "$decomposition"
fi
echo "完成：deliveries/$main 和 deliveries/$decomposition；验解包留在各自 results 目录，请另行传输并备份。"
