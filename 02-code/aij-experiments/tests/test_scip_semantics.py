"""Compare both independent formulations with exhaustive original-model truth."""
from pathlib import Path
from fractions import Fraction
from itertools import product
from math import ceil, floor
import json
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent/'nlipsat-aij'/'codes'))
from scip_baseline import build_model, solve

def t(c=1, **powers):
    return {'c': c, 'vars': powers}

def atom(terms, rel, rhs):
    return {'terms': terms, 'rel': rel, 'rhs': rhs}

def case(name, bounds, terms, constraints=(), sense='max'):
    return name, {'variables': {n: {'lb': lo, 'ub': hi} for n,(lo,hi) in bounds.items()},
                  'objective': {'sense': sense, 'terms': terms}, 'constraints': list(constraints)}

def evaluate(terms, point):
    answer = Fraction(0)
    for term in terms:
        value = Fraction(str(term.get('c', 1)))
        for n,k in term.get('vars', {}).items():
            value *= point[n]**k
        answer += value
    return answer

def satisfied(a, point):
    if a.get('type') == 'disjunction':
        return any(all(satisfied(child,point) for child in branch) for branch in a['disjuncts'])
    lhs, rhs = evaluate(a['terms'],point), Fraction(str(a['rhs']))
    return {'<': lhs<rhs, '<=': lhs<=rhs, '>': lhs>rhs, '>=': lhs>=rhs,
            '=': lhs==rhs, '==': lhs==rhs}[a['rel']]

cases = [
    case('paper-running', {'x':(-1,1),'v':(0,2)}, [t('3/2',x=1,v=1),t('-1/2',x=2),t('1/4')],
         [atom([t(x=2),t(v=1)],'<=',2), {'type':'disjunction','disjuncts':[[atom([t(x=1)],'=',-1)],[atom([t(v=1)],'>=',1)]]}]),
    case('signed-cubic-min', {'x':(-2,1),'y':(-1,2)}, [t(-2,x=3,y=2),t(3,y=1),t('-2/3')],
         [atom([t(x=2),t(-1,y=1)],'>','1/2')], 'min'),
    case('fractional-strict', {'x':(-1,2),'y':(0,2)}, [t('2/3',x=2,y=1),t('-1/5',y=2)],
         [atom([t('1/3',x=1),t('1/2',y=1)],'<','5/6')]),
    case('fractional-equality-unsat', {'x':(0,2)}, [t(x=1)], [atom([t(2,x=1)],'=',1)]),
    case('inactive-branch', {'x':(0,2),'y':(0,1)}, [t(x=2,y=1)],
         [{'type':'disjunction','disjuncts':[[atom([t(x=1)],'>',3)],[atom([t(x=1)],'<',1),atom([t(y=1)],'=',1)]]}]),
    case('nested-branch', {'x':(-1,1)}, [t(x=3)],
         [{'type':'disjunction','disjuncts':[[{'type':'disjunction','disjuncts':[[atom([t(x=1)],'=',-1)], [atom([t(x=1)],'=',1)]]}]]}]),
    case('empty-disjunction', {'x':(0,1)}, [t(x=1)], [{'type':'disjunction','disjuncts':[]}]),
    case('true-branch', {'x':(0,1)}, [t(x=2)], [{'type':'disjunction','disjuncts':[[],[atom([t(x=1)],'>',3)]]}]),
    case('fixed-variable', {'x':(-2,-2),'y':(1,1)}, [t(x=4,y=3),t(-7)]),
    case('constant-true', {}, [t('-7/3')], [atom([], '<=', 0)]),
    case('constant-false', {}, [], [atom([], '>', 0)]),
    case('empty-domain', {'x':(2,1)}, [t(x=1)]),
    case('rational-domain', {'x':('-3/2','5/2')}, [t(x=3)], [atom([t(x=1)],'>','-1/2')]),
    case('cancelled-cross-terms', {'x':(0,2),'y':(0,2)}, [t(3,x=2,y=1),t(-3,x=2,y=1),t('1/7',x=1)]),
]
rng = random.Random(20260911)
for i in range(10):
    terms = [t(rng.choice([-3,-2,1,2,3]),x=rng.randrange(4),y=rng.randrange(3)) for _ in range(4)]
    cons = [atom([t(rng.choice([-2,1,3]),x=rng.randrange(3),y=rng.randrange(3)) for _ in range(3)],rng.choice(['<=','>=','<','>','=']),rng.randrange(-3,5))]
    cases.append(case(f'polynomial-{i}',{'x':(-1,2),'y':(-1,1)},terms,cons,'max' if i%2 else 'min'))

start = time.monotonic()
rows = []
for name,p in cases:
    names = list(p['variables'])
    points = [dict(zip(names,values)) for values in product(*(range(ceil(Fraction(str(v['lb']))),floor(Fraction(str(v['ub'])))+1) for v in p['variables'].values()))]
    feasible = [point for point in points if all(satisfied(a,point) for a in p['constraints'])]
    values = [evaluate(p['objective']['terms'],point) for point in feasible]
    optimum = (max(values) if p['objective']['sense']=='max' else min(values)) if values else None
    for route in ['milp','native']:
        for point in points:
            expected = point in feasible
            model,_,_ = build_model(p,route,forced=point)
            model.setRealParam('limits/time', 5)
            model.optimize()
            status = str(model.getStatus())
            assert status in ('optimal','infeasible'),(name,route,point,status)
            assert (status=='optimal')==expected,(name,route,point,status,expected)
            model.freeProb()
        result = solve(p,route,10)
        assert result['status']==('UNSAT' if optimum is None else 'OPTIMAL'),(name,route,result)
        if optimum is not None:
            assert Fraction(result['objective_exact'])==optimum,(name,route,result,optimum)
            assert result['verified']
        rows.append({'case':name,'route':route,'assignments':len(points),'feasible':len(feasible),
                     'optimum':str(optimum) if optimum is not None else None,'status':result['status']})
        print(name,route,result['status'],str(optimum),flush=True)
output = Path(sys.argv[1])
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'cases':len(cases),'projection_checks':sum(r['assignments'] for r in rows),
                            'optimization_checks':len(rows),'seconds':time.monotonic()-start,'results':rows},indent=2))
print('All projection and optimum comparisons passed.',flush=True)
