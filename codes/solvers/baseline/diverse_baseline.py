"""JFPC 2025 DW/IW formulations, reimplemented for tuple Diverse SAT."""
from itertools import combinations
from pathlib import Path
import time


def verify(n, clauses, k, values):
    expected = {f'x{j}_m{i}' for i in range(1, k+1) for j in range(1, n+1)}
    if set(values) != expected or any(v not in (0, 1) for v in values.values()):
        raise ValueError('incomplete or non-Boolean Diverse SAT witness')
    for i in range(1, k+1):
        if not all(any(values[f'x{abs(l)}_m{i}'] == int(l > 0) for l in c) for c in clauses):
            raise ValueError('Diverse SAT witness violates original CNF')
    distance = sum(values[f'x{j}_m{a}'] != values[f'x{j}_m{b}']
                   for a, b in combinations(range(1, k+1), 2) for j in range(1, n+1))
    distinct = len({tuple(values[f'x{j}_m{i}'] for j in range(1, n+1)) for i in range(1, k+1)})
    return distance, distinct


def build_scip(n, clauses, k, encoding, forced=None):
    from solvers.baseline.scip_baseline import Model, quicksum
    if encoding not in ('DW', 'IW') or k < 2:
        raise ValueError('expected DW/IW and k >= 2')
    model = Model('DiverseSAT_' + encoding)
    model.hideOutput()
    model.setIntParam('parallel/maxnthreads', 1)
    model.setIntParam('randomization/randomseedshift', 0)
    model.setRealParam('numerics/feastol', 1e-9)
    model.setRealParam('limits/gap', 0.)
    model.setRealParam('limits/absgap', 0.)
    v = {(i, j): model.addVar(name=f'x{j}_m{i}', vtype='B')
         for i in range(1, k+1) for j in range(1, n+1)}
    for i in range(1, k+1):
        for clause in clauses:
            model.addCons(quicksum(v[i, abs(l)] if l > 0 else 1-v[i, abs(l)] for l in clause) >= 1)
    objective = []
    for j in range(1, n+1):
        r_values = range(0 if encoding == 'DW' else 1, k+1)
        u = {r: model.addVar(name=f'u{j}_{r}', vtype='B') for r in r_values}
        total = quicksum(v[i, j] for i in range(1, k+1))
        if encoding == 'DW':
            model.addCons(quicksum(u.values()) == 1)
            model.addCons(quicksum(r*u[r] for r in u) == total)
            objective.extend(r*(k-r)*u[r] for r in u)
        else:
            for r in range(2, k+1):
                model.addCons(u[r] <= u[r-1])
            model.addCons(quicksum(u.values()) == total)
            objective.extend((k+1-2*r)*u[r] for r in u)
    model.setObjective(quicksum(objective), 'maximize')
    original = {f'x{j}_m{i}': var for (i, j), var in v.items()}
    if forced is not None:
        for name, var in original.items():
            model.addCons(var == forced[name])
    return model, original


def build_wcnf(n, clauses, k, encoding):
    from pysat.card import CardEnc, EncType
    from pysat.pb import PBEnc
    from pysat.formula import WCNF, IDPool
    if encoding not in ('DW', 'IW') or k < 2:
        raise ValueError('expected DW/IW and k >= 2')
    pool, formula = IDPool(), WCNF()
    v = {(i, j): pool.id(f'x{j}_m{i}') for i in range(1, k+1) for j in range(1, n+1)}
    for i in range(1, k+1):
        for clause in clauses:
            formula.append([v[i, abs(l)] if l > 0 else -v[i, abs(l)] for l in clause])
    positive_sum = 0
    for j in range(1, n+1):
        u = {r: pool.id(f'u{j}_{r}') for r in range(0 if encoding == 'DW' else 1, k+1)}
        negative_v = [-v[i, j] for i in range(1, k+1)]
        if encoding == 'DW':
            formula.extend(CardEnc.equals(list(u.values()), bound=1, vpool=pool,
                                          encoding=EncType.cardnetwrk).clauses)
            formula.extend(PBEnc.equals([u[r] for r in range(1, k+1)] + negative_v,
                                        weights=list(range(1, k+1)) + [1]*k,
                                        bound=k, vpool=pool).clauses)
        else:
            for r in range(2, k+1):
                formula.append([-u[r], u[r-1]])
            formula.extend(CardEnc.equals(list(u.values()) + negative_v, bound=k,
                                          vpool=pool, encoding=EncType.cardnetwrk).clauses)
        for r, literal in u.items():
            weight = r*(k-r) if encoding == 'DW' else k+1-2*r
            if weight:
                formula.append([literal if weight > 0 else -literal], weight=abs(weight))
                positive_sum += max(0, weight)
    formula.nv = max(formula.nv, pool.top)
    return formula, {f'x{j}_m{i}': var for (i, j), var in v.items()}, positive_sum


def solve(path, k, encoding, backend, seconds, workdir, solver_paths, begin_verify=lambda: None):
    from tools.diversesat_parser import _parse_cnf_raw
    start = time.monotonic()
    n, clauses = _parse_cnf_raw(path)
    if backend == 'SCIP':
        model, original = build_scip(n, clauses, k, encoding)
        stats = {'variables': model.getNVars(), 'constraints': model.getNConss()}
    else:
        formula, original, positive_sum = build_wcnf(n, clauses, k, encoding)
        stats = {'variables': formula.nv, 'hard': len(formula.hard), 'soft': len(formula.soft)}
    built = time.monotonic()
    result = {'status': 'TIMEOUT', 'verified': False, 'objective_exact': None,
              'formula': dict(stats, encoding=encoding, k=k, source='JFPC 2025 figures 3-5', semantics='tuple'),
              'solver_timings': {'build': built-start}}
    if built-start >= seconds:
        return result
    values = None
    if backend == 'SCIP':
        model.setRealParam('limits/time', seconds-(built-start))
        model.optimize()
        raw = str(model.getStatus())
        result.update(backend_status=raw, status='UNSAT' if raw == 'infeasible' else
                      'TIMEOUT' if raw == 'timelimit' else 'UNKNOWN',
                      primal_bound=model.getPrimalbound(), dual_bound=model.getDualbound(),
                      optimality_certificate='SCIP numerical tolerances; original witness checked exactly')
        if model.getNSols():
            sol = model.getBestSol()
            numeric = {name: model.getSolVal(sol, var) for name, var in original.items()}
            values = {name: round(value) for name, value in numeric.items()}
            if any(abs(numeric[name]-value) > 1e-6 for name, value in values.items()):
                raise ValueError('nonintegral Diverse SAT witness')
            encoded = model.getSolObjVal(sol)
            result['status'] = 'OPTIMAL' if raw == 'optimal' else 'FEASIBLE'
    else:
        if backend == 'RC2':
            from pysat.examples.rc2 import RC2
            with RC2(formula) as oracle:
                assignment = oracle.compute()
                cost = oracle.cost
            status = 'UNSAT' if assignment is None else 'OPTIMAL'
        else:
            from solver.solve import solve_external
            cost, assignment, status = solve_external(formula, str(Path(workdir)), solver_paths[backend], timeout=0)
        result['status'] = status
        if status in ('OPTIMAL', 'FEASIBLE'):
            signed = set(assignment)
            if any(var not in signed and -var not in signed for var in original.values()):
                raise ValueError('missing original variable in MaxSAT witness')
            values = {name: int(var in signed) for name, var in original.items()}
            encoded = positive_sum-cost
    solved = time.monotonic()
    result['solver_timings']['solve'] = solved-built
    if values is not None:
        begin_verify()
        objective, distinct = verify(n, clauses, k, values)
        if abs(objective-encoded) > 1e-6:
            raise ValueError('encoded objective disagrees with original Hamming distance')
        result.update(verified=True, objective_exact=str(objective), witness=values,
                      verification={'original_cnf': True, 'pairwise_hamming': objective,
                                    'distinct_models': distinct, 'semantics': 'tuple'})
        result['solver_timings']['verify'] = time.monotonic()-solved
    return result
