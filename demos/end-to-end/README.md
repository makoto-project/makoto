# Makoto v0.2 end-to-end proof

This is the canonical September 16 demonstration. It creates a signed origin,
applies two deterministic transformations, appends one immutable statement per
step, signs an exact handoff manifest, and verifies the result as an independent
receiver using receiver-owned trust policy and private JSON Schemas.

Run from the repository root:

```console
./scripts/demo.sh --acceptance
```

The acceptance mode uses fixed, insecure demo-only Ed25519 seeds and timestamps
to make every generated JSON byte reproducible. It writes only beneath the
ignored `demos/end-to-end/.work/` directory and removes that directory on
success.

To regenerate the reviewable documentation artifacts without retaining private
demo keys:

```console
./scripts/demo.sh --acceptance --export demos/end-to-end/generated
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
uv run makoto verify bundle demos/end-to-end/generated/positive-bundle \
  --policy demos/end-to-end/generated/receiver/policy.json \
  --schema-catalog demos/end-to-end/generated/receiver/catalog.json \
  --expected-manifest sha256:e24aae77ba1374162edff49aa0ab1d8dd7e38c333e134a2128ad1598fec99fb7 \
  --expected-head sha256:99aee76db46a720405da6d0015d427c791b0d4e02367b9e2bc36ce82ae812bce \
  --expected-artifact demos/end-to-end/generated/receiver/expected-artifact.json \
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
