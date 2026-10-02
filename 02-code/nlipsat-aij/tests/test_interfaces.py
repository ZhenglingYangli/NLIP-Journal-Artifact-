"""Tests for actual consumers of the normalized problem and solver output."""
import contextlib
import importlib.util
import io
import itertools
from fractions import Fraction
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_correctness as helpers
from test_correctness import ROOT, atom, term, problem, oracle
from pysat.formula import WCNF, IDPool
from pysat.solvers import Solver
from solver.config import EncodingConfig
from solver.solve import solve_external, build_and_solve, build_wcnf
from encoders.constraints import _encode_pb_constraint
from encoders.encoder_driver import _ensure_bin_structure
from tools.preprocessing import _expand_term_by_shifts, preprocess_problem
from tools.qplib_parser import parse_qplib_file
from tools.smt2_parser import parse_smt2_file
from tools.verify import verify_solution


class Interfaces(unittest.TestCase):
    def test_pb_adder_and_pblib_match_signed_sum(self):
        rng = random.Random(347)
        for case in range(18):
            lits = [rng.choice([-1, 1]) * rng.randrange(1, 5) for _ in range(6)]
            weights = [rng.randrange(-5, 6) for _ in lits]
            if case >= 15:
                weights[0] = 2**65 + 1
            rhs = rng.randrange(-7, 10)
            for rel, adder in itertools.product(['<=', '<', '>=', '>', '=='], [True, False]):
                vp = IDPool(start_from=5)
                clauses = _encode_pb_constraint(lits, weights, rhs, rel, vp, [], force_adder=adder)
                with Solver(bootstrap_with=clauses) as s:
                    for bits in itertools.product([False, True], repeat=4):
                        total = sum(w for lit, w in zip(lits, weights) if bits[abs(lit)-1] == (lit > 0))
                        expected = {'<=': total <= rhs, '<': total < rhs, '>=': total >= rhs,
                                    '>': total > rhs, '==': total == rhs}[rel]
                        self.assertEqual(s.solve(assumptions=[i+1 if b else -(i+1) for i,b in enumerate(bits)]), expected,
                                         (case, rel, adder, bits, lits, weights, rhs))

    def test_binary_domain_comparator(self):
        for ub in range(33):
            vp = IDPool()
            clauses = []
            # The builder accepts WCNF and always creates the variable bits.
            w = WCNF()
            _ensure_bin_structure(w, lambda q, r: vp.id(f'x_{q}@{r}'), 1, ub)
            with Solver(bootstrap_with=w.hard) as s:
                for value in range(1 << max(1, ub.bit_length())):
                    fixed = [vp.id(f'x_1@{r}') * (1 if (value >> r)&1 else -1)
                             for r in range(max(1, ub.bit_length()))]
                    self.assertEqual(s.solve(assumptions=fixed), value <= ub)
        w, vp = WCNF(), IDPool()
        _ensure_bin_structure(w, lambda q, r: vp.id(f'x_{q}@{r}'), 1, 2**20)
        self.assertEqual(len(w.hard), 20)

    def test_qplib_exact_numbers_and_types(self):
        # One diagonal quadratic constraint x^2 <= 1, integer x in [-0.2, 2.8].
        content = '\n'.join(['tiny', 'QIC', 'maximize', '1', '1',
                             '1', '1 1 1', '9007199254740993', '0', '0.25',
                             '1', '1 1 1 2', '0', '1e20', '-1e20', '0', '1', '0',
                             '-0.2', '0', '2.8', '0'])
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'tiny.qplib'
            f.write_text(content)
            p = parse_qplib_file(str(f))
            self.assertEqual(p['variables']['x1'], {'lb': 0, 'ub': 2})
            self.assertEqual(oracle(p), Fraction(9007199254740993) + Fraction(3, 4))
            helpers.Correctness.compare(self, p)
            f.write_text(content.replace('QIC', 'QCC'))
            with self.assertRaisesRegex(ValueError, 'variable type'):
                parse_qplib_file(str(f))
            f.write_text(content.replace('2.8', '1e20'))
            with self.assertRaisesRegex(ValueError, 'finite'):
                parse_qplib_file(str(f))
            f.write_text('\n'.join(['binary', 'QBN', 'maximize', '1', '0', '1', '0', '0', '1e20']))
            helpers.Correctness.compare(self, parse_qplib_file(str(f)))

    def test_external_solver_models_status_and_cost(self):
        w = WCNF()
        w.extend([[1], [-2]])
        w.append([2], weight=3)
        cases = [
            ('s OPTIMUM FOUND\no 3\nv 1\nv -2 0\n', 30, 'OPTIMAL'),
            ('o 3\ns OPTIMUM FOUND\nv 10\n', 30, 'OPTIMAL'),
            ('o 3\ns UNKNOWN\nv 1 -2 0\n', 0, 'FEASIBLE'),
            ('o 3\ns UNKNOWN\n', 0, 'UNKNOWN'),
            ('s OPTIMUM FOUND\no 3\n', 30, 'INVALID'),
            ('s OPTIMUM FOUND\no 0\nv 1 -2 0\n', 30, 'INVALID'),
            ('s SATISFIABLE\no 0\nv 1 2 0\n', 10, 'INVALID'),
            ('s UNSATISFIABLE\n', 30, 'INVALID')]
        with tempfile.TemporaryDirectory() as d:
            for output, code, expected in cases:
                with self.subTest(output=output), patch('solver.solve.subprocess.run', return_value=subprocess.CompletedProcess([],code,output,'')):
                    self.assertEqual(solve_external(w,d,'maxhs')[2],expected)
            with patch('solver.solve.subprocess.run', side_effect=subprocess.TimeoutExpired('maxhs',1,output=b'o 3\nv 1 -2 0\n')):
                self.assertEqual(solve_external(w,d,'maxhs',timeout=1)[2],'FEASIBLE')
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_qplib_cross_terms_have_half_factor(self):
        # Convention checked against QPLIB's official LP/GAMS exports:
        # https://qplib.zib.de/lp/QPLIB_3562.lp
        cases = [
            ('\n'.join(['objective','QBB','maximize','2','1','2 1 2','0','0','0','1e20']), 1),
            ('\n'.join(['constraint','LBQ','maximize','2','1','1','0','0','1',
                        '1 2 1 2','0','1e20','-1e20','0','1','0']), 2)]
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'cross.qplib'
            for content, expected in cases:
                f.write_text(content)
                p=parse_qplib_file(str(f))
                self.assertEqual(oracle(p),expected)
                helpers.Correctness.compare(self,p)
                spec=importlib.util.spec_from_file_location('qplib_z3_check',ROOT/'solvers/baseline/run_z3.py')
                baseline=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(baseline)
                result=baseline.solve_qplib(p,5)
                self.assertEqual(result['status'],'OPTIMAL')
                self.assertEqual(result['objective'],expected)

    def test_qplib_public_solution_point(self):
        # QPLIB CC BY 4.0: https://qplib.zib.de/sol/QPLIB_3562.sol
        # Public solution point; this is a feasibility/objective check, not an optimality certificate.
        from tools.verify import verify_values
        p=parse_qplib_file(str(ROOT/'tests/fixtures/QPLIB_3562.qplib'))
        values={f'x{i}':0 for i in range(1,64)}
        nonzero={1:1,2:1,3:1,4:1,8:5,9:4,10:3,11:2,15:1,17:3,19:1,
                 27:3,28:1,30:3,32:1,33:1,36:2,37:1,39:1,42:1,43:6,56:4,57:6}
        values.update({f'x{i}':v for i,v in nonzero.items()})
        objective,checks,_=verify_values(p,values)
        self.assertEqual(objective,15)
        self.assertEqual(len(checks),42)

    def test_z3_baseline_reads_dnf_and_exact_coefficients(self):
        spec = importlib.util.spec_from_file_location('aij_z3_baseline', ROOT/'solvers/baseline/run_z3.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for sense in ['min', 'max']:
            p = problem({'x': (-2,2)}, [term('9007199254740993', x=1), term('1/3')],
                        [{'type':'disjunction','disjuncts':[[atom([term(1,x=1)],'==',-1)],
                                                         [atom([term(1,x=1)],'==',1)]]}], sense)
            result = module.solve_qplib(p,10)
            self.assertEqual(result['status'],'OPTIMAL',result)
            self.assertEqual(result['objective'],oracle(p))
            self.assertIn(result['witness']['x'],[-1,1])

    def test_original_smt_witness_and_decision_entry(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)/'case.smt2'
            f.write_text('(declare-const x Int)\n(assert (>= x (- 2)))\n(assert (<= x 2))\n(assert (= (* x x) 1))')
            p = parse_smt2_file(str(f), objective_mode='zero')
            with contextlib.redirect_stdout(io.StringIO()):
                result = build_and_solve(p,'BIN',EncodingConfig())
            self.assertTrue(result['verified'],result['verification'])
            self.assertTrue(result['verification']['source_smt_verified'])
            for backend in ['CADICAL','GLUCOSE']:
                proc = subprocess.run([sys.executable,str(ROOT/'solvers/baseline/run_nlip_sat.py'),str(f),
                                       '-e','BIN','--sat-solver',backend,'--timeout','20'],capture_output=True,text=True,timeout=30)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                self.assertIn('Original SMT assertions: passed',proc.stdout)
                self.assertIn('Status SAT',proc.stdout)

    def test_feasible_objective_is_evaluated_at_original_witness(self):
        p = problem({'x': (0,2), 'y': (0,2)}, [term(1,x=1,y=1)])
        def feasible_backend(w, *args, **kwargs):
            vp = w._vpool
            # x=y=2, with an allowed unsaturated positive objective gate.
            fixed = {vp.id('x_1@1'), vp.id('x_2@1')}
            assignment = [i if i in fixed else -i for i in range(1,w.nv+1)]
            return sum(w.wght), assignment, 'FEASIBLE'
        with contextlib.redirect_stdout(io.StringIO()), patch('solver.solve.solve_external',side_effect=feasible_backend):
            result = build_and_solve(p,'BIN',EncodingConfig(),solver='MAXHS')
        self.assertEqual(result['solver_status'],'FEASIBLE',result['verification'])
        self.assertEqual(result['objective_value_exact'],'4')
        self.assertEqual(result['encoded_objective_value_exact'],'0')

    def test_json_preserves_decimal_text(self):
        from nlipsat import load_problem
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'exact.json'
            f.write_text('{"variables":{"x":{"lb":0,"ub":1}},"objective":{"sense":"max","terms":[{"c":9007199254740993.5,"vars":{"x":1}}]},"constraints":[]}')
            p=load_problem(f)
            self.assertEqual(p['objective']['terms'][0]['c'],Fraction('9007199254740993.5'))
            helpers.Correctness.compare(self,p)

    def test_corrupted_witness_and_objective_fail(self):
        p = problem({'x':(0,2)},[term(1,x=1)])
        with contextlib.redirect_stdout(io.StringIO()):
            result=build_and_solve(p,'BIN',EncodingConfig())
        result['objective_value'] = -1
        self.assertFalse(verify_solution(p,result,'BIN')[0])
        result['objective_value'] = 2
        result['assignment'] = [result['vpool'].id('x_1@0'),result['vpool'].id('x_1@1')]
        self.assertFalse(verify_solution(p,result,'BIN')[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
