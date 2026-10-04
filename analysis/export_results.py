"""Export compact tables and plots; keep witnesses in a separate local archive."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import tarfile

def export(source, target):
    plan = json.loads((source / 'campaign.json').read_text())
    summary = json.loads((source / 'summary.json').read_text())
    with (source / 'results.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    expected = {job for task in plan['tasks'] for job in task['job_ids']}
    counts = dict(Counter(row['status'] for row in rows))
    if len(rows) != len(expected) or {r['job_id'] for r in rows} != expected or counts != summary['statuses']:
        raise ValueError('总表与计划/汇总不一致，请先完成最终分析。')
    if counts.get('PENDING', 0):
        raise ValueError('仍有 PENDING，请先完成或处理未运行实例，再交付。失败、超时等已结束结果会保留。')
    if not (source / 'analysis/report.md').is_file() or not (source / 'sumup').is_dir():
        raise ValueError('缺少最终分析报告或 sumup，请先运行分析。')
    selected = [source / name for name in ['results.csv', 'summary.json', 'campaign.json', 'submit.sh',
                'array_job_id.txt', 'analysis_job_id.txt', 'submissions.log'] if (source / name).is_file()]
    selected += sorted((source / 'sumup').glob('*.csv'))
    selected += sorted(p for p in (source / 'analysis').rglob('*')
                       if p.is_file() and p.suffix.lower() in {'.csv', '.md', '.png', '.pdf'})
    large = [str(p) for p in selected if p.stat().st_size > 50 * 1024 * 1024]
    if large:
        raise ValueError('这些文件超过 50 MiB，请单独传输：' + ', '.join(large))
    if target.exists():
        raise ValueError(f'交付目录已存在：{target}；保留已填写的说明，请先移走旧导出再重新生成。')
    environments = {}
    for task in plan['tasks']:
        record = source / 'runs' / task['key'] / 'run.json'
        if not record.is_file():
            raise ValueError(f'缺少运行环境记录：{record}')
        data = json.loads(record.read_text())
        environments[task['key']] = {'created_utc': data.get('created_utc'),
            'plan': {k: v for k, v in data['plan'].items() if k != 'jobs'}}
    for path in selected:
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    (target / 'environment.json').write_text(json.dumps(environments, indent=2) + '\n', encoding='utf-8')
    (target / 'README.md').write_text(
        '# NLIP-AIJ 实验结果交付\n\n'
        f"Profile: {plan['profile']}; matrix: {plan['matrix']}.\n"
        f'计划运行：{len(expected)}；状态：{counts}。\n\n'
        f'原始目录：{source.resolve()}。\n'
        '原问题见证位于原始 result.json，验解记录包单独传输。\n\n'
        '最终分析报告已生成；各状态和具体错误见 results.csv 与 analysis/report.md。\n'
        '原始记录备份位置：未记录。请另行备份原始 runs 与验解包；GitHub 交付不包含它们。\n', encoding='utf-8')
    archive_path = source / 'verification-records.tar.gz'
    records = [source / 'campaign.json'] + sorted(source.glob('runs/*/run.json'))
    records += sorted(source.glob('runs/*/jobs/*/result.json'))
    with tarfile.open(archive_path, 'w:gz') as archive:
        for path in records:
            archive.add(path, arcname=str(path.relative_to(source)), recursive=False)
    print(f'GitHub 交付目录：{target.resolve()}\n另行传输验解包：{archive_path.resolve()}\n状态：{counts}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.campaign.resolve(), args.output.resolve())
