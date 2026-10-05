# NLIP-AIJ experiment artifact

主实验包含 QPLIB 137、Diverse SAT 108（k=2）、MIPO 870、有界 SMT 150；61 个配置、23,335 次运行。正式实验关闭 LRN，求解预算 3600 秒，外围时限 4000 秒。

```text
NLIP-Journal-Artifact-/
├── codes/                 # NLIPSat、编码器和求解器接口
├── jobs/
│   ├── goSolver.py        # 跑实例与小测试
│   ├── generate_scripts.py # 生成批量实验
│   ├── generate_slurm.py  # 写出 Slurm 提交脚本
│   ├── test.slurm         # 用 sbatch 提交小测试
│   ├── config.json       # 路径和运行预算
│   ├── internal/        # 内部执行与资源控制
│   ├── data/            # 本地 MIPO 数据转换
│   ├── tools/           # 环境和路径检查
│   └── smoke/            # 自带小测试输入
├── analysis/              # 汇总、统计、画图与精简结果导出
├── benchmarks/            # 固定清单；MIPO 在目标机器准备
├── tests/                 # 求解语义与结果统计测试
└── results/               # 每个批次的原始结果和分析
```

从项目根目录运行：

```bash
# 在计算节点上跑一个小测试。
sbatch jobs/test.slurm

# 准备好路径和求解器后，测试全部 61 个配置。
sbatch --time=00:45:00 jobs/test.slurm all

# 生成正式任务，再提交。
python jobs/generate_scripts.py
bash results/main/submit.sh

# 汇总分析。
python analysis/analyze_campaign.py results/main
```

正式默认配置为 bigmem-amd、每作业 60 路、970G，同时只运行 1 个配置作业；每个配置作业申请 1 台节点，每个实例仍为单核心、16 GiB。生成的 submit.sh 自动登记实验结束后的分析作业。

- [集群手动操作](docs/COLLABORATOR_GUIDE.md)
- [实验矩阵、预算和求解语义](jobs/README.md)

当前 MatriCS checkout 为 `/scratch/scherif/NLIP/AIJ/NLIP-Journal-Artifact-/`，旧数据和求解器根目录为 `/scratch/scherif/NLIP/NLIP/`。路径可在站点配置中修改。

原始结果位于 `results/<批次>/runs/`，总表为 `results.csv`，旧格式汇总表为 `sumup/`，比较表与图为 `analysis/`。MIPO 使用作者原始整数 TXT 转换得到的 870 个实例。原始数据、运行日志、虚拟环境和许可证不上传 GitHub；精简结果由 `analysis/export_results.py` 导出到 deliveries。
