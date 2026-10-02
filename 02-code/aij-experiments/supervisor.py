"""Linux wall-clock and aggregate-RSS supervision, including descendants."""
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import psutil
from metrics import merge


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def supervise(command, folder, limits, stop=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    state = {'verify_at': None, 'final': None, 'metrics': {}, 'history': []}
    start = time.monotonic()
    peak = 0
    termination = None
    with (folder / 'stdout.log').open('a', encoding='utf-8') as log:
        proc = subprocess.Popen(command, cwd=folder, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                start_new_session=True, bufsize=1)

        def drain():
            def save_progress():
                temporary = folder/'progress.json.tmp'
                temporary.write_text(json.dumps({'metrics':state['metrics'], 'history':state['history']}, ensure_ascii=False), encoding='utf-8')
                temporary.replace(folder/'progress.json')
            for line in proc.stdout:
                log.write(line)
                log.flush()
                if line.startswith('AIJ_PHASE '):
                    event = json.loads(line[10:])
                    state['history'].append({'phase':event['phase'], 'at':event['at']})
                    if event['phase'] == 'verify' and state['verify_at'] is None:
                        state['verify_at'] = event['at']
                    save_progress()
                elif line.startswith('AIJ_PROGRESS '):
                    event = json.loads(line[13:])
                    merge(state['metrics'], event['metrics'])
                    if event.get('phase'):
                        state['history'].append({'phase':event['phase'], 'at':event['at']})
                    save_progress()
                elif line.startswith('AIJ_RESULT '):
                    state['final'] = json.loads(line[11:])

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            while proc.poll() is None:
                now = time.monotonic()
                verify_at = state['verify_at']
                if stop is not None and stop.is_set():
                    termination = 'INTERRUPTED'
                elif now - start >= limits.get('outer_seconds', float('inf')):
                    termination = 'OUTER_TIMEOUT'
                elif verify_at is None and now - start >= limits['solve_seconds']:
                    termination = 'TIMEOUT'
                elif verify_at is not None and verify_at - start > limits['solve_seconds']:
                    termination = 'TIMEOUT'
                elif verify_at is not None and now - verify_at >= limits['verify_seconds']:
                    termination = 'VERIFY_TIMEOUT'
                try:
                    root = psutil.Process(proc.pid)
                    rss = 0
                    for item in [root] + root.children(recursive=True):
                        try:
                            rss += item.memory_info().rss
                        except psutil.NoSuchProcess:
                            pass
                    peak = max(peak, rss)
                    if rss > limits['memory_gib'] * 1024**3:
                        termination = 'OOM'
                except psutil.NoSuchProcess:
                    pass
                if termination:
                    kill_group(proc)
                    break
                time.sleep(limits.get('poll_seconds', .05))
        finally:
            # An exited wrapper can leave an external solver running.
            kill_group(proc)
            reader.join(timeout=2)
            proc.stdout.close()
    end = time.monotonic()
    verify_at = state['verify_at']
    if termination is None:
        solve_end = verify_at if verify_at is not None else end
        if solve_end - start > limits['solve_seconds']:
            termination = 'TIMEOUT'
        elif verify_at is not None and end - verify_at > limits['verify_seconds']:
            termination = 'VERIFY_TIMEOUT'
    result = state['final'] or {'status': 'ERROR', 'verified': False, 'error': 'worker exited without a result'}
    if termination:
        result = {'status': 'INVALID' if termination == 'VERIFY_TIMEOUT' else termination,
                  'verified': False, 'termination': termination, 'claimed_result': state['final']}
    elif proc.returncode and result['status'] not in ('ERROR', 'INVALID'):
        result.update(status='ERROR', error=f'worker exit code {proc.returncode}', verified=False)
    elapsed = end - start
    result = merge(dict(state['metrics']), result)
    history = [{'phase':'startup','at':start}] + state['history']
    phase_seconds = {}
    for event, following in zip(history, history[1:]+[{'at':end}]):
        phase_seconds[event['phase']] = phase_seconds.get(event['phase'],0) + max(0,following['at']-event['at'])
    result.update(last_phase=history[-1]['phase'], termination_phase=history[-1]['phase'] if termination else None,
                  phase_seconds=phase_seconds)
    result.update(solve_budget_seconds=limits['solve_seconds'], outer_budget_seconds=limits.get('outer_seconds'),
                  verify_budget_seconds=limits['verify_seconds'], memory_budget_gib=limits['memory_gib'],
                  returncode=proc.returncode, wall_seconds=elapsed,
                  solve_wall_seconds=(verify_at - start) if verify_at is not None else elapsed,
                  verify_wall_seconds=(end - verify_at) if verify_at is not None else 0,
                  peak_tree_rss_bytes=peak)
    return result
