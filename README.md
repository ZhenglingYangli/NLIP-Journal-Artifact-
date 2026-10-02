# NLIP-AIJ experiment artifact

NLIPSat encodings and solver comparisons for QPLIB (137), Diverse SAT (108, k=2),
MIPO (870), and bounded SMT (150). The main matrix contains 23,335 runs.
LRN is an optional module and is disabled in the formal main experiment.

- [Cluster deployment and data preparation](02-code/aij-experiments/CLUSTER_DEPLOYMENT.md)
- [Experiment protocol and solver routes](02-code/aij-experiments/README.md)
- Solver implementation: `02-code/nlipsat-aij`
- Experiment runner: `02-code/aij-experiments`
- Fixed instance lists: `03-benchmarks/manifests`

MIPO inputs are retrieved from the authors' archive with `prepare_mipo.py`.
The other three datasets and external MaxSAT executables use the site's existing installation.
Python environments, solver licenses, benchmark payloads, and experiment results are not included.
