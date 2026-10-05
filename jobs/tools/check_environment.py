"""Check the selected interpreter; install only missing pinned distributions."""
import argparse
import importlib
import importlib.metadata as metadata
from pathlib import Path
import subprocess
import sys

MODULES = {'python-sat': 'pysat', 'z3-solver': 'z3'}

def requirements(path):
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            yield from requirements(path.parent / line[3:].strip())
        else:
            name, version = line.split('==')
            yield name, version

def inspect(packages):
    missing, problems = [], []
    for name, expected in packages:
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            # Site-provided APIs can be importable without pip metadata.
            try:
                importlib.import_module(MODULES.get(name, name))
            except ModuleNotFoundError as error:
                if error.name != MODULES.get(name, name):
                    problems.append(f'{name}: 接口存在但缺少依赖：{error}')
                    continue
            except Exception as error:
                problems.append(f'{name}: 无安装元数据且无法导入：{error}')
                continue
            else:
                problems.append(f'{name}: 可以导入但无安装版本元数据；请核实站点提供的版本，未自动替换')
                continue
            missing.append(f'{name}=={expected}')
            print(f'{name}: 缺少，要求 {expected}')
            continue
        try:
            importlib.import_module(MODULES.get(name, name))
        except Exception as error:
            problems.append(f'{name}: 已安装但无法导入：{error}')
        if actual != expected:
            problems.append(f'{name}: 已安装 {actual}，要求 {expected}；未自动替换')
        print(f'{name}: {actual}')
    return missing, problems

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-missing', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    packages = list(requirements(root / 'jobs/requirements.txt'))
    packages += list(requirements(root / 'analysis/requirements-analysis.txt'))
    print(f'当前 Python：{sys.executable}')
    missing, problems = inspect(packages)
    if missing and args.install_missing:
        print('只补装：' + ', '.join(missing), flush=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', *missing], check=True)
        importlib.invalidate_caches()
        missing, problems = inspect(packages)
    for problem in problems:
        print(problem, file=sys.stderr)
    if missing or problems:
        print('请在这个项目环境中处理以上问题，再检查；已安装包不会因版本不同自动替换。', file=sys.stderr)
        return 1
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    print('Python 依赖检查通过。求解器执行和完整 CPLEX 许可证由计算节点小实例测试检查。')
    return 0

if __name__ == '__main__':
    sys.exit(main())
