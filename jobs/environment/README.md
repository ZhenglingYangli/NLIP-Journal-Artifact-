# Ubuntu 测试环境导出与 MatriCS 安装（不使用虚拟环境）

导出日期：2026-10-04。源解释器是 Ubuntu 实验实际使用的 Python 3.9.25，位于 `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/02-code/aij-experiments/.venv/bin/python`。这是包版本导出，不复制 `.venv` 目录；MatriCS 使用其站点 Python 3.9.20，二者补丁版本不同，安装后必须在计算节点测试。

## 文件

- `requirements-ubuntu-runtime.txt`：Ubuntu 的 22 个运行依赖及实际版本，已去掉指向 Ubuntu 绝对路径的 NLIPSat editable 安装项。
- `requirements-matrics-python39.txt`：21 个包，版本与 Ubuntu 对应包一致，只排除 CPLEX，供集群安装。
- 本地交付包另附 `requirements-ubuntu-freeze.txt`：原始 `pip freeze --all`，包含 pip、setuptools 与本地源码路径，只用于查看，不直接用于 MatriCS 安装。

NLIPSat 核心代码使用仓库 `codes/`；现有 worker 会从配置的 code_root 加载它，不需要安装原始 freeze 中的 Ubuntu 源码路径。

## Ubuntu 检查结果

`pip check` 返回 No broken requirements found；pysat、pypblib、z3、psutil、pyscipopt、numpy、cvc5、highspy、cplex、matplotlib 均可导入。这些结果确认 Python 依赖可用，不等于所有正式实例已运行。

Ubuntu 的 CPLEX 包为 22.1.2.1，但 1001 变量探测返回社区版限制错误 1016，不能视为完整许可。MatriCS 截图中的站点模块是 optimizer/cplex/22.1.1.0；模块加载后仍需确认 Python API 路径、实际版本及计算节点上的完整许可证。本安装清单不会用 PyPI CPLEX 覆盖站点配置。

## 在 MatriCS 安装

在登录节点执行。下面按当前用户实际 checkout 路径设置项目目录，不创建或激活 `.venv`。

```bash
export NLIP_WORKDIR=/scratch/scherif/NLIP/AIJ/NLIP-Journal-Artifact-
module load python/3.9.20
module load optimizer/cplex/22.1.1.0
export PYTHON="$(python3 -c 'import sys; print(sys.executable)')"
export AIJ_PYTHON="$PYTHON"
export NLIP_LEGACY_ROOT=/scratch/scherif/NLIP/NLIP
export AIJ_RUNNER_DIR="$NLIP_WORKDIR/jobs"
export AIJ_CONFIG="$AIJ_RUNNER_DIR/config.cluster.json"

"$AIJ_PYTHON" --version
curl -fsSL https://raw.githubusercontent.com/ZhenglingYangli/NLIP-Journal-Artifact-/main/jobs/environment/requirements-matrics-python39.txt \
  -o /tmp/nlip-requirements-matrics-python39.txt
"$AIJ_PYTHON" -m pip install --user -r /tmp/nlip-requirements-matrics-python39.txt
"$AIJ_PYTHON" -m pip check
```

也可把本地提供的安装清单传到集群，再把 -r 后的路径换成该文件位置。安装按导出的固定版本执行；满足要求的包不重装，版本不同的包会安装对应用户版本。无需 sudo，也不修改管理员安装的库；用户包会参与当前 Python 的导入。

## 安装后检查 CPLEX

```bash
"$AIJ_PYTHON" - <<'PY'
import sys, importlib
print('Python:', sys.executable, sys.version)
for name in ['pysat','pypblib','z3','psutil','pyscipopt','numpy','cvc5','highspy','matplotlib']:
    importlib.import_module(name)
    print(name, 'OK')
try:
    import cplex
    print('CPLEX API:', cplex.__file__)
    print('CPLEX version:', cplex.Cplex().get_version())
except Exception as error:
    print('CPLEX API 不可用:', error)
PY
module show optimizer/cplex/22.1.1.0
```

如站点仅加载了 CPLEX 命令行、没有使 Python API 可用，需要按其真实安装目录配置 Python API。不要猜路径或仅安装 PyPI 社区包来替代完整安装。

仓库当前常规 requirements/check_environment 固定 CPLEX 22.1.2.1；如果最终采用站点 22.1.1，需先统一该配置，不能把版本不符的环境报告为检查通过。此处安装流程是手动准备，不调用 setup 或总入口。

## 仍需在集群确认的内容

MaxHS、WMaxCDCL、Open-WBO 是外部可执行程序，不在 pip 导出中；旧数据位置和 MIPO 也不包含在环境导出里。Python 依赖装好、CPLEX 版本与完整安装配置统一后，再按手册完成 configure/check 和计算节点 61 配置小实例测试，通过后启动正式实验。正式预算与实验矩阵保持原方案。
