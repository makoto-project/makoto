# Makoto: Data Bill of Materials

**Makoto** is a machine-readable, signable JSON schema for data provenance. Think [SLSA](https://slsa.dev/) but for data, not binaries.

Every data asset gets a `.dbom.json` sidecar that answers three questions:
1. **Where did this data come from?** (source URI + hash)
2. **Who vouches for it?** (signer identity)
3. **How was it produced?** (lineage chain)

## Start Here

Pick the demo that matches your pain point:

| # | Demo | Pain Point | Time | Run |
|---|------|-----------|------|-----|
| 01 | [Poisoned Pipeline](demos/01-poisoned-pipeline/) | Corrupted data silently enters pipeline | 3 min | `./run.sh` |
| 02 | [Reproducibility Gap](demos/02-reproducibility-gap/) | "Which dataset version?" is unanswerable | 2 min | `python3 demo.py` |
| 03 | [GitHub Action](demos/03-github-action/) | No provenance in CI/CD | 2 min | `python3 generate_dbom.py <file>` |
| 04 | [Config Postmortem](demos/04-config-postmortem/) | Config changed, no one knows who/why | 3 min | `python3 demo.py` |
| 05 | [AI Dataset Verification](demos/05-ai-dataset-verification/) | Training on unverified data | 2 min | `python3 demo.py` |

**Fastest payoff:** Start with Demo 05 (AI verification) — it's the most visceral.

**For a 20-minute decision-maker meeting:** Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

## DBOM Format

```json
{
  "schema_version": "0.1",
  "id": "dbom-<uuid>",
  "created_at": "<ISO 8601>",
  "source": {
    "uri": "s3://bucket/path/file.csv",
    "hash": { "algorithm": "sha256", "value": "<hex>" },
    "format": "csv"
  },
  "signature": {
    "algorithm": "sha256",
    "value": "<hex>",
    "signer": "github:username"
  },
  "lineage": [
    {
      "step": 1,
      "description": "What happened",
      "tool": "tool-name v1.0",
      "input_hash": "n/a",
      "output_hash": "<hex>"
    }
  ]
}
```

Full schema: [`dbom_schema.json`](dbom_schema.json)

## Requirements

- **bash** (Demo 01)
- **Python 3.6+** (Demos 02–05, stdlib only — no pip install needed)
- **No Docker required** for any demo

## License

Apache 2.0
