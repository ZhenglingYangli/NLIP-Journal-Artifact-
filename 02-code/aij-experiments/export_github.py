"""Export committed experiment code and manifests to a reviewable GitHub directory."""
import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output', type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = a.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Use an empty delivery directory; existing review content is preserved.')
    paths = ['02-code/nlipsat-aij', '02-code/aij-experiments', '03-benchmarks/manifests']
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--', *paths]).strip():
        raise SystemExit('Commit experiment changes before exporting.')
    names = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--', *paths]).decode().split('\0')
    for name in filter(None, names):
        if name.endswith('/config.ubuntu.json'):
            continue
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    (output / '.gitignore').write_text('__pycache__/\n*.py[cod]\n.venv/\n*.egg-info/\n04-results/\n03-benchmarks/mipo/\n')
    (output / '.gitattributes').write_text('* text=auto eol=lf\n')
    (output / 'README.md').write_text('''# NLIP-AIJ experiment artifact

NLIPSat encodings and solver comparisons for QPLIB (137), Diverse SAT (108, k=2),
MIPO (870), and bounded SMT (150). The main matrix contains 23,335 runs.
LRN is an optional module and is disabled in the formal main experiment.

- [Cluster deployment and data preparation](02-code/aij-experiments/CLUSTER_DEPLOYMENT.md)
- [Experiment protocol and solver routes](02-code/aij-experiments/README.md)
- Solver implementation: `02-code/nlipsat-aij`
- Experiment runner: `02-code/aij-experiments`
- Fixed instance lists: `03-benchmarks/manifests`

MIPO inputs are retrieved from the authors' archive with `prepare_mipo.py`.
The other three datasets and external MaxSAT executables use the site's existing installation.
Python environments, solver licenses, benchmark payloads, and experiment results are not included.
''', encoding='utf-8')
    print('Review directory prepared (no GitHub push): ' + str(output))


if __name__ == '__main__':
    main()
