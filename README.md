# Makoto (誠)

Makoto is a source-first, SLSA-like framework for data provenance and integrity. It is
designed to let a recipient verify:

1. where data was first observed;
2. every attested transformation from that source to the handed-off artifact;
3. which cryptographic identities made those claims; and
4. whether the exact metadata and artifact bytes still match their signed digests.

Makoto v0.2 replaces the v0.1 mutable lineage document with immutable in-toto Statement
payloads, independently signed DSSE envelopes, a hash-linked provenance DAG, digest-pinned
organizational JSON Schema profiles, and a separately signed handoff manifest.

## Status

v0.2 is an unreleased release candidate under active implementation. The repository now
contains the twelve core Draft 2020-12 schemas, digest catalogs, strict DSSE/Ed25519 signing,
consumer-owned trust policy, hash-linked DAG verification, private organizational profiles,
pinned Unicode 15.0 handling, the bounded `makotoPattern` vocabulary, and the complete
September producer-to-consumer demo. It must not yet be described as a released or fully
conformant protocol: the full Phase 0 coverage matrix, diagnostic trigger coverage, bounded
worker isolation, media-conflict handling, aggregate report folding, and final release evidence
are still being completed. The stable diagnostic trigger map and code/step/owner/context report
contract now live in `testdata/v0.2/diagnostic-map.json` and
`schemas/v0.2/verification-report.schema.json`; conformance vectors still need to exercise every
row. Exact dataset-manifest membership, partition digest, and optional size verification are
implemented, but do not yet cover every resource-limit stratum in the spec.

The complete project and protocol-design specification is [spec/v0.2.md](spec/v0.2.md). The
[adversarial review record](docs/v0.2-adversarial-review.md) distinguishes completed reviews,
excluded timeouts, accepted changes, and the still-open current-revision convergence gate.
The specification explicitly distinguishes signature validity from signer authorization,
and graph continuity from completeness or freshness relative to an independent anchor.

## Run the complete proof

From a clean checkout, install the locked dependencies and run one deterministic command:

```bash
uv sync --locked --dev
./scripts/demo-v0.2.sh --acceptance
```

The demo creates a synthetic source dataset, attests an origin, applies and attests two
transformations, signs an exact handoff manifest, then verifies the bundle using a separate
receiver policy and two digest-pinned private schemas. It must produce one `ALLOW` and seven
expected denials:

```text
positive: ALLOW (all checks pass)
mutated-final-data: DENY (E_ARTIFACT_DIGEST)
statement-digest-mismatch: DENY (E_STATEMENT_DIGEST)
edited-signed-metadata: DENY (E_SIGNATURE_INVALID)
removed-predecessor: DENY (E_PREDECESSOR_MISSING)
rewired-step: DENY (E_SIGNATURE_INVALID)
private-schema-violation: DENY (E_PROFILE_INVALID)
unauthorized-signer: DENY (E_SIGNER_UNAUTHORIZED)
```

Acceptance writes only to the ignored demo `.work/` directory and removes it on success.
To regenerate the checked display artifacts used by documentation and the website:

```bash
./scripts/demo-v0.2.sh --acceptance --export demos/v0.2-end-to-end/generated
```

The checked-in keys are deterministic, insecure demo material. They are never production
credentials.

## Core schema contract

Canonical v0.2 resources live under [`schemas/v0.2/`](schemas/v0.2/):

- DSSE envelope and in-toto statement shapes;
- origin and transformation predicates;
- extensible, digest-pinned profile references and the Makoto profile dialect;
- offline schema catalogs and partitioned dataset manifests;
- handoff manifests and transport bundle indexes;
- consumer trust policies; and
- stable verification reports.

Attestation commands accept either compact `--subject name=path` values or closed
`--subject-binding` JSON objects when a subject name contains `=`. `handoff create` accepts
both ordinary historical `--artifact-material` and validated dataset-manifest material. It
refuses any material whose bytes do not match the selected signed subject. Dataset-entry bindings
add partition bytes only after the mandatory manifest profile, logical entry membership, digest,
and optional size pass producer-side validation.

A partition-pruned transformation input uses `entryName` and `predecessorMaterial` together. The
predecessor material is the exact signed dataset-manifest subject; the CLI validates it before it
signs the transformation. Dataset-entry bytes are stored at
`artifacts/dataset-entries/<sha256>.bin`, where the path hash covers only the closed logical
identity `{manifestStatementDigest, manifestSubjectName, entryName}`. The partition digest is
verified evidence, not part of that path preimage.

`schemas/v0.2/catalog.json` pins the exact bytes of all twelve schema resources. Versioned
schema bytes will become immutable when v0.2 is released. The historical v0.1 schema and
demos remain available during migration but are not wire-compatible with v0.2.

## Extensibility model

Makoto core records only portable provenance and integrity facts. A team can keep its own
JSON Schemas private, identify them with an opaque URI, and pin the exact root and transitive
closure digests in a signed profile reference. Profiles can validate:

- the complete in-toto statement;
- an origin or transformation predicate, including organization-specific `extensions`; or
- actual JSON/NDJSON artifact contents selected by signed subject name and media type.

The receiver resolves schemas offline from its own authenticated catalog. Makoto never treats
a familiar URL as sufficient identity and never fetches a private schema during verification.
Portable string constraints use the bounded, non-backtracking `makotoPattern` vocabulary;
standard regular-expression keywords are intentionally unavailable in organizational profiles.

## What verification means

Makoto establishes that exact bytes match signed claims, that configured keys produced valid
signatures, that receiver policy authorizes those keys for those claim types, and that the
complete graph matches an authorized handoff plus independent expectations. It does not prove
that a source told the truth, that a claimed transformation actually executed, that the data is
safe or high quality, or that signed metadata is confidential.

## Local validation

Makoto uses Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --locked --dev
./scripts/check.sh
```

Regenerate the core catalog after changing a draft schema, then rerun the complete gate:

```bash
uv run scripts/build_schema_catalog.py
uv run scripts/generate_unicode_tables.py
./scripts/check.sh
```

Both generators are deterministic; checks fail if catalogs or generated Unicode tables differ
from their authoritative bytes.

The release checksum manifest covers the portable verifier source, schemas, spec, documentation,
scripts, tests, conformance inputs, locked environment, and runnable demo. Regenerate it only
after those inputs are final, then run the full release rehearsal:

```bash
uv run scripts/release_checksums.py --write
./scripts/release-check.sh
```

`release/v0.2/checksums.json` is not self-authenticating. A distributor must independently pin
the reviewed Git tag and peeled commit before relying on the manifest.

## Repository layout

```text
schemas/v0.2/   canonical v0.2 JSON Schemas and digest catalog
spec/v0.2.md    complete v0.2 project and protocol specification
src/makoto/     reference CLI, verifier, crypto, graph, policy, profiles, and reports
testdata/v0.2/  pinned conformance inputs and expected negative outcomes
tests/          schema, crypto, graph, policy, pattern, Unicode, and bundle tests
demos/v0.2-end-to-end/ canonical September producer-to-consumer proof
docs/           v0.2 architecture, integration boundary, and migration guidance
```

## Security boundary

A valid signature authenticates a claim; it does not prove the claim is true. Consumer-owned
policy determines which keys may attest each source, operation, profile, and handoff. Makoto
uses exact-byte hashes and signatures for integrity, but deletion, rollback, equivocation, and
freshness require an independently supplied expected head, manifest digest, artifact tuple,
nonce, age policy, or future transparency anchor.

Makoto metadata is signed, not encrypted. Do not put secrets, credentials, salts, or raw
personal data in attestations.

## License

Apache License 2.0. See [LICENSE](LICENSE).
