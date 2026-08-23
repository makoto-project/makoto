# Makoto v0.2 end-to-end proof

This is the canonical September 16 demonstration. It creates a signed origin,
applies two deterministic transformations, appends one immutable statement per
step, signs an exact handoff manifest, and verifies the result as an independent
receiver using receiver-owned trust policy and private JSON Schemas.

Run from the repository root:

```console
./scripts/demo-v0.2.sh --acceptance
```

The acceptance mode uses fixed, insecure demo-only Ed25519 seeds and timestamps
to make every generated JSON byte reproducible. It writes only beneath the
ignored `demos/v0.2-end-to-end/.work/` directory and removes that directory on
success.

To regenerate the reviewable documentation artifacts without retaining private
demo keys:

```console
./scripts/demo-v0.2.sh --acceptance --export demos/v0.2-end-to-end/generated
```

The export contains the source and transformed data, positive handoff bundle,
receiver policy/catalog/profiles, complete verification reports, and a digest
manifest. The acceptance harness also compares every negative result against
its checked contract in `testdata/v0.2/negative/*/expected-report.json`.

The export is also a self-contained receiver handoff. After the sender transfers
`generated/positive-bundle/`, the receiver can independently verify the exact
manifest, graph head, and final bytes with receiver-owned policy, schemas, and
expectations:

```console
uv run makoto verify bundle demos/v0.2-end-to-end/generated/positive-bundle \
  --policy demos/v0.2-end-to-end/generated/receiver/policy.json \
  --schema-catalog demos/v0.2-end-to-end/generated/receiver/catalog.json \
  --expected-manifest sha256:b83a5cd1870b8ce1f2931650611f0a19deed0796c0f262e4632efc17981f695c \
  --expected-head sha256:962be71738a0146642d27c87fba3c7338b0f2bb764b113b16867bb4808b11977 \
  --expected-artifact demos/v0.2-end-to-end/generated/receiver/expected-artifact.json \
  --evaluation-time 2026-09-16T16:00:00Z \
  --json
```

The command exits zero and returns a report with `"decision":"allow"`. Changing
the transferred final bytes causes the same command to deny with
`E_ARTIFACT_DIGEST`.

The positive flow demonstrates the three questions at Makoto's center:

1. Where did these exact bytes originate?
2. Which signed transformations produced the final bytes?
3. Which receiver-authorized identities attested the steps and handoff?

The negative suite then proves that altered data, altered metadata, a missing
step, a rewired step, a private-schema violation, and an unauthorized signer
are denied. No named third-party tool is a Makoto protocol dependency.
