import os
import subprocess
import tempfile
import time
from math import gcd
from functools import reduce
from pysat.formula import WCNF, IDPool
from pysat.examples.rc2 import RC2
from encoders.encoder_driver import encode_objective, add_domain_constraints, encode_constraints
from .config import EncodingConfig
from tools.preprocessing import preprocess_problem
from fractions import Fraction
from tools.verify import verify_solution


class EncodingTimeoutError(RuntimeError):
    pass


def _preprocess_wcnf(wcnf):
    if not wcnf.hard:
        return

    orig_hard = len(wcnf.hard)

    # Unit propagation on hard clauses
    units = set()
    for clause in wcnf.hard:
        if len(clause) == 1:
            units.add(clause[0])

    if units:
        new_hard = []
        for clause in wcnf.hard:
            if not clause:
                # Preserve an existing contradiction.  Dropping this clause
                # would turn an UNSAT hard formula into a satisfiable one.
                new_hard.append(clause)
                continue
            if any(lit in units for lit in clause):
                if len(clause) == 1:
                    new_hard.append(clause)
                continue
            new_clause = [lit for lit in clause if -lit not in units]
            new_hard.append(new_clause)
        wcnf.hard = new_hard

    # Only shorter clauses can subsume a clause.  Index them by a member
    # literal so unrelated clauses are never compared.
    if len(wcnf.hard) < 50_000:
        by_literal = {}
        unique = sorted({frozenset(c) for c in wcnf.hard}, key=lambda c: (len(c), tuple(sorted(c))))
        retained = []
        for cs in unique:
            if not cs:
                retained = [[]]
                break
            if any(len(sc) < len(cs) and sc.issubset(cs)
                   for lit in cs for sc in by_literal.get(lit, ())):
                continue
            retained.append(sorted(cs))
            if len(cs) <= 3:
                by_literal.setdefault(min(cs), []).append(cs)
        wcnf.hard = retained

    removed = orig_hard - len(wcnf.hard)
    if removed > 0:
        print(f"  [wcnf-preprocess] removed {removed} hard clauses "
              f"(units: {len(units)}, subsumption applied)")


def _check_encoding_deadline(cfg, phase_name=""):
    deadline = getattr(cfg, 'encoding_deadline', 0.0)
    if deadline > 0 and time.time() > deadline:
        raise EncodingTimeoutError(
            f"Encoding deadline exceeded during {phase_name}")


def _formula_counts(wcnf):
    return {'variables': wcnf.nv, 'hard': len(wcnf.hard), 'soft': len(wcnf.soft),
            'max_weight_bits': max(wcnf.wght, default=0).bit_length(),
            'total_weight_bits': sum(wcnf.wght).bit_length()}


def build_wcnf(problem, encoding, cfg, collect_timings=False):
    timings = {} if collect_timings else None

    stats = problem.get('_parse_stats', {})
    if stats.get('skipped') or stats.get('defaulted_bounds'):
        raise ValueError('cannot encode an incomplete or artificially bounded SMT translation')

    # 0. Preprocessing
    t0 = time.time()
    from tools.lrn_entry import prepare_factors
    prepared, lrn_meta, lrn_aux = prepare_factors(problem, cfg.use_lrn)
    processed_problem, preprocess_meta = preprocess_problem(
        prepared, scale_limit=cfg.preprocess_scale_limit,
        enable_integerize=cfg.preprocess_integerize,
        enable_optimizations=cfg.enable_preprocess)
    preprocess_meta['lrn_auxiliaries'] = lrn_aux
    problem = processed_problem
    if collect_timings:
        timings['preprocess'] = time.time() - t0
    _check_encoding_deadline(cfg, "preprocessing")

    vpool = IDPool()
    wcnf = WCNF()

    var_names = sorted(problem.get('variables', {}).keys())
    name2idx = {name: i + 1 for i, name in enumerate(var_names)}

    # Global AND-gate cache shared across constraints and objective (BIN encoding)
    if encoding == 'BIN':
        cfg._global_and_cache = {}

    # 1. Domain constraints
    t1 = time.time()
    add_domain_constraints(problem, encoding, name2idx, vpool, wcnf, cfg)
    if collect_timings:
        timings['domain_constraints'] = time.time() - t1
    _check_encoding_deadline(cfg, "domain constraints")

    # 2. Problem constraints
    t2 = time.time()
    wcnf_cons = encode_constraints(problem, encoding, name2idx, vpool, cfg)
    wcnf.extend(wcnf_cons.hard)
    if collect_timings:
        timings['problem_constraints'] = time.time() - t2
    _check_encoding_deadline(cfg, "problem constraints")

    # 3. Objective function
    t3 = time.time()
    wcnf_obj = encode_objective(problem, encoding, name2idx, vpool, cfg)
    wcnf.extend(wcnf_obj.hard)
    wcnf.extend(wcnf_obj.soft, wcnf_obj.wght)
    _obj_elapsed = time.time() - t3
    if collect_timings:
        timings['objective_encoding'] = _obj_elapsed
    _check_encoding_deadline(cfg, "objective encoding")

    empty_stats = {'decomposed_terms': 0, 'multiplication_requests': 0,
                   'multiplication_nodes': 0, 'cache_hits': 0}
    objective_stats = {**empty_stats, **getattr(wcnf_obj, '_decomposition_stats', {})}
    constraint_stats = {**empty_stats, **getattr(wcnf_cons, '_decomposition_stats', {})}
    wcnf._encoding_stats = {
        'lrn': lrn_meta,
        'objective_binary_fastpath': getattr(wcnf_obj, '_binary_fastpath', False),
        'decomposition_requested': encoding == 'BIN' and cfg.use_decomposition,
        'decomposition_effective': objective_stats['decomposed_terms'] + constraint_stats['decomposed_terms'] > 0,
        'decomp_strategy': cfg.decomp_strategy, 'decomp_shared': cfg.decomp_shared,
        'decomp_exact': cfg.decomp_exact, 'objective': objective_stats,
        'constraints': constraint_stats, 'generated': _formula_counts(wcnf)}

    if encoding == 'BIN' and hasattr(cfg, '_global_and_cache'):
        cache_size = len(cfg._global_and_cache)
        if cache_size > 0:
            print(f"  [global-cache] shared AND-gate cache: {cache_size} gates")
        del cfg._global_and_cache

    # Constant terms in objective (terms with empty vars)
    obj_constant = 0
    for term in problem.get('objective', {}).get('terms', []):
        if not term.get('vars'):
            obj_constant += int(term.get('c', 0))
    wcnf._objective_constant = obj_constant

    # Record negative-weight offset
    if hasattr(wcnf_obj, '_neg_soft_total'):
        wcnf._neg_soft_total = getattr(wcnf_obj, '_neg_soft_total', 0)

    # Soft weight GCD normalization (Direction 1/5: core-friendly)
    weight_gcd = 1
    if getattr(cfg, 'weight_gcd_normalize', True) and wcnf.wght:
        weight_gcd = reduce(gcd, wcnf.wght)
        if weight_gcd > 1:
            wcnf.wght = [w // weight_gcd for w in wcnf.wght]
            if hasattr(wcnf, '_neg_soft_total'):
                wcnf._neg_soft_total = wcnf._neg_soft_total // weight_gcd
            print(f"  [weight-norm] GCD={weight_gcd}, weights reduced {weight_gcd}x")
    wcnf._weight_gcd = weight_gcd

    # WCNF-level preprocessing: unit propagation and subsumption
    _preprocess_wcnf(wcnf)

    wcnf.topw = sum(wcnf.wght) + 1
    wcnf._encoding_stats['simplified'] = _formula_counts(wcnf)
    wcnf._encoding_stats['weight_gcd'] = weight_gcd

    print(f"  Vars: {wcnf.nv}, Hard: {len(wcnf.hard)}, Soft: {len(wcnf.soft)}, Top: {wcnf.topw}")

    # Attach preprocessing metadata and processed problem
    wcnf._preprocess_meta = preprocess_meta
    wcnf._vpool = vpool
    wcnf._processed_problem = problem

    if collect_timings:
        timings['build_total'] = time.time() - t0
        return wcnf, name2idx, timings, vpool
    return wcnf, name2idx, vpool


def solve_rc2(wcnf, phases=None):
    try:
        solver = RC2(wcnf, adapt=True, exhaust=True, trim=3)
        if phases:
            try:
                solver.oracle.set_phases(phases)
            except Exception:
                pass
        solution = solver.compute()

        if solution is None:
            solver.delete()
            return -1, []

        cost = solver.cost
        assignment = solution
        solver.delete()

        return cost, assignment

    except Exception as e:
        raise RuntimeError(f"RC2 failed: {e}")


def solve_external(wcnf, workdir, solver_path, timeout=0, greedy_cost=None):
    with tempfile.NamedTemporaryFile(suffix='.wcnf', dir=workdir, delete=False) as f:
        wcnf_path = f.name
    try:
        wcnf.to_file(wcnf_path)
        cmd = [solver_path]
        if os.path.basename(solver_path).lower().startswith('maxhs'):
            cmd.extend(['-printSoln', '-printSoln-old-format'])
        if timeout and timeout > 0:
            cmd.append(f'-cpu-lim={int(timeout)}')
        cmd.append(wcnf_path)
        timed_out = False
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=int(timeout) + 30 if timeout and timeout > 0 else None)
            output, returncode = proc.stdout or '', proc.returncode
            if returncode not in (0, 1, 10, 20, 30):
                raise RuntimeError(f'external solver failed: rc={returncode}; {(proc.stderr or "")[-2000:]}')
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ''
            if isinstance(output, bytes):
                output = output.decode(errors='replace')
            returncode, timed_out = 0, True
        status_line, cost, model_lines = '', None, []
        in_model = False
        for raw in output.splitlines():
            line = raw.strip()
            if line.startswith('s '):
                status_line = line[2:].strip()
                in_model = False
            elif line.startswith('o '):
                cost = int(line.split()[1])
                in_model = False
            elif line.startswith('v '):
                if not in_model:
                    model_lines = []
                model_lines.append(line[2:].strip())
                in_model = True
        declared = {'OPTIMUM FOUND': 'OPTIMAL', 'SATISFIABLE': 'FEASIBLE',
                    'UNSATISFIABLE': 'UNSAT'}.get(status_line)
        exit_status = {10: 'FEASIBLE', 20: 'UNSAT', 30: 'OPTIMAL'}.get(returncode)
        if declared and exit_status and ((declared == 'UNSAT') != (exit_status == 'UNSAT')):
            return -1, None, 'INVALID'
        status = declared or exit_status
        if status == 'UNSAT':
            return -1, None, status
        if not model_lines and wcnf.nv:
            if status in ('OPTIMAL', 'FEASIBLE'):
                return -1, None, 'INVALID'
            return -1, None, 'TIMEOUT' if timed_out or timeout else 'UNKNOWN'
        tokens = ' '.join(model_lines).split()
        if len(tokens) == 1 and len(tokens[0]) == wcnf.nv and set(tokens[0]) <= {'0', '1'}:
            assignment = [i if bit == '1' else -i for i, bit in enumerate(tokens[0], 1)]
        else:
            assignment = [int(token) for token in tokens if token != '0']
        signed = set(assignment)
        if any(-lit in signed for lit in signed) or any(not any(lit in signed for lit in clause) for clause in wcnf.hard):
            return -1, assignment, 'INVALID'
        actual_cost = sum(weight for clause, weight in zip(wcnf.soft, wcnf.wght)
                          if not any(lit in signed for lit in clause))
        if cost is not None and cost != actual_cost:
            return -1, assignment, 'INVALID'
        return actual_cost, assignment, 'OPTIMAL' if status == 'OPTIMAL' else 'FEASIBLE'
    finally:
        os.unlink(wcnf_path)

def build_and_solve(problem, encoding, cfg, solver='RC2', collect_timings=True, output_path=None):
    t_start = time.time()

    # Build WCNF
    build_result = build_wcnf(problem, encoding, cfg, collect_timings=collect_timings)
    if collect_timings:
        wcnf, name2idx, build_timings, vpool = build_result
    else:
        wcnf, name2idx, vpool = build_result
        build_timings = {}

    if output_path is not None:
        wcnf.to_file(output_path)

    processed_problem = wcnf._processed_problem

    # Solve
    t_solve = time.time()
    solver_upper = solver.upper()
    ext_solver_status = None
    if solver_upper == 'RC2':
        cost, assignment = solve_rc2(wcnf)
        ext_solver_status = 'OPTIMAL' if cost >= 0 else 'UNSAT'
    elif solver_upper in ('MAXHS', 'WMAXCDCL', 'OPENWBO'):
        path_map = {
            'MAXHS': cfg.maxhs_path,
            'WMAXCDCL': cfg.wmaxcdcl_path,
            'OPENWBO': cfg.openwbo_path,
        }
        cost, assignment, ext_solver_status = solve_external(
            wcnf,
            cfg.workdir,
            path_map[solver_upper],
            timeout=getattr(cfg, 'external_solver_timeout', 0)
        )
    else:
        raise ValueError(f"Unsupported solver: {solver}")
    solve_time = time.time() - t_solve

    total_soft_weight = sum(wcnf.wght)
    objective_exact = None
    objective_value = None
    if cost >= 0 and ext_solver_status in ('OPTIMAL', 'FEASIBLE'):
        shifted = ((total_soft_weight - cost) - getattr(wcnf, '_neg_soft_total', 0)) * wcnf._weight_gcd
        meta_obj = (wcnf._preprocess_meta or {}).get('objective', {})
        objective_exact = Fraction(shifted) * Fraction(meta_obj.get('scale_gcd', 1), meta_obj.get('scale_lcm', 1))
        objective_exact += meta_obj.get('constant_shift', 0)
        if meta_obj.get('sense_flip', False):
            objective_exact = -objective_exact
        objective_value = int(objective_exact) if objective_exact.denominator == 1 else float(objective_exact)

    total_time = time.time() - t_start

    use_decomp = (
        encoding == 'BIN' and
        cfg is not None and
        getattr(cfg, 'use_decomposition', False)
    )

    result = {
        'encoding': encoding,
        'use_decomposition': use_decomp,
        'solver': solver,
        'solver_status': ext_solver_status,
        'objective_value': objective_value,
        'objective_value_exact': str(objective_exact) if objective_exact is not None else None,
        'processed_problem': processed_problem,
        'maxsat_cost': cost,
        'total_soft_weight': total_soft_weight,
        'num_variables': wcnf.nv,
        'num_hard_clauses': len(wcnf.hard),
        'num_soft_clauses': len(wcnf.soft),
        'top_weight': wcnf.topw,
        'assignment': assignment,
        'name2idx': name2idx,
        'vpool': vpool
    }
    result['encoding_stats'] = wcnf._encoding_stats

    if collect_timings:
        result['timings'] = {
            **build_timings,
            'solve': solve_time,
            'total': total_time
        }

    if hasattr(wcnf, '_preprocess_meta') and wcnf._preprocess_meta is not None:
        result['preprocess_meta'] = wcnf._preprocess_meta

    if ext_solver_status in ('OPTIMAL', 'FEASIBLE'):
        check_start = time.time()
        check_result = result
        if ext_solver_status == 'FEASIBLE':
            check_result = {**result, 'objective_value': None, 'objective_value_exact': None}
        valid, report = verify_solution(problem, check_result, encoding)
        if valid and ext_solver_status == 'FEASIBLE':
            result['encoded_objective_value_exact'] = result['objective_value_exact']
            result['objective_value_exact'] = report['computed_objective_exact']
            result['objective_value'] = report['computed_objective']
            report['reported_objective'] = result['objective_value']
        result['verification'] = report
        result['verified'] = valid
        if collect_timings:
            result['timings']['verify'] = time.time() - check_start
        if not valid:
            result['solver_status'] = 'INVALID'
    return result
