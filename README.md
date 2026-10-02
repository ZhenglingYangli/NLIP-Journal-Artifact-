# NLIP-AIJ experiment artifact

主实验：QPLIB 137、Diverse SAT 108（k=2）、MIPO 870、有界 SMT 150；61 个配置、23,335 次运行。
正式实验关闭 LRN。默认 normal、每作业 7 路、120G，同时最多 3 个配置作业。

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

- 核心代码：`codes/`。外部基线建模和求解接口：`codes/solvers/baseline/`。
- 跑实验：`jobs/goSolver.py`。
- 生成计划与集群脚本：`jobs/generate_scripts.py`、`jobs/generate_slurm.py`。
- 汇总分析：`analysis/summarize.py`、`analysis/summarize_campaign.py`、`analysis/analyze_campaign.py`。
- [实验矩阵与运行说明](jobs/README.md)
- [集群部署与数据准备](jobs/CLUSTER_DEPLOYMENT.md)

在 jobs 目录运行：

```bash
python generate_scripts.py --config config.cluster.json --output ../results/aij-main
# 检查计划后才提交：
bash ../results/aij-main/submit.sh
# 单独重算汇总和分析：
python ../analysis/analyze_campaign.py ../results/aij-main
```

每批原始结果保存在 `results/<批次>/runs/`；总表为 `results.csv`，旧格式汇总表为 `sumup/`，
比较表为 `analysis/`，图为 `analysis/figures/`，均在同一批次目录内。不同批次不会混合。
MIPO 由 `jobs/prepare_mipo.py` 从作者原包下载转换。数据、结果、环境及许可证不上传 GitHub。

合作者集群操作：[操作说明](jobs/COLLABORATOR_GUIDE.md)，统一入口 `bash jobs/run_cluster_pipeline.sh help`。
