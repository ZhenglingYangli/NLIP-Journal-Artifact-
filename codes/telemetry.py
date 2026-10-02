"""Stage checkpoints and model statistics used by experiment adapters."""
from fractions import Fraction
import json
import math
import time

_enabled = False
_last_phase = None


def enable():
    global _enabled
    _enabled = True


def progress(phase=None, **values):
    global _last_phase
    if _enabled:
        if phase == _last_phase and not values:
            return
        if phase:
            _last_phase = phase
        print('AIJ_PROGRESS ' + json.dumps({'at': time.monotonic(), 'phase': phase, 'metrics': values},
                                           ensure_ascii=False, default=str), flush=True)


def merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value
    return target


def problem_features(problem):
    variables = problem['variables']
    sizes, boolean = [], 0
    for v in variables.values():
        lo, hi = math.ceil(Fraction(str(v['lb']))), math.floor(Fraction(str(v['ub'])))
        sizes.append(max(0, hi-lo+1))
        boolean += lo == 0 and hi == 1
    terms = problem.get('objective', {}).get('terms', [])
    def atoms(items):
        for item in items:
            if item.get('type') == 'disjunction':
                for branch in item['disjuncts']:
                    yield from atoms(branch)
            else:
                yield item
    constraints = list(atoms(problem.get('constraints', [])))
    degrees = [sum(t.get('vars', {}).values()) for t in terms]
    cdegrees = [max([sum(t.get('vars', {}).values()) for t in c.get('terms', c.get('lhs', []))]+[0]) for c in constraints]
    return {'representation': 'parsed_polynomial', 'variables': len(variables), 'boolean_variables': boolean,
            'boolean_fraction': boolean/len(variables) if variables else 0,
            'domain_size_min': min(sizes, default=0), 'domain_size_max': max(sizes, default=0),
            'domain_size_mean': sum(sizes)/len(sizes) if sizes else 0,
            'objective_terms': len(terms), 'objective_degree': max(degrees, default=0),
            'constraints': len(problem.get('constraints', [])), 'constraint_atoms': len(constraints),
            'nonlinear_constraint_atoms': sum(d>1 for d in cdegrees),
            'constraint_degree': max(cdegrees, default=0),
            'objective_sense': problem.get('objective', {}).get('sense', 'max')}


def z3_features(assertions):
    import z3
    seen, constants, stack = set(), {}, list(assertions)
    while stack:
        node = stack.pop()
        if node.get_id() in seen:
            continue
        seen.add(node.get_id())
        if z3.is_const(node) and node.decl().kind() == z3.Z3_OP_UNINTERPRETED:
            constants[node.get_id()] = node
        stack.extend(node.children())
    boolean = sum(z3.is_bool(v) for v in constants.values())
    return {'representation':'original_smt_ast', 'variables':len(constants), 'boolean_variables':boolean,
            'boolean_fraction':boolean/len(constants) if constants else 0,
            'constraints':len(assertions), 'ast_nodes':len(seen)}


def finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def quality(stats, primal=None, dual=None, backend_gap=None, nodes=None):
    primal, dual = finite(primal), finite(dual)
    scale = float(stats.get('objective_scale', 1))
    divisor = float(stats.get('objective_divisor', 1))
    constant = float(stats.get('objective_constant', 0))
    def original(value):
        return (value*divisor+constant)/scale if value is not None else None
    p, d = original(primal), original(dual)
    return {'primal_bound_internal':primal, 'dual_bound_internal':dual,
            'primal_bound_original':p, 'dual_bound_original':d,
            'absolute_gap_original':abs(p-d) if p is not None and d is not None else None,
            'normalized_gap_original':abs(p-d)/max(1,abs(p),abs(d)) if p is not None and d is not None else None,
            'backend_relative_gap':finite(backend_gap) if p is not None and d is not None else None,
            'search_nodes':nodes if nodes is not None and nodes>=0 else None,
            'bound_semantics':'numerical backend bounds mapped to original objective; not an exact certificate'}
