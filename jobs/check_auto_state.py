"""Read existing scientific records for the automatic cluster entry point."""
import json
from pathlib import Path
import sys
from goSolver import ROOT, git_identity, load_config

def check(action, folder, other, matrix=None):
    if action == 'delivery':
        if json.loads((folder/'summary.json').read_text())['statuses'].get('PENDING', 0):
            raise ValueError('当前结果还有 PENDING，不能复用交付。')
        for name in ['campaign.json', 'summary.json', 'results.csv']:
            if (folder/name).read_bytes() != (other/name).read_bytes():
                raise ValueError('已有交付与当前结果不同，请移走旧交付目录再重开入口。')
        if not (folder/'verification-records.tar.gz').is_file():
            raise ValueError('缺少验解包，请重新导出。')
        return
    config = load_config(other)
    if action == 'campaign':
        plan = json.loads((folder/'campaign.json').read_text())
        if plan['matrix'] != matrix or plan['profile'] != 'formal':
            raise ValueError('已有批次不是指定的正式实验，请使用正确的批次名。')
        if plan['config_snapshot'] != config or plan['code_version'] != git_identity(config['code_root']) or plan['runner_version'] != git_identity(str(ROOT)):
            raise ValueError('已有批次依赖的代码或环境配置已改变；不能自动混用，请恢复原版本或使用新批次名。')
        return
    plan = json.loads((folder/'run.json').read_text())['plan']
    if plan['config'] != config or plan['code'] != git_identity(config['code_root']) or plan['execution_code'] != git_identity(str(ROOT)) or len(plan['jobs']) != 61:
        raise ValueError('小实例测试与当前代码/配置不匹配，需要重新测试。')
    for job in plan['jobs']:
        result = json.loads((folder/'jobs'/job['id']/'result.json').read_text())
        if not result.get('verified') or any(result.get(key) != value for key,value in job['smoke_expected'].items()):
            raise ValueError('小实例答案未通过：'+job['id'])
    print('当前代码和配置的 61 配置小实例测试已通过，复用测试结果。')

if __name__ == '__main__':
    try:
        check(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4] if len(sys.argv)>4 else None)
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
