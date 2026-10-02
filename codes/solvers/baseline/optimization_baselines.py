"""CPLEX MIQP and a shared exact bounded-integer MILP for CPLEX/HiGHS.

SCIP builds the linear IR only; it does not presolve or solve the exported MILP.
"""
from fractions import Fraction
from math import ceil, floor
import time
from solvers.baseline.scip_baseline import build_model, integer_polynomial, number, exact_double_integer
from telemetry import progress, quality


class Unsupported(ValueError):
    pass


def milp_ir(problem):
    m, _, stats = build_model(problem, 'milp')
    variables = m.getVars(transformed=False)
    columns = [(v.name, v.getObj(), v.getLbOriginal(), v.getUbOriginal(), v.vtype() != 'CONTINUOUS') for v in variables]
    index = {v[0]: i for i, v in enumerate(columns)}
    rows = [(m.getLhs(c), m.getRhs(c), [(index[n], a) for n, a in m.getValsLinear(c).items()]) for c in m.getConss()]
    mapping, bit = {}, 0
    for n, v in problem['variables'].items():
        lo, hi = ceil(number(v['lb'])), floor(number(v['ub']))
        mapping[n] = (lo, [(index[f'b{bit+j}'], 1 << j) for j in range(max(0, hi-lo).bit_length())])
        bit += max(0, hi-lo).bit_length()
    return columns, rows, m.getObjoffset(), m.getObjectiveSense(), mapping, stats


def native_cplex(problem):
    import cplex
    if problem.get('objective', {}).get('factor_blocks'):
        raise Unsupported('native CPLEX adapter requires a polynomial objective')
    c = cplex.Cplex()
    names = list(problem['variables']); index = {n:i for i,n in enumerate(names)}
    c.variables.add(names=names, lb=[ceil(number(problem['variables'][n]['lb'])) for n in names],
                    ub=[floor(number(problem['variables'][n]['ub'])) for n in names], types='I'*len(names))
    poly, scale = integer_polynomial(problem['objective'].get('terms', []))
    constant = poly.pop((), 0)
    for key, coefficient in poly.items():
        coefficient = exact_double_integer(coefficient)
        factors = [index[n] for n, p in key for _ in range(p)]
        if len(factors) == 1:
            c.objective.set_linear(factors[0], coefficient)
        elif len(factors) == 2:
            i,j = factors
            c.objective.set_quadratic_coefficients(i,j, coefficient*2 if i==j else coefficient)
        else:
            raise Unsupported('CPLEX-NATIVE requires objective degree <= 2')
    quadratic_constraints = 0
    for atom in problem.get('constraints', []):
        if atom.get('type') == 'disjunction':
            raise Unsupported('native CPLEX adapter does not implement disjunctions')
        terms, unit = integer_polynomial(atom.get('terms', atom.get('lhs', [])))
        rhs = number(atom.get('rhs',0))*unit - terms.pop((),0)
        if any(sum(k for _,k in key) > 2 for key in terms):
            raise Unsupported('CPLEX-NATIVE requires constraint degree <= 2')
        rel = atom.get('rel', atom.get('sense','<='))
        if rel in ('<','<='): rhs, sense = (ceil(rhs)-1 if rel=='<' else floor(rhs)), 'L'
        elif rel in ('>','>='): rhs, sense = (floor(rhs)+1 if rel=='>' else ceil(rhs)), 'G'
        elif rel in ('=','=='):
            if rhs.denominator != 1:
                c.linear_constraints.add(lin_expr=[cplex.SparsePair([],[])], senses='E', rhs=[1])
                continue
            rhs, sense = int(rhs), 'E'
        else: raise Unsupported('unsupported constraint relation')
        linear={key:v for key,v in terms.items() if sum(k for _,k in key)==1}
        quadratic={key:v for key,v in terms.items() if sum(k for _,k in key)==2}
        pair=cplex.SparsePair([index[key[0][0]] for key in linear],[exact_double_integer(v) for v in linear.values()])
        if quadratic:
            if sense=='E':
                raise Unsupported('CPLEX-NATIVE does not support general quadratic equality constraints')
            pairs=[[index[n] for n,p in key for _ in range(p)] for key in quadratic]
            c.quadratic_constraints.add(lin_expr=pair,quad_expr=cplex.SparseTriple(
                [p[0] for p in pairs],[p[1] for p in pairs],[exact_double_integer(v) for v in quadratic.values()]),
                sense=sense,rhs=exact_double_integer(rhs))
            quadratic_constraints+=1
        else:
            c.linear_constraints.add(lin_expr=[pair], senses=sense, rhs=[exact_double_integer(rhs)])
    c.objective.set_sense(c.objective.sense.minimize if problem['objective'].get('sense','max').startswith('min') else c.objective.sense.maximize)
    # CPLEX MIQCP only allows target=0 and checks convexity itself (error 5002).
    c.parameters.optimalitytarget.set(0 if quadratic_constraints else 3)
    mapping = {n:(0,[(i,1)]) for n,i in index.items()}
    return c, mapping, {'route':'native-miqcp' if quadratic_constraints else 'native-miqp',
                       'variables':c.variables.get_num(),
                       'constraints':c.linear_constraints.get_num()+c.quadratic_constraints.get_num(),
                       'quadratic_constraints':quadratic_constraints,
                       'objective_scale':scale,'objective_constant':constant,'objective_divisor':1}, 0


def solve(problem, solver, seconds, begin_verify=lambda: None):
    started = time.monotonic()
    try:
        if problem.get('objective', {}).get('factor_blocks'):
            raise Unsupported('baseline input requires an explicit polynomial, not factor_blocks')
        if solver == 'CPLEX-NATIVE':
            c, mapping, stats, offset = native_cplex(problem)
        else:
            columns, rows, offset, sense, mapping, stats = milp_ir(problem)
            if solver == 'HIGHS-MILP':
                import highspy
                c = highspy.Highs()
                def checked(status):
                    if status != highspy.HighsStatus.kOk:
                        raise Unsupported('HiGHS rejected a model or parameter: ' + str(status))
                for k,v in {'output_flag':False,'threads':1,'mip_rel_gap':0.0,'mip_abs_gap':0.0,
                            'mip_feasibility_tolerance':1e-9,'random_seed':0}.items():
                    checked(c.setOptionValue(k,v))
                for i,(_,obj,lb,ub,integer) in enumerate(columns):
                    checked(c.addCol(obj,lb,ub,0,[],[]))
                    if integer: checked(c.changeColIntegrality(i,highspy.HighsVarType.kInteger))
                for lb,ub,entries in rows:
                    checked(c.addRow(-highspy.kHighsInf if lb<=-1e20 else lb,
                                    highspy.kHighsInf if ub>=1e20 else ub,
                                    len(entries), [i for i,_ in entries], [v for _,v in entries]))
                checked(c.changeObjectiveOffset(offset))
                checked(c.changeObjectiveSense(highspy.ObjSense.kMinimize if sense=='minimize' else highspy.ObjSense.kMaximize))
            else:
                import cplex
                c=cplex.Cplex()
                c.variables.add(names=[x[0] for x in columns],obj=[x[1] for x in columns],lb=[x[2] for x in columns],
                                ub=[x[3] for x in columns],types=''.join('I' if x[4] else 'C' for x in columns))
                for lb,ub,entries in rows:
                    pair=cplex.SparsePair([i for i,_ in entries],[v for _,v in entries])
                    if lb==ub: c.linear_constraints.add(lin_expr=[pair],senses='E',rhs=[lb])
                    else:
                        if lb>-1e20: c.linear_constraints.add(lin_expr=[pair],senses='G',rhs=[lb])
                        if ub<1e20: c.linear_constraints.add(lin_expr=[pair],senses='L',rhs=[ub])
                c.objective.set_offset(offset)
                c.objective.set_sense(c.objective.sense.minimize if sense=='minimize' else c.objective.sense.maximize)
        build = time.monotonic()-started
        progress('solve', formula=stats, solver_timings={'build':build})
        remaining = seconds-build
        if remaining<=0: return {'status':'TIMEOUT','verified':False}
        if solver.startswith('CPLEX'):
            import cplex
            c.set_log_stream(None); c.set_results_stream(None); c.set_warning_stream(None)
            c.parameters.threads.set(1); c.parameters.timelimit.set(remaining)
            c.parameters.mip.tolerances.mipgap.set(0); c.parameters.mip.tolerances.absmipgap.set(0)
            c.parameters.mip.tolerances.integrality.set(1e-9); c.parameters.simplex.tolerances.feasibility.set(1e-9)
            c.solve()
            status=c.solution.get_status(); backend=c.solution.get_status_string()
            optimal=status in (101,102); infeasible=status==103
            feasible=c.solution.is_primal_feasible()
            values=c.solution.get_values() if feasible else None
            objective=c.solution.get_objective_value() if feasible else None
            try:
                dual=c.solution.MIP.get_best_objective()
                dual=dual if abs(dual)<cplex.infinity else None
                gap=c.solution.MIP.get_mip_relative_gap() if feasible else None
                nodes=c.solution.progress.get_num_nodes_processed()
            except cplex.exceptions.CplexError:
                dual=gap=nodes=None
        else:
            checked(c.setOptionValue('time_limit',remaining))
            run_status=c.run()
            if run_status==highspy.HighsStatus.kError:
                raise RuntimeError('HiGHS execution error')
            status=c.getModelStatus(); backend=c.modelStatusToString(status)
            optimal=status==highspy.HighsModelStatus.kOptimal; infeasible=status==highspy.HighsModelStatus.kInfeasible
            feasible=c.getInfo().primal_solution_status==highspy.SolutionStatus.kSolutionStatusFeasible
            values=c.getSolution().col_value if feasible else None
            objective=c.getObjectiveValue() if feasible else None
            info=c.getInfo()
            dual, gap, nodes=info.mip_dual_bound, info.mip_gap, info.mip_node_count
        solved=time.monotonic()
        result={'status':'UNSAT' if infeasible else 'TIMEOUT' if 'time' in backend.lower() else 'UNKNOWN',
                'verified':False,'backend_status':backend,'formula':stats,
                'solver_timings':{'build':build,'solve':solved-started-build}}
        result['quality']=quality(stats, objective, dual, gap, nodes)
        progress(quality=result['quality'])
        if feasible:
            begin_verify()
            raw={n:lo+sum(values[i]*weight for i,weight in bits) for n,(lo,bits) in mapping.items()}
            witness={n:round(v) for n,v in raw.items()}
            if any(abs(raw[n]-v)>1e-6 for n,v in witness.items()): raise ValueError('nonintegral original witness')
            from tools.verify import verify_values
            value,checks,source=verify_values(problem,witness)
            encoded=(number(value)*stats['objective_scale']-stats['objective_constant'])/stats['objective_divisor']
            if abs(float(encoded)-objective)>1e-6: raise ValueError('backend objective disagrees with original objective')
            result.update(status='OPTIMAL' if optimal else 'FEASIBLE',verified=True,objective_exact=str(value),witness=witness,
                          verification={'constraint_checks':checks,'source_smt_verified':source},
                          optimality_certificate='backend numerical tolerances; original witness checked exactly')
            result['solver_timings']['verify']=time.monotonic()-solved
        return result
    except Unsupported as exc:
        return {'status':'UNSUPPORTED','verified':False,'error':str(exc)}
    except Exception as exc:
        # Community edition limits must not be misreported as algorithmic failures.
        if '1016' in str(exc) or 'Community Edition' in str(exc):
            return {'status':'LICENSE_LIMIT','verified':False,'error':str(exc)}
        if 'UNSUPPORTED_NUMERIC_RANGE' in str(exc):
            return {'status':'UNSUPPORTED','verified':False,'error':str(exc)}
        if solver=='CPLEX-NATIVE' and 'CPLEX Error  5002' in str(exc):
            return {'status':'UNSUPPORTED','verified':False,'error':str(exc)}
        raise
