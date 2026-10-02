"""Recompute configuration tables, pairwise comparisons and accumulated solved plots."""
import argparse
from collections import Counter, defaultdict
import csv
from itertools import combinations
import json
import math
from pathlib import Path
from statistics import median
from summarize_campaign import summarize


def number(value):
    try:
        answer = float(value)
        return answer if math.isfinite(answer) else None
    except (ValueError, TypeError):
        return None


def success(row, cutoff):
    elapsed = number(row.get('solve_wall_seconds'))
    verified = str(row.get('verified')).lower() == 'true'
    status = row['status']
    valid = ((status == 'SAT' and verified) or status == 'UNSAT') if row['family'] == 'smt' else status == 'OPTIMAL' and verified
    return bool(valid and elapsed is not None and 0 <= elapsed <= cutoff)


def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def instance_id(row):
    return row['job_id'][:-(len(row['method']) + 1)]


def export_legacy(folder, groups, cutoff):
    folder.mkdir(exist_ok=True)
    fields = ['Benchmark', 'Encoding', 'Solver', 'Status', 'OPT', 'Cost', 'Vars', 'Hard', 'Soft',
              'TopW', 'TimeRead', 'TimeEncode', 'TimeSolve', 'TimeTotal', 'TimeForAnalysis', 'Verified', 'EffectiveSuccess']
    family_names = {'qplib': 'qplib', 'diverse': 'diverse_sat', 'mipo': 'mipo', 'smt': 'smt_0_10'}
    for (family, method), records in groups.items():
        rows = []
        for r in records:
            enc = 'BIN+D' if r['method'].startswith('bin-d-') else r['encoding']
            rows.append(dict(zip(fields, [Path(r['input']).name if r['input'] else instance_id(r),
                enc, r['solver'], r['status'], r['objective_exact'], r['maxsat_cost'], r['num_variables'],
                r['num_hard_clauses'], r['num_soft_clauses'], r['top_weight'], r['read_seconds'], r['encode_seconds'], r['backend_seconds'],
                r['solve_wall_seconds'], r['solve_wall_seconds'], r['verified'], int(success(r, cutoff))])))
        write_csv(folder / f'NLIP_{family_names[family]}_{method}.csv', rows, fields)


def make_plots(folder, groups, cutoff):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder.mkdir(exist_ok=True)
    by_family = defaultdict(dict)
    for (family, method), records in groups.items():
        by_family[family][method] = records
    if 'qplib' in by_family and 'diverse' in by_family:
        common = set(by_family['qplib']) & set(by_family['diverse'])
        by_family['qplib-diverse'] = {m: by_family['qplib'][m] + by_family['diverse'][m] for m in common}
    colors = {'RC2': '#D62728', 'MAXHS': '#FF7F0E', 'WMAXCDCL': '#2CA02C', 'OPENWBO': '#9467BD',
              'Z3': '#0047AB', 'CVC5': '#17BECF', 'CADICAL': '#D62728', 'SCIP-NATIVE': '#8C564B',
              'SCIP-MILP': '#8C564B', 'CPLEX-NATIVE': '#E377C2', 'CPLEX-MILP': '#E377C2', 'HIGHS-MILP': '#222222'}
    for family, configs in sorted(by_family.items()):
        fig, ax = plt.subplots(figsize=(11, 9))
        any_solved = False
        pending = sum(r['status'] == 'PENDING' for records in configs.values() for r in records)
        for method, records in sorted(configs.items()):
            times = sorted(float(r['solve_wall_seconds']) for r in records if success(r, cutoff))
            any_solved = any_solved or bool(times)
            enc = records[0]['encoding']
            style = '-.' if method.startswith('bin-d-') or method.endswith('-milp') else {'OH': '-', 'UNA': '--', 'BIN': ':'}.get(enc, '-')
            ax.step([0] + list(range(1, len(times) + 1)) + [len(times)], [0] + times + [cutoff],
                    where='pre', color=colors.get(records[0]['solver'], '#777777'), linestyle=style,
                    linewidth=1.8, label=f'{method} ({len(times)})')
        ax.set(xlabel='Cumulative solved number', ylabel='Time (s)', ylim=(0, cutoff),
               title=family + (' — incomplete runs' if pending else ''))
        ax.set_xlim(left=0, right=max(len(r) for r in configs.values()) + 1)
        ax.grid(alpha=.25)
        ax.legend(loc='upper center', bbox_to_anchor=(.5, -.13), ncol=3, fontsize=8)
        if not any_solved:
            ax.text(.5, .5, 'No completed successful runs', ha='center', transform=ax.transAxes)
        fig.subplots_adjust(bottom=.32)
        for ext in ('png', 'pdf'):
            fig.savefig(folder / f'accumulated-{family}.{ext}', dpi=180, bbox_inches='tight')
        plt.close(fig)


def analyze(folder, plots=True):
    folder = Path(folder)
    plan = json.loads((folder / 'campaign.json').read_text())
    summarize(folder)
    limits = plan.get('limits')
    if limits is None:
        from goSolver import load_config
        limits = load_config(plan['config'])['profiles'][plan['profile']]
    cutoff = float(limits['solve_seconds'])
    with (folder / 'results.csv').open(encoding='utf-8', newline='') as f:
        records = list(csv.DictReader(f))
    groups = defaultdict(list)
    for row in records:
        budget = number(row['solve_budget_seconds'])
        if budget is not None and budget != cutoff:
            raise ValueError('mixed solve budgets in campaign: ' + row['job_id'])
        groups[(row['family'], row['method'])].append(row)
    analysis = folder / 'analysis'
    analysis.mkdir(exist_ok=True)
    summaries, statuses = [], []
    for (family, method), rows in sorted(groups.items()):
        counts = Counter(r['status'] for r in rows)
        times = [float(r['solve_wall_seconds']) for r in rows if success(r, cutoff)]
        pending = counts['PENDING']
        summaries.append({'family': family, 'method': method, 'planned': len(rows), 'completed': len(rows)-pending,
            'pending': pending, 'solved': len(times), 'verified_feasible': sum(r['status']=='FEASIBLE' and r['verified']=='True' for r in rows),
            'reported_unsat': counts['UNSAT'], 'median_solved_seconds': median(times) if times else '',
            'par2_seconds': (sum(times)+(len(rows)-len(times))*2*cutoff)/len(rows) if not pending else '',
            'coverage': (len(rows)-pending)/len(rows)})
        statuses.extend({'family': family, 'method': method, 'status': s, 'count': n} for s, n in sorted(counts.items()))
    write_csv(analysis/'config_summary.csv', summaries, list(summaries[0]))
    write_csv(analysis/'status_counts.csv', statuses, ['family','method','status','count'])
    from result_table import FEATURES, QUALITY
    base=['job_id','family','method','status','verified']
    for name,fields in [
        ('instance_features',base+['original_'+k for k in FEATURES]),
        ('encoding_metrics',base+['read_seconds','encode_seconds','backend_seconds','maxsat_cost','top_weight','total_soft_weight',
                                 'num_variables','num_hard_clauses','num_soft_clauses','decomposition_requested','decomposition_effective',
                                 'decomposed_terms','multiplication_requests','multiplication_nodes','cache_hits',
                                 'generated_variables','generated_hard','generated_soft','simplified_variables','simplified_hard','simplified_soft',
                                 'max_weight_bits','total_weight_bits','weight_gcd']),
        ('model_quality',base+['model_route','model_variables','model_constraints','domain_bits','product_variables',
                              'objective_scale','objective_divisor','objective_constant']+QUALITY),
        ('phase_metrics',base+['last_phase','termination_phase','termination']+
                         ['phase_'+k+'_seconds' for k in ['startup','parse','build','solve','verify']])]:
        write_csv(analysis/(name+'.csv'),[{k:r[k] for k in fields} for r in records],fields)
    pairwise = []
    for family in sorted({f for f, _ in groups}):
        configs = {m: {instance_id(r): r for r in rows} for (f, m), rows in groups.items() if f == family}
        for a, b in combinations(sorted(configs), 2):
            shared = set(configs[a]) & set(configs[b])
            observed = [i for i in shared if configs[a][i]['status']!='PENDING' and configs[b][i]['status']!='PENDING']
            aa = {i for i in observed if success(configs[a][i], cutoff)}
            bb = {i for i in observed if success(configs[b][i], cutoff)}
            both = aa & bb
            pairwise.append({'family':family,'method_a':a,'method_b':b,'planned_common':len(shared),'completed_common':len(observed),
                'both_solved':len(both),'only_a_solved':len(aa-bb),'only_b_solved':len(bb-aa),
                'a_faster_on_both':sum(float(configs[a][i]['solve_wall_seconds'])<float(configs[b][i]['solve_wall_seconds']) for i in both),
                'b_faster_on_both':sum(float(configs[b][i]['solve_wall_seconds'])<float(configs[a][i]['solve_wall_seconds']) for i in both)})
    pair_fields=['family','method_a','method_b','planned_common','completed_common','both_solved','only_a_solved','only_b_solved','a_faster_on_both','b_faster_on_both']
    write_csv(analysis/'pairwise.csv', pairwise, pair_fields)
    export_legacy(folder/'sumup', groups, cutoff)
    if plots:
        make_plots(analysis/'figures', groups, cutoff)
    pending = sum(r['status']=='PENDING' for r in records)
    lines = ['# Experiment analysis', '', f'Profile: {plan["profile"]}; matrix: {plan["matrix"]}; solve cutoff: {cutoff:g} seconds.',
        f'Planned runs: {len(records)}; pending: {pending}.', '',
        'Optimization success requires OPTIMAL and an original-problem verified witness. SMT SAT requires a verified witness; UNSAT counts as a reported decision, without an independent proof claim.',
        'TimeForAnalysis is solve_wall_seconds: startup, parsing, encoding and solving; separate verification time is retained in results.csv.',
        'PENDING runs remain in the planned denominator. PAR-2 is blank for incomplete configurations; completed unsuccessful runs cost twice the solve cutoff. FEASIBLE and UNSUPPORTED are shown separately from solved.',
        'All configured solvers, including SCIP, are retained. A solver result is not used as an independent truth oracle.', '',
        '| Family | Method | Completed / planned | Solved | Median solved seconds |',
        '|---|---|---:|---:|---:|']
    for r in summaries:
        med = r['median_solved_seconds']
        lines.append(f'| {r["family"]} | {r["method"]} | {r["completed"]}/{r["planned"]} | {r["solved"]} | {med:.4g} |' if med != '' else
                     f'| {r["family"]} | {r["method"]} | {r["completed"]}/{r["planned"]} | {r["solved"]} | — |')
    (analysis/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Analysis:', analysis)
    return summaries


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('campaign', type=Path)
    ap.add_argument('--tables-only', action='store_true')
    args=ap.parse_args()
    analyze(args.campaign, not args.tables_only)
