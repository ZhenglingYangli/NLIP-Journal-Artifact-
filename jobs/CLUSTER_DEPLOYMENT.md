# NLIP-AIJ：Ubuntu → GitHub → MatriCS

GitHub 目标：<https://github.com/ZhenglingYangli/NLIP-Journal-Artifact->。
上传内容在 Ubuntu 整理、验证；由用户确认后推送。正式实验在集群小实例验收通过后提交。

## 目录与数据

```text
NLIP-Journal-Artifact-/
├── codes/                      # NLIPSat 核心、编码器、求解器接口
│   └── solvers/baseline/        # Z3、SCIP、CPLEX、HiGHS、cvc5 接口
├── jobs/                       # 实验调度与集群提交
│   ├── goSolver.py             # 并行执行实例、调用求解代码、记录结果
│   ├── generate_scripts.py     # 按数据集与方法生成实验计划
│   └── generate_slurm.py       # 生成 Slurm 提交脚本
├── analysis/                   # 读取结果、汇总指标、比较与画图
├── benchmarks/                 # 固定清单；MIPO 在目标机器准备
├── tests/                      # 小实例与接口测试
└── results/                    # 原始结果；每批内含 sumup 和 analysis/figures
```

Ubuntu 活动目录：`/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ`。
当前求解代码位于其 `codes`，运行代码位于 `jobs`。
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
| MIPO 870 | 本仓库 `benchmarks/mipo`，由 `prepare_mipo.py` 产生 |
| MaxHS | 旧根目录 `solvers/maxsat/maxhs`；或 `/users/scherif/ComputeSpace/solvers/maxhs` |
| WMaxCDCL | 旧根目录 `solvers/maxsat/wmaxcdcl`；或 `/users/scherif/ComputeSpace/solvers/wmaxcdcl_24` |
| Open-WBO | 旧根目录 `solvers/maxsat/openwbo`；或共享目录下同名程序 |
| RC2、CaDiCaL | Python-SAT 包中的接口 |
| Z3、cvc5、SCIP、HiGHS、CPLEX | 对应 Python 包；CPLEX 需可用于大模型的完整许可证 |

共享目录中的 Open-WBO 路径只是候选；Diverse SAT 脚本不能证明它已安装。
`configure_cluster.py` 会检查所有 1,265 个输入路径和三个外部可执行文件，打印最终选择。
不要将 Diverse SAT 的 289 个实例或 7200 秒预算直接用于本实验。当前作业内存选择 120G，配合 7 路并行。

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
cd NLIP-Journal-Artifact-/jobs
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r ../analysis/requirements-analysis.txt
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
"$AIJ_PYTHON" generate_scripts.py --config config.cluster.json \
  --output ../results/aij-main-config
# 提交 61 个配置作业，并登记一个 afterany 依赖的汇总分析作业。
bash ../results/aij-main-config/submit.sh
# 可随时手动重算进度表和图；未完成项保留 PENDING。
"$AIJ_PYTHON" ../analysis/analyze_campaign.py ../results/aij-main-config

# 原定额外分解对照独立生成，共 2 个配置、1020 次运行。
"$AIJ_PYTHON" generate_scripts.py --config config.cluster.json \
  --matrix decomposition --output ../results/aij-decomposition-config
# 需要运行该对照时再执行对应 submit.sh。
```

`campaign.json` 包含目标机器绝对路径；必须在集群重新生成，不能复制 Ubuntu 生成的计划直接提交。
`config.cluster.json` 是本机解析结果，Git 忽略它；修改求解代码则应提交并重新生成计划。
运行中的正式批次不要 `git pull`；待批次结束或停止后再更新。

## 结果落盘与分析

以 `results/aij-main-config` 为本批根目录，所有实例和分析文件都写入此处：

```text
aij-main-config/
├── campaign.json                  # 本批配置、预算、代码版本及固定清单
├── submit.sh                      # 配置数组及依赖分析作业的提交入口
├── slurm-<array>_<index>.log       # 每配置作业日志
├── analysis-<jobid>.log            # 汇总分析作业日志
├── runs/<数据组-方法>/
│   ├── run.json                   # 该配置环境与输入
│   ├── jobs/<实例-方法>/
│   │   ├── job.json
│   │   ├── stdout.log
│   │   ├── progress.json          # 已完成阶段的检查点，硬终止后仍保留
│   │   └── result.json            # 状态、见证、精确目标、耗时和内存
│   ├── results.csv
│   └── summary.json
├── results.csv                    # 按计划展开的全批长表
├── summary.json
├── sumup/NLIP_<数据组>_<方法>.csv  # 每配置表，保留旧表常用列
└── analysis/
    ├── config_summary.csv
    ├── status_counts.csv
    ├── pairwise.csv
    ├── instance_features.csv      # 原问题规模、整数域、次数与约束特征
    ├── encoding_metrics.csv       # 读取/编码/求解、Cost/TopW、分解与简化统计
    ├── model_quality.csv          # 模型规模、内外目标尺度、上下界、gap、搜索节点
    ├── phase_metrics.csv          # 阶段耗时及终止发生阶段
    ├── report.md
    └── figures/accumulated-*.png、*.pdf
```

提交脚本在配置数组结束后自动运行分析作业（`afterany`），即使部分配置失败也汇总现有结果。
汇总独立于求解 worker，不占用单实例的 3600 秒预算。绘图用无图形界面的 Agg 后端。
续跑仍以同一 `submit.sh` 提交，必须等上一数组和分析作业停止；已保存结果跳过，未完成实例重启。
分析读取 JSON 结果而非搜索日志中的 `>>>` 行，不挑选“最新目录”来混合不同批次。

沿用旧实验的每配置 CSV、成功数/时间比较以及累计求解图形式；图中横轴为累计求解数，纵轴为秒。
各数据组独立作图，另外生成 QPLIB＋Diverse SAT 合并图。SCIP 和新增基线均保留。
旧脚本中的硬编码配置名、排除 SCIP 及把 Z3 当作真值的规则不用于当前实验。
每配置 CSV 的 `TimeTotal`、`TimeForAnalysis` 均映射为当前协议的 `solve_wall_seconds`，包含启动、解析、编码与求解；验解时间另存。
当前运行记录读取耗时、MaxSAT Cost 和 TopW；数学规划与 SMT 不适用的字段留空。
历史结果缺失的字段不会事后编造，仍保留为空。

优化成功为 `OPTIMAL` 且原问题见证验解通过；SMT 的 SAT 要求验解通过，UNSAT 作为求解器报告的判定结果统计，不声称已有独立不可满足证明。
所有成功记录还必须在求解时间预算内。FEASIBLE、UNSUPPORTED、TIMEOUT、OOM、ERROR、INVALID 等状态分列保留。
PENDING 保留在计划分母中；未完成配置的 PAR-2 留空，全部完成后按本批求解预算两倍惩罚未成功记录（正式批次为 7200 秒）。
`pairwise.csv` 按同数据组、同实例对齐，给出双方已运行数、共同成功数、各自独有成功数及共同成功上的时间比较。
正式结论仍需对正式结果执行原问题与可用公开 oracle 的最终核对；环境小实例不会混入正式分析。

### 指标定义和缺失值

`progress.json` 由外围监督器在收到阶段事件时写入，并采用临时文件替换。
解析完成后保存原问题特征，编码/建模完成后立即保存规模与构建时间，再进入求解。
TIMEOUT、OOM、VERIFY_TIMEOUT 等结果合并这些已取得指标，同时记录 `termination_phase`。
某阶段尚未完成时不声称已经取得该阶段的规模或总耗时；最后阶段的 `phase_*_seconds` 是截至终止的时间。
阶段记录及特征统计开销包含在原有预算内，没有额外延长求解时间。

`read_seconds` 是读取/解析实际耗时，Z3 SMT 多次尝试时累计读取时间。
`encode_seconds`、`backend_seconds` 保留接口自身计时；`phase_*_seconds` 是监督器按阶段事件计算的墙钟时间，
还包括该阶段的记录和调度开销。两组指标不保证逐项完全一致，不把它们重复相加。
WCNF 记录原始 MaxSAT 代价 `maxsat_cost`、硬约束标记 `top_weight` 和软权重总和；原问题目标另存 `objective_exact`。

原问题特征包括变量数、布尔变量数/比例、有限整数域大小、目标项数/次数、约束及非线性约束数。
多项式接口标记 `parsed_polynomial`；直接 SMT 接口标记原生 AST 或声明表示，只记录该表示可直接取得的特征。
直接 SMT 的多项式次数/整数域等未进行额外推导，留空；不同表示的特征不可混作同一尺度。

SCIP、CPLEX、HiGHS 记录内部上下界以及还原到原问题目标尺度的上下界。
若内部目标为 `(原目标×scale−constant)/divisor`，还原为 `(内部目标×divisor+constant)/scale`。
统一绝对 gap 为 `abs(primal−dual)`，统一归一化 gap 为 `abs(primal−dual)/max(1,abs(primal),abs(dual))`；
求解器自身的 relative gap 另列。上下界属于数值后端报告，不等同于独立精确证书；可行解仍需原问题验解。
记录搜索节点数和模型变量/约束数；原生 CPLEX 二次约束计入模型约束数。
后端尚未返回就被硬终止时，未取得的上下界和节点数留空，不用已知答案填补，也不默认 gap 为零。
SAT/MaxSAT 路线未统一提供数学规划意义的搜索节点/界时同样留空。

## 正式资源与当前验收边界

主实验共 23,335 次运行：QPLIB 2,329、Diverse SAT 1,836、MIPO 18,270、SMT 900。
61 个 Slurm 数组元素按“数据集＋方法”分开输出。每作业内 7 个单核 worker，默认同时最多 3 个作业，
即最多 21 个实例并行；4 个作业时最多 28 个实例并行。

每作业申请 normal、1 个独占节点、7 个 CPU、120G 内存、141 小时墙钟上限。
141 小时覆盖最长 870 实例配置按 7 路、每实例 4000 秒计算并加余量；不是主实验总完成时间。
独占节点可能按整节点核心数占用账户配额，7 worker 不等于只占用 7 核的调度配额。
normal 官方页面列出单节点 28 核、用户上限 448 核。当前保留最多 4 个并发作业的软件设置，默认 3 个；这不是 normal 的账户上限，实际获配仍服从账户与调度器。
来源：<https://www.matrics.u-picardie.fr/en/documentation-2/partitions/>。

每实例求解阶段 3600 秒（包括启动、解析与编码），验解 120 秒，外围 4000 秒；进程树 RSS 16 GiB。
LRN 默认及正式方法配置均关闭，仍可通过 API 独立开启。

Ubuntu 已核对数据、代码和计划生成；还没有在 MatriCS 计算节点完成验收。
剩余集群端确认项集中为：实际路径、二进制及动态库可运行、Python 依赖安装、完整 CPLEX 许可证、Slurm 账户实际资源。
这些由上面的路径检查和一次计算节点 61 项小实例作业确认。未经这一步不能称为已具备正式开跑条件。

合作者可使用 [统一操作入口说明](COLLABORATOR_GUIDE.md) 完成环境检查、提交和分析。
