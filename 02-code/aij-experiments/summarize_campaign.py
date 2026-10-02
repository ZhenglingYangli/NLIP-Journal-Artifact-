"""Merge configuration outputs against the full planned set, retaining pending rows."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys

def summarize(folder):
    folder=Path(folder); plan=json.loads((folder/'campaign.json').read_text())
    statuses=Counter(); seen=set()
    fields=['job_id','family','method','status','verified','objective_exact','solve_wall_seconds',
            'verify_wall_seconds','wall_seconds','peak_tree_rss_bytes','host','cpu','input']
    with (folder/'results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for task in plan['tasks']:
            for job_id in task['job_ids']:
                if job_id in seen: raise ValueError('duplicate job in campaign: '+job_id)
                seen.add(job_id)
                p=folder/'runs'/task['key']/'jobs'/job_id/'result.json'
                r=json.loads(p.read_text()) if p.exists() else {'status':'PENDING'}
                if p.exists() and (r['job_id']!=job_id or r['method']!=task['method']):
                    raise ValueError('result belongs to a different configuration')
                row={k:r.get(k,'') for k in fields}
                row.update(job_id=job_id,family=task['family'],method=task['method']['id'])
                writer.writerow(row); statuses[r['status']]+=1
    summary={'planned':len(seen),'configuration_jobs':len(plan['tasks']),'statuses':dict(statuses)}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2)); return summary

if __name__=='__main__': summarize(sys.argv[1])
