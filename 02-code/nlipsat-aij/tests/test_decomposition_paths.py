"""Compare BIN routes on original assignments and report actual sharing."""
import contextlib
import io
import itertools
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'codes'))
from pysat.examples.rc2 import RC2
from solver.config import EncodingConfig
from solver.solve import build_wcnf, build_and_solve


def term(names, coefficient=1):
    return {'c': coefficient, 'vars': {n: names.count(n) for n in names}}


def problem(terms, ub=2, constraints=None):
    names = sorted(set(''.join(''.join(t['vars']) for t in terms)))
    return {'variables': {n: {'lb': 0, 'ub': ub} for n in names},
            'objective': {'sense': 'max', 'terms': terms},
            'constraints': constraints or []}


class DecompositionPaths(unittest.TestCase):
    def build(self, p, **options):
        cfg = EncodingConfig(enable_preprocess=False, save_wcnf=False, **options)
        with contextlib.redirect_stdout(io.StringIO()):
            return build_wcnf(p, 'BIN', cfg)

    def check_fibers(self, p, objective, feasible=lambda v: True):
        for options in ({}, {'use_decomposition': True, 'decomp_shared': False},
                        {'use_decomposition': True, 'decomp_shared': True}):
            formula, mapping, pool = self.build(p, **options)
            names = sorted(p['variables'])
            domains = [range(p['variables'][n]['ub'] + 1) for n in names]
            for values in itertools.product(*domains):
                assignment = dict(zip(names, values))
                fixed = formula.copy()
                for name, value in assignment.items():
                    for bit in range(max(1, p['variables'][name]['ub'].bit_length())):
                        var = pool.id(f'x_{mapping[name]}@{bit}')
                        fixed.append([var if (value >> bit) & 1 else -var])
                with RC2(fixed) as solver:
                    model = solver.compute()
                    self.assertEqual(model is not None, feasible(assignment), (options, assignment))
                    if model is not None:
                        score = (sum(formula.wght) - solver.cost -
                                 getattr(formula, '_neg_soft_total', 0)) * formula._weight_gcd
                        meta = formula._preprocess_meta['objective']
                        score = Fraction(score) * Fraction(meta.get('scale_gcd', 1), meta.get('scale_lcm', 1))
                        score += meta.get('constant_shift', 0)
                        if meta.get('sense_flip', False):
                            score = -score
                        self.assertEqual(score, objective(assignment), (options, assignment))

    def test_quadratic_fallback_matches_bin(self):
        p = problem([term('xx')], ub=3)
        formulas = [self.build(p, **o)[0] for o in ({},
                    {'use_decomposition': True, 'decomp_shared': False},
                    {'use_decomposition': True, 'decomp_shared': True})]
        for f in formulas:
            self.assertEqual((f.hard, f.soft, f.wght),
                             (formulas[0].hard, formulas[0].soft, formulas[0].wght))
            self.assertFalse(f._encoding_stats['decomposition_effective'])
        self.check_fibers(p, lambda v: v['x'] ** 2)

    def test_binary_fastpath_is_reported(self):
        p = problem([term('abc'), term('abd')], ub=1)
        direct = self.build(p)[0]
        for shared in (False, True):
            f = self.build(p, use_decomposition=True, decomp_shared=shared)[0]
            self.assertTrue(f._encoding_stats['objective_binary_fastpath'])
            self.assertFalse(f._encoding_stats['decomposition_effective'])
            self.assertEqual((f.hard, f.soft, f.wght), (direct.hard, direct.soft, direct.wght))

    def test_multivalued_sharing_counts_and_values(self):
        p = problem([term('abc'), term('abd')])
        for shared, nodes, hits in ((False, 4, 0), (True, 3, 1)):
            f = self.build(p, use_decomposition=True, decomp_shared=shared)[0]
            self.assertEqual(f._encoding_stats['objective'], {
                'decomposed_terms': 2, 'multiplication_requests': 4,
                'multiplication_nodes': nodes, 'cache_hits': hits})
            self.assertEqual(f._encoding_stats['simplified']['hard'], len(f.hard))
        self.check_fibers(p, lambda v: v['a'] * v['b'] * (v['c'] + v['d']))

    def test_fallback_reuses_exact_constraint_gates(self):
        p = problem([term('ab'), term('a', -1)], constraints=[
            {'terms': [term('ab')], 'rel': '<=', 'rhs': 2}])
        direct = self.build(p)[0]
        f = self.build(p, use_decomposition=True)[0]
        self.assertEqual((f.hard, f.soft, f.wght), (direct.hard, direct.soft, direct.wght))
        self.check_fibers(p, lambda v: v['a'] * v['b'] - v['a'],
                          lambda v: v['a'] * v['b'] <= 2)

    def test_mixed_degree_signed_objective(self):
        p = problem([term('abc'), term('ab', -2), term('aa')])
        self.check_fibers(p, lambda v: v['a'] * v['b'] * v['c'] -
                          2 * v['a'] * v['b'] + v['a'] ** 2)

    def test_disjunction_cache_is_branch_local(self):
        def atom(rhs):
            return {'terms': [term('abc')], 'rel': '==', 'rhs': rhs}
        p = problem([term('abc'), term('ab')], constraints=[{
            'type': 'disjunction', 'disjuncts': [[atom(0), atom(0)], [atom(8)]]}])
        f = self.build(p, use_decomposition=True)[0]
        stats = f._encoding_stats['constraints']
        self.assertEqual(stats['decomposed_terms'], 3)
        self.assertEqual(stats['multiplication_requests'], 6)
        self.assertEqual(stats['multiplication_nodes'], 4)
        self.assertEqual(stats['cache_hits'], 2)
        self.check_fibers(p, lambda v: v['a'] * v['b'] * (v['c'] + 1),
                          lambda v: v['a'] * v['b'] * v['c'] in (0, 8))
        with contextlib.redirect_stdout(io.StringIO()):
            result = build_and_solve(p, 'BIN', EncodingConfig(use_decomposition=True))
        self.assertTrue(result['verified'])
        self.assertEqual(result['objective_value_exact'], '12')
        self.assertIn('encoding_stats', result)


if __name__ == '__main__':
    unittest.main()
