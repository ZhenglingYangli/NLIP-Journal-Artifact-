#!/usr/bin/env bash
# Export is local. Push explicitly creates a result branch and sends compact files.
set -euo pipefail
JOBS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$JOBS_DIR/.." && pwd)"
action="${1:-help}"
batch="${2:-aij-main}"
if [[ "$action" != export && "$action" != push ]]; then
  echo '用法：bash jobs/push_results.sh export|push [批次名]'
  echo 'export：导出精简结果，并把验解记录包留在 results；不提交、不推送。'
  echo 'push：确认队列中的本项目作业已结束，提交 deliveries 到 results-<批次名> 分支并推送。'
  [[ "$action" == help || "$action" == --help || "$action" == -h ]] && exit 0
  exit 2
fi
[[ "$batch" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]] || { echo '请使用批次目录名，不传绝对路径。' >&2; exit 1; }
cd "$PROJECT_DIR"
campaign="$PROJECT_DIR/results/$batch"
delivery="deliveries/$batch"
python="${AIJ_PYTHON:-$JOBS_DIR/.venv/bin/python}"
[[ -x "$python" ]] || { echo "Python 不可用：$python" >&2; exit 1; }
if [[ "$action" == export ]]; then
  "$python" "$PROJECT_DIR/analysis/export_results.py" --campaign "$campaign" --output "$PROJECT_DIR/$delivery"
  echo "请检查 $delivery/README.md 和报告，补充异常及备份位置；全部批次结束后再执行 push。"
  exit 0
fi
[[ -f "$delivery/environment.json" && -f "$delivery/analysis/report.md" ]] || { echo '请先 export 并检查交付内容。' >&2; exit 1; }
command -v squeue >/dev/null || { echo '请在集群环境推送，以检查本项目作业是否结束。' >&2; exit 1; }
queue=$(squeue --noheader --user="$(id -un)" --format='%i %j')
while read -r job name; do
  [[ -n "$job" ]] || continue
  if [[ "$name" == *[Aa][Ii][Jj]* || "$name" == *[Nn][Ll][Ii][Pp]* ]]; then
    echo "本项目作业仍在队列中：$job $name；结束后再 push。" >&2; exit 1
  fi
  for file in "$PROJECT_DIR"/results/*/array_job_id.txt "$PROJECT_DIR"/results/*/analysis_job_id.txt "$PROJECT_DIR"/results/cluster-smoke-last-job.txt; do
    [[ -f "$file" ]] || continue
    recorded=$(cat "$file")
    if [[ "$job" == "$recorded" || "$job" == "${recorded}_"* || "$job" == "${recorded}."* ]]; then
      echo "本项目作业仍在队列中：$job；结束后再 push。" >&2; exit 1
    fi
  done
done <<< "$queue"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo '存在已跟踪文件的未提交修改，请先处理；未提交任何结果。' >&2; exit 1; }
branch="results-$batch"
current=$(git branch --show-current)
if [[ "$current" != "$branch" ]]; then
  git show-ref --verify --quiet "refs/heads/$branch" && { echo "分支 $branch 已存在；请检查后自行切换到该分支重试。" >&2; exit 1; }
  git switch -c "$branch"
fi
# Use the export whitelist, including sumup CSV ignored by the repository.
"$python" - "$delivery" <<'PY'
import csv, json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
with (root/'results.csv').open(encoding='utf-8', newline='') as f:
    rows = list(csv.DictReader(f))
if not rows or any(r['status'] == 'PENDING' for r in rows):
    raise SystemExit('交付仍有未运行记录，未提交。')
allowed = {'results.csv','summary.json','campaign.json','submit.sh','array_job_id.txt',
           'analysis_job_id.txt','submissions.log','environment.json','README.md'}
files = []
for path in sorted(root.rglob('*')):
    if not path.is_file(): continue
    rel = path.relative_to(root)
    ok = (len(rel.parts)==1 and rel.name in allowed) or (rel.parts[0]=='sumup' and path.suffix=='.csv') or (rel.parts[0]=='analysis' and path.suffix.lower() in {'.csv','.md','.png','.pdf'})
    if not ok or path.stat().st_size > 50*1024*1024:
        raise SystemExit(f'交付包含非导出文件或大文件，请移走后重试：{path}')
    files.append(str(path))
subprocess.run(['git','add','-f','--',*files],check=True)
PY
git diff --cached --stat
if ! git diff --cached --quiet; then
  git commit -m "Add NLIP-AIJ results: $batch"
fi
git push -u origin "$branch"
echo "结果已推送：$branch。验解记录包没有上传，请单独传输并保留原始结果。"
