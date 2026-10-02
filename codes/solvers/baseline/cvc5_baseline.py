"""Native SMT decision and bounded exact-integer bisection optimization."""
from fractions import Fraction
from math import ceil, floor, lcm
from pathlib import Path
import sys
import time

# Prefer the active interpreter's packages over a legacy --target installation.
sys.path.append(str(Path(__file__).with_name('baseline-deps')))
import cvc5
from cvc5 import Kind as K


class Unsupported(ValueError):
    pass


def make_solver():
    tm = cvc5.TermManager()
    solver = cvc5.Solver(tm)
    solver.setOption('produce-models', 'true')
    solver.setOption('incremental', 'true')
    solver.setOption('seed', '0')
    return tm, solver


def combine(tm, kind, terms, identity):
    if not terms:
        return identity
    return terms[0] if len(terms) == 1 else tm.mkTerm(kind, *terms)


def scaled(terms, rhs=0):
    scale = lcm(Fraction(str(rhs)).denominator,
                *(Fraction(str(t.get('c', 1))).denominator for t in terms))
    return [(int(Fraction(str(t.get('c', 1)))*scale), t.get('vars', {})) for t in terms], scale


def expression(tm, variables, terms):
    summands = []
    for c, powers in terms:
        factors = [tm.mkInteger(c)]
        for n, exponent in powers.items():
            if int(exponent) != exponent or exponent < 0:
                raise Unsupported('only nonnegative integer polynomial exponents are supported')
            if exponent:
                factors.append(variables[n] if exponent == 1 else
                               tm.mkTerm(K.POW, variables[n], tm.mkInteger(int(exponent))))
        summands.append(combine(tm, K.MULT, factors, tm.mkInteger(1)))
    return combine(tm, K.ADD, summands, tm.mkInteger(0))


def objective_interval(terms, bounds):
    lower = upper = 0
    for c, powers in terms:
        lo = hi = 1
        for name, power in powers.items():
            a, b = bounds[name]
            endpoints = [a**power, b**power]
            if power and power % 2 == 0 and a <= 0 <= b:
                endpoints.append(0)
            products = [lo*min(endpoints), lo*max(endpoints), hi*min(endpoints), hi*max(endpoints)]
            lo, hi = min(products), max(products)
        lower += min(c*lo, c*hi)
        upper += max(c*lo, c*hi)
    return lower, upper


def build_model(problem):
    tm, solver = make_solver()
    solver.setLogic('QF_NIA')
    variables = {name: tm.mkConst(tm.getIntegerSort(), name) for name in problem['variables']}
    bounds = {}
    for name, info in problem['variables'].items():
        if info.get('lb') is None or info.get('ub') is None:
            raise Unsupported('optimization needs finite original integer bounds')
        lo, hi = ceil(Fraction(str(info['lb']))), floor(Fraction(str(info['ub'])))
        bounds[name] = lo, hi
        solver.assertFormula(tm.mkTerm(K.GEQ, variables[name], tm.mkInteger(lo)))
        solver.assertFormula(tm.mkTerm(K.LEQ, variables[name], tm.mkInteger(hi)))

    def constraint(atom):
        if atom.get('type') == 'disjunction':
            return combine(tm, K.OR, [combine(tm, K.AND, [constraint(a) for a in branch], tm.mkBoolean(True))
                                     for branch in atom.get('disjuncts', [])], tm.mkBoolean(False))
        terms, scale = scaled(atom.get('terms', atom.get('lhs', [])), atom.get('rhs', 0))
        relation = atom.get('rel', atom.get('sense', '<='))
        kinds = {'<': K.LT, '<=': K.LEQ, '>': K.GT, '>=': K.GEQ, '=': K.EQUAL, '==': K.EQUAL}
        if relation not in kinds:
            raise Unsupported('unsupported relation: '+relation)
        return tm.mkTerm(kinds[relation], expression(tm, variables, terms),
                         tm.mkInteger(int(Fraction(str(atom.get('rhs', 0)))*scale)))

    for atom in problem.get('constraints', []):
        solver.assertFormula(constraint(atom))
    objective = problem.get('objective', {})
    terms, scale = scaled(objective.get('terms', []))
    expr = expression(tm, variables, terms)
    lo, hi = objective_interval(terms, bounds)
    return tm, solver, variables, expr, scale, lo, hi


def check(solver, deadline):
    left = deadline-time.monotonic()
    if left <= 0:
        return None
    solver.setOption('tlimit-per', str(max(1, int(left*1000))))
    return solver.checkSat()


def solve(problem, seconds, begin_verify=lambda: None):
    start = time.monotonic()
    deadline = start+seconds
    tm, solver, variables, objective, scale, lo, hi = build_model(problem)
    built = time.monotonic()
    result = {'status': 'UNKNOWN', 'verified': False, 'objective_exact': None,
              'formula': {'route': 'cvc5-bisection', 'cvc5': cvc5.__version__, 'objective_scale': scale},
              'solver_timings': {'build': built-start}}
    answer = check(solver, deadline)
    calls = 1 if answer is not None else 0
    values = None
    best = None
    maximize = problem.get('objective', {}).get('sense', 'max').lower() in ('max', 'maximize')
    if answer is not None and answer.isUnsat():
        result['status'] = 'UNSAT'
    elif answer is not None and answer.isSat():
        values = {n: int(solver.getValue(v).getIntegerValue()) for n, v in variables.items()}
        best = int(solver.getValue(objective).getIntegerValue())
        if maximize:
            lo = best
        else:
            hi = best
        result['status'] = 'FEASIBLE'
        while lo < hi:
            mid = (lo+hi+1)//2 if maximize else (lo+hi)//2
            solver.push()
            solver.assertFormula(tm.mkTerm(K.GEQ if maximize else K.LEQ, objective, tm.mkInteger(mid)))
            answer = check(solver, deadline)
            calls += answer is not None
            if answer is None or answer.isUnknown():
                solver.pop()
                break
            if answer.isSat():
                values = {n: int(solver.getValue(v).getIntegerValue()) for n, v in variables.items()}
                best = int(solver.getValue(objective).getIntegerValue())
                if maximize:
                    lo = best
                else:
                    hi = best
            elif maximize:
                hi = mid-1
            else:
                lo = mid+1
            solver.pop()
        if lo == hi:
            result['status'] = 'OPTIMAL'
        result.update(objective_bound_exact=str(Fraction(hi if maximize else lo, scale)),
                      optimality_certificate='finite integer bound search using cvc5 SAT/UNSAT answers')
    solved = time.monotonic()
    if answer is None:
        result['backend_status'] = 'TIMEOUT'
        if values is None:
            result['status'] = 'TIMEOUT'
    elif answer.isUnknown():
        reason = str(answer.getUnknownExplanation())
        result['backend_status'] = reason
        if values is None:
            result['status'] = 'TIMEOUT' if 'TIMEOUT' in reason.upper() else 'UNKNOWN'
    result['solver_timings'].update(solve=solved-built, check_sat_calls=calls)
    if values is not None:
        begin_verify()
        from tools.verify import verify_values
        value, checks, source = verify_values(problem, values)
        if value != Fraction(best, scale):
            raise ValueError('cvc5 objective disagrees with original polynomial')
        result.update(verified=True, objective_exact=str(value), witness=values,
                      verification={'constraint_checks': checks, 'source_smt_verified': source})
        result['solver_timings']['verify'] = time.monotonic()-solved
    return result


def load_smt2(path):
    tm, solver = make_solver()
    parser = cvc5.InputParser(solver)
    parser.setFileInput(cvc5.InputLanguage.SMT_LIB_2_6, str(path))
    symbols = parser.getSymbolManager()
    query_seen = False
    while True:
        command = parser.nextCommand()
        if command.isNull():
            break
        name = command.getCommandName()
        if name == 'check-sat':
            if query_seen:
                raise Unsupported('only a single SMT query is supported')
            query_seen = True
            continue
        if name in ('get-model', 'get-info', 'get-value', 'exit', 'set-info'):
            continue
        if name not in ('set-logic', 'declare-fun', 'declare-const', 'define-fun', 'assert') or query_seen:
            raise Unsupported('SMT command outside the static benchmark scope: '+name)
        output = command.invoke(solver, symbols)
        if output and '(error' in output:
            raise ValueError(output)
    declared = symbols.getDeclaredTerms()
    if any(not (t.getSort().isInteger() or t.getSort().isBoolean()) for t in declared):
        raise Unsupported('original-SMT witness checking supports Int/Bool constants')
    return tm, solver, declared


def solve_smt2(path, seconds, begin_verify=lambda: None):
    from telemetry import progress
    progress('parse')
    start = time.monotonic()
    tm, solver, declared = load_smt2(path)
    built = time.monotonic()
    boolean=sum(t.getSort().isBoolean() for t in declared)
    progress('solve', read_seconds=built-start,
             problem_features={'representation':'original_smt_declarations','variables':len(declared),
                               'boolean_variables':boolean, 'boolean_fraction':boolean/len(declared) if declared else 0,
                               'constraints':len(solver.getAssertions())})
    answer = check(solver, start+seconds)
    result = {'status': 'TIMEOUT' if answer is None else 'UNSAT' if answer.isUnsat() else
              'SAT' if answer.isSat() else 'UNKNOWN', 'verified': False, 'objective_exact': None,
              'formula': {'route': 'cvc5-original-smt', 'cvc5': cvc5.__version__},
              'solver_timings': {'build': built-start, 'solve': time.monotonic()-built}}
    if answer is not None and answer.isUnknown():
        result['backend_status'] = str(answer.getUnknownExplanation())
        if 'TIMEOUT' in result['backend_status'].upper():
            result['status'] = 'TIMEOUT'
    if result['status'] == 'SAT':
        values = {t.getSymbol(): (solver.getValue(t).getBooleanValue() if t.getSort().isBoolean()
                                  else int(solver.getValue(t).getIntegerValue())) for t in declared}
        begin_verify()
        verifying = time.monotonic()
        import z3
        replacements = [(z3.Bool(n), z3.BoolVal(v)) if isinstance(v, bool) else
                        (z3.Int(n), z3.IntVal(v)) for n, v in values.items()]
        assertions = z3.parse_smt2_file(str(path))
        if not all(z3.is_true(z3.simplify(z3.substitute(a, *replacements))) for a in assertions):
            raise ValueError('cvc5 witness fails original SMT assertions')
        result.update(verified=True, witness=values, verification={'original_smt_assertions': len(assertions)})
        result['solver_timings']['verify'] = time.monotonic()-verifying
    return result
