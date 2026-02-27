# Demo 05: AI Dataset Verification

**Time:** 2 minutes | **Deps:** python3 (stdlib only) | **Docker:** not needed

## The Story

Your ML team downloads a training dataset from a shared drive. Is it the official version? Has anyone modified labels? A single poisoned label can compromise model behavior — and you'd never know.

With a DBOM sidecar, hash verification catches even a single changed byte. Signer identity confirms who vouches for the data.

## Run It

```bash
python3 demo.py
```

## What You'll See

1. **Part 1 (no verification):** Dataset loaded on blind trust
2. **Part 2 (with DBOM):** SHA-256 hash verified, signer confirmed, lineage shown
3. **Part 3 (tampered data):** One label changed → instant hash mismatch → training blocked

## Key Files

| File | Purpose |
|------|---------|
| `demo.py` | The demo script |
| `datasets/imagenet_sample.csv` | Fake ImageNet sample (10 images, labeled) |
| `datasets/imagenet_sample.dbom.json` | DBOM with hash + signer + lineage |

## What Else This Could Handle

- Per-row hash verification for datasets too large to hash as a whole
- Model card generation that includes training data DBOM references
- Dataset registry integration (HuggingFace, Kaggle) with DBOM metadata
- Continuous monitoring: re-verify dataset integrity on a schedule
