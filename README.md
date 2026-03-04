# Makoto (誠) — Data Bill of Materials

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)]()
[![Spec site](https://img.shields.io/badge/spec-usemakoto.dev-black.svg)](https://usemakoto.dev)

> **SLSA for data.** Cryptographically signed provenance for every dataset, config, and model artifact — without new infrastructure.

**[Read the full spec →](https://usemakoto.dev)**

---

## The Problem

Data moves through pipelines silently. When something breaks — a poisoned training set, a config change that tanks throughput, a dataset the reviewer can't trace — there's no record of where the data came from, who touched it, or what happened to it.

Makoto fixes that with a **DBOM (Data Bill of Materials)**: a JSON sidecar that travels with your data and answers three questions:

1. **Where did this come from?** — source URI + SHA-256 hash
2. **Who vouches for it?** — signer identity
3. **How was it produced?** — full lineage chain

---

## Start Here: 5 Demos, One Command Each

Pick the scenario that matches your pain:

| # | Demo | Pain Point | Time | Run |
|---|------|-----------|------|-----|
| 01 | [Poisoned Pipeline](demos/01-poisoned-pipeline/) | Corrupted data silently enters pipeline | 3 min | `./run.sh` |
| 02 | [Reproducibility Gap](demos/02-reproducibility-gap/) | "Which dataset version?" is unanswerable | 2 min | `python3 demo.py` |
| 03 | [GitHub Action](demos/03-github-action/) | No provenance in CI/CD | 2 min | `python3 generate_dbom.py <file>` |
| 04 | [Config Postmortem](demos/04-config-postmortem/) | Config changed, no one knows who/why | 3 min | `python3 demo.py` |
| 05 | [AI Dataset Verification](demos/05-ai-dataset-verification/) | Training on unverified data | 2 min | `python3 demo.py` |

**New here?** Start with Demo 05 — it's the most visceral. One changed label, caught instantly.

**Running a 20-minute meeting?** Follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a proven decision-maker walkthrough.

---

## Quick Start

```bash
git clone https://github.com/makoto-project/makoto
cd makoto

# Run any demo — no pip install, no Docker
cd demos/05-ai-dataset-verification && python3 demo.py
cd demos/01-poisoned-pipeline && ./run.sh
cd demos/03-github-action && python3 generate_dbom.py yourdata.csv
```

**Requirements:** bash (Demo 01), Python 3.6+ stdlib (Demos 02–05). That's it.

---

## The DBOM Format

A DBOM is a JSON file. Three sections. No runtime dependency. It lives next to your data.

```json
{
  "schema_version": "0.1",
  "id": "dbom-<uuid>",
  "created_at": "2025-01-15T10:30:00Z",
  "source": {
    "uri": "s3://my-bucket/sensor-data/2025-01-15.csv",
    "hash": { "algorithm": "sha256", "value": "a1b2c3d4..." },
    "format": "csv"
  },
  "signature": {
    "algorithm": "sha256",
    "value": "e5f6a7b8...",
    "signer": "github:data-eng-team"
  },
  "lineage": [
    {
      "step": 1,
      "description": "Raw ingestion from IoT gateway",
      "tool": "ingestion-service v2.1",
      "input_hash": "n/a",
      "output_hash": "a1b2c3d4..."
    }
  ]
}
```

Full JSON Schema: [`dbom_schema.json`](dbom_schema.json)

---

## Makoto Levels

The [Makoto specification](https://usemakoto.dev/spec/) defines three assurance levels:

| Level | What It Guarantees |
|-------|--------------------|
| **L1** | A DBOM exists. Origin and hash are recorded. |
| **L2** | The DBOM is cryptographically signed. Tamper-evident. |
| **L3** | Provenance is unforgeable. Isolated signing environment. |

Start at L1 — it takes minutes. L2 and L3 add crypto guarantees when your compliance team comes asking.

---

## Add to Your CI in 5 Lines

```yaml
# .github/workflows/dbom.yml
- uses: makoto-project/makoto/demos/03-github-action@main
  with:
    data-path: data/training-set.csv
    signer: github:${{ github.actor }}
```

Every data file push automatically generates a DBOM. See [Demo 03](demos/03-github-action/) for full details.

---

## How It Compares

| Tool | What It Tracks | What It Misses |
|------|---------------|----------------|
| DVC / LakeFS | *Which* version of a dataset | Who vouches for it, how it was produced |
| SLSA | Software artifact provenance | Data — different threat model entirely |
| Checksums | File integrity | Identity, lineage, chain of custody |
| **Makoto DBOM** | Origin + integrity + identity + lineage | Nothing — that's the point |

---

## Repository Layout

```
makoto/
├── demos/
│   ├── 01-poisoned-pipeline/     # bash demo, corrupted IoT data
│   ├── 02-reproducibility-gap/   # Python, research dataset lineage
│   ├── 03-github-action/         # Reusable GitHub Action + generator
│   ├── 04-config-postmortem/     # Python + SQLite, audit trail
│   └── 05-ai-dataset-verification/ # Python, ML dataset tamper detection
├── dbom_schema.json              # Full JSON Schema for DBOM v0.1
├── DEMO_SCRIPT.md                # 20-min decision-maker walkthrough
└── README.md
```

---

## Contributing

Issues, PRs, and new demo scenarios welcome. The format is intentionally simple — if you have a pipeline pain point that a DBOM would have caught, we want to see it.

- Open an issue describing the scenario
- Fork, add a `demos/NN-your-scenario/` directory with a README and runnable script
- PR against `main`

---

## Learn More

- **Spec & levels:** [usemakoto.dev](https://usemakoto.dev)
- **Threat model:** [usemakoto.dev/threats/](https://usemakoto.dev/threats/)
- **Attestation formats:** [usemakoto.dev/spec/](https://usemakoto.dev/spec/)
- **Privacy techniques:** [usemakoto.dev/privacy/](https://usemakoto.dev/privacy/)

---

## License

Apache 2.0 — use it, build on it, ship it.
