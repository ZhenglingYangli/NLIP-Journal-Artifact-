# 合作者集群操作说明

统一入口为 `jobs/run_cluster_pipeline.sh`。它调用现有实验与分析程序，默认 normal、每作业 7 路、120G，同时最多 3 个作业；每实例 3600 秒求解、4000 秒外围上限、16 GiB。正式主实验关闭 LRN。

## 首次获取代码并自动启动

```bash
export NLIP_WORKDIR=/scratch/scherif/NLIP/NLIP-AIJ
curl -fsSL https://raw.githubusercontent.com/ZhenglingYangli/NLIP-Journal-Artifact-/main/jobs/start_cluster.sh \
  -o /tmp/start-nlip-aij.sh
bash /tmp/start-nlip-aij.sh --push
```

先加载站点的 Python、CPLEX 等环境；已有项目环境可设置 AIJ_PYTHON。启动脚本首次自动克隆；已有 checkout 则先检查队列与冻结计划，再更新并进入总流程。--push 包括最终结果推送；去掉它则只导出。

## 自动总入口

如果希望脚本自动判断并接续全部步骤，在集群登录节点进入项目后运行：

```bash
cd /scratch/scherif/NLIP/NLIP-AIJ
# 有已有项目 Python 环境时，先设置 AIJ_PYTHON；需要的站点模块也先加载
bash jobs/run_cluster_all.sh
```

总入口默认先判断是否同步代码，再补齐准备、小实例测试、主实验、分解对照、最终分析与精简结果导出。运行这个命令就会在条件满足时提交正式实验，无需再逐步调用 prepare/submit。它保持 normal、7 路、120G、同时最多 3 个配置作业，以及原来的 3600s/4000s 预算；主实验与分解对照顺序运行，不把两个数组的并发叠加。

需要连结果推送一起自动完成时，加 --push：

```bash
mkdir -p results
nohup bash jobs/run_cluster_all.sh --push >> results/cluster-all.log 2>&1 < /dev/null &
tail -n 50 results/cluster-all.log
```

nohup 让总入口在 SSH 断开后继续运行；它每 30 秒查看队列，可能持续数天。总入口进程在登录节点只负责检查和提交，实际求解与画图在计算节点运行。需要站点模块、CPLEX 完整许可证、网络及 Git 认证就绪；自动化无法替代这些站点配置。

它会复用与当前代码和配置一致的 61 配置小实例测试，跳过已完成结果，并对缺失项进行有限续跑。超时、内存不足与已记录失败仍按原口径保留。若许可证/路径/版本不符、小实例失败、队列查询失败或续跑后仍缺结果，流程停止并说明原因；修复后重新运行同一入口，不无限重复提交。中断总入口不会取消已经提交的 Slurm 作业。

结果默认在 results/aij-main 与 results/aij-decomposition；精简交付在 deliveries 下，验解包留在 results 中另行传输和备份。--push 会自动推送 results-aij-main、results-aij-decomposition 分支；已完成交付可以重开入口补做因认证等原因未成功的推送。作业运行期间不要手工更新或切分支。总入口先等现有作业结束；已有冻结 campaign.json（含未提交计划）或结果分支时保留原版本；新实验在 main 上用 git pull --ff-only origin main 同步并重开新版入口。未提交修改或网络失败会停止。--no-pull 可显式保留当前代码、不联网。需要其他批次名时可设置 AIJ_MAIN_BATCH、AIJ_DECOMPOSITION_BATCH；已有离线 MIPO 原包可设置 AIJ_MIPO_ARCHIVE。

## 1. 获取代码和环境

以下命令在 MatriCS 登录节点执行。先按集群实际模块加载 Python 3.9 和需要的 CPLEX 环境，再进行安装。

```bash
export NLIP_WORKDIR=/scratch/scherif/NLIP/NLIP-AIJ
git clone https://github.com/ZhenglingYangli/NLIP-Journal-Artifact-.git "$NLIP_WORKDIR"
cd "$NLIP_WORKDIR"
export PYTHON=python3.9
bash jobs/run_cluster_pipeline.sh setup
```

已有环境可以先 `export AIJ_PYTHON=/绝对路径/bin/python`。默认环境在 `jobs/.venv/`，无需每次激活。`setup` 先检查选定环境，只按固定版本补装缺少的包；已经安装的包不会自动重装。版本不符或导入失败会报告并停止，请处理后再检查。只查看、不安装可用 `bash jobs/run_cluster_pipeline.sh env-check`。若使用集群提供的完整 CPLEX Python API，请先按站点方式加载/配置。安装 cplex 包本身不代表有完整许可证，小实例作业会用超过社区版限制的模型检查许可证。

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


MatriCS 部署目录固定为 `/scratch/scherif/NLIP/NLIP-AIJ/`；旧数据和求解器根目录为 `/scratch/scherif/NLIP/NLIP/`。主实验结果写入新项目 `results/aij-main/`，新 MIPO 写入 `benchmarks/mipo/`。脚本默认使用新安装位置，可通过 `AIJ_RUNNER_DIR` 和 `AIJ_PYTHON` 指定实际运行环境。

## 6. 导出并推送结果

全部实验与分析作业结束后，执行：

```bash
bash jobs/push_results.sh export aij-main
# 检查 deliveries/aij-main/README.md 和报告，填写异常说明和备份位置
bash jobs/push_results.sh push aij-main
```

export 只导出逐实例总表、配置、环境、汇总表、分析表和图，不提交。带原问题见证的 result.json 和 run.json 打包为 results/aij-main/verification-records.tar.gz，另行传输。push 检查本项目队列、只提交精简交付文件，推送 results-aij-main 分支；需有仓库写权限。超时、内存不足和失败均保留，尚有 PENDING 时不交付。分解对照把批次名改为 aij-decomposition。已有交付目录不会被 export 覆盖。
