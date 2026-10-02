import copy
from fractions import Fraction
from itertools import product
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent/'nlipsat-aij'),str(ROOT.parent/'nlipsat-aij/codes')]
from nlipsat import solve, EncodingConfig
from tools.verify import verify_values
from run_batch import methods
from optimization_baselines import solve as baseline


def optimum(p):
    names=list(p['variables']); values=[]
    for row in product(*(range(p['variables'][n]['lb'],p['variables'][n]['ub']+1) for n in names)):
        try: values.append(verify_values(p,dict(zip(names,row)))[0])
        except ValueError: pass
    return (min if p['objective']['sense']=='min' else max)(values)


class FinalMatrix(unittest.TestCase):
    def test_counts(self):
        counts=[len(methods('decision' if f=='smt' else 'optimization','main',f)) for f in ['qplib','diverse','mipo','smt']]
        self.assertEqual(counts,[17,17,21,6])
        self.assertEqual(sum(n*k for n,k in zip([137,108,870,150],counts)),23335)
        self.assertEqual([len(methods('optimization','decomposition',f)) for f in ['qplib','diverse','mipo']],[0,0,1])

    def test_lrn_end_to_end(self):
        p={'variables':{'x':{'lb':-1,'ub':2},'y':{'lb':0,'ub':1}},'constraints':[],
           'objective':{'sense':'min','terms':[{'c':'1/2','vars':{}}], 'factor_blocks':[{'residuals':[
               {'coefficients':{'x':2,'y':2},'constant':c,'weight':1} for c in [-2,0,2]]}]}}
        before=copy.deepcopy(p); expected=optimum(p)
        for enc in ['OH','UNA','BIN']:
            for enabled in [False,True]:
                with self.subTest(enc=enc,enabled=enabled):
                    result=solve(p,encoding=enc,config=EncodingConfig(use_lrn=enabled),solver='RC2')
                    self.assertEqual(result['solver_status'],'OPTIMAL')
                    self.assertTrue(result['verified'],result.get('verification'))
                    self.assertEqual(Fraction(result['objective_value_exact']),expected)
                    self.assertEqual(bool(result['encoding_stats']['lrn']['applied_groups']),enabled)
        self.assertEqual(p,before)

    def test_baselines_against_enumeration(self):
        for sense in ['min','max']:
            for quartic in [False,True]:
                p={'variables':{'x':{'lb':-2,'ub':2},'y':{'lb':0,'ub':2}},
                   'objective':{'sense':sense,'terms':[{'c':'1/2','vars':{'x':4 if quartic else 2}},
                       {'c':-3,'vars':{'x':1,'y':1}},{'c':2,'vars':{'y':1}},{'c':'3/7','vars':{}}]},
                   'constraints':[{'terms':[{'c':1,'vars':{'x':1}},{'c':1,'vars':{'y':1}}],'rel':'<=','rhs':2}]}
                expected=optimum(p)
                for backend in ['HIGHS-MILP','CPLEX-MILP']+([] if quartic else ['CPLEX-NATIVE']):
                    with self.subTest(sense=sense,quartic=quartic,backend=backend):
                        result=baseline(p,backend,10)
                        self.assertEqual(result['status'],'OPTIMAL',result)
                        self.assertTrue(result['verified'])
                        self.assertEqual(Fraction(result['objective_exact']),expected)

    def test_lrn_fractional_center_and_constant(self):
        p={'variables':{'x':{'lb':-1,'ub':2}},'constraints':[], 'objective':{'sense':'max','terms':[],
           'factor_blocks':[{'residuals':[{'coefficients':{'x':1},'constant':c} for c in [0,0,1]]+
              [{'coefficients':{},'constant':2,'weight':3}]}]}}
        result=solve(p,encoding='BIN',config=EncodingConfig(use_lrn=True),solver='RC2')
        self.assertEqual(result['solver_status'],'OPTIMAL')
        self.assertTrue(result['verified'],result.get('verification'))
        self.assertEqual(Fraction(result['objective_value_exact']),optimum(p))
        self.assertEqual(result['encoding_stats']['lrn']['output_residuals'],2)

    def test_cplex_quadratic_constraints(self):
        p={'variables':{'x':{'lb':-2,'ub':2},'y':{'lb':-2,'ub':2}},
           'objective':{'sense':'max','terms':[{'c':1,'vars':{'x':1}},{'c':1,'vars':{'y':1}}]},
           'constraints':[{'terms':[{'c':1,'vars':{'x':2}},{'c':1,'vars':{'y':2}}],'rel':'<=','rhs':4}]}
        result=baseline(p,'CPLEX-NATIVE',10)
        self.assertEqual(result['status'],'OPTIMAL',result)
        self.assertEqual(Fraction(result['objective_exact']),optimum(p))
        p['constraints'][0]['rel']='=='
        self.assertEqual(baseline(p,'CPLEX-NATIVE',10)['status'],'UNSUPPORTED')

if __name__=='__main__': unittest.main(verbosity=2)
