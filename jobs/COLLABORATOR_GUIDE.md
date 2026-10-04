# NLIP-AIJ 合作者手册：服务器位置、环境测试与正式实验

核对日期：2026-10-04。适用仓库：[ZhenglingYangli/NLIP-Journal-Artifact-](https://github.com/ZhenglingYangli/NLIP-Journal-Artifact-)。

本文是合作者的主操作文档。命令默认在 **MatriCS 登录节点、仓库根目录**执行；计算任务由 Slurm 分配到计算节点。`setup` 等单词是统一操作脚本的子命令。

## 1. 目前完成了什么，正式开跑前还缺什么

代码、四组输入清单、求解器接口、预算管理、汇总分析和集群操作脚本已在 Ubuntu 验证；GitHub 已发布。MatriCS 尚未由本次核查登录或提交测试作业，不能把 Ubuntu 验证当成 MatriCS 已验收。

| 项目 | 当前证据 | 合作者下一步 |
|---|---|---|
| 正式矩阵与输入位置 | Ubuntu 重新定位 1265 个输入，生成 23335 次运行、61 个配置 | 在 MatriCS 重新 configure 和 check |
| 全部正式方法的调用接口 | 61 个代表性小实例：55 OPTIMAL、6 SAT，均原问题验解通过 | 在计算节点运行 smoke |
| 基线语义与矩阵测试 | 本次运行 test_final_matrix.py，5 项通过，包括小模型枚举比较与 CPLEX 二次约束边界 | 无须把所有开发测试再变成一轮性能实验 |
| 预算、终止和结果统计 | 既有监督器 7 项、指标 3 项、配置 3 项、分析 2 项测试通过；结果文件仍可读取 | smoke 后检查实际节点、线程与资源分配 |
| 汇总与画图 | 既有真实小实例结果生成 61 份旧格式汇总表、5 组 PNG/PDF 图 | 正式批次自动分析，也可单独重算 |
| 提交、依赖、续跑 | 本次模拟 Slurm 检查通过，含作业号、afterany、重复提交拦截、含空格路径 | 实际调度仍需 MatriCS 验证 |
| CPLEX 许可证 | Ubuntu 本次 1001 变量探测仍报 1016，属于规模受限环境 | MatriCS 必须配置可用的完整许可证 |
| 正式实验 | 本次工作未提交正式批次 | 完成下面步骤后，由合作者明确执行 submit |

这里的 61 个小实例是 61 个方法配置各跑一个已知答案模型，**不是全部 1265 个 benchmark 已证明正确或已经跑完**。正式运行仍逐条验解；UNSAT 保留为后端判定，不声称独立证明。

## 2. 三种服务器不要混用

### 2.1 已验证的云端 Ubuntu

SSH 配置中的别名为 `2026-2027-gz`，登录用户为 `ubuntu`，主机名为 `VM-0-7-ubuntu`。本次核对为 2 个可用逻辑 CPU、约 3.6 GiB 内存，用于单路小实例验证。

| 内容 | 真实位置 |
|---|---|
| 活动项目根目录 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ` |
| 核心代码 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/codes` |
| 跑实验的代码 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/jobs` |
| 分析代码 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/analysis` |
| 与 GitHub 同步的整理仓库 | `/home/ubuntu/NLIP-Journal-Artifact-publish` |
| 当前 Python 环境 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/02-code/aij-experiments/.venv/bin/python` |
| 本机配置 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/jobs/config.ubuntu.json` |
| 固定清单 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/benchmarks/manifests` |
| 61 项验证结果 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/results/structure-smoke-20261002` |
| 对应汇总分析 | `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ/results/structure-analysis-20261002` |

Python 环境保留在原安装位置，避免破坏虚拟环境的内部路径；**当前代码入口在新的 codes/jobs/analysis 中**。带 `#` 的路径在命令里要加引号。

Ubuntu 的三组旧数据位于：

```text
/home/ubuntu/#科研项目/MIS/0-NLIP/NLIP_composes/experiment/benchmarks/
├── qplib_fully_passed/
├── diverse_sat/
└── smt_0_10/
```

MaxHS、WMaxCDCL、Open-WBO 的可执行文件位于：

```text
/home/ubuntu/#科研项目/MIS/0-NLIP/NLIP_composes/experiment/solvers/maxsat/maxhs
/home/ubuntu/#科研项目/MIS/0-NLIP/NLIP_composes/experiment/solvers/maxsat/wmaxcdcl
/home/ubuntu/#科研项目/MIS/0-NLIP/NLIP_composes/experiment/solvers/maxsat/openwbo
```

本次确认上述文件存在并可执行。MIPO 对外入口是 `benchmarks/mipo`，在活动 Ubuntu 上链接到仍保留的 `03-benchmarks/mipo`，其中已有 870 个转换后的 JSON。GitHub 不携带虚拟环境、外部求解器二进制、这些数据本体和运行结果。

### 2.2 本地服务器 10.50.2.30

本次只读登录成功：用户 `ylzl`，主机 `jh-2ndXeon`，双路 Xeon Gold 6226，共 24 个物理核、48 个逻辑 CPU，约 251 GiB 内存。此前讨论的“使用 18 个核心”是计划分配数量，不是机器总核心数。

在 `/home/ylzl` 下最多三层目录范围内没有找到本项目的 NLIP/DiverseSAT 目录；未发现 `sbatch` 命令。**没有在这台机器部署或安装本项目，不能把云端 `/home/ubuntu/...` 当成这台机器上的位置。**本手册正式流程针对 MatriCS，不在该服务器直接执行 submit。

### 2.3 MatriCS 集群

本次没有可用的 MatriCS 登录配置，因此该账户的实际 HOME、数据目录、模块名称、许可证、额度和排队状态仍需合作者确认。本文给出的旧共享目录是候选，不是已现场确认的路径。

官方 `normal` 分区资料为每节点 28 核、128 GB 物理内存、最大申请 125 GB；当前选择 `normal + 7 路 + 120G`，仍需服从实际账户调度规则。[官方分区说明](https://www.matrics.u-picardie.fr/en/documentation-2/partitions/)

## 3. 下载到哪里，如何确定绝对位置

登录 MatriCS 后，先选定**登录节点和计算节点都能访问、容量足够、不会在作业期间被清理**的项目目录。以下明确示例使用 `$HOME/NLIP-Journal-Artifact`；如果账户有指定的 ComputeSpace/项目存储，把第一行改成该目录的绝对路径。不要把结果放到登录节点私有 `/tmp`。

```bash
export NLIP_WORKDIR="$HOME/NLIP-Journal-Artifact"
mkdir -p "$(dirname "$NLIP_WORKDIR")"
git clone https://github.com/ZhenglingYangli/NLIP-Journal-Artifact-.git "$NLIP_WORKDIR"
cd "$NLIP_WORKDIR"
pwd -P
git log -1 --oneline
df -h .
```

`pwd -P` 输出的就是这台集群上真实下载位置。例如 HOME 由集群设置为什么，上面的 `$HOME` 就展开为什么；不要照抄 Ubuntu 的 `/home/ubuntu`。

已有 checkout 时不再 clone。在确认该 checkout 没有运行中的批次后：

```bash
cd "$NLIP_WORKDIR"
git status --short
git pull --ff-only
```

所有后续示例都从仓库根目录执行。重新登录后，重新设置 `NLIP_WORKDIR` 并 `cd` 到同一位置；自定义的模块、`AIJ_PYTHON`、`AIJ_CONFIG` 等设置也要重新加载。

## 4. 文件结构与职责

```text
NLIP-Journal-Artifact/
├── README.md
├── codes/                         核心算法和求解接口
│   ├── nlipsat/                   对外 API
│   ├── codes/                     原有编码器、解析器、求解及验解
│   ├── telemetry.py               阶段与模型指标采集
│   └── solvers/baseline/           Z3、SCIP、CPLEX、HiGHS、cvc5 等接口
├── jobs/                          实验运行与集群提交
│   ├── goSolver.py                调度实例、并行执行、保存结果
│   ├── generate_scripts.py        生成实验计划 campaign.json
│   ├── generate_slurm.py          生成 submit.sh
│   ├── run_cluster_pipeline.sh    本手册统一操作入口
│   ├── run_config_array.sh        Slurm 数组作业入口
│   ├── run_campaign_task.py       执行数组中一个配置
│   ├── run_cluster_smoke.sh       计算节点小实例与许可证测试
│   ├── worker.py / supervisor.py  单次调用与时间/内存监督
│   ├── config.json                已提交的通用配置模板
│   ├── config.cluster.json        configure 生成的本机配置，不提交 Git
│   ├── prepare_mipo.py            下载、核对及转换 MIPO
│   ├── convert_mipo.py            精确多项式转换
│   ├── configure_cluster.py       解析本机数据和外部程序位置
│   ├── requirements*.txt          固定依赖
│   └── smoke/                     已知答案的小模型
├── analysis/                      独立汇总和画图
│   ├── summarize.py               单配置汇总
│   ├── summarize_campaign.py      全批汇总
│   ├── analyze_campaign.py        成功数、PAR-2、比较表和累计图
│   ├── result_table.py            公共结果字段
│   ├── run_campaign_analysis.sh   分析作业入口
│   └── requirements-analysis.txt
├── benchmarks/
│   ├── manifests/                 四组固定清单
│   └── mipo/                      data 命令生成，不随 GitHub 分发
├── tests/                         开发验证用例
└── results/                       执行后生成，不随 GitHub 分发
```

`codes/codes` 是核心项目保留的内部模块目录；根目录 `codes` 是完整求解项目。跑实验仍使用熟悉的 `goSolver.py` 和脚本生成文件名。运行器调用分析程序，不在运行器中重写分析逻辑。

## 5. 正式方案：哪些数据跑哪些方法

| 数据组 | 实例 | NLIPSat 编码 | 后端 | 外部基线 | 配置数 | 运行数 |
|---|---:|---|---|---|---:|---:|
| QPLIB | 137 | OH、UNA、BIN | MaxHS、RC2、WMaxCDCL、Open-WBO | SCIP-NATIVE、Z3、CPLEX-NATIVE、SCIP-MILP、HiGHS-MILP | 17 | 2329 |
| Diverse SAT | 108 | OH、UNA、BIN | 同上四个后端 | 同上五条基线 | 17 | 1836 |
| MIPO | 870 | OH、UNA、BIN、BIN+D | 同上四个后端 | SCIP-NATIVE、Z3、CPLEX-MILP、SCIP-MILP、HiGHS-MILP | 21 | 18270 |
| 有界 SMT | 150 | OH、UNA、BIN、BIN+D | CaDiCaL | Z3、cvc5 | 6 | 900 |
| 总计 | 1265 | | | | 61 | 23335 |

- Diverse SAT 固定 `k=2`，继承历史执行配置；这里不声称旧论文正文已明确固定该参数。不运行 DW/IW 对比。
- QPLIB 接受当前固定整数数据；CPLEX-NATIVE 保留原生二次路线，不支持的二次约束记录 UNSUPPORTED，不悄悄改用 MILP。
- MIPO 使用原包 `integer/txtfiles` 的全部 870 个模型，包括 530 个多值整数模型和 340 个布尔模型；布尔变量属于接受范围。目标最小化，按 TXT 十进制系数精确转换，不能用同包 NL 的不同精度系数替换。
- BIN+D 使用阈值 3、顺序分解、精确乘法及共享；记录 requested/effective，不能把布尔快速路径未触发分解误报为启用了分解。
- SCIP-MILP、CPLEX-MILP、HiGHS-MILP 使用共同的精确线性建模结果，但各自调用自己的求解器；SCIP 不替代 CPLEX/HiGHS 求解。
- SMT 是判定组；此组不加入 SCIP，不把 cvc5 当成其他优化组的正式基线。
- 正式主实验关闭 LRN，保留独立可选模块；不加入 IMF、MINLPLib 或新的 LRN 性能实验。

额外分解对照使用 `prepare-decomposition`：MIPO/RC2 和 SMT/CaDiCaL 的不共享 BIN+D，2 个配置、1020 次新运行。共享对照复用主实验相应结果；不要把主矩阵重新提交一次。两部分都完成时，新运行总计 24355 次。

### 正式预算与调度

| 层级 | 配置 | 含义 |
|---|---|---|
| 单个实例 | 1 个物理核心 | 不是一个求解器使用 7 核 |
| 单个实例 | 16 GiB 进程树 RSS | 包含子进程，按监测采样执行限制 |
| 求解阶段 | 3600 秒墙钟 | 包含启动、解析、编码、求解 |
| 验解阶段 | 最多 120 秒 | 独立记录，不能延长求解预算 |
| 外围上限 | 4000 秒 | 整体兜底，不是 4000 秒求解时间 |
| 每配置作业 | normal、1 独占节点、7 CPU、120G | 7 个独立单核实例并行；7×16=112 GiB，留运行管理余量 |
| 数组并发 | 默认最多 3 个配置作业 | 最多 21 个实例同时运行，实际取决于调度 |
| 作业墙钟 | 141 小时，即 5-21:00:00 | 覆盖最长 870 实例配置；不代表全实验预计用时 |
| 分析作业 | normal、1 CPU、4G、30 分钟 | 与求解资源分开 |

独占节点可能按整节点计入账户核心配额。实际作业启动后用 `scontrol show job` 看 AllocTRES/CPU/内存，不以 7 worker 推断只占 7 核配额。不要在同一批正式结果里随意更换 CPU 型号、工作线程或预算。

## 6. 第一步：安装环境

**目的：**建立所有 Python 求解接口和分析程序共用的解释器。安装成功只说明依赖可安装，尚不能证明计算节点动态库、许可证和外部程序可运行。

先按站点方式加载模块，可用 `module avail` 查找；本项目不猜测 MatriCS 模块的具体名称。

```bash
cd "$NLIP_WORKDIR"
export PYTHON=python3.9
bash jobs/run_cluster_pipeline.sh setup
```

默认环境为 `$NLIP_WORKDIR/jobs/.venv/bin/python`。已有适用环境可先设置：

```bash
export AIJ_PYTHON=/已有环境的绝对路径/bin/python
bash jobs/run_cluster_pipeline.sh setup
```

setup 会按 requirements 安装固定版本。如果使用站点提供的完整 CPLEX Python API，应在安装后按站点说明加载或配置；pip 的 cplex 包本身不保证解除社区版规模限制。

本次 Ubuntu 实际核对的版本如下：

| 包 | 版本 | 包 | 版本 |
|---|---|---|---|
| Python | 3.9.25 | python-sat | 1.8.dev25 |
| pypblib | 0.0.4 | z3-solver | 4.15.4.0 |
| psutil | 7.2.2 | pyscipopt | 6.2.1 |
| numpy | 2.0.2 | cvc5 | 1.3.4 |
| highspy | 1.15.1 | cplex | 22.1.2.1 |
| matplotlib | 3.9.4 | | |

成功标准：setup 返回码为 0，随后 check 能导入相关接口。若完整 CPLEX 需要不同于当前锁定版本的 API，应先与项目负责人明确版本，再固定到正式批次；不要无记录地混用。

## 7. 第二步：准备数据和定位求解器

### 7.1 MIPO

**目的：**从同一作者来源恢复固定 870 个模型，保留精确系数与实例清单。

```bash
bash jobs/run_cluster_pipeline.sh data
# 集群不能联网但已有作者原包时：
# bash jobs/run_cluster_pipeline.sh data --archive /绝对路径/mipo.tar.gz
```

原包来源：<https://wwwold.mathematik.tu-dortmund.de/lsv/instances/mipo.tar.gz>。输出位于 `$NLIP_WORKDIR/benchmarks/mipo/`。现有数据不会被盲目覆盖；转换程序会比较内容。成功标准是固定清单中的 870 个模型均生成并匹配。

### 7.2 旧数据和外部 MaxSAT 程序

**目的：**生成这一台机器专用的绝对路径配置，防止 Ubuntu 路径被带到 MatriCS。

```bash
export NLIP_LEGACY_ROOT=/scratch/scherif/NLIP/NLIP
bash jobs/run_cluster_pipeline.sh configure
```

候选路径及必要时的覆盖变量：

| 内容 | 默认候选 | 覆盖方式 |
|---|---|---|
| 旧三组数据根目录 | `$NLIP_LEGACY_ROOT/benchmarks` | `NLIP_BENCHMARK_ROOT` |
| QPLIB | 数据根目录下 `qplib_fully_passed` | 修改数据根目录 |
| SMT | 数据根目录下 `smt_0_10` | 修改数据根目录 |
| Diverse SAT | 数据根目录下 `diverse_sat` | `NLIP_DIVERSE_ROOT` |
| MaxHS | `$NLIP_LEGACY_ROOT/solvers/maxsat/maxhs` | `NLIP_MAXHS` |
| WMaxCDCL | `$NLIP_LEGACY_ROOT/solvers/maxsat/wmaxcdcl` | `NLIP_WMAXCDCL` |
| Open-WBO | `$NLIP_LEGACY_ROOT/solvers/maxsat/openwbo` | `NLIP_OPENWBO` |

另有历史候选 `/users/scherif/ComputeSpace/solvers/maxhs`、`wmaxcdcl_24`、`openwbo`。这些需要真实文件检查；旧 DiverseSAT 配置不能证明共享 Open-WBO 已安装。配置程序打印最终实际选择，请核对，不只看退出码。

```bash
# 只有实际路径不同才设置，例如：
# export NLIP_MAXHS=/实际目录/maxhs
# export NLIP_WMAXCDCL=/实际目录/wmaxcdcl_24
# export NLIP_OPENWBO=/实际目录/openwbo
# export NLIP_DIVERSE_ROOT=/实际CNF目录
# bash jobs/run_cluster_pipeline.sh configure
cat jobs/config.cluster.json
```

成功标准：打印 23335 次运行，四组数量为 2329、1836、18270、900，实际输入与外部程序路径正确。`jobs/config.cluster.json` 仅属于本机，不提交 Git。已有配置可用 `export AIJ_CONFIG=/绝对路径/config.json`，跳过 configure。正式批次准备后不重新 configure。

## 8. 第三步：登录节点检查

```bash
bash jobs/run_cluster_pipeline.sh check
sinfo -p normal
scontrol show partition normal
```

**check 的目的与范围：**确认解释器可导入所有依赖；固定清单的 1265 个输入能定位；三个外部 MaxSAT 程序存在且有执行权限；sbatch、squeue、sacct 可用。它不执行全量求解，也不证明 ELF/动态库在计算节点可运行。

成功标准：check 返回 0，打印 `runs: 23335`、`instances: 1265` 和实际软件版本。通过分区查询确认本账户可以使用 normal，120G 与 141 小时申请符合实际规则。没有访问权限或额度不符时，应先解决账户配置，不擅自把脚本改成 bigmem/AMD 或降低单实例预算。

## 9. 第四步：计算节点小实例与许可证测试

```bash
bash jobs/run_cluster_pipeline.sh smoke
bash jobs/run_cluster_pipeline.sh smoke-status
```

smoke 只提交测试作业，返回作业号不是测试已通过。它申请 normal、1 CPU、2G、45 分钟；内部使用每实例 20 秒求解、5 秒验解、30 秒外围、1 GiB 的 smoke 配置。

| 测试 | 具体目的 | 通过标准 |
|---|---|---|
| 完整 CPLEX 许可证探测 | 区分“能 import、能跑小模型”与“能跑超出社区版限制的模型” | 1001 变量探测成功，无 1016 |
| 61 配置调用 | 覆盖实际编码/后端组合、外部二进制、Python API、路径与动态库 | 61 条均有结果，无异常退出 |
| QPLIB 小模型 | 检查数值目标与原问题验解 | 17 条 OPTIMAL，精确目标 1 |
| Diverse SAT 小模型 | 检查 k=2、各方法目标含义 | 17 条 OPTIMAL，精确目标 2 |
| MIPO 小模型 | 检查四次项、分解及 MILP 路线 | 21 条 OPTIMAL，精确目标 -1/2 |
| SMT 小模型 | 检查决策编码与原公式见证 | 6 条 SAT、verified=true |
| 结果读回 | 确认保存的状态/目标与已知答案相同 | 日志结尾 planned=61、failures=[] |

后端覆盖次数：MaxHS/RC2/WMaxCDCL/Open-WBO 各 10，CaDiCaL 4，Z3 4，SCIP-NATIVE 3，SCIP-MILP 3，HiGHS-MILP 3，CPLEX-NATIVE 2，CPLEX-MILP 1，cvc5 1。

```bash
SMOKE_ID=$(cat results/cluster-smoke-last-job.txt)
sacct -j "$SMOKE_ID" --format=JobID,State,ExitCode,Elapsed,MaxRSS
cat "results/cluster-smoke-$SMOKE_ID.log"
```

**正式开跑的通过条件：作业 COMPLETED、ExitCode 0:0，日志最后 planned=61 且 failures=[]。**其中 WAIT/PENDING/RUNNING 都不是通过；许可证失败可能在生成全部结果之前终止。详细结果在 `results/cluster-smoke-<作业号>/`。

本次 Ubuntu 已保存的 61 项结果重新读回全部通过；Ubuntu 完整许可证探测仍失败。因此合作者不能跳过 MatriCS 上的这一步。小实例均为已知可行模型，不能把这一步解释成全部 SMT 的 UNSAT 已获独立证明。

## 10. 第五步：生成正式计划，核对后提交

```bash
bash jobs/run_cluster_pipeline.sh prepare aij-main
cat results/aij-main/submit.sh
```

**目的：**把数据集、方法、输入顺序和预算固定为可检查的计划，尚不执行求解。

核对打印内容：`partition=normal`、`workers=7`、`concurrent_jobs=3`、`memory_gib=120`、`configuration_jobs=61`、`instance_runs=23335`。提交脚本应含 `--array=0-60%3 --cpus-per-task=7 --mem=120G --time=5-21:00:00`。

`campaign.json` 内含本机绝对路径和代码身份，必须在 MatriCS 生成，不能复制 Ubuntu 的计划直接提交。一次计划生成后不要修改代码、软件版本、配置或清单。

```bash
# 只有上面的环境测试通过并核对计划后，执行这一行才正式提交
bash jobs/run_cluster_pipeline.sh submit aij-main
bash jobs/run_cluster_pipeline.sh status aij-main
```

submit 保存实验数组与依赖分析作业号。数组全部结束（包括存在失败任务时）触发 afterany 分析；“分析运行成功”不等于“每个实验成功”。启动后可检查实际分配：

```bash
ARRAY_ID=$(cat results/aij-main/array_job_id.txt)
squeue -j "$ARRAY_ID"
# 从 squeue 中取一个实际数组任务号，例如 12345_0，再执行：
# scontrol show job 12345_0
```

实例 `result.json` 记录实际 host、CPU 等信息，配置 `run.json` 保存环境和预算。21 路是最多同时处理的实例数；独占资源和账户额度可能导致实际小于 21。

## 11. 监控、停止、续跑与额外对照

```bash
bash jobs/run_cluster_pipeline.sh status aij-main
ARRAY_ID=$(cat results/aij-main/array_job_id.txt)
sacct -j "$ARRAY_ID" --format=JobID,State,ExitCode,Elapsed,MaxRSS
# 确需停止该批次时：
# scancel "$ARRAY_ID"
```

status 显示当前用户队列并重算该批次状态计数。PENDING 是尚无最终结果，TIMEOUT/OOM 是已完成的失败结果，二者不同。Slurm MaxRSS 是调度记录，不能直接等同于程序统计的整个进程树峰值。

```bash
# 等原数组停止后再续跑
bash jobs/run_cluster_pipeline.sh resume aij-main
```

resume 拒绝重复提交仍在队列中的已记录数组。它会跳过已有最终结果，包括 TIMEOUT/OOM，续跑缺失条目；不是给超时实例额外时间。续跑要求代码、输入、预算、软件版本与硬件类别一致。运行中不能 git pull；若确需改代码，应停止并区分原批与新批，不能混入正式统计。

```bash
# 额外分解对照单独准备和提交
bash jobs/run_cluster_pipeline.sh prepare-decomposition aij-decomposition
bash jobs/run_cluster_pipeline.sh submit aij-decomposition
```

该对照新运行 1020 次。主实验和对照各自默认最多 3 个配置作业；若同时提交，两批的并发会相加。默认建议主批结束后再提交对照，避免把“每批最多 21 路”误认成账户总并发限制。

## 12. 汇总分析、输出指标和数据交付

数组结束后已自动安排分析，也可以单独提交：

```bash
bash jobs/run_cluster_pipeline.sh analyze aij-main
```

这只重新读取结果，不重新求解。分析作业申请 1 CPU、4G、30 分钟。大批次画图由计算节点执行；进度 status 只做结果表汇总。

```text
results/aij-main/
├── campaign.json
├── submit.sh
├── array_job_id.txt / analysis_job_id.txt
├── submissions.log
├── slurm-<数组号>_<索引>.log
├── analysis-<作业号>.log
├── runs/<数据组-方法>/
│   ├── run.json
│   ├── results.csv / summary.json
│   └── jobs/<实例任务号>/
│       ├── job.json
│       ├── result.json
│       └── …                       stdout/stderr、阶段信息及后端文件
├── results.csv / summary.json       全批总表与状态汇总
├── sumup/                          每配置旧格式 CSV
└── analysis/
    ├── config_summary.csv
    ├── status_counts.csv
    ├── pairwise.csv
    ├── instance_features.csv
    ├── encoding_metrics.csv
    ├── model_quality.csv
    ├── phase_metrics.csv
    ├── report.md
    └── figures/                    各组及 QPLIB+Diverse 合并累计图，PNG/PDF
```

`results.csv` 当前共有 87 个字段，主要包括：

| 类别 | 内容 |
|---|---|
| 身份与状态 | 实例、数据组、方法、编码、后端、输入位置、状态、verified、错误与退出码 |
| 解与界 | 精确目标，内部/原目标尺度的 primal/dual bound，绝对差、归一化 gap、后端 gap |
| 时间与资源 | 求解、验解、总墙钟、启动/解析/编码/求解阶段、预算、终止原因、进程树峰值 RSS、host/CPU |
| 编码 | 变量数、硬/软子句数、Cost、TopW、总软权重、分解是否请求/实际触发、共享命中和生成规模 |
| 原问题与模型 | 变量及布尔比例、整数域大小、项数、次数、约束数，MILP 模型规模和搜索节点 |

各方法不支持或终止前未返回的指标留空，不能当零；原始 `result.json` 还保留见证与详细信息。优化成功要求 OPTIMAL 且原问题验解通过、在求解预算内；FEASIBLE 单独保留。SMT 的 SAT 要求验解，UNSAT 按后端报告统计。未完成配置的 PAR-2 留空；完整配置中未成功条目按两倍求解预算计入。

**交付结果时保留整个批次目录，不能只交图片或总表。**应包含计划、环境、逐实例结果、日志和最终分析。若需打包，在批次与最终分析结束后，从仓库根目录执行：

```bash
tar -czf aij-main-results.tar.gz -C results aij-main
```

包写在 results 目录之外，不会把自己打进自己；请先确认存储空间。旧实验结果是否复用需按输入、求解路径、软件、预算与验解口径逐配置确认，不因服务器名称相同就直接混入新批次。

## 13. 常见失败及下一步

| 现象 | 原因判断与处理 |
|---|---|
| 找不到 python3.9 | 加载集群实际 Python 模块，或设置已有环境 AIJ_PYTHON |
| import 缺包/动态库失败 | 确认登录节点与计算节点使用同一解释器、模块和库路径；修复后重跑 smoke |
| configure 找不到输入 | 检查四组清单、实际目录和 NLIP_* 覆盖变量，不能随意删掉实例 |
| 外部二进制 Permission denied | 使用已有可执行安装；核对文件权限，不用另一个程序冒名顶替 |
| CPLEX 1016 | 社区版规模受限；配置完整 API/许可证后重新 smoke，不能靠小模型成功放行 |
| 作业一直 PENDING | 查看 squeue 的等待原因和账户额度；不改实验预算来绕过排队 |
| 整个 Slurm 作业 OUT_OF_MEMORY | 与单实例 OOM 区分；检查作业总申请和实际分配，不把缺失结果算成求解超时 |
| 实例 UNSUPPORTED | 保留结果，例如不支持的原生 CPLEX 二次约束；不自动替换方法 |
| 实例 INVALID | 原问题验解失败；保留证据并联系负责人，不能计为成功 |
| 配置或版本发生变化 | 当前冻结批次不能继续混跑；先核实改动影响，建立明确的新批次 |
| 数组提交了，分析提交失败 | 原数组可能仍在运行；先 status，后续单独 analyze，不重复提交主实验 |
| 分析里有 PENDING | 查看缺失任务日志；批次停止后 resume，全部完成后再重算分析 |

## 14. 最短操作顺序

```bash
# 已在本手册第 3 节选定目录并 clone；已加载站点所需模块
cd "$NLIP_WORKDIR"
bash jobs/run_cluster_pipeline.sh setup
bash jobs/run_cluster_pipeline.sh data
export NLIP_LEGACY_ROOT=/scratch/scherif/NLIP/NLIP  # 按实际位置修改
bash jobs/run_cluster_pipeline.sh configure
bash jobs/run_cluster_pipeline.sh check
bash jobs/run_cluster_pipeline.sh smoke
bash jobs/run_cluster_pipeline.sh smoke-status
# 等待测试真正通过后，再继续：
bash jobs/run_cluster_pipeline.sh prepare aij-main
bash jobs/run_cluster_pipeline.sh submit aij-main
bash jobs/run_cluster_pipeline.sh status aij-main
# 数组结束后自动分析；需要补交/重算时：
# bash jobs/run_cluster_pipeline.sh analyze aij-main
```

不要把这一段未经停顿地整段粘贴执行：smoke 是异步提交，必须等其通过再执行正式 submit。帮助随时可查看：`bash jobs/run_cluster_pipeline.sh help`。
