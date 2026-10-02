#!/usr/bin/env python3
"""Recompute a long-format table from saved per-job results."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys


def summarize(output):
    output = Path(output)
    jobs = json.loads((output / 'run.json').read_text())['plan']['jobs']
    fields = ['job_id', 'family', 'task', 'method', 'status', 'verified', 'objective_exact',
              'solve_wall_seconds', 'verify_wall_seconds', 'wall_seconds', 'peak_tree_rss_bytes', 'termination', 'input']
    statuses = Counter()
    with (output / 'results.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for job in jobs:
            p = output / 'jobs' / job['id'] / 'result.json'
            result = json.loads(p.read_text()) if p.exists() else {'status': 'PENDING'}
            statuses[result['status']] += 1
            row = {key: result.get(key, '') for key in fields}
            row.update(job_id=job['id'], family=job['family'], task=job['task'], input=job['input'], method=job['method']['id'])
            writer.writerow(row)
    (output / 'summary.json').write_text(json.dumps({'planned': len(jobs), 'statuses': dict(statuses)}, indent=2))
    print(dict(statuses))


if __name__ == '__main__':
    summarize(sys.argv[1])
