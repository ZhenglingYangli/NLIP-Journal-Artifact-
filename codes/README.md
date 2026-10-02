# NLIPSat: Satisfiability-Based Nonlinear Integer Programming Encoding Toolkit

NLIPSat is a research prototype for encoding nonlinear integer programming (NLIP) instances into weighted MaxSAT and solving them with modern MaxSAT engines. The toolkit supports multiple encoding strategies, optional order decomposition for high-degree terms, lightweight preprocessing, and solution verification. It also includes benchmark collections used in our experiments.

## AIJ execution release 0.2.0

This is the unique AIJ execution code, tagged `aij-code-v0.2` in the enclosing
AIJ repository. See [the correctness review](../../01-experiment-config/CORRECTNESS_REVIEW.md)
for the repaired mathematical defects, validation and implications for historical results.
In particular, QPLIB cross coefficients must also carry the factor 1/2.

Successful results are always checked in the original problem. `--verify` prints
the report; `--no-preprocess` disables optional bound propagation and probing.
Variable shifts, minimization conversion and exact normalization remain active.
Use `objective_value_exact` (API) or `OPTExact` (CLI) for exact objective values.
Final witness verification is timed separately as `TimeVerify`.

The code package contains no bundled external MaxSAT binaries or bulk benchmarks.
Set `NLIP_MAXHS`, `NLIP_WMAXCDCL`, and `NLIP_OPENWBO` to existing solver binaries.
The AIJ benchmark manifests are in `../../03-benchmarks/manifests`. On the current
Ubuntu host the historical input root for the examples below is:

```bash
export BENCH_ROOT='/home/ubuntu/#科研项目/MIS/0-NLIP/NLIP_composes/experiment/benchmarks'
python -m unittest discover -s tests -v
```

## Repository Structure

```text
.
├── codes/
├── examples/
├── nlipsat/
├── solvers/baseline/
└── tests/
```

## Benchmark Collections

The historical manifests reference these benchmark groups at the input root:

- `benchmarks/diverse_sat`: 108 CNF instances
- `benchmarks/qplib_fully_passed`: 137 QPLIB instances
- `benchmarks/smt_0_10`: 150SMT-LIB2 instances

## Requirements

- Python 3.9 or newer; the AIJ experiment environment uses Python 3.9.
- [PySAT](https://pysathq.github.io/) with PB support (`python-sat[pblib,aiger]`)
- Z3 Python bindings (`z3-solver`) for SMT-LIB2 parsing

## Quick Start

Run from the repository root:

```bash
python3 codes/main.py path/to/problem.json
```

Examples:

```bash
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib"
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib" -e BIN
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib" -e BIN --decomp
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib" -s RC2 --verify
python3 codes/main.py "$BENCH_ROOT/diverse_sat/ais/ais10.cnf" --k 2 -e BIN
```

## Python API

NLIPSat also exposes a small Python API for constructing and inspecting the
generated WCNF formula object before solving:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python3 examples/api_example.py
```

```python
from nlipsat import load_problem, EncodingConfig, \
                    build_wcnf, solve, verify_solution

problem = load_problem("examples/example4.json")  # .qplib .smt2 .cnf also accepted
cfg = EncodingConfig()  # use_decomposition=True for order decomp

wcnf, name2idx, vpool = build_wcnf(problem, "BIN", cfg)
print(len(wcnf.hard), len(wcnf.soft), wcnf.wght, wcnf.topw)
# 18 4 [1, 2, 2, 4] 10

wcnf.to_file("example.wcnf")
result = solve(problem, encoding="BIN", config=cfg, solver="RC2")
ok, report = verify_solution(problem, result)
print(result["objective_value"], ok)
# 2 True
```

### Generate WCNF only (no solving)

If you only want to build the weighted CNF encoding (for inspection or for running a third-party MaxSAT solver manually), use solver `NONE`:

```bash
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib" -e BIN -s NONE -o out.wcnf
python3 codes/main.py "$BENCH_ROOT/smt_0_10/calypto/problem-005596.cvc.1.smt2" -e BIN --decomp -s NONE -o out.wcnf
```

## Supported Input Formats

### JSON

Native NLIP instances can be provided in JSON format.

### QPLIB

QPLIB instances are parsed through `codes/tools/qplib_parser.py`.

### SMT-LIB2

SMT2 benchmark files are parsed through `codes/tools/smt2_parser.py`.
This parser uses `z3-solver` for extracting bounds and constraints, and may skip unsupported assertions (see `--verbose` for parse stats).

### CNF for Diverse-SAT

When the input file is a CNF instance and `--k` is set to a value of at least `2`, the toolkit interprets the instance as a Diverse-SAT problem and builds the corresponding quadratic objective.

## Main Command-Line Options

```text
usage: python3 codes/main.py input [options]
```

Common options:

- `-e, --encoding {OH,UNA,BIN}`: choose the encoding strategy
- `-s, --solver {RC2,MAXHS,WMAXCDCL,OPENWBO,NONE}`: choose the solver backend (`NONE` = build WCNF only)
- `--decomp`: enable order decomposition for high-degree terms in binary encoding
- `--decomp-threshold N`: minimum degree that triggers decomposition
- `--decomp-strategy {sequential,binary_tree}`: choose the decomposition strategy
- `--decomp-relaxed`: use relaxed multiplication semantics
- `--no-decomp-shared`: disable shared substructure caching
- `--no-weight-gcd`: disable soft-weight normalization by GCD
- `--no-preprocess`: disable preprocessing
- `--verify`: verify the decoded solution
- `--timeout T`: set a timeout in seconds
- `--k K`: number of diverse models for CNF input (`K >= 2`)
- `-o, --output FILE`: save the generated WCNF to a file
- `-v, --verbose`: print detailed statistics

## Example Workflows

### Solve a QPLIB instance with the default encoding

```bash
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib"
```

### Solve with binary encoding and decomposition

```bash
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib" -e BIN --decomp
```

### Solve an SMT-LIB2 instance and verify the result

```bash
python3 codes/main.py "$BENCH_ROOT/smt_0_10/calypto/problem-005596.cvc.1.smt2" --verify
```

### Build a WCNF file without further processing

```bash
python3 codes/main.py "$BENCH_ROOT/qplib_fully_passed/QPLIB_0067.qplib" -s NONE -o out.wcnf
```

## Output

For each run, the tool prints a compact summary line containing:

- benchmark name
- encoding
- solver
- status
- objective value
- MaxSAT cost
- variable and clause statistics
- read, encoding, solving, and total runtime

With `--verbose`, the tool prints additional encoding and timing details. With `--verify`, it prints the original-problem verification that is already performed for every successful result.

## References

If you use NLIPSat, please cite the following papers:

- Zhengling Yangli, Zhifei Zheng, Sami Cherif, Rui Sá Shibasaki, and Chu-Min Li. *NLIPSat: Satisfiability-Based Nonlinear Integer Programming Encoding Toolkit*. In Proceedings of the 29th International Conference on Theory and Applications of Satisfiability Testing (SAT 2026), LIPIcs, to appear.
- Zhifei Zheng, Sami Cherif, Rui Sá Shibasaki, Chu-Min Li, and Jialu Zhang. *Maximum Satisfiability Formulations for Nonlinear Integer Programming*. In Proceedings of the 19th European Conference on Logics in Artificial Intelligence (JELIA 2025), LNCS 16094, pp. 190--206, Springer, 2025. DOI: [10.1007/978-3-032-04590-4_14](https://doi.org/10.1007/978-3-032-04590-4_14).
