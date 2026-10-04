# 合作者集群操作说明

统一入口为 `jobs/run_cluster_pipeline.sh`。它调用现有实验与分析程序，默认 normal、每作业 7 路、120G，同时最多 3 个作业；每实例 3600 秒求解、4000 秒外围上限、16 GiB。正式主实验关闭 LRN。

## 1. 获取代码和环境

以下命令在 MatriCS 登录节点执行。先按集群实际模块加载 Python 3.9 和需要的 CPLEX 环境，再进行安装。

```bash
git clone https://github.com/ZhenglingYangli/NLIP-Journal-Artifact-.git
cd NLIP-Journal-Artifact-
export PYTHON=python3.9
bash jobs/run_cluster_pipeline.sh setup
```

已有环境可以先 `export AIJ_PYTHON=/绝对路径/bin/python`。默认环境在 `jobs/.venv/`，无需每次激活。`setup` 安装固定依赖；若使用集群提供的完整 CPLEX Python API，请在安装后按站点方式加载/配置。安装 cplex 包本身不代表有完整许可证，小实例作业会用超过社区版限制的模型检查许可证。

## 2. 准备数据和站点路径

```bash
bash jobs/run_cluster_pipeline.sh data
# 无法联网但已有作者原包时，改用：
# bash jobs/run_cluster_pipeline.sh data --archive /路径/mipo.tar.gz

export NLIP_LEGACY_ROOT=/scratch/scherif/NLIP/NLIP
bash jobs/run_cluster_pipeline.sh configure
bash jobs/run_cluster_pipeline.sh check
```

旧安装根目录是候选路径，按实际情况修改。需要分别指定时，可在 configure 前设置 `NLIP_BENCHMARK_ROOT`、`NLIP_DIVERSE_ROOT`、`NLIP_MAXHS`、`NLIP_WMAXCDCL`、`NLIP_OPENWBO`。完整路径说明见 [CLUSTER_DEPLOYMENT.md](CLUSTER_DEPLOYMENT.md)。configure 生成本机 `jobs/config.cluster.json`；已有配置可设置 `AIJ_CONFIG` 的绝对路径，并跳过 configure。

check 检查 Python 依赖、1265 个输入、23335 次运行计划、三个外部可执行程序及 Slurm 命令，不在登录节点执行正式求解。

## 3. 在计算节点测试环境

```bash
bash jobs/run_cluster_pipeline.sh smoke
bash jobs/run_cluster_pipeline.sh smoke-status
```

smoke 提交 normal 分区的 1 核、2G、45 分钟小作业，检查完整 CPLEX 许可证并执行 61 个小实例配置。作业号写入 `results/cluster-smoke-last-job.txt`，日志为 `results/cluster-smoke-<作业号>.log`，详细结果为 `results/cluster-smoke-<作业号>/`。

**通过标准：Slurm 状态 COMPLETED，退出码 0:0，日志最后 planned 为 61，failures 为空。**排队中或运行中还不能判断通过；若日志显示路径、动态库、依赖或许可证问题，先修复对应环境，再重新 smoke。

## 4. 准备并提交正式实验

```bash
# 仅生成计划和提交脚本
bash jobs/run_cluster_pipeline.sh prepare aij-main
# 小实例通过、核对配置后提交
bash jobs/run_cluster_pipeline.sh submit aij-main
# 查看队列和完成数量
bash jobs/run_cluster_pipeline.sh status aij-main
```

主实验 61 个配置、23335 次运行，每个配置作业的墙钟上限为 141 小时。提交时同时登记依赖分析作业，实验数组结束后自动汇总。结果在 `results/aij-main/`；作业号保存为 `array_job_id.txt` 和 `analysis_job_id.txt`，提交输出追加到 `submissions.log`。

运行中不要更新代码、重新 configure 或改变原计划。批次结束后需要更新代码时再 git pull，并为新代码另建批次。不同配置的结果分别保留在 `runs/`，总表为 `results.csv`，旧格式表为 `sumup/`，比较表和图为 `analysis/`、`analysis/figures/`。

## 5. 续跑、重算分析和分解对照

```bash
# 原批次已停止时续跑；保留已有结果，包含既有 TIMEOUT/OOM
bash jobs/run_cluster_pipeline.sh resume aij-main
# 单独提交汇总/画图作业，不重新求解
bash jobs/run_cluster_pipeline.sh analyze aij-main
# 额外分解对照：2 个配置、1020 次运行，单独准备和提交
bash jobs/run_cluster_pipeline.sh prepare-decomposition aij-decomposition
bash jobs/run_cluster_pipeline.sh submit aij-decomposition
```

resume 会检查记录的数组作业是否仍在队列中，运行中不重复提交。若数组提交成功但后续分析作业提交失败，原实验可能已运行；先 status 查看，后续用 analyze 补交分析即可。

可用 `scancel <作业号>` 手动停止指定作业；提交依赖分析后再续跑时，结束后可用 analyze 更新全批表格。不同批次名彼此隔离，批次参数也可以传绝对路径。
