"""Independent finite-domain oracles for the AIJ compilation pipeline."""
import contextlib
import copy
from fractions import Fraction
import io
import itertools
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'codes'))
from pysat.formula import WCNF
from pysat.solvers import Solver
from solver.config import EncodingConfig
from solver.solve import build_and_solve, build_wcnf, _preprocess_wcnf
from tools.verify import verify_solution
from tools.smt2_parser import parse_smt2_file


def term(c, **powers):
    return {'c': c, 'vars': powers}


def atom(terms, rel, rhs):
    return {'terms': terms, 'rel': rel, 'rhs': rhs}


def poly(terms, values):
    total = Fraction(0)
    for t in terms:
        value = Fraction(str(t.get('c', 1)))
        for name, power in t['vars'].items():
            value *= values[name] ** power
        total += value
    return total


def holds(c, values):
    if c.get('type') == 'disjunction':
        return any(all(holds(a, values) for a in branch) for branch in c['disjuncts'])
    lhs, rhs = poly(c.get('terms', c.get('lhs', [])), values), Fraction(str(c['rhs']))
    rel = c.get('rel', c.get('sense', '<='))
    return {'<': lhs < rhs, '<=': lhs <= rhs, '>': lhs > rhs, '>=': lhs >= rhs,
            '=': lhs == rhs, '==': lhs == rhs}[rel]


def oracle(problem):
    names = list(problem['variables'])
    domains = [range(v['lb'], v['ub'] + 1) for v in problem['variables'].values()]
    feasible = []
    for values in itertools.product(*domains):
        assignment = dict(zip(names, values))
        if all(holds(c, assignment) for c in problem['constraints']):
            feasible.append((poly(problem['objective']['terms'], assignment), assignment))
    if not feasible:
        return None
    fn = min if problem['objective']['sense'].startswith('min') else max
    return fn(v for v, _ in feasible)


def problem(variables, objective, constraints=(), sense='max'):
    return {'variables': {n: {'lb': lo, 'ub': hi} for n, (lo, hi) in variables.items()},
            'objective': {'sense': sense, 'terms': objective}, 'constraints': list(constraints)}


class Correctness(unittest.TestCase):
    def compare(self, p, no_preprocess=False):
        expected = oracle(p)
        for enc, decomp in [('OH', False), ('UNA', False), ('BIN', False), ('BIN', True)]:
            with self.subTest(encoding=enc, decomp=decomp, problem=p):
                cfg = EncodingConfig(use_decomposition=decomp, enable_preprocess=not no_preprocess)
                with contextlib.redirect_stdout(io.StringIO()):
                    result = build_and_solve(p, enc, cfg)
                self.assertEqual(result['solver_status'], 'UNSAT' if expected is None else 'OPTIMAL')
                if expected is not None:
                    self.assertEqual(Fraction(result['objective_value_exact']), expected)
                    ok, report = verify_solution(p, result, enc)
                    self.assertTrue(ok, report)
                    values = report['var_values']
                    self.assertEqual(set(values), set(p['variables']))
                    self.assertTrue(all(p['variables'][n]['lb'] <= v <= p['variables'][n]['ub']
                                        for n, v in values.items()))
                    self.assertTrue(all(holds(c, values) for c in p['constraints']))
                    self.assertEqual(poly(p['objective']['terms'], values), expected)

    def test_unit_propagation_contradiction(self):
        w = WCNF()
        w.extend([[1], [2], [-1, -2]])
        _preprocess_wcnf(w)
        with Solver(bootstrap_with=w.hard) as s:
            self.assertFalse(s.solve())

    def test_conditional_product_sharing(self):
        # The true product is 2, so both branches are false.
        cons = {'type': 'disjunction', 'disjuncts': [
            [atom([term(1, x=1, y=1)], '<=', 1)],
            [atom([term(1, x=1, y=1)], '>=', 3)]]}
        p = problem({'x': (0, 2), 'y': (0, 2)}, [], [cons])
        for enc, dec in [('OH', False), ('UNA', False), ('BIN', False), ('BIN', True)]:
            with self.subTest(enc=enc, decomposition=dec):
                with contextlib.redirect_stdout(io.StringIO()):
                    w, mapping, vp = build_wcnf(p, enc, EncodingConfig(use_decomposition=dec, decomp_threshold=2))
                fixed = []
                for n, value in [('x', 2), ('y', 1)]:
                    for r in range(2 if enc == 'BIN' else 3):
                        bit = (value >> r) & 1 if enc == 'BIN' else (r == value if enc == 'OH' else r <= value)
                        v = vp.id(f'x_{mapping[n]}@{r}')
                        fixed.append(v if bit else -v)
                with Solver(bootstrap_with=w.hard) as s:
                    self.assertFalse(s.solve(assumptions=fixed))

    def test_nonlinear_bound_tightening(self):
        self.compare(problem({'x': (0, 2), 'y': (0, 2)}, [term(1, x=1), term(1, y=1)],
                             [atom([term(1, x=1), term(1, y=1), term(-1, x=1, y=1)], '<=', 0)]))

    def test_strict_rational_bound(self):
        self.compare(problem({'x': (0, 2), 'y': (0, 2)}, [term(1, x=1), term(1, y=1)],
                             [atom([term(2, x=1), term(2, y=1)], '<', 3)]))

    def test_high_degree_probing(self):
        self.compare(problem({'x': (0, 1), 'y': (0, 1), 'z': (0, 1)},
                             [term(-1, x=1), term(10, x=1, y=1, z=1)]))

    def test_failed_linearization_does_not_publish_cache(self):
        self.compare(problem({'x': (0, 1), 'y': (0, 1), 'z': (0, 1)},
                             [term(1, x=1), term(1, y=1)],
                             [atom([term(1, x=1, y=1), term(1, x=1, y=1, z=1)], '>=', 0),
                              atom([term(1, x=1, y=1)], '<=', 0)]))

    def test_fractional_constant_and_shifts(self):
        self.compare(problem({'x': (0, 2)}, [term('0.5', x=1), term('0.25')]))
        self.compare(problem({'x': (-2, 2)}, [term('0.5', x=2), term('0.25')], sense='min'))
        self.compare(problem({'x': (2, 4)}, [term(1, x=1)], sense='min'), no_preprocess=True)
        self.compare(problem({'x': (-2, 2)}, [term('1/3', x=2), term('1/7')], sense='min'))

    def test_empty_domain(self):
        self.compare(problem({'x': (2, 1)}, [term(1, x=1)]))

    def test_wrong_model_must_fail(self):
        p = problem({'x': (0, 1)}, [term(1, x=1)])
        ok, report = verify_solution(p, {'assignment': [1], 'name2idx': {}, 'objective_value': 2}, 'BIN')
        self.assertFalse(ok, report)

    def test_smt_large_integer_and_boolean_constants(self):
        for assertions in ['(assert false)', '(assert true)',
                           '(assert (= (* 9007199254740992 x) 9007199254740993))']:
            with self.subTest(assertions=assertions), tempfile.TemporaryDirectory() as d:
                f = Path(d) / 'input.smt2'
                f.write_text('(declare-const x Int)\n(assert (>= x 0))\n(assert (<= x 1))\n' + assertions)
                p = parse_smt2_file(str(f), objective_mode='zero')
                expected = None if assertions != '(assert true)' else 0
                self.assertEqual(oracle(p), expected)
                self.compare(p)

    def test_seeded_finite_domain_oracle(self):
        rng = random.Random(92817)
        for case in range(60):
            names = ['x', 'y', 'z'][:2 + case % 2]
            domains = {n: (rng.choice([-1, 0, 1]), rng.choice([2, 3])) for n in names}
            def terms():
                result = []
                for _ in range(rng.randrange(1, 5)):
                    powers = {}
                    for _ in range(rng.randrange(4)):
                        n = rng.choice(names)
                        powers[n] = powers.get(n, 0) + 1
                    result.append(term(str(Fraction(rng.choice([-3, -2, -1, 1, 2, 3]), rng.choice([1, 2]))), **powers))
                return result
            constraints = []
            for _ in range(rng.randrange(3)):
                a = atom(terms(), rng.choice(['<=', '>=', '==', '<', '>']), rng.randrange(-2, 5))
                if rng.random() < .3:
                    a = {'type': 'disjunction', 'disjuncts': [[a], [atom(terms(), '<=', 2)]]}
                constraints.append(a)
            with self.subTest(case=case):
                self.compare(problem(domains, terms(), constraints, rng.choice(['min', 'max'])))


if __name__ == '__main__':
    unittest.main(verbosity=2)
