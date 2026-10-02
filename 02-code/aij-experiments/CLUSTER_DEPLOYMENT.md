# NLIP-AIJ：Ubuntu → GitHub → MatriCS

GitHub 目标：<https://github.com/ZhenglingYangli/NLIP-Journal-Artifact->。
上传内容在 Ubuntu 整理、验证；由用户确认后推送。正式实验在集群小实例验收通过后提交。

## 目录与数据

```text
NLIP-Journal-Artifact-/
├── README.md
├── 02-code/
│   ├── nlipsat-aij/             # 当前 NLIPSat，LRN 默认关闭
│   └── aij-experiments/         # 四组数据的运行器与 Slurm 入口
├── 03-benchmarks/
│   ├── manifests/              # 固定实例清单
│   └── mipo/                   # 在目标机器下载、转换产生；不上传公开仓库
└── 04-results/                 # 运行后产生；不上传 GitHub
```

Ubuntu 活动目录：`/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ`。
当前求解代码位于其 `02-code/nlipsat-aij`，运行代码位于 `02-code/aij-experiments`。
旧实验参考为 `/home/ubuntu/#科研项目/MIS/0-NLIP/NLIP_composes/experiment`；
并行组织参考为 `/home/ubuntu/#科研项目/MIS/2-DiverseSAT_QiKan/new-exps`。
待推送目录另行导出为 `/home/ubuntu/NLIP-Journal-Artifact-publish`，只包含上述部署内容。

旧 NLIP 代码以 `benchmarks/`、`solvers/maxsat/` 相对目录组织数据和外部程序。
当前配置中的 `/scratch/scherif/NLIP/NLIP` 是候选旧安装根目录，须由集群实际文件检查确认。
部署入口还支持 Diverse SAT 脚本明确使用的共享求解器位置：

| 内容 | 候选位置或获取方式 |
|---|---|
| QPLIB 137 | `$NLIP_LEGACY_ROOT/benchmarks/qplib_fully_passed` |
| Diverse SAT 108，k=2 | `$NLIP_LEGACY_ROOT/benchmarks/diverse_sat` |
| 有界 SMT 150 | `$NLIP_LEGACY_ROOT/benchmarks/smt_0_10` |
| MIPO 870 | 本仓库 `03-benchmarks/mipo`，由 `prepare_mipo.py` 产生 |
| MaxHS | 旧根目录 `solvers/maxsat/maxhs`；或 `/users/scherif/ComputeSpace/solvers/maxhs` |
| WMaxCDCL | 旧根目录 `solvers/maxsat/wmaxcdcl`；或 `/users/scherif/ComputeSpace/solvers/wmaxcdcl_24` |
| Open-WBO | 旧根目录 `solvers/maxsat/openwbo`；或共享目录下同名程序 |
| RC2、CaDiCaL | Python-SAT 包中的接口 |
| Z3、cvc5、SCIP、HiGHS、CPLEX | 对应 Python 包；CPLEX 需可用于大模型的完整许可证 |

共享目录中的 Open-WBO 路径只是候选；Diverse SAT 脚本不能证明它已安装。
`configure_cluster.py` 会检查所有 1,265 个输入路径和三个外部可执行文件，打印最终选择。
不要将 Diverse SAT 的 289 个实例、7200 秒预算或 120G 作业内存直接用于本实验。

## MIPO

来源：<https://wwwold.mathematik.tu-dortmund.de/lsv/instances/mipo.tar.gz>。
使用发布包 `integer/txtfiles` 下的全部 870 个模型，530 个多值整数模型和 340 个布尔模型。
保留有限整数域、最小化方向以及 TXT 十进制系数的精确有理数值。
同包 NL 文件系数精度可能不同，不能替换为 NL 或静默采用 NL 最优值作为精确 oracle。

公开仓库提供作者来源、固定清单和转换程序；原数据及转换后的 JSON 在目标机器生成。
原包未查到明确的再分发许可说明，因此不把数据本体重新发布到 GitHub。
现有 Ubuntu 输入和部署包中的本地数据可继续使用；无需更换实验实例。

`prepare_mipo.py` 下载原包，核对 870 个文件与固定清单完全一致，再调用同一转换函数生成 JSON。
若目标目录已有数据，先比较模型内容，发现不同即报告。已有原包可传 `--archive /path/to/mipo.tar.gz`。

## 集群部署

以下命令在获确认、GitHub 已推送后执行。集群 checkout 位置可自行选择，目录相对布局需保留。

```bash
git clone https://github.com/ZhenglingYangli/NLIP-Journal-Artifact-.git
cd NLIP-Journal-Artifact-/02-code/aij-experiments
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export AIJ_PYTHON="$PWD/.venv/bin/python"
export AIJ_RUNNER_DIR="$PWD"

# 若集群以 module 提供 Python 或 CPLEX，先加载该站点实际模块。
# requirements 中的 cplex 包本身不保证拥有完整许可证。
# 配置集群完整 CPLEX 的 Python API/许可证后，由小实例作业进行大模型许可证检测。

"$AIJ_PYTHON" prepare_mipo.py

# 默认候选旧根目录；如实际安装不同，在这里改路径。
export NLIP_LEGACY_ROOT=/scratch/scherif/NLIP/NLIP
# 可选覆盖：NLIP_BENCHMARK_ROOT、NLIP_MAXHS、NLIP_WMAXCDCL、NLIP_OPENWBO。
# 若只从 Diverse SAT 目录取 CNF，可设置：
# export NLIP_DIVERSE_ROOT=/users/scherif/ComputeSpace/DiverseSAT/benchmarks
"$AIJ_PYTHON" configure_cluster.py

# 在计算节点测试完整 61 配置的小实例与 CPLEX 完整许可证。
sbatch --export=ALL run_cluster_smoke.sh
```

查看小实例作业日志：必须完成 61 项，见证通过，状态与已知目标吻合，且 `failures` 为空。
许可证、动态库或路径错误先在当前 checkout 修复；不要提交正式批次来试错。

```bash
# 小实例验收通过后，仅生成正式计划。
"$AIJ_PYTHON" prepare_campaign.py --config config.cluster.json \
  --output ../../04-results/aij-main-config
# 以下命令才提交 61 个配置作业。
bash ../../04-results/aij-main-config/submit.sh
"$AIJ_PYTHON" summarize_campaign.py ../../04-results/aij-main-config

# 原定额外分解对照独立生成，共 2 个配置、1020 次运行。
"$AIJ_PYTHON" prepare_campaign.py --config config.cluster.json \
  --matrix decomposition --output ../../04-results/aij-decomposition-config
# 需要运行该对照时再执行对应 submit.sh。
```

`campaign.json` 包含目标机器绝对路径；必须在集群重新生成，不能复制 Ubuntu 生成的计划直接提交。
`config.cluster.json` 是本机解析结果，Git 忽略它；修改求解代码则应提交并重新生成计划。
运行中的正式批次不要 `git pull`；待批次结束或停止后再更新。

## 正式资源与当前验收边界

主实验共 23,335 次运行：QPLIB 2,329、Diverse SAT 1,836、MIPO 18,270、SMT 900。
61 个 Slurm 数组元素按“数据集＋方法”分开输出。每作业内 10 个单核 worker，默认同时最多 3 个作业，
即最多 30 个实例并行；4 个作业时最多 40 个实例并行。

每作业申请 bigmem、1 个独占节点、10 个 CPU、170G 内存、99 小时墙钟上限。
99 小时覆盖最长 870 实例配置按 10 路、每实例 4000 秒计算并加余量；不是主实验总完成时间。
独占节点可能按整节点核心数占用账户配额，10 worker 不等于只占用 10 核的调度配额。
bigmem 官方页面列出单节点 28 核、用户上限 112 核，因而并发独占节点按最多 4 个设置；实际仍服从账户现有占用。
来源：<https://www.matrics.u-picardie.fr/en/documentation-2/partitions/>。

每实例求解阶段 3600 秒（包括启动、解析与编码），验解 120 秒，外围 4000 秒；进程树 RSS 16 GiB。
LRN 默认及正式方法配置均关闭，仍可通过 API 独立开启。

Ubuntu 已核对数据、代码和计划生成；还没有在 MatriCS 计算节点完成验收。
剩余集群端确认项集中为：实际路径、二进制及动态库可运行、Python 依赖安装、完整 CPLEX 许可证、Slurm 账户实际资源。
这些由上面的路径检查和一次计算节点 61 项小实例作业确认。未经这一步不能称为已具备正式开跑条件。
