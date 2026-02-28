# Demo 01: The Poisoned Pipeline

**Time:** 3 minutes | **Deps:** bash, python3, bc | **Docker:** not needed

## The Story

Your IoT pipeline ingests sensor CSVs from partners. Without provenance checks, corrupted data — including SQL injection payloads, NaN values, and physically impossible readings — flows right through to your analytics.

With a DBOM gate, unsigned data is rejected at intake. Only hash-verified, signer-identified data enters the pipeline.

## Run It

```bash
./run.sh
```

## What You'll See

1. **Part 1 (no DBOM):** Corrupted CSV accepted silently — bad stats computed
2. **Part 2 (with DBOM):** Unsigned CSV rejected, signed+verified CSV accepted

## Key Files

| File | Purpose |
|------|---------|
| `run.sh` | The demo script |
| `data/sensors_corrupted.csv` | CSV with NaN, injection, impossible values |
| `data/sensors_clean.csv` | Valid sensor readings |
| `data/sensors_clean.dbom.json` | DBOM sidecar with hash + signer |

## What Else This Could Handle

- Multiple signers with role-based trust (e.g., only QA team can sign production data)
- Automatic DBOM generation at the IoT gateway
- Integration with S3 event triggers for real-time gating
- Schema validation as an additional DBOM-enforced check
