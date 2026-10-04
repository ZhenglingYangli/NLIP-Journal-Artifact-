# AIJ 实验执行

GitHub → 集群的具体部署、MIPO 下载转换和计算节点验收见 [CLUSTER_DEPLOYMENT.md](CLUSTER_DEPLOYMENT.md)。

Ubuntu 活动目录为 `/home/ubuntu/#科研项目/MIS/3-NLIP_AIJ`：求解器在 `codes`，运行器在 `jobs`。执行要求 Linux、Python 3.9。原 LRN 的 2,040 条性能记录保持只读。


## 文件分工

沿用旧实验的 codes / jobs / analysis 组织方式和入口名称。
`jobs/goSolver.py` 只负责实例调度、调用求解程序与结果落盘。
`jobs/generate_scripts.py` 生成配置计划，再调用 `jobs/generate_slurm.py` 写出 Slurm 提交脚本。
求解算法、编码和数学规划建模位于 `codes/`；汇总与画图位于 `analysis/`。
`goSolver.py` 结束后调用独立的 `analysis/summarize.py`，提交脚本为全批分析设置作业依赖。
自动调用不改变分工，分析程序也可单独运行，无需重新求解。

## 当前矩阵

| 数据 | 数量 | NLIPSat 编码与后端 | 外部基线 | 每实例配置 | 主实验运行数 |
|---|---:|---|---|---:|---:|
| QPLIB | 137 | OH/UNA/BIN × MaxHS/RC2/WMaxCDCL/Open-WBO | SCIP-NATIVE、Z3、CPLEX-NATIVE、SCIP-MILP、HiGHS-MILP | 17 | 2,329 |
| Diverse SAT，k=2 | 108 | 同上 | 同上 | 17 | 1,836 |
| MIPO | 870 | OH/UNA/BIN/BIN+D × 四个 MaxSAT 后端 | SCIP-NATIVE、Z3、CPLEX-MILP、SCIP-MILP、HiGHS-MILP | 21 | 18,270 |
| 有界 SMT | 150 | OH/UNA/BIN/BIN+D × CaDiCaL | Z3、cvc5 | 6 | 900 |
| 合计 | 1,265 | | | | 23,335 |

主矩阵不含 DW/IW、cvc5 优化或 SMT 的 SCIP 路线。BIN+D 使用阈值 3、顺序分解、精确乘法、共享。布尔快速路径可能使 D 不实际触发，记录保留 requested/effective。

`--matrix decomposition` 仅增加 MIPO 的 RC2 和 SMT 的 CaDiCaL 不共享 BIN+D，共 1,020 次，其余对照复用主实验。此命令单独提交，不自动启动。没有新增 LRN 性能消融。

## LRN 与验解

正式主实验及分解对照显式设置 `use_lrn=False`，NLIPSat API 默认也关闭 LRN。LRN 保留为独立可选预处理，专项调用使用 `EncodingConfig(use_lrn=True)` 开启。仅在输入提供 `objective.factor_blocks` 时，对同方向、正整数权重的整数仿射残差平方执行原有 compress 规则。随后用有界整数残差变量及精确等式接入现有 OH/UNA/BIN 编码。普通展开多项式不进行猜测性平方分解。

`encoding_stats.lrn` 记录适用性、实际压缩组数和前后残差数。验解直接计算原输入的残差平方及原多项式；辅助变量不充当原问题见证。接入 LRN 不意味着四组普通多项式数据都有 LRN 加速收益。

SAT/优化成功状态必须有原模型可行性与目标值验解。UNSAT 是后端的不可满足结论，未声称取得独立证明。数值优化器的最优状态仍遵循其数值容差，原问题见证使用有理数重算。

## 预算与并行

| 参数 | 正式 | 小实例 |
|---|---:|---:|
| 启动、解析、编码、求解合计墙钟上限 | 3,600 秒 | 20 秒 |
| 原问题验解上限 | 120 秒 | 5 秒 |
| 外围整体兜底上限 | 4,000 秒 | 30 秒 |
| 进程树 RSS 内存上限 | 16 GiB | 1 GiB |
| 每任务 CPU | 1 个物理核 | 1 个物理核 |

监督器在求解阶段达到 3,600 秒时终止整个进程组，外围 4,000 秒不是延长求解预算。验解超时、求解超时、外围超时、内存超限分别记录。终止清理和监测有少量调度开销，超时后返回的结果不能算成预算内成功。

`--workers N` 表示一个配置作业内 N 个同时执行的单核任务，绑定不同物理核。默认按“数据组＋方法”拆为 61 个 Slurm 数组元素，每个元素申请 normal 独占节点、7 核、120G；最多 3 个元素同时运行，总计最多 21 个实例并行。`--concurrent-jobs 4` 可改为最多 28 路，实际获配以账户和调度器为准。Ubuntu 约 3.6 GiB 内存只用于单任务小实例验收。

每个配置作业的实例集合互不重复。例如 QPLIB/OH/RC2 的一个作业处理该配置下 137 个实例，MIPO/BIN+D/MaxHS 的另一个作业处理该配置下 870 个实例。数组元素编号固定，代码版本、方法参数和实例清单在准备时记录；运行时检查是否改变。每个配置使用独立输出目录与运行锁，重复启动不会同时写同一目录。

作业时长按最长配置的实例数、worker 数和 4000 秒外围预算计算并留 2 小时余量。默认申请 141 小时，最长的 870 个实例按 7 路计算仍在此范围内；不是对整个主实验只给 141 小时。

## 求解器与数据

`../codes/solvers/baseline/optimization_baselines.py` 提供 CPLEX 原生 MIQP，以及 CPLEX/HiGHS 的 MILP 路线。后两者读取 SCIP-MILP 建模器的**未预求解线性模型**，只共享数学转换，SCIP 不代替它们求解。CPLEX 原生路线保留二次目标、设置全局非凸 MIQP 求解，不偷偷改走 MILP；有二次约束时采用 MIQCP 接口，并由 CPLEX 检查凸性；一般二次等式或不支持的非凸约束记录为 UNSUPPORTED。

Ubuntu 测试版本：CPLEX 22.1.2.1、HiGHS/highspy 1.15.1，其余固定版本见 requirements。**Ubuntu 的 CPLEX 当前为 Community Edition，1001 个变量的测试报 1016。正式 CPLEX 批次需集群完整学术版 Python API/许可证；只安装 pip 包不能保证解除规模限制。**正式入口会先检测许可证，避免大批量产生无效记录。

逐个解析优化输入已确认：QPLIB 137 个中有 16 个带非线性约束；目标次数统计为 126 个二次、11 个线性；Diverse SAT 108 个均为二次目标、线性约束；MIPO 870 个均有四次项。当前四组入口都不提供 factor_blocks，LRN 在本主矩阵中不触发。SMT 150 个核对了清单与入口，求解语义由专项测试和逐次原问题验解检查。

MIPO 使用发布包的 `integer/txtfiles`，870 个文件转换到 `benchmarks/mipo`，精确保留 TXT 系数，目标为最小化。TXT 与同包 NL 的小数精度并非总相同，不能把 NL 文件的浮点系数静默当作 TXT 的精确 oracle。转换器为 `convert_mipo.py`。

集群 `config.json` 沿用历史路径 `/scratch/scherif/NLIP/NLIP/benchmarks` 与 `/scratch/scherif/NLIP/NLIP/solvers/maxsat`。MIPO 指向同包 `benchmarks/mipo`。三个外部二进制名称为 `maxhs`、`wmaxcdcl`、`openwbo`。上述路径、分区和许可证须在真实集群确认；Ubuntu 通过不等于已经在集群计算节点验证。

## 部署和运行

保留 `codes/`、`jobs/`、`analysis/`、`benchmarks/` 相对布局。集群已有研究目录时，将改动应用到活动 checkout；单独解压交付包时，在解压根目录初始化 Git 并提交代码和清单，正式入口据此记录版本。不要提交 `.venv` 或输出目录。

```bash
cd jobs
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r ../analysis/requirements-analysis.txt
# 如集群安装了完整 CPLEX，用对应完整 Python API 替代 Community Edition。
export AIJ_PYTHON="$PWD/.venv/bin/python"

# 展开完整矩阵、确认实际数据路径，不启动实验。
"$AIJ_PYTHON" goSolver.py --profile formal
# Ubuntu 加 --config config.ubuntu.json；集群使用默认 config.json。
"$AIJ_PYTHON" goSolver.py --profile smoke --execute --output ../results/cluster-smoke

# 准备 61 个配置作业，默认每个 7 路、同时最多 3 个作业。仅生成，不提交。
"$AIJ_PYTHON" generate_scripts.py --output ../results/aij-main-config
# 集群路径、依赖和 CPLEX 完整许可证验收后，执行这一行才实际提交。
bash ../results/aij-main-config/submit.sh
# submit.sh 同时登记依赖分析作业；手动更新总表、配置表及累计图使用：
"$AIJ_PYTHON" ../analysis/analyze_campaign.py ../results/aij-main-config
# 可选提速：准备阶段指定 --partition bigmem --workers 28 --concurrent-jobs 4，最多 112 路，自动申请每作业 460G。
# 原定分解对照：另用 --matrix decomposition --output ../results/aij-decomposition-config。
# 续跑：确认同一数组已停止后，重交同一 submit.sh；已完成记录自动跳过。
```

监督器处理 Slurm 结束信号并清理子进程。续跑允许改派同 CPU 型号、同系统平台的节点，仍要求代码、依赖版本、配置、worker 数及输入一致；每条结果记录实际主机和 CPU。`run.json` 记录配置环境，`result.json` 保留原问题见证与精确目标，`summarize_campaign.py` 将各配置合并为一份表并保留未完成项。旧实验数据是否复用仍逐配置判断。

`run_slurm.sh` 保留为单作业兼容入口，已改为 7 核、120G；多配置并行使用上面的 campaign 流程，不重复提交完整矩阵。

全批结果位于 campaign 目录的 `results.csv`，每配置表位于 `sumup/`，比较表和累计求解图位于 `analysis/`。
列和统计口径见 `CLUSTER_DEPLOYMENT.md` 的“结果落盘与分析”。所有计划行均保留；未完成配置不报告完整批次 PAR-2。


MatriCS 部署目录固定为 `/scratch/scherif/NLIP/NLIP-AIJ/`；旧数据和求解器根目录为 `/scratch/scherif/NLIP/NLIP/`。主实验结果写入新项目 `results/aij-main/`，新 MIPO 写入 `benchmarks/mipo/`。脚本默认使用新安装位置，可通过 `AIJ_RUNNER_DIR` 和 `AIJ_PYTHON` 指定实际运行环境。
