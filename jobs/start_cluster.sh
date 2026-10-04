#!/usr/bin/env bash
# Can be downloaded and run before the repository exists.
set -euo pipefail
export NLIP_WORKDIR="${NLIP_WORKDIR:-/scratch/scherif/NLIP/NLIP-AIJ}"
repository="${AIJ_REPO_URL:-https://github.com/ZhenglingYangli/NLIP-Journal-Artifact-.git}"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  echo '用法：bash start_cluster.sh [--push] [--no-pull]'
  echo '首次自动克隆到 NLIP_WORKDIR；已有 checkout 按作业和冻结计划判断是否更新。'
  exit 0
fi
if [[ ! -d "$NLIP_WORKDIR/.git" ]]; then
  if [[ -d "$NLIP_WORKDIR" && -n "$(ls -A "$NLIP_WORKDIR")" ]]; then
    echo "目标目录已有文件但不是 Git checkout：$NLIP_WORKDIR；请指定正确的 NLIP_WORKDIR。" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$NLIP_WORKDIR")"
  git clone --branch main "$repository" "$NLIP_WORKDIR"
  export AIJ_CODE_SYNCED=1
else
  # This standalone entry also upgrades a checkout whose total script is older.
  cd "$NLIP_WORKDIR"
  mkdir -p results
  exec 9>results/.cluster-all.lock
  flock -n 9 || { echo '已有总入口运行中，未更新代码；请查看原入口日志。' >&2; exit 1; }
  export AIJ_ALL_LOCK_HELD=1
  frozen=false
  for plan in results/*/campaign.json; do
    if [[ -f "$plan" ]]; then frozen=true; break; fi
  done
  branch=$(git branch --show-current)
  pull=true
  for arg in "$@"; do if [[ "$arg" == --no-pull ]]; then pull=false; fi; done
  if $pull && ! $frozen && [[ "$branch" == main ]]; then
    command -v squeue >/dev/null || { echo '请在集群登录环境运行，需先检查队列再更新。' >&2; exit 1; }
    queue=$(squeue --noheader --user="$(id -un)" --format='%i %j')
    if awk '$2 ~ /[Aa][Ii][Jj]|[Nn][Ll][Ii][Pp]/ {found=1} END {exit !found}' <<< "$queue"; then
      echo '本项目作业仍在队列中，保留当前代码，进入现有入口等待。'
    else
      [[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo '存在未提交代码修改，未更新；请处理后重开入口。' >&2; exit 1; }
      git pull --ff-only origin main
      export AIJ_CODE_SYNCED=1
    fi
  fi
fi
exec bash "$NLIP_WORKDIR/jobs/run_cluster_all.sh" "$@"
