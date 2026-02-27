# Demo 03: GitHub Action for DBOM Generation

**Time:** 2 minutes to read, 5 minutes to integrate | **Deps:** python3 (stdlib only)

## The Story

Every time a data file changes in your repo, a DBOM is automatically generated in CI. No manual steps, no forgotten provenance. The DBOM travels with the data as a build artifact.

## What's Here

This is a **real, usable GitHub Action** — not a mock.

| File | Purpose |
|------|---------|
| `action.yml` | Composite action definition |
| `generate_dbom.py` | DBOM generator (stdlib only, runs anywhere) |
| `example-workflow.yml` | Copy-paste workflow for your repo |
| `sample-output.dbom.json` | Example of what gets generated |

## Try It Locally

```bash
# Generate a DBOM for any file
python3 generate_dbom.py path/to/your/data.csv

# With custom signer
python3 generate_dbom.py data.csv --signer "github:yourname"

# Custom output path
python3 generate_dbom.py data.csv --output my-dbom.json
```

## Add to Your Repo

Copy `example-workflow.yml` to `.github/workflows/dbom.yml` in your repo. Done.

> **💬 What the champion says:**
>
> *"We added this to our ML pipeline in 10 minutes. Every training dataset now has a DBOM generated automatically on push. When the model audit came, we had provenance for every artifact — no scramble, no manual work."*

## What Else This Could Handle

- Multi-file DBOM generation (glob patterns)
- DBOM validation step that blocks merge if hash mismatches
- Automatic DBOM signing with GitHub OIDC tokens
- DBOM registry upload (push to central provenance store)
