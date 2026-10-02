#!/usr/bin/env python3
"""One AIJ job. The parent process enforces wall time and process-tree RSS."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback


def emit(kind, value):
    print('AIJ_' + kind + ' ' + json.dumps(value, ensure_ascii=False, default=str), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('job')
    args = ap.parse_args()
    job = json.loads(Path(args.job).read_text())
    import psutil
    psutil.Process().cpu_affinity([job['cpu']])
    for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        os.environ[name] = '1'
    root = Path(job['code_root'])
    sys.path.insert(0, str(root / 'codes'))
    sys.path.insert(0, str(root))
    from nlipsat import load_problem
    import tools.verify as verification
    import solver.solve as engine
    from solver.config import EncodingConfig
    verify_started = None

    def begin_verify():
        nonlocal verify_started
        if verify_started is None:
            verify_started = time.monotonic()
            emit('PHASE', {'phase': 'verify', 'at': verify_started})

    old_solution_check = engine.verify_solution
    old_value_check = verification.verify_values

    def solution_check(*a, **kw):
        begin_verify()
        return old_solution_check(*a, **kw)

    def value_check(*a, **kw):
        begin_verify()
        return old_value_check(*a, **kw)

    # Adapter-local timing hooks; no second implementation of the encodings.
    engine.verify_solution = solution_check
    verification.verify_values = value_check
    method = job['method']
    started = time.monotonic()
    if method.get('encoding') in ('DW', 'IW'):
        if job['task'] != 'optimization' or job['family'] != 'diverse':
            raise ValueError('DW/IW is only defined for Diverse SAT optimization')
        from diverse_baseline import solve
        remaining = max(.001, job['solve_seconds'] - (time.monotonic() - started))
        result = solve(job['input'], job['k'], method['encoding'], method['solver'], remaining,
                       Path(args.job).parent, job['solver_paths'], begin_verify)
    elif method['solver'] == 'CVC5':
        from cvc5_baseline import solve, solve_smt2, Unsupported
        try:
            if job['task'] == 'decision':
                result = solve_smt2(job['input'], max(.001, job['solve_seconds'] - (time.monotonic()-started)), begin_verify)
            else:
                problem = load_problem(job['input'], k=job.get('k'))
                result = solve(problem, max(.001, job['solve_seconds'] - (time.monotonic()-started)), begin_verify)
        except Unsupported as exc:
            result = {'status': 'UNSUPPORTED', 'verified': False, 'error': str(exc)}
    elif method['solver'] in ('SCIP-MILP', 'SCIP-NATIVE'):
        if job['task'] == 'decision':
            from tools.smt2_parser import parse_smt2_file
            problem = parse_smt2_file(job['input'], objective_mode='zero')
        else:
            problem = load_problem(job['input'], k=job.get('k'))
        from scip_baseline import solve
        remaining = max(.001, job['solve_seconds'] - (time.monotonic() - started))
        result = solve(problem, 'milp' if method['solver']=='SCIP-MILP' else 'native',
                       remaining, job['task'], begin_verify)
    elif method['solver'] in ('CPLEX-NATIVE', 'CPLEX-MILP', 'HIGHS-MILP'):
        from optimization_baselines import solve
        problem = load_problem(job['input'], k=job.get('k'))
        result = solve(problem, method['solver'], max(.001, job['solve_seconds'] - (time.monotonic()-started)), begin_verify)
    elif method['solver'] == 'Z3':
        spec = importlib.util.spec_from_file_location('aij_z3', root / 'solvers/baseline/run_z3.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        if job['task'] == 'decision':
            witness = {}
            old_try = baseline._try_solver

            def attempt(solver, path, timeout_ms):
                answer = old_try(solver, path, timeout_ms)
                if answer == baseline.sat:
                    begin_verify()
                    model = solver.model()
                    witness['model_sexpr'] = model.sexpr()
                return answer

            baseline._try_solver = attempt
            raw = baseline.solve_smt2(job['input'], job['solve_seconds'])
        else:
            problem = load_problem(job['input'], k=job.get('k'))
            remaining = max(.001, job['solve_seconds'] - (time.monotonic() - started))
            raw = baseline.solve_qplib(problem, remaining)
            witness = raw.get('witness')
        objective = raw.get('objective')
        result = {'status': raw['status'], 'verified': raw.get('verified', False),
                  'objective_exact': str(objective) if objective not in (None, 'N/A') else None,
                  'witness': witness, 'error': raw.get('error_msg'),
                  'solver_timings': {'total': raw.get('time'), 'verify': raw.get('time_verify')}}
    else:
        if job['task'] == 'decision':
            from tools.smt2_parser import parse_smt2_file
            problem = parse_smt2_file(job['input'], objective_mode='zero')
        else:
            problem = load_problem(job['input'], k=job.get('k'))
        cfg = EncodingConfig(**method.get('options', {}))
        cfg.workdir = str(Path(args.job).parent)
        # A single parent wall deadline includes import, parsing and encoding.
        # Native CPU limits are deliberately not used as competing budgets.
        cfg.external_solver_timeout = 0
        cfg.encoding_deadline = time.time() + max(.001, job['solve_seconds'] - (time.monotonic()-started))
        for key, value in job['solver_paths'].items():
            setattr(cfg, key.lower() + '_path', value)
        if job['task'] == 'decision':
            from pysat.solvers import Solver
            wcnf, names, timings, pool = engine.build_wcnf(problem, method['encoding'], cfg, True)
            if wcnf.soft:
                raise ValueError('decision job produced soft clauses')
            backend = {'CADICAL': 'cadical195', 'GLUCOSE': 'glucose4'}[method['solver']]
            t = time.monotonic()
            with Solver(name=backend, bootstrap_with=wcnf.hard) as sat_solver:
                sat = sat_solver.solve()
                model = sat_solver.get_model() if sat else None
            timings['solve'] = time.monotonic() - t
            report = {}
            if sat:
                begin_verify()
                valid, report = verification.verify_solution(problem, {
                    'assignment': model, 'vpool': pool, 'name2idx': names,
                    'processed_problem': wcnf._processed_problem,
                    'preprocess_meta': wcnf._preprocess_meta}, method['encoding'])
            result = {'status': ('SAT' if valid else 'INVALID') if sat else 'UNSAT',
                      'verified': bool(sat and valid), 'witness': report.get('var_values'),
                      'name_map': problem.get('_name_map'), 'objective_exact': None,
                      'verification': report, 'solver_timings': timings,
                      'encoding_stats': wcnf._encoding_stats,
                      'formula': {'variables': wcnf.nv, 'hard': len(wcnf.hard), 'soft': len(wcnf.soft)}}
        else:
            raw = engine.build_and_solve(problem, method['encoding'], cfg, solver=method['solver'])
            result = {'status': raw['solver_status'], 'verified': raw.get('verified', False),
                      'objective_exact': raw.get('objective_value_exact'),
                      'witness': raw.get('verification', {}).get('var_values'),
                      'verification': raw.get('verification'), 'solver_timings': raw.get('timings'),
                      'encoding_stats': raw['encoding_stats'],
                      'formula': {k: raw[k] for k in ['num_variables', 'num_hard_clauses', 'num_soft_clauses']}}
    if result['status'] in ('SAT', 'OPTIMAL', 'FEASIBLE') and not result['verified']:
        result.update(status='INVALID', error='successful status without completed original-problem verification')
    expected = job.get('smoke_expected')
    if expected is not None:
        if result['status'] != expected['status'] or result.get('objective_exact') != expected.get('objective_exact'):
            result.update(status='INVALID', error='smoke result differs from the hand-computed answer')
    emit('RESULT', result)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        emit('RESULT', {'status': 'ERROR', 'verified': False, 'error': f'{type(exc).__name__}: {exc}'})
        sys.exit(1)
