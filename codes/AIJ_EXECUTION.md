# AIJ execution code

This directory is the only NLIPSat source tree used for new AIJ runs.

It was formed by a semantic review of the 12 Python files that differ between
the public-tool snapshot and the SAT 2026 experiment snapshot.  The two source
trees remain beside this directory as read-only provenance references.

Before a development change is accepted, run:

```bash
python tests/test_aij_semantics.py
python tests/test_api.py
```

`test_aij_semantics.py` checks exact and directional multiplication, exact SMT
Boolean lowering against Z3 under exhaustive assignments, all three integer
encodings, preprocessing with shifted bounds, hard-UNSAT status, verification,
and both WCNF export paths.

SMT parsing is strict by default.  Unsupported assertions and variables that
would need artificial finite bounds are rejected instead of being silently
relaxed.  This is required for all reported AIJ results.

The current server environment is for development checks only.  Formal solver
and dependency versions, CPU allocation, 3600-second total timeout, and 16-GiB
memory limit must be frozen before performance runs.
