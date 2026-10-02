#!/usr/bin/env python3
"""Recompute a long-format table from saved per-job results."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys
from result_table import FIELDS, row_for


def summarize(output):
    output = Path(output)
    jobs = json.loads((output / 'run.json').read_text())['plan']['jobs']
    statuses = Counter()
    with (output / 'results.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for job in jobs:
            p = output / 'jobs' / job['id'] / 'result.json'
            result = json.loads(p.read_text()) if p.exists() else {'status': 'PENDING'}
            statuses[result['status']] += 1
            writer.writerow(row_for(job, result))
    (output / 'summary.json').write_text(json.dumps({'planned': len(jobs), 'statuses': dict(statuses)}, indent=2))
    print(dict(statuses))


if __name__ == '__main__':
    summarize(sys.argv[1])
