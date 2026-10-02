"""Shared long-table fields for individual runs and configuration campaigns."""
FIELDS = ['job_id', 'family', 'task', 'method', 'encoding', 'solver', 'status', 'verified',
          'objective_exact', 'solve_wall_seconds', 'verify_wall_seconds', 'wall_seconds',
          'solve_budget_seconds', 'peak_tree_rss_bytes', 'termination', 'host', 'cpu', 'input',
          'num_variables', 'num_hard_clauses', 'num_soft_clauses', 'encode_seconds', 'backend_seconds',
          'decomposition_requested', 'decomposition_effective', 'lrn_requested']


def row_for(job, result):
    method = job['method']
    row = {key: result.get(key, '') for key in FIELDS}
    row.update(job_id=job['id'], family=job['family'], task=job.get('task', ''),
               method=method['id'], encoding=method.get('encoding', ''), solver=method['solver'],
               input=result.get('input', job.get('input', '')), status=result.get('status', 'PENDING'))
    formula = result.get('formula', {})
    for key, alternate in [('num_variables', 'variables'), ('num_hard_clauses', 'hard'), ('num_soft_clauses', 'soft')]:
        row[key] = formula.get(key, formula.get(alternate, ''))
    timings = result.get('solver_timings', {})
    row['encode_seconds'] = timings.get('build_total', timings.get('build', ''))
    row['backend_seconds'] = timings.get('solve', '')
    stats = result.get('encoding_stats', {})
    row['decomposition_requested'] = stats.get('decomposition_requested', '')
    row['decomposition_effective'] = stats.get('decomposition_effective', '')
    row['lrn_requested'] = stats.get('lrn', {}).get('requested', '')
    return row
