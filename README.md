# Makoto (誠)

Makoto is a source-first, SLSA-like framework for data provenance and integrity. It is
designed to let a recipient verify:

1. where data was first observed;
2. every attested transformation from that source to the handed-off artifact;
3. which cryptographic identities made those claims; and
4. whether the exact metadata and artifact bytes still match their signed digests.

Makoto v0.3 retains the v0.2 signed-lineage model and adds a standard licence-claim profile plus optional record-level Merkle commitments for dataset entries. The reference verifier continues to support v0.2 as a separate immutable protocol.

## Status

v0.3 is an unreleased draft under active implementation. The repository now
contains fourteen v0.3 Draft 2020-12 schemas, digest catalogs, strict DSSE/Ed25519 signing,
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

The v0.3 design and complete protocol specification is [spec/v0.3.md](spec/v0.3.md). The immutable prior contract remains [spec/v0.2.md](spec/v0.2.md). The
[adversarial review record](docs/v0.2-adversarial-review.md) distinguishes completed reviews,
excluded timeouts, accepted changes, and the still-open current-revision convergence gate.
The specification explicitly distinguishes signature validity from signer authorization,
and graph continuity from completeness or freshness relative to an independent anchor.
The public explanation of why source-to-handoff history matters is at
[usemakoto.dev/why-lineage/](https://usemakoto.dev/why-lineage/).

Makoto is developed in public under Apache-2.0. Run the proof, bring a real data handoff, file a
failing case, review the specification or schemas, or submit a tested patch through
[`makoto-project/makoto`](https://github.com/makoto-project/makoto). The current contribution
paths are documented at
[usemakoto.dev/community/](https://usemakoto.dev/community/). Formal governance has not been
established; public issues, tests, and reviewable changes are the current technical record.

## Run the complete proof

From a clean checkout, install the locked dependencies and run one deterministic command:

```bash
uv sync --locked --dev
./scripts/demo.sh --acceptance
```

The versioned `./scripts/demo-v0.2.sh --acceptance` entry point remains supported for
commands copied from earlier documentation.

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
./scripts/demo.sh --acceptance --export demos/v0.2-end-to-end/generated
```

The checked-in keys are deterministic, insecure demo material. They are never production
credentials.

## Core schema contract

Canonical v0.3 resources live under [`schemas/v0.3/`](schemas/v0.3/). The unchanged v0.2 resources remain under [`schemas/v0.2/`](schemas/v0.2/).

- DSSE envelope and in-toto statement shapes;
- origin and transformation predicates;
- extensible, digest-pinned profile references and the Makoto profile dialect;
- offline schema catalogs and partitioned dataset manifests;
- record declarations and record-inclusion proofs;
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

`schemas/v0.3/catalog.json` pins the exact bytes of all fourteen v0.3 schema resources. A verifier dispatches one protocol family and rejects mixed v0.2/v0.3 identifiers. The existing demo remains a v0.2 compatibility proof.

## Licence claims

v0.3 includes a verifier-owned, digest-pinned standard profile for one SPDX expression and evidence URL per statement subject. Generate its exact profile reference with `makoto profile standard-license`. A receiver can require it through a rule's `profileConstraints`.

The claim records what a signer vouched for. Makoto does not decide whether the licence is correct, whether the evidence is sufficient, or whether the data is legally usable.

## Record inclusion proofs

A v0.3 dataset entry may carry a record count and Merkle root. Producers declare record boundaries as byte ranges or supply an ordered record-hash list. Makoto does not parse the entry's file format.

`makoto record root` computes the manifest commitment. `makoto record prove` and `makoto record verify` require a bundle that the v0.3 verifier allows under the supplied consumer policy. Proof verification checks one record digest against the signed dataset entry. Supplying the record or entry bytes also checks the corresponding byte digest. See [the migration guide](docs/v0.3-migration.md) for command examples.

## Language examples

The published JSON Schemas are the language-independent contract. Applications
bind generic JSON to those schemas instead of relying on protocol types native
to one language. The Python package in `src/makoto/` remains the reference CLI
and complete receiver verifier. The tested [Go examples](examples/go/README.md)
show schema validation, canonicalization and hashing, DSSE Ed25519 signatures,
and how to call the reference verifier from Go.

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

## Assurance model

Makoto follows SLSA's structure instead of turning receiver checks into a score. Two cumulative
producer tracks describe how evidence was created:

| Track | L1 | L2 | L3 |
|---|---|---|---|
| Origin | Traceable capture | Platform-authenticated capture | Policy-controlled capture |
| Transform | Traceable execution | Platform-authenticated execution | Hardened execution |

Receiver results are separate verified properties: authorization, graph completeness, anchored
freshness, schema conformance, and strict reproduction. `makoto vsa summarize` evaluates the
track evidence and properties and emits a signed SLSA v1 Verification Summary Attestation. It
uses exact verifier keys, assessment-policy digests, resource URIs, required claims, and
reproduction independence groups from the existing consumer trust policy. There is no opaque
score. `--evaluation-out` optionally writes the deterministic levels, properties, and diagnostic
codes beside the standard VSA without adding Makoto-only fields to the SLSA predicate.

`makoto vsa assess` lets a trusted platform or assessor sign an Origin L2/L3 or Transform L2/L3
claim over exact statement envelopes. Transform L3 additionally requires digests and URIs for
the raw hardware evidence the assessor evaluated; Makoto deliberately does not invent a TPM or
TEE quote format. The standard digest-pinned Origin L3 reference profile is in
[`docs/profiles/`](docs/profiles/).

Track levels and verified properties do not certify that the data's content is correct. They
bind downstream tests, review, calibration, or model evaluation to exact provenance so a bad
answer can be traced and repaired.

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

`release/v0.3/checksums.json` is not self-authenticating. A distributor must independently pin
the reviewed Git tag and peeled commit before relying on the manifest.

## Repository layout

```text
schemas/v0.2/   canonical v0.2 JSON Schemas and digest catalog
schemas/v0.3/   canonical v0.3 JSON Schemas and digest catalog
spec/v0.2.md    complete v0.2 project and protocol specification
spec/v0.3.md    v0.3 design and complete protocol specification
src/makoto/     reference CLI, verifier, crypto, graph, policy, profiles, and reports
examples/go/    schema-first Go integration examples and fixture-backed tests
testdata/v0.2/  pinned conformance inputs and expected negative outcomes
testdata/v0.3/  v0.3 licence, record, and diagnostic fixtures
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
