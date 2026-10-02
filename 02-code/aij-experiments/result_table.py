"""Shared long-table fields for individual runs and configuration campaigns."""
FIELDS = ['job_id', 'family', 'task', 'method', 'encoding', 'solver', 'status', 'verified',
          'objective_exact', 'solve_wall_seconds', 'verify_wall_seconds', 'wall_seconds',
          'solve_budget_seconds', 'peak_tree_rss_bytes', 'termination', 'host', 'cpu', 'input',
          'num_variables', 'num_hard_clauses', 'num_soft_clauses', 'encode_seconds', 'backend_seconds',
          'decomposition_requested', 'decomposition_effective', 'lrn_requested']
FEATURES = ['representation','variables','boolean_variables','boolean_fraction','domain_size_min','domain_size_max',
            'domain_size_mean','objective_terms','objective_degree','constraints','constraint_atoms',
            'nonlinear_constraint_atoms','constraint_degree','objective_sense','ast_nodes']
QUALITY = ['primal_bound_internal','dual_bound_internal','primal_bound_original','dual_bound_original',
           'absolute_gap_original','normalized_gap_original','backend_relative_gap','search_nodes']
FIELDS += ['read_seconds','maxsat_cost','top_weight','total_soft_weight','last_phase','termination_phase',
           'model_variables','model_constraints','domain_bits','product_variables','model_route',
           'objective_scale','objective_divisor','objective_constant',
           'decomposed_terms','multiplication_requests','multiplication_nodes','cache_hits',
           'generated_variables','generated_hard','generated_soft','simplified_variables','simplified_hard','simplified_soft',
           'max_weight_bits','total_weight_bits','weight_gcd']
FIELDS += ['original_'+key for key in FEATURES] + QUALITY
FIELDS += ['phase_'+key+'_seconds' for key in ['startup','parse','build','solve','verify']]
FIELDS += ['outer_budget_seconds','verify_budget_seconds','memory_budget_gib','backend_status','error','returncode']


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
    row['model_route'] = formula.get('route','sat-maxsat' if formula.get('hard') is not None or formula.get('num_hard_clauses') is not None else '')
    for key,source in [('model_variables','variables'),('model_constraints','constraints'),('domain_bits','domain_bits'),
                       ('product_variables','product_variables'),('objective_scale','objective_scale'),
                       ('objective_divisor','objective_divisor'),('objective_constant','objective_constant')]:
        row[key] = formula.get(source,'')
    for key in ['decomposed_terms','multiplication_requests','multiplication_nodes','cache_hits']:
        row[key] = sum(stats.get(scope,{}).get(key,0) for scope in ['objective','constraints']) if stats else ''
    for stage in ['generated','simplified']:
        for key in ['variables','hard','soft']:
            row[stage+'_'+key] = stats.get(stage,{}).get(key,'')
    for key in ['max_weight_bits','total_weight_bits']:
        row[key] = stats.get('simplified',{}).get(key,'')
    row['weight_gcd'] = stats.get('weight_gcd','')
    row.update({'original_'+k:result.get('problem_features',{}).get(k,'') for k in FEATURES})
    row.update({k:result.get('quality',{}).get(k,'') for k in QUALITY})
    for phase in ['startup','parse','build','solve','verify']:
        row['phase_'+phase+'_seconds'] = result.get('phase_seconds',{}).get(phase,'')
    return row
