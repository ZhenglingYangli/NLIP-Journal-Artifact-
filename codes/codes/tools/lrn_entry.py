"""LRN preprocessing and exact affine-square lowering into the polynomial IR."""
from copy import deepcopy
from fractions import Fraction
from math import ceil, floor
from .lrn import normalize_problem, check_certificate


def integer(value):
    value = Fraction(str(value))
    if value.denominator != 1:
        raise ValueError('LRN factor coefficients, weights and constants must be integers')
    return int(value)


def prepare_factors(problem, enabled=True):
    if not problem.get('objective', {}).get('factor_blocks'):
        return problem, {'requested': enabled, 'applicable': False, 'applied_groups': 0}, []
    # Keep the original SMT AST outside deepcopy, as in the core preprocessor.
    p = deepcopy({k: v for k, v in problem.items() if k != '_smt_assertions'})
    objective = p['objective']
    objective.setdefault('terms', [])
    for block in objective['factor_blocks']:
        if set(block) - {'name', 'residuals'}:
            raise ValueError('unsupported factor block fields')
        nonconstant = []
        for r in block['residuals']:
            if set(r) - {'coefficients', 'constant', 'weight'}:
                raise ValueError('unsupported residual fields')
            r['coefficients'] = {n: integer(c) for n, c in r['coefficients'].items() if integer(c)}
            if set(r['coefficients']) - set(p['variables']):
                raise ValueError('unknown residual variable')
            r['constant'] = integer(r.get('constant', 0))
            r['weight'] = integer(r.get('weight', 1))
            if r['weight'] <= 0:
                raise ValueError('factor weights must be positive')
            if r['coefficients']:
                nonconstant.append(r)
            else:
                objective['terms'].append({'c': r['weight'] * r['constant']**2, 'vars': {}})
        block['residuals'] = nonconstant
    if enabled:
        p, meta = normalize_problem(p, mode='compress')
        for cert in meta['certificates']:
            valid, errors = check_certificate(cert)
            if not valid:
                raise ValueError('LRN identity failed: ' + str(errors))
    else:
        count = sum(len(b['residuals']) for b in objective['factor_blocks'])
        meta = {'applied_groups': 0, 'original_residuals': count, 'output_residuals': count}
    meta.update(requested=enabled, applicable=True)
    objective = p['objective']
    auxiliaries = []
    for block in objective.pop('factor_blocks'):
        for r in block['residuals']:
            name = '__lrn_residual_' + str(len(auxiliaries))
            while name in p['variables']:
                name += '_'
            lo = hi = r['constant']
            terms = [{'c': 1, 'vars': {name: 1}}]
            for n, c in r['coefficients'].items():
                v = p['variables'][n]
                bounds = (ceil(Fraction(str(v['lb']))), floor(Fraction(str(v['ub']))))
                lo += min(c * bounds[0], c * bounds[1])
                hi += max(c * bounds[0], c * bounds[1])
                terms.append({'c': -c, 'vars': {n: 1}})
            p['variables'][name] = {'lb': lo, 'ub': hi}
            p.setdefault('constraints', []).append({'terms': terms, 'rel': '==', 'rhs': r['constant']})
            objective['terms'].append({'c': r['weight'], 'vars': {name: 2}})
            auxiliaries.append(name)
    return p, meta, auxiliaries
