"""Semantic regression tests for the unified AIJ execution code."""

from __future__ import annotations

import itertools
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import z3
from pysat.formula import IDPool
from pysat.solvers import Solver


ROOT = Path(__file__).resolve().parent.parent
CODES = ROOT / "codes"
if str(CODES) not in sys.path:
    sys.path.insert(0, str(CODES))

from encoders.decomposition import mul  # noqa: E402
from solver.config import EncodingConfig  # noqa: E402
from solver.solve import build_and_solve, build_wcnf  # noqa: E402
from tools.smt2_parser import parse_smt2_file  # noqa: E402
from tools.verify import check_constraint, verify_solution  # noqa: E402


def _lit(var: int, value: int) -> int:
    return var if value else -var


def _fixed_value_assumptions(wcnf, name2idx, encoding, original_problem, values):
    processed = wcnf._processed_problem
    shifts = (wcnf._preprocess_meta or {}).get('variable_shifts', {})
    assumptions = []
    for original_name, original_value in values.items():
        safe_name = original_problem['_name_map'][original_name]
        value = original_value - int(shifts.get(safe_name, 0))
        ub = int(processed['variables'][safe_name]['ub'])
        q = name2idx[safe_name]
        if encoding == 'OH':
            for r in range(ub + 1):
                assumptions.append(_lit(wcnf._vpool.id(f'x_{q}@{r}'), r == value))
        elif encoding == 'UNA':
            for r in range(ub + 1):
                assumptions.append(_lit(wcnf._vpool.id(f'x_{q}@{r}'), r <= value))
        else:
            nbits = max(1, math.ceil(math.log2(ub + 1)))
            for r in range(nbits):
                assumptions.append(_lit(wcnf._vpool.id(f'x_{q}@{r}'), (value >> r) & 1))
    return assumptions


class DecompositionTests(unittest.TestCase):
    def test_exact_multiplication_exhaustive(self):
        checked = 0
        for ub_a in range(1, 8):
            for ub_b in range(1, 8):
                na = max(1, math.ceil(math.log2(ub_a + 1)))
                nb = max(1, math.ceil(math.log2(ub_b + 1)))
                vpool = IDPool()
                a_bits = [vpool.id(f'a{i}') for i in range(na)]
                b_bits = [vpool.id(f'b{i}') for i in range(nb)]
                y_bits, clauses = mul(a_bits, b_bits, vpool, 'm', ub_a, ub_b, 0)
                with Solver(bootstrap_with=clauses) as solver:
                    for a in range(ub_a + 1):
                        for b in range(ub_b + 1):
                            fixed = [_lit(v, (a >> i) & 1) for i, v in enumerate(a_bits)]
                            fixed += [_lit(v, (b >> i) & 1) for i, v in enumerate(b_bits)]
                            expected = a * b
                            for y in range(1 << len(y_bits)):
                                assumptions = fixed + [
                                    _lit(v, (y >> i) & 1) for i, v in enumerate(y_bits)
                                ]
                                self.assertEqual(solver.solve(assumptions=assumptions), y == expected)
                            checked += 1
        self.assertEqual(checked, 1225)

    def test_relaxed_multiplication_is_directional(self):
        for sense in (1, -1):
            vpool = IDPool()
            a_bits = [vpool.id('a0'), vpool.id('a1')]
            b_bits = [vpool.id('b0'), vpool.id('b1')]
            y_bits, clauses = mul(a_bits, b_bits, vpool, 'relax', 3, 3, sense)
            with Solver(bootstrap_with=clauses) as solver:
                for a, b in itertools.product(range(4), repeat=2):
                    fixed = [_lit(v, (a >> i) & 1) for i, v in enumerate(a_bits)]
                    fixed += [_lit(v, (b >> i) & 1) for i, v in enumerate(b_bits)]
                    feasible = []
                    for y in range(1 << len(y_bits)):
                        y_fixed = [_lit(v, (y >> i) & 1) for i, v in enumerate(y_bits)]
                        if solver.solve(assumptions=fixed + y_fixed):
                            feasible.append(y)
                    self.assertIn(a * b, feasible)
                    if sense == 1:
                        self.assertLessEqual(max(feasible), a * b)
                    else:
                        self.assertGreaterEqual(min(feasible), a * b)


class SmtBooleanTests(unittest.TestCase):
    CASES = [
        (
            {'x': (0, 2)},
            '(not (= x 1))',
        ),
        (
            {'x': (0, 2), 'y': (0, 2)},
            '(not (and (>= x 1) (>= y 1)))',
        ),
        (
            {'x': (0, 2), 'y': (0, 2)},
            '(or (and (= x 0) (= y 0)) (and (= x 2) (= y 2)))',
        ),
        (
            {'x': (0, 2), 'y': (0, 2)},
            '(=> (= x 0) (= y 1))',
        ),
        (
            {'x': (2, 4)},
            '(or (= x 2) (= x 4))',
        ),
    ]

    @staticmethod
    def _write_case(bounds, formula):
        lines = ['(set-logic QF_NIA)']
        for name in bounds:
            lines.append(f'(declare-fun {name} () Int)')
        for name, (lb, ub) in bounds.items():
            lines.append(f'(assert (>= {name} {lb}))')
            lines.append(f'(assert (<= {name} {ub}))')
        lines.append(f'(assert {formula})')
        handle = tempfile.NamedTemporaryFile('w', suffix='.smt2', delete=False, encoding='utf-8')
        with handle:
            handle.write('\n'.join(lines) + '\n')
        return handle.name

    def test_parser_and_all_encodings_match_original_smt(self):
        for bounds, formula in self.CASES:
            path = self._write_case(bounds, formula)
            try:
                problem = parse_smt2_file(path)
                assertions = z3.parse_smt2_file(path)
                encoded = {}
                for encoding in ('OH', 'UNA', 'BIN'):
                    encoded[encoding] = build_wcnf(problem, encoding, EncodingConfig())[:2]

                names = list(bounds)
                domains = [range(lb, ub + 1) for lb, ub in bounds.values()]
                for tuple_values in itertools.product(*domains):
                    values = dict(zip(names, tuple_values))
                    z3_solver = z3.Solver()
                    z3_solver.add(assertions)
                    z3_solver.add(*[z3.Int(name) == value for name, value in values.items()])
                    expected = z3_solver.check() == z3.sat

                    safe_values = {
                        problem['_name_map'][name]: value for name, value in values.items()
                    }
                    ir_value = all(
                        check_constraint(constraint, safe_values)[0]
                        for constraint in problem['constraints']
                    )
                    self.assertEqual(ir_value, expected, (formula, values, 'IR'))

                    for encoding, (wcnf, name2idx) in encoded.items():
                        assumptions = _fixed_value_assumptions(
                            wcnf, name2idx, encoding, problem, values
                        )
                        with Solver(bootstrap_with=wcnf.hard) as solver:
                            got = solver.solve(assumptions=assumptions)
                        self.assertEqual(got, expected, (formula, values, encoding))
            finally:
                os.unlink(path)

    def test_strict_parser_rejects_artificial_bounds(self):
        handle = tempfile.NamedTemporaryFile('w', suffix='.smt2', delete=False, encoding='utf-8')
        with handle:
            handle.write('(declare-fun x () Int)\n(assert (> x 0))\n')
        try:
            with self.assertRaisesRegex(ValueError, 'artificial bounds'):
                parse_smt2_file(handle.name)
            exploratory = parse_smt2_file(handle.name, strict=False, default_ub=9)
            self.assertEqual(exploratory['variables']['x1']['ub'], 9)
        finally:
            os.unlink(handle.name)


class PipelineRegressionTests(unittest.TestCase):
    def test_constant_contradiction_survives_preprocessing_and_is_unsat(self):
        problem = {
            'variables': {'x': {'lb': 0, 'ub': 1}},
            'objective': {'sense': 'max', 'terms': [{'c': 1, 'vars': {'x': 1}}]},
            'constraints': [{'terms': [], 'sense': '==', 'rhs': 1}],
        }
        wcnf, _, _ = build_wcnf(problem, 'BIN', EncodingConfig())
        self.assertIn([], wcnf.hard)
        result = build_and_solve(problem, 'BIN', EncodingConfig(), solver='RC2')
        self.assertEqual(result['solver_status'], 'UNSAT')
        self.assertIsNone(result['objective_value'])

    def test_manual_single_branch_disjunction_is_enforced_after_preprocessing(self):
        problem = {
            'variables': {'x': {'lb': 0, 'ub': 1}},
            'objective': {'sense': 'max', 'terms': [{'c': 1, 'vars': {'x': 1}}]},
            'constraints': [{
                'type': 'disjunction',
                'disjuncts': [[{
                    'terms': [{'c': 1, 'vars': {'x': 1}}], 'rel': '==', 'rhs': 0
                }]],
            }],
        }
        result = build_and_solve(problem, 'BIN', EncodingConfig(), solver='RC2')
        self.assertEqual(result['solver_status'], 'OPTIMAL')
        self.assertEqual(result['objective_value'], 0)
        valid, report = verify_solution(problem, result, 'BIN')
        self.assertTrue(valid, report)

    def test_cli_wcnf_export_for_none_and_rc2(self):
        source = ROOT / 'examples' / 'example4.json'
        for solver_name in ('NONE', 'RC2'):
            with tempfile.NamedTemporaryFile(suffix='.wcnf', delete=False) as tmp:
                output = tmp.name
            os.unlink(output)
            try:
                proc = subprocess.run(
                    [sys.executable, str(CODES / 'main.py'), str(source),
                     '-e', 'BIN', '-s', solver_name, '-o', output],
                    capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertTrue(os.path.exists(output))
                self.assertGreater(os.path.getsize(output), 0)
            finally:
                if os.path.exists(output):
                    os.unlink(output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
