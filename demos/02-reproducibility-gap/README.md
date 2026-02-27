# Demo 02: The Reproducibility Gap

**Time:** 2 minutes | **Deps:** python3 (stdlib only) | **Docker:** not needed

## The Story

A researcher submits a paper citing `experiment_v2.csv`. The reviewer asks: which version of the raw data? Were outliers removed? By what method? The researcher can't answer — the paper is rejected.

With a DBOM sidecar, the full lineage is machine-readable: every processing step, tool version, and hash chain from instrument to analysis.

## Run It

```bash
python3 demo.py
```

## What You'll See

1. **Part 1 (no DBOM):** CSV exists but origin, processing, and ownership are unknown
2. **Part 2 (with DBOM):** Full 3-step lineage chain verified, reviewer satisfied

## Key Files

| File | Purpose |
|------|---------|
| `demo.py` | The demo script |
| `datasets/experiment_v2.csv` | Trial results (10 rows) |
| `datasets/experiment_v2.dbom.json` | DBOM with 3-step lineage chain |

## What Else This Could Handle

- Automatic DBOM generation from Jupyter notebook execution
- Integration with data versioning tools (DVC, LakeFS)
- Journal submission requirements enforcing DBOM presence
- Cross-institution lineage linking (lab A's output → lab B's input)
