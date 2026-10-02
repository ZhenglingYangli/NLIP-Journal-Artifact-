"""Exhaustive original semantics, independent of DW/IW counters and SMT IR."""
from fractions import Fraction
from itertools import product, combinations
from math import ceil, floor
from pathlib import Path
import argparse
import json
import random
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent/'nlipsat-aij'/'codes'), str(ROOT.parent/'nlipsat-aij')]
import diverse_baseline as diverse
import cvc5_baseline as cvc
from pysat.solvers import Solver
from run_batch import load_config


def evaluate(terms, point):
    result = Fraction(0)
    for term in terms:
        value = Fraction(str(term.get('c', 1)))
        for name, exponent in term.get('vars', {}).items():
            value *= point[name]**exponent
        result += value
    return result


def satisfies(atom, point):
    if atom.get('type') == 'disjunction':
        return any(all(satisfies(a, point) for a in branch) for branch in atom['disjuncts'])
    a, b = evaluate(atom['terms'], point), Fraction(str(atom['rhs']))
    return {'=': a == b, '<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[atom['rel']]


def test_diverse(work, config):
    cases = [('two', 2, [[1, 2], [-1, -2]], 2),
             ('unique', 2, [[1], [-2]], 2),
             ('unsat', 2, [[]], 2),
             ('unused', 3, [[1], [2, -2], [1, 1]], 2),
             ('negative-weights', 2, [[1, 2]], 4),
             ('zero-weight', 1, [], 5)]
    rows, projections = [], 0
    for name, n, clauses, k in cases:
        names = [f'x{j}_m{i}' for i in range(1, k+1) for j in range(1, n+1)]
        feasible_values = []
        for encoding in ('DW', 'IW'):
            formula, original, offset = diverse.build_wcnf(n, clauses, k, encoding)
            with Solver(name='cadical195') as sat:
                for clause in formula.hard:
                    sat.add_clause(clause)
                for point in product((0, 1), repeat=n*k):
                    values = dict(zip(names, point))
                    feasible = all(any(values[f'x{abs(l)}_m{i}'] == int(l > 0) for l in clause)
                                   for clause in clauses for i in range(1, k+1))
                    distance = sum(values[f'x{j}_m{a}'] != values[f'x{j}_m{b}']
                                   for a, b in combinations(range(1, k+1), 2) for j in range(1, n+1))
                    if feasible and encoding == 'DW':
                        feasible_values.append(distance)
                    truth = sat.solve(assumptions=[v if values[nm] else -v for nm, v in original.items()])
                    assert truth == feasible, (name, encoding, point, 'CNF feasibility')
                    if truth:
                        signed = set(sat.get_model())
                        cost = sum(w for cl, w in zip(formula.soft, formula.wght) if not any(l in signed for l in cl))
                        assert offset-cost == distance, (name, encoding, point, cost, distance)
                    model, _ = diverse.build_scip(n, clauses, k, encoding, forced=values)
                    model.setRealParam('limits/time', 5.)
                    model.optimize()
                    status = str(model.getStatus())
                    assert status == ('optimal' if feasible else 'infeasible'), (name, encoding, status)
                    if feasible:
                        assert abs(model.getObjVal()-distance) < 1e-6
                    model.freeProb()
                    projections += 2
        optimum = max(feasible_values) if feasible_values else None
        path = work/(name+'.cnf')
        path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str, c))+' 0\n' for c in clauses))
        for encoding in ('DW', 'IW'):
            for backend in ('SCIP', 'RC2', 'MAXHS', 'WMAXCDCL'):
                result = diverse.solve(path, k, encoding, backend, 10, work, config['solver_paths'])
                assert result['status'] == ('UNSAT' if optimum is None else 'OPTIMAL'), (name, encoding, backend, result)
                if optimum is not None:
                    assert result['verified'] and int(result['objective_exact']) == optimum
                rows.append({'case': name, 'encoding': encoding, 'backend': backend,
                             'status': result['status'], 'optimum': optimum})
        print('Diverse SAT:', name, 'passed', flush=True)
    return {'cases': len(cases), 'projection_checks': projections, 'optimization_checks': len(rows), 'results': rows}


def term(c=1, **powers):
    return {'c': c, 'vars': powers}


def atom(terms, rel, rhs):
    return {'terms': terms, 'rel': rel, 'rhs': rhs}


def problem(bounds, terms, constraints=(), sense='max'):
    return {'variables': {n: {'lb': a, 'ub': b} for n, (a, b) in bounds.items()},
            'objective': {'sense': sense, 'terms': terms}, 'constraints': list(constraints)}


def test_cvc(work):
    cases = [
        ('fractional', problem({'x': (-1, 2), 'y': (0, 2)}, [term('2/3', x=2, y=1), term('-1/5', y=2)],
                               [atom([term('1/3', x=1), term('1/2', y=1)], '<', '5/6')])),
        ('cubic-min', problem({'x': (-2, 1)}, [term('-2/3', x=3), term('1/7')], sense='min')),
        ('fractional-equality', problem({'x': (0, 2)}, [term(x=1)], [atom([term(2, x=1)], '=', 1)])),
        ('nested-or', problem({'x': (-1, 1)}, [term(x=2)], [{'type': 'disjunction', 'disjuncts': [
            [atom([term(x=1)], '>', 3)], [{'type': 'disjunction', 'disjuncts': [
                [atom([term(x=1)], '=', -1)], [atom([term(x=1)], '=', 1)]]}]]}])),
        ('empty-or', problem({}, [], [{'type': 'disjunction', 'disjuncts': []}])),
        ('empty-branch', problem({'x': (-1, 1)}, [term(x=1)], [{'type': 'disjunction', 'disjuncts': [[]]}])),
        ('constant', problem({}, [term('-7/3')])),
        ('rational-domain', problem({'x': ('-3/2', '5/2')}, [term(x=3)])),
        ('empty-domain', problem({'x': (2, 1)}, [term(x=1)])),
    ]
    rng = random.Random(20260911)
    for i in range(12):
        terms = [term(rng.choice([-3, -1, 2, 4]), x=rng.randrange(4), y=rng.randrange(3)) for _ in range(3)]
        cons = [atom([term(1, x=2), term(-1, y=1)], rng.choice(['<', '>', '<=', '>=', '=']), rng.randrange(-2, 4))]
        cases.append((f'random-{i}', problem({'x': (-1, 2), 'y': (-1, 1)}, terms, cons, 'min' if i % 2 else 'max')))
    rows, projections = [], 0
    for name, p in cases:
        feasible = []
        tm, solver, variables, _, _, _, _ = cvc.build_model(p)
        names = list(p['variables'])
        points = product(*(range(ceil(Fraction(str(v['lb']))), floor(Fraction(str(v['ub'])))+1) for v in p['variables'].values()))
        for values in points:
            point = dict(zip(names, values))
            expected = all(satisfies(a, point) for a in p['constraints'])
            solver.push()
            for n, value in point.items():
                solver.assertFormula(tm.mkTerm(cvc.K.EQUAL, variables[n], tm.mkInteger(value)))
            answer = cvc.check(solver, time.monotonic()+5)
            assert answer is not None and not answer.isUnknown()
            assert answer.isSat() == expected, (name, point, expected, str(answer))
            solver.pop()
            projections += 1
            if expected:
                feasible.append(evaluate(p['objective']['terms'], point))
        optimum = (max(feasible) if p['objective']['sense'] == 'max' else min(feasible)) if feasible else None
        result = cvc.solve(p, 10)
        assert result['status'] == ('UNSAT' if optimum is None else 'OPTIMAL'), (name, result)
        if optimum is not None:
            assert result['verified'] and Fraction(result['objective_exact']) == optimum, (name, result, optimum)
        rows.append({'case': name, 'status': result['status'], 'optimum': str(optimum) if optimum is not None else None})
    smt_cases = [
        ('bool-quoted', '(declare-const |x spaced| Int) (declare-const b Bool) (assert (and (= |x spaced| -2) b))', 'SAT'),
        ('nonlinear-unsat', '(declare-const x Int) (assert (= (* x x) 2))', 'UNSAT'),
        ('defined', '(declare-const x Int) (define-fun sq ((a Int)) Int (* a a)) (assert (= x -2)) (assert (= (sq x) 4))', 'SAT'),
    ]
    for name, body, expected in smt_cases:
        path = work/(name+'.smt2')
        path.write_text('(set-logic QF_NIA)\n'+body+'\n(check-sat)\n')
        result = cvc.solve_smt2(path, 5)
        assert result['status'] == expected, (name, result)
        if expected == 'SAT':
            assert result['verified']
        rows.append({'case': name, 'status': result['status']})
    # Stop during optimization after a first SAT answer: retain only FEASIBLE.
    original_check = cvc.check
    calls = 0
    def stop_after_one(solver, deadline):
        nonlocal calls
        calls += 1
        return original_check(solver, deadline) if calls == 1 else None
    cvc.check = stop_after_one
    try:
        p = problem({'x': (0, 2)}, [term(x=1)], [atom([term(x=1)], '<=', 1)])
        result = cvc.solve(p, 5)
        assert calls >= 2 and result['status'] == 'FEASIBLE' and result['verified'], result
    finally:
        cvc.check = original_check
    rows.append({'case': 'interrupted-search-incumbent', 'status': result['status']})
    print('cvc5: all original polynomial and SMT cases passed', flush=True)
    return {'polynomial_cases': len(cases), 'projection_checks': projections, 'optimization_checks': len(cases),
            'original_smt_checks': len(smt_cases), 'incumbent_check': 1, 'results': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    args = parser.parse_args()
    config = load_config(args.config)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='aij-baselines-') as directory:
        work = Path(directory)
        report = {'diverse': test_diverse(work, config), 'cvc5': test_cvc(work)}
    report['seconds'] = time.monotonic()-start
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print('All extended-baseline checks passed.', flush=True)
