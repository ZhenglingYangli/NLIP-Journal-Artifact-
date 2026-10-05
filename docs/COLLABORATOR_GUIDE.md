# NLIP-AIJ 集群手动操作

从项目根目录执行。以下命令使用当前选定的 Python，不自动创建环境、补装软件、拉取代码或推送结果。更新代码前，确保该项目没有正在运行或等待的批次，保留本地修改；然后在项目根目录执行 `git pull --ff-only origin main`。已有 `.venv`、MIPO 和 config.cluster.json 保留。

```bash
export NLIP_WORKDIR=/scratch/scherif/NLIP/AIJ/NLIP-Journal-Artifact-
cd "$NLIP_WORKDIR"
module load python/3.9.20
module load optimizer/cplex/22.1.1.0
source "$NLIP_WORKDIR/.venv/bin/activate"
export AIJ_GIT="$(command -v git)"
python --version
```

沿用项目根目录已有的 `.venv`；不重新创建。补装依赖使用 `python -m pip install`，不加 `--user`。测试脚本显式使用项目 `.venv/bin/python`。

站点 CPLEX 22.1.1.0 模块是待核实的安装入口；代码固定版本为 22.1.2.1。先核实接口版本和完整许可证，版本不一致时处理后再进行正式实验。不要用 pip 的社区版覆盖站点完整接口。

1. 检查依赖：`python jobs/tools/check_environment.py`。只为报缺少的包运行安装命令；版本冲突单独处理。分析依赖位于 `analysis/requirements-analysis.txt`，Ubuntu 的 Python 3.9 导出参考位于 `jobs/environment/`。
2. 跑一个小测试：

```bash
sbatch jobs/test.slurm
```

预期 `OPTIMAL`、目标值 `1`、`verified=true`，并输出 `Tests passed: 1`。结果目录由程序显示。

3. 使用已经手动下载的 MIPO，不重新下载。根据实际格式选择一次操作：

```bash
# 已转换好的 JSON：指定所在目录，不重新转换。
export NLIP_MIPO_ROOT=/实际路径/JSON目录

# 作者原始压缩包：转换 integer/txtfiles 到本项目 benchmarks/mipo。
python jobs/data/prepare_mipo.py --archive /实际路径/mipo.tar.gz

# 已解压的 integer/txtfiles：直接转换，并保持固定清单不变。
python jobs/data/convert_mipo.py benchmarks/mipo/integer/txtfiles benchmarks/mipo benchmarks/manifests/mipo_list.txt
```

三种情况选符合实际的一种，替换占位路径。然后：

```bash
python jobs/tools/configure_cluster.py
```

数据检查应显示 23,335 次主实验运行。若旧数据和求解器位置不同，设置 `NLIP_BENCHMARK_ROOT`、`NLIP_MAXHS`、`NLIP_WMAXCDCL`、`NLIP_OPENWBO`，然后重新配置。配置只写入本地 `jobs/config.cluster.json`。MIPO 报 found 0 时检查这里的 input_root 和实际文件格式。

4. 全部配置的小测试：

```bash
sbatch --time=00:45:00 jobs/test.slurm all
```

入口先检查完整 CPLEX 许可证，再运行 61 个配置，最后自动核对预期答案和原问题验解。成功输出 `Tests passed: 61`。这是小实例接口测试，不是正式 benchmark 结果。

5. 全部测试通过后，生成正式计划：

```bash
python jobs/generate_scripts.py
```

输出应为 formal/main、bigmem-amd、60 workers、970 GiB、1 concurrent job、61 configuration jobs、23,335 instance runs。确认 `git status --short` 没有实验代码和清单的未提交修改，再提交：

```bash
bash results/main/submit.sh
squeue -u "$USER"
```

每个配置作业申请一台节点，数组同一时刻只运行一个配置作业，作业内最多 60 个单核实例并行。生成的 submit.sh 记录选定的 Python 路径，提交数组作业并登记依赖分析作业。批次中运行时不要更新代码、配置或清单。

6. 查看状态和分析：

```bash
sacct -j "$(cat results/main/array_job_id.txt)" --format=JobID,State,ExitCode,Elapsed
sacct -j "$(cat results/main/analysis_job_id.txt)" --format=JobID,State,ExitCode,Elapsed
```

必要时重算分析：`python analysis/analyze_campaign.py results/main`。查看 `results/main/analysis/report.md` 和 `results/main/results.csv`，保留超时、错误、不支持和未完成记录。

7. 分解对照在主实验与其分析结束后单独提交：

```bash
python jobs/generate_scripts.py --matrix decomposition
bash results/decomposition/submit.sh
```

计划应为 2 个配置、1,020 次运行。逐配置已完成记录会保留；数组结束后，重新执行同一 submit.sh 可续跑缺少的记录。

8. 全部结果完成后导出精简交付：

```bash
python analysis/export_results.py --campaign results/main --output deliveries/main
python analysis/export_results.py --campaign results/decomposition --output deliveries/decomposition
```

交付包含结果表、分析表与图、报告、配置、清单和运行环境。原始日志与输入不进入 deliveries；验解记录包保留在各批次的 `verification-records.tar.gz`，另行备份或传输。GitHub 推送由操作者在所有项目作业结束后手动进行。

代码版本由登录节点在生成和提交时用 Git 检查，计算节点从已准备的 campaign.json 读取版本记录，不要求节点安装 Git。独立小测试的版本字段可为空；正式结果仍记录提交版本。批次运行期间不要修改 checkout。
