"""Write the Slurm submission script for a prepared experiment plan."""
import shlex


def write_submission(plan, output, ROOT, wall_hours):
    command=['sbatch','--parsable',f'--partition={plan["partition"]}',f'--array=0-{plan["configuration_jobs"]-1}%{plan["concurrent_jobs"]}',f'--cpus-per-task={plan["workers"]}',
             f'--mem={plan["memory_gib"]}G',f'--time={wall_hours//24}-{wall_hours%24:02d}:00:00',
             f'--output={output}/slurm-%A_%a.log',
             f'--export=ALL,AIJ_RUNNER_DIR={ROOT},AIJ_CAMPAIGN={output}',str(ROOT/'internal/run_config_array.sh')]
    analysis=['sbatch','--parsable',f'--output={output}/analysis-%j.log',
              f'--export=ALL,AIJ_RUNNER_DIR={ROOT},AIJ_CAMPAIGN={output}',str(ROOT.parent/'analysis/run_campaign_analysis.sh')]
    script='#!/usr/bin/env bash\nset -euo pipefail\n'
    script+='export AIJ_PYTHON='+shlex.quote(plan['config_snapshot']['python'])+'\n'
    script+='"$AIJ_PYTHON" -c "import matplotlib"\n'
    script+='array_id=$('+shlex.join(command)+')\narray_id=${array_id%%;*}\n'
    script+='printf "%s\\n" "$array_id" > '+shlex.quote(str(output/'array_job_id.txt'))+'\n'
    script+='printf "Configuration array: %s\\n" "$array_id"\n'
    script+='analysis_id=$(sbatch --dependency="afterany:$array_id" '+shlex.join(analysis[1:])+')\nanalysis_id=${analysis_id%%;*}\n'
    script+='printf "%s\\n" "$analysis_id" > '+shlex.quote(str(output/'analysis_job_id.txt'))+'\n'
    script+='printf "Analysis job: %s\\n" "$analysis_id"\n'
    (output/'submit.sh').write_text(script)


if __name__ == '__main__':
    import argparse
    import json
    from math import ceil
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', required=True, type=Path)
    args = parser.parse_args()
    output = args.campaign.resolve()
    plan = json.loads((output / 'campaign.json').read_text())
    seconds = max(ceil(len(task['job_ids']) / plan['workers']) * plan['limits']['outer_seconds'] for task in plan['tasks'])
    write_submission(plan, output, Path(__file__).resolve().parent, ceil(seconds / 3600) + 2)
    print('Prepared only:', output / 'submit.sh')
