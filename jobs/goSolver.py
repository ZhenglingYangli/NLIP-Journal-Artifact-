#!/usr/bin/env python3
"""Plan or execute the current AIJ matrix. Defaults to planning only."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent


def methods(task, matrix, family=None):
    if task == 'decision':
        baselines = [{'id': 'z3', 'solver': 'Z3'}, {'id': 'cvc5', 'solver': 'CVC5'}]
        backends = ['CADICAL']
    else:
        native = 'CPLEX-MILP' if family == 'mipo' else 'CPLEX-NATIVE'
        baselines = [{'id': s.lower(), 'solver': s}
                     for s in ['SCIP-NATIVE', 'Z3', native, 'SCIP-MILP', 'HIGHS-MILP']]
        backends = ['MAXHS', 'RC2', 'WMAXCDCL', 'OPENWBO']
    if matrix == 'baselines':
        return baselines
    if matrix == 'decomposition':
        if family not in ('mipo', 'smt'):
            return []
        backend = 'CADICAL' if task == 'decision' else 'RC2'
        return [{'id': 'bin-d-unshared-' + backend.lower(), 'encoding': 'BIN', 'solver': backend,
                 'options': {'use_lrn': False, 'use_decomposition': True, 'decomp_shared': False}}]
    variants = [{'id': f'{enc.lower()}-{solver.lower()}', 'encoding': enc, 'solver': solver, 'options': {'use_lrn': False}}
                for enc in ['OH', 'UNA', 'BIN'] for solver in backends]
    if family in ('mipo', 'smt'):
        variants += [{'id': 'bin-d-' + s.lower(), 'encoding': 'BIN', 'solver': s,
                      'options': {'use_lrn': False, 'use_decomposition': True, 'decomp_shared': True}}
                     for s in backends]
    return variants + baselines


def resolve(value):
    return str((ROOT / os.path.expandvars(value)).resolve())


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    for key in ['code_root', 'benchmark_root', 'manifest_root', 'python']:
        value = (config[key] or sys.executable) if key == 'python' else config[key]
        config[key] = (os.path.abspath(ROOT / os.path.expandvars(value))
                       if key == 'python' else resolve(value))
    config['solver_paths'] = {k: resolve(v) for k, v in config['solver_paths'].items()}
    for desc in config['families'].values():
        if 'input_root' in desc:
            desc['input_root'] = resolve(desc['input_root'])
    return config


def make_jobs(config, profile, matrix, families):
    jobs = []
    for family in families:
        desc = config['families'][family]
        if profile == 'smoke':
            files = [ROOT / 'smoke' / desc['smoke_file']]
        else:
            directory = Path(desc['input_root']) if 'input_root' in desc else Path(config['benchmark_root']) / desc['directory']
            names = (Path(config['manifest_root']) / desc['manifest']).read_text().splitlines()
            names = [n.strip() for n in names if n.strip() and not n.startswith('#')]
            index = {}
            for path in directory.rglob('*' + desc['extension']):
                index.setdefault(path.name, []).append(path)
            files = []
            for name in names:
                direct = directory / name
                matches = [direct] if direct.is_file() else index.get(name, [])
                if len(matches) != 1:
                    raise ValueError(f'{family}/{name}: expected one input, found {len(matches)}; search directory: {directory}')
                files.append(matches[0])
        for number, path in enumerate(files, 1):
            for method in methods(desc['task'], matrix, family):
                job = {'id': f'{family}-{number:04d}-{method["id"]}', 'family': family,
                       'task': desc['task'], 'input': str(path.resolve()), 'method': method,
                       'code_root': config['code_root'], 'solver_paths': config['solver_paths'],
                       'solve_seconds': config['profiles'][profile]['solve_seconds']}
                if 'k' in desc:
                    job['k'] = desc['k']
                if profile == 'smoke':
                    job['smoke_expected'] = desc['smoke_expected']
                jobs.append(job)
    return jobs


def available_cpus():
    import psutil
    found = {}
    for cpu in psutil.Process().cpu_affinity():
        topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        try:
            key = ((topology / 'physical_package_id').read_text().strip(),
                   (topology / 'core_id').read_text().strip())
        except OSError:
            key = ('logical', cpu)
        found.setdefault(key, cpu)
    return list(found.values())


def git_identity(code):
    def git(*args):
        return subprocess.check_output(['git', '-C', code, *args], text=True).strip()
    return {'commit': git('rev-parse', 'HEAD'),
            'dirty': bool(git('status', '--porcelain', '--', code))}


def check_cplex_license(python):
    probe = """import cplex
c=cplex.Cplex()
c.set_results_stream(None); c.set_log_stream(None); c.set_error_stream(None)
c.variables.add(types='B'*1001)
c.parameters.threads.set(1); c.parameters.timelimit.set(2)
try:
    c.solve()
except cplex.exceptions.CplexError as exc:
    raise SystemExit('CPLEX full-size license unavailable: '+str(exc))
"""
    checked = subprocess.run([python, '-c', probe], capture_output=True, text=True, timeout=30)
    if checked.returncode:
        raise ValueError(checked.stdout + checked.stderr)


def resume_compatible(previous, current):
    if previous.get('cpu_model'):
        def comparable(value):
            return {k:v for k,v in value.items() if k not in ('host', 'cpus')}
        return comparable(previous) == comparable(current)
    return previous == {k:v for k,v in current.items() if k != 'cpu_model'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', nargs='?', choices=['test', 'run'], help='test a bundled instance or run one formal configuration')
    ap.add_argument('family', nargs='?', choices=['qplib', 'diverse', 'mipo', 'smt', 'all'])
    ap.add_argument('method', nargs='?', help='method id, e.g. bin-rc2 or bin-cadical')
    ap.add_argument('--config')
    ap.add_argument('--profile', choices=['smoke', 'formal'], default='smoke')
    ap.add_argument('--matrix', choices=['main', 'decomposition', 'baselines'], default='main')
    ap.add_argument('--families', nargs='+', choices=['qplib', 'diverse', 'mipo', 'smt'], default=['qplib', 'diverse', 'mipo', 'smt'])
    ap.add_argument('--workers', type=int)
    ap.add_argument('--methods', nargs='+', help='run only these exact method ids')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--plan-output', type=Path, help='save the expanded job list without running it')
    ap.add_argument('--execute', action='store_true', help='execute instead of printing the plan')
    ap.add_argument('--resume', action='store_true', help='continue jobs that have no completed result')
    args = ap.parse_args()
    if args.action:
        if args.action == 'run' and (args.family in (None, 'all') or not args.method):
            ap.error('run requires a family and method, e.g. run qplib bin-rc2')
        args.profile = 'smoke' if args.action == 'test' else 'formal'
        if args.family == 'all':
            if args.method:
                ap.error('test all runs the complete matrix; omit the method')
            args.families = ['qplib', 'diverse', 'mipo', 'smt']
            args.methods = None
        else:
            args.families = [args.family or 'qplib']
            args.methods = [args.method or ('bin-cadical' if args.family == 'smt' else 'bin-rc2')]
        args.execute = True
    if args.workers is None:
        args.workers = 7 if args.action == 'run' else 1
    if args.config is None:
        site_config = ROOT / 'config.cluster.json'
        args.config = str(site_config if (args.profile == 'formal' or args.action) and site_config.exists() else ROOT / 'config.json')
    config = load_config(args.config)
    jobs = make_jobs(config, args.profile, args.matrix, args.families)
    if args.methods:
        missing = set(args.methods) - {j['method']['id'] for j in jobs}
        if missing:
            raise ValueError('unknown method ids: ' + str(sorted(missing)))
        jobs = [j for j in jobs if j['method']['id'] in args.methods]
    limits = config['profiles'][args.profile]
    counts = dict(Counter(job['family'] for job in jobs))
    plan = {'profile': args.profile, 'matrix': args.matrix, 'jobs': len(jobs),
                      'by_family': counts, 'solve_core_hours_upper_bound': len(jobs) * limits['solve_seconds'] / 3600,
            'limits': limits}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.plan_output:
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.write_text(json.dumps(dict(plan, job_list=jobs), ensure_ascii=False, indent=2))
    if not args.execute:
        return
    if os.name != 'posix':
        raise ValueError('execution requires Linux; edit/run this package on the Ubuntu or cluster host')
    import psutil
    from internal.supervisor import supervise
    cpus = available_cpus()
    if args.workers < 1 or args.workers > len(cpus):
        raise ValueError(f'workers must be between 1 and {len(cpus)} available distinct cores')
    memory = psutil.virtual_memory().available
    if os.environ.get('SLURM_MEM_PER_NODE'):
        memory = min(memory, int(os.environ['SLURM_MEM_PER_NODE']) * 1024**2)
    cgroup = Path('/sys/fs/cgroup/memory.max')
    if cgroup.exists() and cgroup.read_text().strip() != 'max':
        memory = min(memory, int(cgroup.read_text()))
    needed = (args.workers * limits['memory_gib'] + .5) * 1024**3
    if memory < needed:
        raise ValueError(f'need {needed/1024**3:.1f} GiB including runner reserve; available/allocation {memory/1024**3:.1f} GiB')
    for solver in {j['method']['solver'] for j in jobs} & set(config['solver_paths']):
        if not os.access(config['solver_paths'][solver], os.X_OK):
            raise ValueError(f'{solver} binary is missing or not executable: {config["solver_paths"][solver]}')
    identity = git_identity(config['code_root'])
    execution_identity = git_identity(str(ROOT))
    if args.profile == 'formal' and (identity['dirty'] or execution_identity['dirty']):
        raise ValueError('commit both the active solver and experiment runner code before a formal batch')
    if any(j['method']['solver'].startswith('CPLEX') for j in jobs):
        check_cplex_license(config['python'])
    versions = subprocess.check_output([config['python'], '-c',
        "import importlib.metadata as m,json,sys; print(json.dumps({'python':sys.version, **{p:m.version(p) for p in ['python-sat','pypblib','z3-solver','psutil']}}))"], text=True)
    versions = json.loads(versions)
    if any(j['method']['solver'].startswith('SCIP') for j in jobs):
        scip_version = subprocess.check_output([config['python'], '-c',
            "import pyscipopt as b,json,numpy; m=b.Model(); print(json.dumps({'pyscipopt':b.__version__, 'numpy':numpy.__version__, 'scip':f'{m.getMajorVersion()}.{m.getMinorVersion()}.{m.getTechVersion()}'}))"], cwd=ROOT, text=True)
        versions.update(json.loads(scip_version))
    if any(j['method']['solver'] == 'CVC5' for j in jobs):
        versions['cvc5'] = subprocess.check_output([config['python'], '-c',
            'import cvc5; print(cvc5.__version__)'], cwd=ROOT, text=True).strip()
    for package in ('highspy', 'cplex'):
        needed_solver = 'HIGHS' if package == 'highspy' else 'CPLEX'
        if any(j['method']['solver'].startswith(needed_solver) for j in jobs):
            versions[package] = subprocess.check_output([config['python'], '-c',
                f'import importlib.metadata as m; print(m.version({package!r}))'], text=True).strip()
    cpu_model = sorted({line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                        if line.startswith('model name')})
    snapshot = {'config': config, 'profile': args.profile, 'matrix': args.matrix, 'jobs': jobs,
                'workers': args.workers, 'cpus': cpus[:args.workers], 'code': identity,
                'execution_code': execution_identity,
                'versions': versions, 'host': platform.node(), 'platform': platform.platform(), 'cpu_model': cpu_model}
    output = (args.output or ROOT / '../results' /
              (args.profile + '-' + args.matrix + '-' + datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
    output.mkdir(parents=True, exist_ok=True)
    import fcntl
    run_lock = (output / '.runner.lock').open('a')
    try:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('another runner is already using this output directory')
    planfile = output / 'run.json'
    if planfile.exists():
        if not args.resume:
            raise ValueError('output already contains a run; use --resume or choose another output directory')
        previous = json.loads(planfile.read_text())['plan']
        # Cluster requeues can use another node of the same hardware class.
        if not resume_compatible(previous, snapshot):
            raise ValueError('resume requires the same code, configuration, CPU model, platform, versions and inputs')
    else:
        if args.resume:
            raise ValueError('no existing run.json to resume')
        planfile.write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(),
                                       'plan': snapshot}, ensure_ascii=False, indent=2))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    cpu_queue = __import__('queue').Queue()
    for cpu in cpus[:args.workers]:
        cpu_queue.put(cpu)

    def run(job):
        if stop.is_set():
            return None
        folder = output / 'jobs' / job['id']
        resultfile = folder / 'result.json'
        if resultfile.exists():
            return json.loads(resultfile.read_text())
        cpu = cpu_queue.get()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            payload = dict(job, cpu=cpu)
            jobfile = folder / 'job.json'
            jobfile.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            command = [config['python'], '-u', str(ROOT / 'internal/worker.py'), str(jobfile)]
            result = supervise(command, folder, limits, stop)
            if result['status'] == 'INTERRUPTED':
                return None
            result.update(job_id=job['id'], family=job['family'], task=job['task'],
                          input=job['input'], method=job['method'], cpu=cpu, command=command,
                          host=platform.node(), cpu_model=cpu_model)
            temporary = folder / 'result.json.tmp'
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            temporary.replace(resultfile)
            print(job['id'], result['status'], result.get('objective_exact'), flush=True)
            return result
        finally:
            cpu_queue.put(cpu)

    pool = ThreadPoolExecutor(max_workers=args.workers)
    futures = [pool.submit(run, job) for job in jobs]
    try:
        for future in as_completed(futures):
            future.result()
    except KeyboardInterrupt:
        stop.set()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    subprocess.run([config["python"], str(ROOT.parent / "analysis/summarize.py"), str(output)], check=True)
    print('Results:', output)
    if args.profile == 'smoke':
        failures = []
        for job in jobs:
            path = output / 'jobs' / job['id'] / 'result.json'
            result = json.loads(path.read_text()) if path.exists() else {}
            if not result.get('verified') or any(result.get(key) != value for key, value in job['smoke_expected'].items()):
                failures.append(job['id'])
        if failures:
            raise ValueError('small-instance tests failed: ' + ', '.join(failures))
        print(f'Tests passed: {len(jobs)} (expected answers and original-problem verification)')


if __name__ == '__main__':
    main()
