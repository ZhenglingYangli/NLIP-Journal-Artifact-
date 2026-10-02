"""Independent exact Boolean-product MILP and native polynomial SCIP models."""
from fractions import Fraction
from functools import reduce
from math import ceil, floor, gcd, lcm
from pathlib import Path
import sys
import time

# Prefer the active interpreter's packages over a legacy --target installation.
sys.path.append(str(Path(__file__).with_name('baseline-deps')))
from pyscipopt import Model, quicksum
import pyscipopt


def number(x):
    return Fraction(str(x))


def product(a, b):
    out = {}
    for ka, ca in a.items():
        for kb, cb in b.items():
            key = ka | kb
            out[key] = out.get(key, 0) + ca * cb
    return {k: c for k, c in out.items() if c}


def integer_polynomial(terms):
    merged = {}
    for term in terms:
        key = tuple(sorted((n, int(k)) for n, k in term.get('vars', {}).items() if k))
        if any(k < 0 for _, k in key):
            raise ValueError('negative exponent outside polynomial scope')
        merged[key] = merged.get(key, Fraction(0)) + number(term.get('c', 1))
    merged = {key: c for key, c in merged.items() if c}
    scale = lcm(*(v.denominator for v in merged.values())) if merged else 1
    return {key: int(c * scale) for key, c in merged.items()}, scale


def interval(poly, bounds):
    low = high = 0
    for key, c in poly.items():
        lo = hi = 1
        for name, power in key:
            a, b = bounds[name]
            ends = [a ** power, b ** power]
            if power % 2 == 0 and a <= 0 <= b:
                ends.append(0)
            x, y = min(ends), max(ends)
            products = [lo*x, lo*y, hi*x, hi*y]
            lo, hi = min(products), max(products)
        low += min(c*lo, c*hi)
        high += max(c*lo, c*hi)
    return low, high


def exact_double_integer(value):
    if abs(value) > 2**53:
        raise ValueError('UNSUPPORTED_NUMERIC_RANGE: integer coefficient or bound exceeds 2^53')
    return int(value)


def build_model(problem, route, forced=None):
    if route not in ('milp', 'native'):
        raise ValueError(route)
    model = Model('NLIP_' + route)
    model.hideOutput()
    model.setIntParam('parallel/maxnthreads', 1)
    model.setRealParam('numerics/feastol', 1e-9)
    model.setRealParam('limits/gap', 0.0)
    model.setRealParam('limits/absgap', 0.0)
    model.setIntParam('randomization/randomseedshift', 0)
    bounds = {n: (ceil(number(v['lb'])), floor(number(v['ub'])))
              for n, v in problem.get('variables', {}).items()}
    if any(a > b for a, b in bounds.values()):
        model.addCons(quicksum([]) <= -1)
        return model, {}, {'route': route, 'empty_domain': True}
    original, bits, expansions, gates = {}, {}, {}, {}
    for n, (lo, hi) in bounds.items():
        exact_double_integer(lo); exact_double_integer(hi)
        if route == 'native':
            original[n] = model.addVar(name=n, vtype='I', lb=lo, ub=hi)
        else:
            width = hi-lo
            expansions[n] = {frozenset(): lo} if lo else {}
            for j in range(width.bit_length()):
                key = (n, j)
                bits[key] = model.addVar(name=f'b{len(bits)}', vtype='B')
                expansions[n][frozenset([key])] = 1 << j
            original[n] = lo + quicksum((1 << j)*bits[n, j] for j in range(width.bit_length()))
            model.addCons(original[n] <= hi)
        if forced is not None:
            model.addCons(original[n] == forced[n])

    def expression(poly):
        if route == 'native':
            return quicksum(exact_double_integer(c) * reduce(lambda a,b: a*b,
                (original[n] ** k for n,k in key), 1) for key,c in poly.items())
        total = {}
        for key, c in poly.items():
            expanded = {frozenset(): c}
            for n, power in key:
                for _ in range(power):
                    expanded = product(expanded, expansions[n])
            for support, coef in expanded.items():
                total[support] = total.get(support, 0) + coef
        summands = []
        for support, c in total.items():
            if not c:
                continue
            c = exact_double_integer(c)
            if not support:
                summands.append(c)
            elif len(support) == 1:
                summands.append(c * bits[next(iter(support))])
            else:
                if support not in gates:
                    z = model.addVar(name=f'p{len(gates)}', vtype='C', lb=0, ub=1)
                    inputs = [bits[b] for b in sorted(support)]
                    for b in inputs:
                        model.addCons(z <= b)
                    model.addCons(z >= quicksum(inputs)-len(inputs)+1)
                    gates[support] = z
                summands.append(c*gates[support])
        return quicksum(summands)

    def constraint(atom, guard=None):
        if atom.get('type') == 'disjunction':
            selectors = []
            for branch in atom.get('disjuncts', []):
                selector = model.addVar(vtype='B')
                selectors.append(selector)
                if guard is not None:
                    model.addCons(selector <= guard)
                for child in branch:
                    constraint(child, selector)
            model.addCons(quicksum(selectors) >= (1 if guard is None else guard))
            return
        poly, scale = integer_polynomial(atom.get('terms', atom.get('lhs', [])))
        rhs = number(atom.get('rhs', 0))*scale
        divisor = reduce(gcd, (abs(c) for c in poly.values()), 0) or 1
        poly = {key: c//divisor for key,c in poly.items()}
        rhs /= divisor
        expr = expression(poly)
        lo, hi = interval(poly, bounds)
        rel = atom.get('rel', atom.get('sense', '<='))
        def upper(bound):
            m = exact_double_integer(max(0, hi-bound)) if guard is not None else 0
            model.addCons(expr <= exact_double_integer(bound) + (m*(1-guard) if guard is not None else 0))
        def lower(bound):
            m = exact_double_integer(max(0, bound-lo)) if guard is not None else 0
            model.addCons(expr >= exact_double_integer(bound) - (m*(1-guard) if guard is not None else 0))
        if rel == '<=': upper(floor(rhs))
        elif rel == '<': upper(ceil(rhs)-1)
        elif rel == '>=': lower(ceil(rhs))
        elif rel == '>': lower(floor(rhs)+1)
        elif rel in ('=', '=='):
            upper(floor(rhs)); lower(ceil(rhs))
        else: raise ValueError('unsupported relation: '+rel)

    for atom in problem.get('constraints', []):
        constraint(atom)
    objective = problem.get('objective', {})
    poly, scale = integer_polynomial(objective.get('terms', []))
    constant = poly.pop((), 0)
    divisor = reduce(gcd, (abs(c) for c in poly.values()), 0) or 1
    poly = {key: c//divisor for key,c in poly.items()}
    expr = expression(poly)
    sense = 'minimize' if objective.get('sense', 'max').lower() in ('min', 'minimize') else 'maximize'
    if route == 'native' and any(sum(k for _,k in key)>1 for key in poly):
        lo, hi = interval(poly, bounds)
        t = model.addVar(name='objective_value', lb=exact_double_integer(lo), ub=exact_double_integer(hi))
        model.addCons(t <= expr if sense == 'maximize' else t >= expr)
        model.setObjective(t, sense)
    else:
        model.setObjective(expr, sense)
    stats = {'route': route, 'variables': model.getNVars(), 'constraints': model.getNConss(),
             'domain_bits': len(bits), 'product_variables': len(gates),
             'objective_scale': scale, 'objective_divisor': divisor, 'objective_constant': constant,
             'feasibility_tolerance': 1e-9, 'relative_gap': 0.0, 'absolute_gap': 0.0,
             'pyscipopt': pyscipopt.__version__, 'scip_version': f'{model.getMajorVersion()}.{model.getMinorVersion()}.{model.getTechVersion()}'}
    return model, original, stats


def solve(problem, route, seconds, task='optimization', begin_verify=lambda: None):
    from telemetry import progress, quality
    if problem.get('objective', {}).get('factor_blocks'):
        return {'status': 'UNSUPPORTED', 'verified': False, 'error': 'baseline input requires an explicit polynomial, not factor_blocks'}
    start = time.monotonic()
    model, original, stats = build_model(problem, route)
    build = time.monotonic()-start
    progress('solve', formula=stats, solver_timings={'build':build})
    remaining = seconds-build
    if remaining <= 0:
        return {'status': 'TIMEOUT', 'verified': False, 'formula': stats}
    model.setRealParam('limits/time', remaining)
    model.optimize()
    solved = time.monotonic()
    status = str(model.getStatus())
    result = {'status': 'UNSAT' if status=='infeasible' else 'TIMEOUT' if status=='timelimit' else 'UNKNOWN',
              'backend_status': status, 'verified': False, 'objective_exact': None,
              'formula': stats, 'solver_timings': {'build': build, 'solve': solved-start-build},
              'optimality_certificate': 'SCIP numerical tolerances; original witness checked exactly',
              'primal_bound': model.getPrimalbound(), 'dual_bound': model.getDualbound()}
    primal, dual = model.getPrimalbound(), model.getDualbound()
    result['quality'] = quality(stats, primal if model.getNSols() and not model.isInfinity(abs(primal)) else None,
                                dual if not model.isInfinity(abs(dual)) else None,
                                model.getGap() if model.getNSols() else None, model.getNNodes())
    progress(quality=result['quality'])
    if model.getNSols():
        begin_verify()
        sol = model.getBestSol()
        values = {n: round(model.getSolVal(sol, v)) for n,v in original.items()}
        if any(abs(model.getSolVal(sol,v)-values[n]) > 1e-6 for n,v in original.items()):
            raise ValueError('nonintegral original witness')
        from tools.verify import verify_values
        value, checks, source = verify_values(problem, values)
        encoded = (number(value)*stats['objective_scale']-stats['objective_constant'])/stats['objective_divisor']
        if status == 'optimal' and abs(float(encoded)-model.getSolObjVal(sol)) > 1e-6:
            raise ValueError('SCIP objective and original objective disagree')
        result.update(status='SAT' if task=='decision' else 'OPTIMAL' if status=='optimal' else 'FEASIBLE',
                      verified=True, objective_exact=str(value) if task=='optimization' else None,
                      witness=values, encoded_incumbent_objective=model.getSolObjVal(sol),
                      verification={'constraint_checks': checks, 'source_smt_verified': source})
        result['solver_timings']['verify'] = time.monotonic()-solved
    return result
