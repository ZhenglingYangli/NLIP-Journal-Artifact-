"""Convert the published integer TXT MIPO models (decimal text is exact)."""
import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path


def convert(path):
    lines=iter(line.strip() for line in path.read_text(encoding='ascii').splitlines() if line.strip())
    count=int(next(lines)); variables={}
    for i in range(1,count+1):
        kind,lb,ub=next(lines).split()
        if kind!='i': raise ValueError('only integer MIPO inputs belong to this experiment')
        variables[f'x{i}']={'lb':int(lb),'ub':int(ub)}
    terms=[]
    for _ in range(int(next(lines))):
        c,degree,*indices=next(lines).split()
        if len(indices)!=int(degree): raise ValueError('incorrect degree')
        powers=dict(Counter(f'x{int(i)}' for i in indices))
        if set(powers)-set(variables): raise ValueError('unknown variable')
        terms.append({'c':str(Fraction(c)),'vars':powers})
    if next(lines,None) is not None: raise ValueError('unexpected trailing input')
    return {'name':path.stem,'variables':variables,'objective':{'sense':'min','terms':terms},'constraints':[],
            '_source':{'format':'published MIPO integer TXT','filename':path.name,'coefficients':'exact TXT decimals'}}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('txt_root',type=Path); ap.add_argument('output',type=Path); ap.add_argument('manifest',type=Path)
    a=ap.parse_args(); files=sorted(a.txt_root.rglob('*.txt'))
    if len(files)!=870: raise ValueError(f'expected 870 original integer TXT inputs, found {len(files)}')
    expected=a.manifest.read_text().splitlines()
    models={}
    for path in files:
        model=convert(path); name=path.stem+'.json'
        if name in models: raise ValueError('duplicate instance filename')
        models[name]=model
    if len(expected)!=870 or set(models)!=set(expected):
        raise ValueError('integer TXT inputs do not match the fixed MIPO manifest')
    a.output.mkdir(parents=True,exist_ok=True)
    for name in expected:
        target=a.output/name
        if target.exists() and json.loads(target.read_text())!=models[name]:
            raise ValueError('existing input differs from published TXT: '+str(target))
    for name in expected:
        (a.output/name).write_text(json.dumps(models[name],separators=(',',':'))+'\n',encoding='utf-8')
    print(f'Converted {len(models)} MIPO TXT models without rounding; fixed manifest unchanged.')


if __name__=='__main__': main()
