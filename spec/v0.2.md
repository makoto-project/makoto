# Makoto v0.2 Project Specification

**Status:** Project specification draft; protocol conformance remains unfrozen until Phase 0 publishes every normative schema and conformance vector

**Target:** Runnable public proof by September 16, 2026

**Specification version:** 0.2 proposal

**Repositories:** `makoto-project/makoto` (canonical schemas and tooling) and `makoto-project/usemakoto.dev` (documentation, hosted schemas, and web demo)

**Implementation baselines:** core `main` at `0969dd7a20c41323da56e1da8fc682afe2a83cb6`; website `main` at `30f9eea1977630f7b365fd2c16e30915cf8f97bd`

**Release refs:** core immutable tag `v0.2.0`; website deploys reviewed `main` after pinning that tag

**Normative language:** “MUST”, “MUST NOT”, “SHOULD”, “SHOULD NOT”, and “MAY” are to be interpreted as described in RFC 2119 and RFC 8174.

## 1. Executive summary

Makoto is a source-first, SLSA-like framework for data provenance and integrity. It gives a data consumer a machine-verifiable answer to three questions:

1. Where did this data start?
2. What transformations led to the artifact I received?
3. Who attested to each claim?

Makoto v0.2 represents provenance as an append-only directed acyclic graph (DAG) of immutable, signed statements. An origin statement binds a source observation to the digest of the first data artifact. Every transformation statement identifies its input artifacts and their predecessor attestations, describes the operation, and binds the resulting artifact bytes to new digests. Statements are wrapped in DSSE envelopes and use the in-toto Statement v1 shape so existing supply-chain tooling can parse the outer format.

Makoto is deliberately extensible. Its core schemas define only the portable provenance vocabulary. A team can add public or private JSON Schemas that require internal metadata, constrain extension fields, or validate structured JSON artifacts. Every referenced profile is identified by a URI and an immutable SHA-256 digest. Private schemas never need to be published: a consumer can resolve them from a local schema catalog. Unknown critical profiles fail closed.

The September 16 proof is a complete producer-to-consumer handoff, not a static JSON example. A clean clone will create provenance for a synthetic source dataset, apply and attest two transformations, produce a signed handoff bundle, and independently verify core schemas, private organizational profiles, every configured-key signature and every signature relied upon for authorization, signer authorization, graph continuity, the expected head, and the final data digest. The same story will be presented on a core website page, and all public v0.2 schemas will be available at immutable versioned URLs.

This document is the executable project and protocol-design specification. Approval authorizes Phase 0 contract encoding only; it is not, by itself, an interoperability or conformance claim. The frozen v0.2 protocol is the reviewed tuple of this prose, immutable JSON Schemas, verification-report schema, versioned `diagnostic-map.json`, coverage matrix, and positive/negative conformance vectors produced in Phase 0. Every normative artifact is included in the tagged release checksum manifest and any semantic change to one requires the complete version-family rules in Section 17. Where those artifacts expose an ambiguity, Phase 0 changes this document before implementation begins rather than letting implementations choose divergent behavior.

## 2. Why v0.2 is necessary

Data pipelines routinely produce artifacts without portable evidence of origin, processing history, or the parties responsible for those claims. Teams compensate with orchestration logs, catalog entries, checksums, bespoke audit tables, or narrative documentation. Those records are often system-specific, mutable, incomplete at organizational boundaries, and detached from the exact bytes a consumer receives.

Makoto v0.1 established the right user-facing questions but does not yet provide the guarantees its documentation implies. The current project has three incompatible representations: the hosted DBOM schema, in-toto-shaped specification examples, and other website examples. The published examples do not validate against the hosted schema. Current “signatures” are SHA-256 values rather than digital signatures, and current verification code does not authenticate signers, enforce authorization, prove graph continuity, pin an expected terminal state, or protect metadata against substitution. Several advertised schema and repository URLs do not resolve.

v0.2 is intentionally breaking. It replaces a mutable lineage array with immutable signed statements, separates authenticity from authorization, and makes verification results precise enough that a consumer can safely automate a decision.

### 2.1 Verified current-state audit

This subsection is non-normative project evidence. Its repository counts describe the audited baseline and are not protocol conformance requirements.

The following was verified against website commit `30f9eea1977630f7b365fd2c16e30915cf8f97bd` and core commit `0969dd7a20c41323da56e1da8fc682afe2a83cb6` on August 21, 2026:

| Surface | Verified state | v0.2 consequence |
|---|---|---|
| `schema/v0.1.json` | Requires one mutable `lineage` array and labels SHA-256 as the signature algorithm. | Preserve as immutable history; do not extend it into v0.2. |
| `sdk/python/makoto/generate.py:46` | Computes `sha256(file_hash + signer)` and calls it a signature. | Replace with DSSE and Ed25519 in the core implementation. |
| `sdk/python/makoto/verify.py:70` | Checks schema and optionally the source file hash; it does not verify digital signatures, authorization, graph continuity, or an expected head. | Replace with the verifier contract in Section 15. |
| Website examples | Eleven JSON examples fail the published v0.1 schema because the site presents incompatible formats. | Every example must declare and pass one immutable version. |
| Hosted/core identifiers | Hosted v0.1 works, while the core schema `$id` and predicate URLs do not consistently resolve. | Core owns IDs; all v0.2 schema and predicate URLs have deployment probes. |
| Links | All 1,307 local references across 42 HTML files have local targets; four external GitHub URLs are broken across seven occurrences. | Preserve the working local topology and repair or remove every known external 404. |
| Demo mapping | Website demo 06 points to a nonexistent core-repository directory. | The v0.2 page pins an existing tagged core demo path. |
| Package claims | PyPI `makoto` is unrelated and npm `@makoto/sdk` is unpublished. | No registry publication or install claim in v0.2. |
| Repository hygiene | 542 JavaScript `node_modules` files are tracked; site says MIT while code manifests say Apache-2.0 and no site `LICENSE` exists. | Remove tracked dependencies and make Apache-2.0 authoritative. |

## 3. Product thesis

Makoto succeeds if it becomes the smallest useful common language for carrying data provenance across tools and organizational boundaries.

It is not a data catalog, orchestrator, policy engine, storage system, or universal data validator. It is the portable evidence layer those systems can produce, preserve, exchange, and evaluate.

The framework is built around six principles:

1. **Start at the source.** A valid history reaches one or more origin statements. A list of transformations without an origin is not complete Makoto provenance.
2. **Append; never rewrite.** A new processing event creates a new signed statement. It never edits an earlier statement.
3. **Bind claims to bytes.** Artifact digests refer to exact bytes. Metadata signatures cover exact statement payload bytes.
4. **Separate evidence from trust.** A valid signature proves key control. Trust policy decides whether that key is authorized to make that claim.
5. **Make extensions first-class.** Organizations can impose schemas and data rules without changing or publishing the Makoto core.
6. **Degrade explicitly.** Optional information may be absent, but a verifier reports exactly which guarantees were and were not established.

## 4. Goals

### 4.1 Protocol goals

- Define one coherent v0.2 representation for origins, transformations, artifact bindings, profiles, signatures, graph edges, and handoffs.
- Support linear pipelines, multiple origins, joins, and splits.
- Make each provenance event immutable, independently signed, and content-addressable.
- Allow a receiver to detect mutated data, edited metadata, missing predecessors, rewired lineage, unauthorized signers, and policy/schema violations.
- Provide an explicit bundle-completeness anchor through an authorized signed handoff manifest and separate selection/freshness evidence through an expected manifest digest, expected head set, expected final-artifact set, nonce, or age policy; recipient is audience binding only, and replay acceptance is an explicit waiver rather than an anchor.
- Reuse in-toto Statement v1 and DSSE where they fit instead of inventing new envelope and statement formats.

### 4.2 Extensibility goals

- Allow public and private organizational profiles using JSON Schema Draft 2020-12.
- Allow a profile to validate a whole statement, a Makoto predicate, or a structured JSON artifact.
- Pin every profile and its transitive schema resources by digest.
- Permit ordinary extension data that older consumers can safely ignore.
- Require consumers to fail closed when an unknown profile is marked critical.

### 4.3 Product and developer-experience goals

- Ship a reference CLI and library that can create, sign, bundle, and verify v0.2 provenance.
- Make the complete demonstration runnable from a clean clone with one documented command sequence.
- Host immutable, CORS-enabled v0.2 schemas at `usemakoto.dev`.
- Make the website’s examples, downloads, CLI behavior, and hosted schemas agree byte-for-byte.
- Preserve v0.1 URLs and clearly label v0.1 as historical and incompatible with v0.2.

### 4.4 September 16 outcome

At the end of the live demo, an independent consumer must be able to say:

- This final file matches the digest attested by the terminal transformation.
- Every transformation connects to its declared input artifact and predecessor statement.
- The complete reachable graph terminates at the expected source origins.
- Every statement was signed with a valid key.
- Trust policy authorizes those keys for those claims.
- The metadata satisfies the Makoto core schema and the sender’s private organizational profile.
- The final structured data satisfies the declared data-content schema.
- The exact head set and graph match an authorized signed handoff manifest, and the consumer's expected head or challenge matches when freshness is required.

## 5. Non-goals for v0.2

- Community formation, project governance, foundation contribution, or a technical oversight committee.
- A Docling integration. Docling may later produce or consume Makoto evidence, but it is not part of the core protocol or September 16 acceptance path.
- A claim that Makoto proves a transformation actually ran exactly as described. v0.2 records authenticated claims; stronger execution isolation is future work.
- “L3” isolated builders, hardware-backed keys, remote attestation, or control-plane-generated evidence.
- Transparency logs, global key discovery, certificate authorities, Sigstore integration, or public revocation infrastructure.
- A production streaming/window protocol. The data model must not preclude it, but the reference implementation covers finite artifacts.
- A hosted policy decision service, data catalog, workflow orchestrator, or provenance database.
- Validation of arbitrary CSV, Parquet, images, audio, or proprietary binary semantics. v0.2 content validation is normative for JSON artifacts; other formats require future adapters.
- Package publication to PyPI or npm. Local installation from the repository is sufficient for v0.2 acceptance.
- A guarantee of confidentiality, source truthfulness, legal compliance, data quality, or absence of malicious content.

## 6. Users and primary stories

### 6.1 Data producer

As a data engineer, I want to create an origin attestation and append signed transformation attestations so that downstream consumers can reconstruct and verify how an artifact was produced.

### 6.2 Data platform team

As a platform engineer, I want to define a private organizational profile so that every pipeline supplies required internal metadata and approved structured outputs without requiring changes to Makoto core or publication of internal schemas.

### 6.3 Data consumer

As a recipient, I want one offline verification command with machine-readable results so that I can reject data with invalid structure, signatures, authorization, provenance continuity, expected-head, or content-digest checks.

### 6.4 Auditor or investigator

As an auditor, scientist, or incident responder, I want to traverse from a final artifact back to all source origins so that I can identify the attested actors, tools, and transformations behind a result.

### 6.5 Tool author

As an orchestrator or data-tool author, I want stable wire schemas and CLI semantics so that my product can emit Makoto evidence without adopting a Makoto-specific storage or execution system.

## 7. Terminology

| Term | Definition |
|---|---|
| Artifact | A finite sequence of bytes, such as a JSON file, CSV file, model, configuration, or archive. |
| Subject | An output artifact named and digested in an in-toto statement. |
| Origin | The first Makoto observation of an artifact from a source. An origin has no Makoto predecessor. |
| Transformation | A processing event that consumes one or more attested artifacts and produces one or more subjects. |
| Statement | An in-toto Statement v1 JSON object containing subjects, a predicate type, and a Makoto predicate. |
| Envelope | A DSSE object that carries exact statement payload bytes and one or more digital signatures. |
| Statement digest | SHA-256 of the exact decoded DSSE payload bytes. It identifies the signed statement independent of envelope formatting or added co-signatures. |
| Artifact digest | SHA-256 of the exact artifact bytes. No semantic or format-level canonicalization is implied. |
| Profile | A digest-pinned JSON Schema that adds organization- or use-case-specific requirements. |
| Schema catalog | A local mapping from schema URI and digest to schema bytes. It allows private and offline schema resolution. |
| Trust policy | Consumer-controlled rules mapping keys to allowed predicates, profiles, sources, and signature thresholds. |
| Head | A provenance statement selected by a handoff because at least one of its subjects is terminal and handed off; another subject of the same statement may have descendants. |
| Root | An origin statement reachable from a head. A graph may have multiple roots. |
| Handoff manifest | A signed declaration of the exact statement set, roots, heads, profiles, and final artifacts being transferred. |
| Bundle | A transport directory containing a manifest, envelopes, selected artifacts, and schemas. A verifier MUST never load trust policy from producer-supplied bundle contents. Archive transport is deferred until a safe archive format is specified. |
| DBOM | Human shorthand for the Makoto provenance graph and handoff evidence for data. In v0.2 it is not a separate mutable lineage document. |

Throughout this specification, authorization and final allow/deny decisions use the **trust policy** supplied to the verifier.

## 8. Guarantee model

### 8.1 Guarantees a conforming verifier can establish

Given the necessary artifacts, schema catalog, trust policy, and completeness anchor, a verifier can establish:

- core schema validity;
- profile schema validity;
- digital-signature validity over exact metadata bytes;
- signer authorization under trust policy;
- artifact integrity for every available artifact whose digest is checked;
- graph continuity from every authorized manifest head to all declared origins, plus equality to an independently expected head set when supplied;
- consistency between transformation inputs and predecessor outputs;
- absence of graph cycles;
- exact agreement with a trusted handoff statement set; and
- agreement between the terminal node and an independently supplied expected head.

### 8.2 Guarantees Makoto does not establish by itself

Makoto cannot establish that:

- a signer told the truth;
- a described transformation actually executed;
- the source itself was correct, complete, licensed, safe, or legally usable;
- a bundle history is complete without an authorized handoff manifest, or fresh without an independently obtained expected manifest/head/artifact set, nonce challenge, or consumer age policy; explicit replay acceptance waives rather than establishes freshness;
- an unavailable historical artifact still matches its recorded digest;
- a timestamp came from a trusted clock;
- a URI still serves the original bytes;
- signing keys were stored securely; or
- data is confidential merely because provenance exists.

Documentation and CLI output MUST distinguish “signature valid” from “signer authorized,” and “graph internally complete” from “complete relative to a trusted anchor.”

## 9. System architecture

```text
Producer pipeline
  source bytes
      |
      v
  origin statement --DSSE/Ed25519--> immutable envelope
      |
      v
  transform A + new bytes ----------> immutable envelope
      |                                  references origin payload digest
      v
  transform B + final bytes ----------> immutable envelope
                                         references transform A payload digest
      |
      v
  signed handoff manifest + bundle
      |
      v
Independent consumer verifier
  core schemas + local profile catalog + trust policy + expected head
      |
      +--> structure/profile checks
      +--> signature/authorization checks
      +--> graph and handoff-set checks
      +--> final artifact digest check
      '--> allow/deny decision + machine-readable evidence
```

The protocol is storage-neutral. Envelopes may live beside data, in object storage, in a catalog, or in a dedicated provenance store. A bundle is the reference interchange format, not a required system of record.

## 10. Normative encoding and cryptography

### 10.1 JSON and DSSE

- Statements MUST be UTF-8 JSON objects conforming to in-toto Statement v1.
- Statements MUST be carried in DSSE envelopes for a handoff to qualify as authenticated Makoto v0.2 provenance.
- A statement envelope's DSSE `payloadType` MUST be `application/vnd.in-toto+json`; a handoff envelope's type MUST be `application/vnd.makoto.handoff.v0.2+json`. `envelope.schema.json` requires `payloadType` to be an ASCII string of at most 255 bytes with exactly one `/`. Its type and subtype are each 1 through 127 characters, begin with a lowercase ASCII letter or digit, and otherwise contain only lowercase ASCII letters, digits, `!`, `#`, `$`, `&`, `^`, `_`, `.`, `+`, or `-`; parameters, whitespace, and every other byte are forbidden. The schema deliberately does not enumerate the two supported values. A string that fails this lexical grammar is `E_ENVELOPE_MALFORMED`; a lexically valid string that is not the exact value required at that index position is `E_PAYLOAD_TYPE`. After canonical base64 decoding and strict JSON parsing, the verifier semantically dispatches the two supported values to `statement.schema.json` or `handoff.schema.json`; standard JSON Schema content keywords do not perform decoding or dispatch.
- The DSSE signature MUST cover the DSSE pre-authentication encoding of `payloadType` and the exact decoded `payload` bytes.
- v0.2 uses the DSSE v1 wire protocol. PAE is the byte concatenation `"DSSEv1" SP decimal_byte_length(payloadType) SP payloadType SP decimal_byte_length(payload) SP payload`, where `SP` is byte `0x20`, lengths are base-10 ASCII with no leading zeros except that the one-digit spelling `0` is valid for zero length, `payloadType` is UTF-8, and `payload` is the exact decoded byte sequence.
- Envelope `payload` and signature `sig` values MUST use RFC 4648 standard base64 with required padding and no whitespace. After decoding, re-encoding with canonical RFC 4648 rules MUST reproduce the exact input string; nonzero unused pad bits and every alternate spelling are rejected. An Ed25519 `sig` decodes to exactly 64 raw signature bytes.
- Every DSSE envelope in v0.2 MUST contain at least one signature entry. An empty `signatures` array fails transport validation with `E_ENVELOPE_MALFORMED`, not the generic `E_CORE_SCHEMA`.
- Verifiers MUST reject duplicate JSON object keys in statements, manifests, profiles, policies, and bundles.
- Producers SHOULD serialize deterministically for reproducibility, but verifiers MUST verify exact payload bytes and MUST NOT reserialize before signature verification.

The core repository MUST vendor or checksum-pin the exact DSSE v1 protocol, in-toto Statement v1 schema, RFC 8032 Ed25519, RFC 8410 Ed25519 SubjectPublicKeyInfo and PKCS#8 encoding, RFC 5280 DER rules as incorporated by RFC 8410, JSON Schema Draft 2020-12 meta-schemas, RFC 8785 JCS, and Unicode 15.0 data used by conformance. It MUST publish positive and negative interoperability vectors for PAE, base64, SPKI/key IDs, signatures, strict JSON, and schema resolution. This specification's rules win if a generic library accepts a looser encoding.

Makoto's in-toto/DSSE interoperability claim is deliberately limited to the outer in-toto Statement v1 and DSSE v1 wire formats, PAE, payload parsing, and standard cryptographic primitives. It does not promise that arbitrary foreign envelopes satisfy the narrower Makoto profile, key, graph, or policy contract. A conforming v0.2 verifier may intentionally reject foreign key-ID conventions, unsupported co-signature shapes, non-Ed25519 policy keys, multiple digest algorithms on subjects, extension predicate semantics, or any otherwise valid in-toto/DSSE feature outside the closed v0.2 subset. Documentation MUST say “parseable outer format,” not imply drop-in policy or semantic compatibility with every in-toto implementation.

### 10.2 Digests

- v0.2 MUST support SHA-256 and MUST use lowercase hexadecimal encoding in JSON digest objects.
- Artifact digests are calculated over exact bytes from byte zero through end-of-file.
- Statement digests are calculated over exact decoded DSSE payload bytes.
- Schema digests are calculated over exact schema-resource bytes.
- SHA-256 is not domain-separated at the hash-function level. Artifact, statement, schema, policy, and manifest digests acquire their meaning from the typed field and payload/schema context that contains them. An implementation MUST NOT use a bare digest as an untyped cross-domain object lookup; it must require the expected object class and, for DSSE payloads, the expected `payloadType` before interpreting bytes.
- Text newline conversion, JSON key sorting, Unicode normalization, decompression, and format conversion all change the artifact unless a transformation explicitly produces and attests the changed bytes.
- Unknown digest algorithms MUST fail closed when used by a critical check.

Exact-byte hashing is intentional. A universal “logical data” canonicalization would introduce format-specific ambiguity and attack surface, and no single canonicalization can cover JSON, CSV, Parquet, archives, models, and media. Producers SHOULD make serialization, row ordering, compression, newline handling, and transfer encoding deterministic before attestation. A transport that changes bytes has produced a different artifact and needs a new attested transformation. Dataset manifests, defined in Section 12.5, avoid inventing a directory-hashing convention for partitioned data.

The digest object is:

```json
{ "sha256": "64 lowercase hexadecimal characters" }
```

The v0.2 digest object contains exactly one member named `sha256`; all other members are rejected with closed-object schema validation. The enclosing field shape can be versioned later to add algorithms without ambiguity.

Adding or replacing a required digest algorithm changes protocol validation semantics and therefore requires a new versioned schema and predicate identifier. A future version may permit multiple algorithms during a transition, but a v0.2 verifier MUST NOT negotiate or silently substitute another algorithm.

### 10.3 Digital signatures

- DSSE remains algorithm-neutral, but the v0.2 trust-policy schema and reference implementation accept only Ed25519 verification keys. Verification MUST reject noncanonical `S >= L`, noncanonical point encodings, small-order public keys, and small-order `R` values, following the pinned strict vectors rather than permissive library defaults. A non-Ed25519 policy entry is invalid v0.2 consumer configuration and exits 2 before evidence evaluation; future signature algorithms require a versioned policy/schema extension.
- The reference repository MUST label demo keys as insecure test material, store them only under the demo fixture tree, exclude them from every non-demo configuration and package artifact, and fail repository scans if a demo key appears elsewhere. External reuse is outside project control and is never evidence of a Makoto failure.
- Every v0.2 DSSE signature entry MUST contain a `keyid` equal to `sha256:<64 lowercase hex>` over the canonical DER SubjectPublicKeyInfo bytes of its Ed25519 public key. The only accepted SPKI encoding is the 44-byte RFC 8410 DER sequence `302a300506032b6570032100 || 32-byte-public-key`: OID `1.3.101.112`, absent algorithm parameters, a zero-unused-bit BIT STRING, no trailing DER, and no alternate encoding. Policy `publicKey` is canonical RFC 4648 padded base64 of exactly those 44 DER bytes. The verifier MUST recompute the identifier for every configured key; a policy map key that differs from the recomputed identifier is invalid consumer configuration with exit 2. Evidence lookup uses exact `keyid` matching and MUST NOT trial-verify against unrelated keys.
- Strict Ed25519 verification uses the following single variant. Let `p = 2^255 - 19` and `L = 2^252 + 27742317777372353535851937790883648493`. Decode public key `A` and signature point `R` from their 32-byte RFC 8032 compressed encodings: interpret the low 255 bits as little-endian `y`, require `y < p`, recover an Edwards25519 `x`, reject a nonsquare, reject `x = 0` with sign bit 1, and require re-encoding the recovered point to reproduce the exact input bytes. Require `A` and `R` to be nonidentity prime-order points by checking `[L]A = identity` and `[L]R = identity`; any torsion component or small-order point fails. Interpret the final 32 signature bytes as little-endian `S` and require `S < L`. Compute the 64-byte `SHA-512(R-encoding || A-encoding || message)` digest, interpret that complete digest as one unsigned little-endian integer, reduce it modulo `L` to obtain `h`, and accept only when the Edwards-group equation `[S]B = R + [h]A` holds. No cofactored equation, ZIP-215 relaxation, alternate point decoding, or library-default variant is accepted. Point/encoding/scalar/equation failures all produce `E_SIGNATURE_INVALID` for evidence and invalid configuration during policy-key preflight for `A`. In this paragraph, `message` is exactly the DSSE PAE byte sequence from Section 10.1 for the envelope's decoded payload type and payload bytes, never the raw payload alone.
- A `keyid` identifies a verification key; it is not an authorization decision or human identity.
- A verifier MUST validate every signature it relies on and MUST apply consumer trust policy after cryptographic verification.
- At least one authorized valid signature is required per statement in the reference policy. The policy format permits higher thresholds.
- A structurally malformed signature entry, missing/invalid `keyid`, noncanonical base64, wrong decoded signature length, or duplicate `keyid` fails at Step 2 with `E_ENVELOPE_MALFORMED`; no signature record is emitted for an entry without a usable key ID. A structurally valid signature claiming a configured key that fails strict cryptographic verification fails at Step 5 with `E_SIGNATURE_INVALID`. A structurally valid signature from an unknown key cannot be named by policy because every authorized key must be configured; it does not count toward a threshold and produces `W_SIGNATURE_UNKNOWN`, not an independent denial. Envelopes are never partially repaired.

For every transport-invalid envelope, “never partially repaired” means no per-signature report record is emitted at all, even when some entries have usable key IDs or valid-looking bytes. The verifier performs no Step 5 cryptographic work on that envelope; the always-present `handoff.signatures` array is empty for an invalid handoff, and an invalid attestation appears only in `unindexedEnvelopes` rather than contributing statement-signature records. Structurally enumerable raw signature-array entries still count toward `signaturesTotal` and `maxSignaturesTotal` as defensive resource accounting, but contribute zero to `signaturesChecked` and `signaturesValid`. Duplicate usable key IDs, one malformed entry beside valid-looking entries, and an empty signature array all follow this same empty-detail rule. Phase 0 pins report and budget vectors for each case.
- A conforming Makoto producer, CLI, demo generator, and website build MUST never copy private signing-key bytes into an attestation, bundle metadata, log, command output, or published website asset. This is a tooling/producer obligation, not a verifier claim to content-scan arbitrary user artifact bytes or unreferenced files.

The strict point checks explicitly require `A != identity` and `R != identity` in addition to `[L]A = identity` and `[L]R = identity`; the identity encoding is rejected before the signature equation. Phase 0 vectors include identity `A` and identity `R`.

### 10.4 Lexical rules

- Strict JSON parsing MUST reject unpaired escaped Unicode surrogates. Protocol strings represent Unicode scalar values.
- Every protocol, policy, catalog, schema, index, and report JSON byte sequence MUST be UTF-8 without a byte-order mark. JSON depth counts the root array or object as depth 1 and increments once for each nested array or object; scalar members do not add depth. Number-token character and exponent bounds are enforced lexically before numeric conversion on input evidence/configuration as defined in Sections 14 and 15. Consumer `maxJsonNumberChars` and `maxJsonExponentMagnitude` never constrain verifier-generated report numbers; the report schema already restricts JSON integers to the RFC 8785 interoperable range and represents larger exact values as bounded decimal strings. Report generation is governed by `maxReportBytes` and its fixed minimum, so a valid consumer policy cannot make output impossible merely by selecting a small input-number limit.
- An `absolute URI` is an RFC 3986 URI with a nonempty scheme. HTTPS extension keys require lowercase `https` and an authority; URN keys conform to RFC 8141. A `URI-reference` follows RFC 3986 and may be relative only where the field explicitly permits it. URI comparisons elsewhere in this specification are exact JSON-string comparisons unless a field says otherwise.
- Everywhere in v0.2, a `canonical lowercase UUID` means exactly `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`. The nil UUID is allowed and version/variant bits are not constrained unless a field explicitly adds a rule.
- `event.id` is either an absolute URI or a canonical lowercase UUID string matching exactly `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`. The nil UUID is allowed; version and variant bits are not constrained in v0.2. For every v0.2 URI-or-UUID field, including `event.id` and `bundleId`, any value whose case-insensitive prefix is `urn:uuid:` MUST use the exact lowercase prefix `urn:uuid:` followed by that exact lowercase UUID grammar; an uppercase or mixed-case prefix/value is invalid and cannot bypass UUID lexical rules through the generic absolute-URI branch. Graph uniqueness compares complete event-ID JSON strings exactly: a bare UUID and `urn:uuid:` plus the same UUID are distinct identifiers. UUID uniqueness, not UUID version semantics, is enforced.
- v0.2 media types are lowercase RFC 6838 type/subtype tokens without parameters.
- Protocol timestamps use the RFC 3339 profile `YYYY-MM-DDTHH:MM:SS[.fraction]Z`: UTC `Z` only, four-digit year `0001` through `9999`, required seconds, one to nine fractional digits when present, valid proleptic-Gregorian dates, and no leap-second value `60`. Comparisons use the represented instant; generated report timestamps use `Z` and trim trailing fractional zeros.
- A control scalar means Unicode General Category `Cc`, exactly U+0000–U+001F and U+007F–U+009F.
- Every identifier or human label in Makoto-owned protocol, policy, catalog, index, and report objects—including event IDs, subject and input names, source and operation URIs/names, profile/resource/rule IDs, media types, extension keys, key IDs, and logical paths—MUST be at most 4096 UTF-8 bytes unless this specification gives that field a smaller bound. Fixed digests, DSSE base64 payload/signature material, human diagnostic messages, JSON Schema contents, and artifact contents use their own fixed or resource-budget bounds instead. An implementation MUST NOT impose a lower private string limit on an otherwise conforming value.

## 11. Normative statement model

### 11.1 Common in-toto statement

Every origin and transformation payload has this outer shape:

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "customers.public.json",
      "digest": { "sha256": "..." }
    }
  ],
  "predicateType": "https://usemakoto.dev/predicate/v0.2/transform",
  "predicate": {}
}
```

Requirements:

- `_type` MUST equal the in-toto Statement v1 URI.
- `subject` MUST contain at least one output artifact.
- Each subject MUST have a non-empty name and SHA-256 digest.
- Each subject `name` MUST be unique within a statement. Repeating one name with a different digest is invalid because graph edges, profile targets, handoff artifacts, and bundle mappings resolve subjects by name.
- Subject names are labels, not trusted filesystem paths. Verifiers MUST use explicit bundle mappings and MUST reject path traversal.
- `predicateType` MAY name a Makoto core or extension predicate, but the v0.2 reference bundle verifier accepts only the core origin and transformation types; consumer policy cannot override missing graph semantics.
- The core statement schema MUST allow extension predicate types without claiming to understand them.

The v0.2 reference verifier has graph semantics only for the core origin and transformation predicates. Another predicate type MAY be parsed and inspected out of band, but every v0.2 bundle verifier MUST reject it when it appears in the manifest statement set or reachable graph with `E_PREDICATE_SEMANTICS_UNSUPPORTED`. Semantic adapters are outside the v0.2 protocol and cannot change a v0.2 bundle decision; a future adapter contract must pin its identity, bytes, authorization, predecessor semantics, and report fields under a new protocol version. An implementation MUST NOT label an extension predicate as authenticated auxiliary evidence, treat it as an origin, or skip it during root discovery.

### 11.2 Common Makoto predicate fields

Origin and transformation predicates share:

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schemaVersion` | string constant `0.2` | yes | Makoto predicate version. |
| `event.id` | URI or UUID string | yes | Producer-selected event identifier; uniqueness is enforced across the verified graph. |
| `event.occurredAt` | RFC 3339 timestamp | yes | Signer-asserted event time; not a trusted timestamp unless policy adds that guarantee. |
| `profiles` | array of profile references | no | Additional schemas to apply. |
| `extensions` | object | no | URI-namespaced extension values. |

Extension keys MUST be absolute HTTPS URIs or URNs. Extension authors SHOULD use namespaces they control; v0.2 has no registry or ownership-proof mechanism, so ownership is operational guidance rather than a verifier decision. Core schemas MUST permit unknown extension keys. Consumers MAY ignore an unknown ordinary extension, but MUST NOT ignore an unknown critical profile.

`event.id` MUST be unique across all reachable statements in one verified graph. Manifest-listed but unreachable statements fail exact-set completeness separately and do not expand this uniqueness scope. Any duplicate among reachable statements, even across different keys or predicate types, fails with `E_EVENT_ID_DUPLICATE`. Producers that merge independently generated graphs must generate UUID/URI identifiers with sufficient collision resistance; there is no global registry.

### 11.3 Origin predicate

Predicate type: `https://usemakoto.dev/predicate/v0.2/origin`

An origin statement records the first Makoto observation of the subject bytes.

```json
{
  "schemaVersion": "0.2",
  "event": {
    "id": "urn:uuid:...",
    "occurredAt": "2026-09-16T16:00:00Z"
  },
  "source": {
    "kind": "https://usemakoto.dev/source/file",
    "uri": "file:fixtures/customers.raw.json",
    "mediaType": "application/json",
    "retrievedAt": "2026-09-16T16:00:00Z"
  },
  "profiles": [],
  "extensions": {}
}
```

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `source.kind` | absolute URI | yes | Machine-readable source category. |
| `source.uri` | nonempty URI-reference string | no | Source locator. It may be omitted or redacted for privacy; an empty string is invalid when the member is present. |
| `source.name` | string | no | Human-readable source name. |
| `source.mediaType` | media type string | no | Media type observed at collection. |
| `source.retrievedAt` | RFC 3339 timestamp | no | Time the producer retrieved or observed the source. |
| `source.version` | string | no | Source-controlled version or revision. |

The origin’s subject digest binds the collected snapshot. A source URI alone never identifies immutable data. An origin has no predecessor field; any predecessor edge in an origin is invalid.

### 11.4 Transformation predicate

Predicate type: `https://usemakoto.dev/predicate/v0.2/transform`

```json
{
  "schemaVersion": "0.2",
  "event": {
    "id": "urn:uuid:...",
    "occurredAt": "2026-09-16T16:01:00Z"
  },
  "operation": {
    "type": "https://example.org/transforms/public-safe-v1",
    "name": "Remove direct identifiers and bucket ages",
    "tool": {
      "name": "makoto-demo-transform",
      "version": "0.2.0",
      "digest": { "sha256": "..." }
    }
  },
  "inputs": [
    {
      "name": "customers.normalized.json",
      "digest": { "sha256": "..." },
      "provenance": {
        "statementDigest": { "sha256": "..." },
        "subjectName": "customers.normalized.json"
      }
    }
  ],
  "profiles": [],
  "extensions": {}
}
```

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `operation.type` | absolute URI | yes | Stable transformation category. |
| `operation.name` | string | no | Human-readable operation description. |
| `operation.tool.name` | string | no | Tool or service name. |
| `operation.tool.version` | string | no | Tool version. |
| `operation.tool.uri` | absolute URI | no | Tool or recipe locator. |
| `operation.tool.digest` | digest | no | Digest of executable, script, image, or recipe when available. |
| `operation.parametersDigest` | digest | no | Digest of exact parameter/configuration bytes when available. |
| `inputs` | array | yes | One or more consumed artifacts and their provenance bindings. |
| `inputs[].name` | string | yes | Input artifact label. |
| `inputs[].digest` | digest | yes | Exact input artifact digest. |
| `inputs[].provenance.statementDigest` | digest | yes | Payload digest of the predecessor statement. |
| `inputs[].provenance.subjectName` | string | yes | Subject in that predecessor that supplied this input. |
| `inputs[].provenance.entryName` | string | no | Relative entry name when the input is one member of a predecessor dataset-manifest subject. |

Input `name` values MUST be unique within the transformation. Complete provenance bindings `(inputs[].name, statementDigest.sha256, subjectName, entryName-or-null, digest.sha256)` MUST also be unique; duplicates fail core validation rather than being collapsed or counted twice. Including the local input name is deliberate: one transformation may consume the same predecessor artifact more than once under distinct role aliases, enabling self-joins and repeated-role inputs while keeping each signed input occurrence unambiguous. For every input, the referenced predecessor and named subject MUST exist.

- When `entryName` is absent, the predecessor subject digest MUST equal the input digest.
- When `entryName` is present, the predecessor subject MUST have a critical core dataset-manifest profile reference, the exact manifest artifact bytes MUST be available to the verifier, the manifest itself MUST match the predecessor subject digest and schema, the named entry MUST exist exactly once, and that entry digest MUST equal the input digest.
- If an entry-based edge cannot be proved because the predecessor manifest bytes are absent, Step 8 dataset-dependency verification fails with `E_DATASET_MANIFEST_REQUIRED`; it is not merely `not_checked`, and Step 9 does not duplicate the failure.

A join has inputs from multiple predecessor statements. A split is represented by multiple subjects in one statement or multiple descendant transformation statements. Bundle file ordering carries no semantic meaning.

`inputs[].provenance.subjectName` MUST exactly match a subject name in the predecessor. `inputs[].name` is the consuming operation’s local alias and MAY differ from the predecessor subject name.

## 12. Profiles and organizational extensibility

### 12.1 Profile reference

```json
{
  "id": "https://schemas.example.com/makoto/customer-public-v1.json",
  "digest": { "sha256": "..." },
  "closureDigest": { "sha256": "..." },
  "target": "artifact",
  "subjectName": "customers.public.json",
  "mediaType": "application/json",
  "critical": true,
  "resources": [
    {
      "id": "https://schemas.example.com/common/identifiers-v1.json",
      "digest": { "sha256": "..." }
    }
  ]
}
```

| Field | Required | Rules |
|---|---:|---|
| `id` | yes | Absolute schema URI. It is an identifier, not permission to fetch over the network. |
| `digest.sha256` | yes | Digest of exact root schema bytes. |
| `closureDigest.sha256` | yes | Digest of the exact root-plus-resource closure descriptor defined below. |
| `target` | yes | One of `statement`, `predicate`, or `artifact`. |
| `subjectName` | for `artifact` | Identifies the statement subject whose actual bytes are validated. |
| `mediaType` | for `artifact` | Signed declaration selecting the supported artifact parser, such as `application/json` or `application/x-ndjson`. |
| `critical` | yes | If true, unresolved or unsupported validation MUST fail. |
| `resources` | yes | Sorted digest-pinned transitive schema resources; an empty array means the root has no non-core external resources. |

`resources` MUST be duplicate-free and sorted by `(id, digest.sha256)` using UTF-8 bytes for the ID and ASCII bytes for the hexadecimal digest. A duplicate or unsorted signed resources array fails containing-statement core validation with `E_CORE_SCHEMA` at Step 4. `closureDigest` is SHA-256 of RFC 8785 JCS bytes, with no trailing LF, for exactly `{"resources":<the complete sorted resources array>,"root":{"digest":<digest object>,"id":<id>}}`. The immutable core catalog is not copied into this descriptor. The verifier MUST recompute and match `closureDigest` before resolving the profile. The root schema and the complete non-core transitive closure are therefore one portable profile identity: retaining the root bytes while changing any dependency changes `closureDigest` and cannot satisfy a pinned requirement.

Every schema resource identifier in v0.2—the profile-reference `id`, every `resources[].id`, every catalog resource `id`, and every schema root `$id`—MUST be an absolute URI with no fragment delimiter at all; both a nonempty fragment and an empty trailing `#` are invalid. The profile-reference/root `$id` strings must match exactly, as must each catalog/resource pair. `$ref` values may contain a fragment because they identify a schema location inside one fragmentless resource ID. This rule applies only to schema-resource identity; source, operation, event, extension, and tool URIs retain their field-specific URI rules. Phase 0 rejects resource IDs ending in `#`, containing `#anchor`, or using percent-encoded spellings as attempted aliases.

Every profile resource MUST declare `$schema` exactly `https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json`. That immutable Makoto dialect meta-schema declares the pinned JSON Schema Draft 2020-12 core, applicator, validation, metadata, content, format-annotation, and unevaluated vocabularies plus required custom vocabulary `https://usemakoto.dev/vocab/v0.2/bounded-pattern`; format assertions are disabled. At load time, before closure traversal or instance evaluation, every profile-owned root and transitive resource MUST validate as a schema against that exact dialect meta-schema. A known keyword with an ill-typed or otherwise meta-schema-invalid value—including a non-string `type`, non-integer `minLength`, or array-form Draft-07 `items`—makes the resource unsupported; it is never passed to a tolerant host validator. Standard Draft 2020-12 `pattern` and `patternProperties` are forbidden in Makoto profile resources. Portable pattern assertions use only the custom `makotoPattern` keyword from the required Makoto vocabulary, so Makoto never changes the semantics of a keyword owned by the standard validation vocabulary. A schema object may contain only keywords defined by those pinned vocabularies plus `$comment`. Only the dialect meta-schema declares `$vocabulary`; profile resources are instances of that dialect and MUST NOT contain `$vocabulary`. Any unknown keyword makes the profile unsupported. The known-but-prohibited keywords `pattern`, `patternProperties`, `$dynamicRef`, `$dynamicAnchor`, and `$vocabulary` also make a profile unsupported rather than schema-invalid. In every unsupported case, a critical, manifest-required, or consumer-required profile fails with `E_PROFILE_UNRESOLVED`; a candidate-only constraint follows the candidate-local unresolved behavior in Section 12.4; and an optional noncritical profile is `indeterminate` with `W_PROFILE_INDETERMINATE`. `E_PROFILE_INVALID` is reserved for a supported, resolved schema evaluated against an instance that does not satisfy it. This mechanical rule replaces host-library guesses about whether a keyword affects validation. A profile MAY use `allOf` to compose the Makoto core schema with internal requirements. Profiles SHOULD add constraints without assigning prose semantics that conflict with Makoto core; the enforceable rule is that core validation always runs independently, and any instance that fails either core or profile validation fails.

In a profile-owned resource, `$schema` is required exactly once at the resource root and is forbidden at every nested schema location; a nested `$schema` is unsupported and produces `E_PROFILE_UNRESOLVED`. Immutable core resources retain their own checked-in dialect declarations under the core exemption.

The profile-dialect meta-schema declares `$schema` exactly `https://json-schema.org/draft/2020-12/schema` and is the only Makoto profile resource permitted to declare `$vocabulary`. Prohibited profile keywords are detected by the separate load-time semantic pass after dialect meta-schema validation, so every implementation classifies them as unsupported even if its general meta-schema engine would ignore an unknown annotation.

Draft 2020-12 meta-validation is fully offline and uses a second, immutable registry that is separate from the Makoto core catalog and every producer-supplied catalog. The registry catalog is `src/makoto/standard-schemas/draft-2020-12/catalog.json`; it is strict JCS plus one LF and contains exactly the following `(id, repository-relative path, sha256, byte length)` entries, sorted by ID UTF-8 bytes. The vendored files are the exact response bodies identified here, with no reserialization or newline conversion:

| ID | Vendored path | SHA-256 | Bytes |
|---|---|---|---:|
| `https://json-schema.org/draft/2020-12/meta/applicator` | `meta/applicator.json` | `bf273b26f9f735b93ece78f2b61b36676e1d122ce78ab37ad5a2e45dfa1ca2b1` | 1560 |
| `https://json-schema.org/draft/2020-12/meta/content` | `meta/content.json` | `a10456605b2b5bb12a1b4dcfc0300f02f54d3e8bb3646bed7724583866627682` | 423 |
| `https://json-schema.org/draft/2020-12/meta/core` | `meta/core.json` | `21f79d143fab1f180245c331e5657057045b36794d41fe151e6e4fed65035299` | 1471 |
| `https://json-schema.org/draft/2020-12/meta/format-annotation` | `meta/format-annotation.json` | `5c79404f831dd905c0f40fefac7c6f3e51bf3729b4a876a5c2020178d97f3bcc` | 342 |
| `https://json-schema.org/draft/2020-12/meta/meta-data` | `meta/meta-data.json` | `c664d438a84d58889c8edecd248ce2f945a4bc0e3b087323b11303dc136abfbe` | 794 |
| `https://json-schema.org/draft/2020-12/meta/unevaluated` | `meta/unevaluated.json` | `fc99f32188da41689a9382af174dd42e8b255e4374965c157b8286556b4ab2bc` | 406 |
| `https://json-schema.org/draft/2020-12/meta/validation` | `meta/validation.json` | `e921c5b79264d3689af01c1af1ffdf692e09f1c45df90a0f08eb7288c9acdeab` | 2735 |
| `https://json-schema.org/draft/2020-12/schema` | `schema.json` | `41da76f5afb7ce062d248f762463a92f7ca47e4e0f905b224ba6afeef91ded0f` | 2452 |

Startup verifies the catalog shape, every file's exact length and digest, and every parsed root `$id` against its catalog ID before any profile is accepted. Missing, extra, or mismatched registry entries are a trusted-tool invariant failure and exit 3. Resolution of these IDs MUST use only this registry and MUST NOT perform network retrieval, consult a host validator's bundled copy, or accept a consumer/producer catalog override. Each distinct standard resource actually reached during one profile's dialect meta-validation is charged once to that evaluation's `maxSchemaBytes` and `maxSchemaResources` using its catalog identity; registry startup verification itself is not charged to producer evidence. These resources remain excluded from the producer-signed profile closure descriptor because the verifier release, not the producer, selects them. Phase 0 compares all eight vendored byte digests and exercises an offline run with DNS/network access disabled.

The table above is the normative v0.2 byte identity even if a later upstream HTTP response changes; an implementation MUST use the table bytes rather than silently refreshing from the URLs. The constants were independently recomputed from the eight HTTPS response bodies on 2026-08-22. Phase 0 MUST retain outside the runtime registry a retrieval-evidence record containing retrieval time, final URL, response byte length, computed SHA-256, and the retrieval command/tool version for each body. A named reviewer who did not vendor or compute the table bytes MUST independently fetch every official URL, recompute every length/digest, and compare that separately captured record with both the table and vendored files; the same role-separation rule applies to every Unicode 15.0.0 input and its release catalog. A mismatch blocks Phase 1 and requires an explicit spec correction before implementation continues; it is never resolved by choosing host-bundled or newly fetched bytes at runtime. This makes the registry self-consistent and auditable without pretending that an unpinned future upstream response authenticates the release.

Trusted meta-schema evaluation supports Draft 2020-12 `$dynamicAnchor` and `$dynamicRef` only inside the checksum-pinned Makoto profile-dialect resource and the eight vendored standard resources; profile-owned and ordinary Makoto core resources still reject those keywords. A trusted resource may declare at most one `$dynamicAnchor` with a given name. Resolution first resolves the `$dynamicRef` URI against the containing fragmentless `$id` exactly as for `$ref` and locates its static target. When its fragment is a plain-name anchor and that static target declares the same `$dynamicAnchor`, the evaluator examines the complete current dynamic resource-scope stack from outermost to innermost and selects the first resource whose visited root declares that name; if none does, it uses the static target. This outermost-wins rule is the Draft 2020-12 dynamic-scope override behavior. JSON Pointer fragments and targets without a matching dynamic anchor always use the static target. Entering any `$ref`/`$dynamicRef` resource target pushes that resource for the target evaluation and pops it afterward; re-entry participates in normal depth/cycle/operation bounds. `$dynamicRef` dispatch charges one schema operation, each examined dynamic-scope entry charges one, and target entry charges normally. Applicable keywords and scope entries use the canonical traversal order below. Phase 0 includes the recursive official meta-schema path, a shadowed outer dynamic anchor that overrides the referenced inner anchor, static fallback, pointer fragment, cycle/depth exhaustion, and operation-boundary traces. Host-library dynamic-scope behavior is never used as an unexamined default.

Standard `pattern` is permitted only while evaluating the checksum-pinned trusted meta-schema resources, never in profile-owned or ordinary Makoto core resources. The complete v0.2 trusted inventory contains exactly decoded patterns `^[A-Za-z_][-A-Za-z0-9._]*$` and `^[^#]*#?$`; the Phase 0 profile-dialect resource MUST introduce no other standard `pattern` value and none of the trusted resources may contain the `patternProperties` keyword. The first predicate accepts a nonempty ASCII string whose first byte is `A`–`Z`, `a`–`z`, or `_` and whose later bytes additionally may be `-`, `0`–`9`, `.`, or `_`; the second accepts any Unicode-scalar sequence containing no `#`, optionally followed by one final `#`. The trusted evaluator implements those two predicates directly with no host regex engine. Dispatch costs one keyword operation; each examined Unicode scalar costs one inner operation through the first failure or end, and the optional final-`#` decision costs one. Any other trusted standard `pattern`, any actual trusted `patternProperties` keyword, or a release-inventory mismatch is a trusted-tool invariant failure and exit 3. Phase 0 pins positive, negative, supplementary-scalar, and operation-boundary vectors for both predicates.

Load-time dialect meta-schema validation is untrusted profile-closure work and MUST execute inside the same bounded profile worker as instance evaluation, under `maxSchemaBytes`, `maxSchemaResources`, `maxSchemaEvaluationDepth`, metadata/schema token and numeric limits, `profileEvaluationTimeoutSeconds`, `profileWorkerMemoryBytes`, and the canonical non-short-circuit traversal. One logical profile evaluation reserves one `maxProfileEvaluations` unit before this meta-validation; validating up to `maxSchemaResources` resources consumes no additional profile-evaluation units. A cached successful meta-validation MAY avoid repeated computation but never changes charged units. Meta-schema invalidity or a prohibited/unknown keyword is `E_PROFILE_UNRESOLVED`; exhaustion is the applicable `E_RESOURCE_LIMIT`; no untrusted schema instance is evaluated in the parent process.

The mandatory dataset-manifest profile defined in Section 12.5 is the sole direct-root exemption to the rule that profile-owned resources declare the Makoto dialect: its root MUST be the exact immutable core `dataset-manifest.schema.json` ID and digest, uses that core resource's generic Draft 2020-12 dialect, and has no non-core resources. Any other direct core-schema root is unsupported. Core resources reached from an organizational profile remain the referenced-core exemption already described.

`contentEncoding`, `contentMediaType`, and `contentSchema` are annotation-only in v0.2 and never change instance validity. `contentSchema` is still traversed at load time as a schema-bearing position so its references must be in the pinned closure and its schema syntax is checked, but it is never entered during instance evaluation or charged as an instance-evaluation branch.

Within one statement, profile references MUST be duplicate-free by `(id, digest.sha256, closureDigest.sha256, target, subjectName-or-null, mediaType-or-null)`. Repeating that tuple fails core schema validation rather than being collapsed or evaluated twice. Every resource ID MUST be unique within one profile closure. Static closure is computed at profile-load time by schema-location traversal, not a raw JSON-property scan. Beginning with the root schema location and its root `$id` already visited, the traversal visits subschemas only in schema-bearing positions defined by the pinned Draft 2020-12 vocabularies: each map value under `$defs`, `properties`, `patternProperties`, and `dependentSchemas`; each array element under `prefixItems`, `allOf`, `anyOf`, and `oneOf`; each single schema value under `items`, `contains`, `additionalProperties`, `propertyNames`, `unevaluatedItems`, `unevaluatedProperties`, `not`, `if`, `then`, `else`, and `contentSchema`; plus any core resource subschema reached by `$ref`. `patternProperties` remains in this generic schema-location traversal solely for the checksum-pinned Draft 2020-12 standard meta-schemas; it is prohibited in every Makoto profile-owned and Makoto core resource. A property named `$ref` inside instance data held by `const`, `enum`, `default`, `examples`, or another non-schema-valued keyword is ignored. At every visited schema location, ordinary `$ref` is resolved under RFC 3986; fragment-only, empty, absolute-root-self, and root-ID-plus-fragment references stay within the already visited root and never add it to `resources`. An external non-core base ID is added once and its resource is traversed recursively; a visited-ID set terminates self/cyclic external references. Immutable core IDs are traversable but excluded from `resources`. The discovered non-core ID set MUST equal the declared `resources` ID set exactly: a missing reachable resource and an unused declared superset resource both make the profile unresolved. Every `$ref` base MUST therefore be closed before instance evaluation begins. Core resource IDs are reserved and cannot be shadowed. Root and transitive resource bytes are strict JSON. Each declared resource's root `$id` MUST equal its pinned `id`; no non-root subschema may contain `$id`, absolute or relative, and reusable locations use ordinary `$anchor` values instead. `$anchor` values MUST be unique within each resource. URI fragments select anchors within already digest-pinned resource bytes and never identify separately hashed bytes. Fragment-only `$ref` and `$anchor` are permitted within the closed set. `$dynamicRef` and `$dynamicAnchor` are rejected as unsupported profile-schema features under the preceding diagnostic rule. Resolution MUST never fall back to ambient registries or network access. Recursive schemas are not invalid merely because their ordinary reference graph contains a cycle, but evaluation remains subject to policy depth and resource budgets. Phase 0 vectors cover ill-typed known keywords, `$ref` inside instance-valued keywords, empty/absolute self-references, root fragments, cyclic external resources, and every known-but-prohibited keyword.

For avoidance of doubt, the preceding historical rationale does not permit `patternProperties` in a Makoto core schema: both profile-owned and ordinary Makoto core resources forbid it. The traversal position remains in the generic trusted meta-schema walker solely because the checksum-pinned Draft 2020-12 standard meta-schemas may use it. Phase 0 marks the profile/core wire position prohibited and the trusted-standard-meta position covered.

The `makotoPattern` schema value MUST be a JSON string; any other schema value makes the profile unsupported. The keyword applies only to string instances: a non-string instance passes this keyword and remains subject to other keywords such as `type`. String values use the following complete regular-language subset with unanchored search behavior. Precedence is quantifier, concatenation, then alternation. `pattern := alternative ("|" alternative)*`; `alternative := quantified+`; `quantified := atom quantifier?`; `atom := literal | "." | "^" | "$" | "(" pattern ")" | character-class`; and `quantifier := "?" | "*" | "+" | "{" n "}" | "{" n "," m? "}"`, where decimal `n` and `m` have no leading zeros except `0`, are at most 1000, and `m >= n`. Empty patterns, alternatives, groups, and classes; nested quantifiers; and nongreedy suffixes are invalid. A character class is `[` followed by optional `^`, then one or more literal/escaped scalar values or ASCII ranges such as `a-z`, then `]`; `^` negates only in that first class position. An unescaped `-` inside a class is always a range operator and never an ordinary literal. Both endpoints of a range MUST be unescaped permitted ASCII class literals and the first code point MUST be less than or equal to the second; a range with either non-ASCII endpoint is invalid, `a-a` is valid and is equivalent to literal `a`, and an escaped atom cannot be a range endpoint. A negated class complements its positive member set over all Unicode scalar values U+0000 through U+D7FF and U+E000 through U+10FFFF. Thus `[^a]` matches control scalars including NUL, LF, and CR when they occur in a valid JSON string; control-scalar restrictions apply to pattern syntax, not to the instance universe. Outside a class, every `. ^ $ * + ? { } [ ] ( ) | \\` metacharacter used literally must be escaped. After JSON-string decoding, the only permitted backslash-derived atoms are `\\`, `\.`, `\^`, `\$`, `\*`, `\+`, `\?`, `\{`, `\}`, `\[`, `\]`, `\(`, `\)`, `\|`, `\-`, `\t`, `\n`, and `\r`; `\-` is valid only in a character class and is invalid outside one. A literal solidus needs no regex escape. `.` matches any Unicode scalar except U+000A and U+000D; `^` and `$` match only the beginning and end of the complete scalar sequence; no multiline or other flags exist. Matching uses Unicode scalar values without normalization and returns true when any substring matches. The reference verifier MUST evaluate this grammar with the following canonical Thompson NFA, not a backtracking host regex engine. Each literal, dot, class, or anchor contributes one consuming/assertion state; concatenation adds none; an alternation of `k` branches adds `k - 1` split states; every source-level or generated `?`, `*`, or `+` fragment adds one split state; `{n}` expands to `n` atom copies, `{n,m}` to `n` required atom copies plus `m - n` generated optional copies, each of which contributes its copied atom states and one split state, and `{n,}` to `n` required atom copies plus one generated starred atom copy contributing its copied atom states and one split state; groups add none; and one terminal match state is added. Compilation MUST reject a decoded pattern whose resulting count exceeds 131,072 states with the applicable profile resource-limit result before instance evaluation. Backreferences, lookaround, inline flags, shorthand classes such as `\w`, Unicode properties, class subtraction, and engine-specific constructs are invalid profile schemas. `format` remains annotation-only and MUST NOT affect allow/deny. This grammar and its conformance vectors, including exponential-backtracking adversarial patterns, not host regex extensions, determine validation. Phase 0 includes state-count vectors at 131,071, 131,072, and 131,073 states, with the last rejected before instance evaluation.

`maxRegexLength` applies independently to each `makotoPattern` keyword occurrence and counts Unicode scalar values in that keyword's decoded JSON string before grammar parsing or NFA expansion. It is not a UTF-8-byte count, UTF-16-code-unit count, aggregate across a resource, or count of the containing JSON escape spelling. Phase 0 has exact 4095-, 4096-, and 4097-scalar vectors under the sample policy value, including a supplementary-plane scalar and an escaped source spelling that decode to the same scalar sequence; the first two enter grammar parsing and the third receives the applicable profile resource-limit result before compilation.

Quantifier semantics follow these exact rules: `?`, `*`, and `+` mean zero-or-one, zero-or-more, and one-or-more repetitions; `{n}` means exactly `n`; `{n,m}` means from `n` through `m` inclusive; and `{n,}` means at least `n` with no finite upper bound. Character-class escaping is independently scoped: inside a class, the outside-class metacharacters `. ^ $ * + ? { } [ ( ) |` are ordinary unescaped literals, while `]`, `-`, and `\\` retain their delimiter/range/escape roles. All examples in this paragraph describe the decoded `makotoPattern` string, not its containing JSON source. Thus `[a.]`, `[a+]`, and `[{]` are valid; `[a-]`, `[-a]`, `[a-b-c]`, and `[а-я]` are invalid dangling, chained-range, or non-ASCII-range forms under left-to-right tokenization; and `[a\-]` is valid and matches `a` or `-`. The JSON source spelling of that last decoded pattern is `"[a\\-]"`. Phase 0 vectors cover each quantifier spelling and all eight class examples at both decoded-pattern and strict-JSON encoding layers. Zero bounds are deliberate: decoded `a{0}` and `a{0,0}` are valid and match the empty string, while `a{0,}` is equivalent to `a*`; the ban on an empty pattern or alternative is syntactic and does not forbid a well-formed expression whose language contains the empty string. The exact counts are: `a{0}` = 1 state, `a{0,0}` = 1 state, and `a{0,}` = 3 states (one copied `a` state, one generated star split, and one terminal match state). Phase 0 includes explicit positive/search/anchored vectors for all three zero-bound forms. Phase 0 also includes decoded and strict-JSON vectors for anchor-only `^`, `$`, and `^$`, plus the root-alternative case `a|^b`; all are valid under the root-alternative anchor-placement rules.

In that grammar, an outside-class `literal` is one Unicode scalar other than a control scalar or the unescaped metacharacters listed above; U+0009, U+000A, and U+000D are the sole control-scalar exceptions and are valid only as the decoded `\t`, `\n`, and `\r` atoms (strict JSON necessarily escapes them in schema bytes). An inside-class literal instead permits every non-control scalar except unescaped `]`, `-`, and `\\`; the decoded tab/LF/CR exceptions remain allowed only through their escapes. A quantifier may apply only to a literal, dot, character class, or group whose entire descendant syntax tree contains no quantifier; therefore `(a*)+` is invalid while `a*`, `[0-9a-f]{20}`, and `(ab)+` are valid. Anchors are zero-width atoms that may not be quantified: `^` may appear only as the first atom of an alternative at the root pattern level and `$` only as its last atom, so `^*`, `a^b`, `a(^b)`, and `$+` are invalid. These semantic well-formedness checks occur when the profile schema is loaded.

For `$ref`, resolve the reference with RFC 3986 Section 5.2 against the exact containing resource `$id`. The resulting absolute base URI is compared as an exact JSON string with catalog resource IDs; scheme/host case, percent encodings, and default ports are not normalized beyond the RFC 3986 reference-resolution algorithm. A fragment selects an ordinary `$anchor` or JSON Pointer within those already pinned bytes. Its target MUST be the root or a boolean/object schema location reached by the load-time schema-bearing-position traversal and validated by the applicable meta-schema. A pointer into `const`, `enum`, `default`, `examples`, or any other unvisited instance-valued/non-schema location is deterministically unsupported and produces `E_PROFILE_UNRESOLVED` before instance evaluation. Any reference whose resolved base URI is absent from the declared profile closure or immutable core catalog is unresolved; ambient registries and network fallback are forbidden. Phase 0 resolution vectors include mixed-case URI schemes and hosts, percent-encoding distinctions, and a pointer into a non-schema location; exact string identity after RFC 3986 resolution remains authoritative.

Profile-owned root and transitive resources use the Makoto profile dialect. Immutable core-catalog schemas are the sole exemption: each keeps its declared generic Draft 2020-12 dialect and is evaluated under that dialect when referenced from `allOf`. Makoto v0.2 core schemas MUST NOT use standard `pattern` or `patternProperties`; protocol lexical checks remain semantic verifier rules so no host-regex dialect can affect core validity. A profile cannot cause a core resource to inherit the profile dialect or shadow its `$schema`.

`critical` is an explicit boolean chosen by the producer for that profile reference. It means the producer considers successful resolution and validation necessary to interpret the evidence. It does not let the producer weaken consumer requirements: a trust policy MAY require an artifact profile by ID, digest, subject name, and media type even if the producer omits it or marks it noncritical. Consumer `requiredProfiles` are restricted to artifact targets in v0.2 and bind to final handoff artifacts as defined in Section 14; an intermediate same-named subject cannot satisfy them. An ordinary value under `extensions` has no criticality flag; requirements that must fail closed belong in a profile.

When `target` is `artifact`, `subjectName` and `mediaType` MUST be structurally present and signed inside the containing statement; omission is `E_CORE_SCHEMA`. When target is `statement` or `predicate`, both fields are forbidden. After the containing statement has passed core validation, an artifact `subjectName` MUST match one subject; zero matches fail with `E_PROFILE_TARGET_MISSING`. Multiple matches cannot reach this check because duplicate subject names already fail core validation. The signed `mediaType`, not a filename or unsigned bundle index, selects the parser.

Profiles can remain private. The URI need not resolve publicly, and the schema need not be included in a handoff when producer and consumer already share an authenticated catalog. The receiver must possess the exact bytes matching the declared digest.

Pattern control escaping is byte-for-byte unambiguous. JSON source `"\t"`, `"\n"`, or `"\r"` decodes to an actual control scalar and is invalid `makotoPattern` syntax. The valid tab/newline/carriage-return atoms are decoded backslash-plus-letter sequences, whose JSON source spellings are `"\\t"`, `"\\n"`, and `"\\r"` respectively. No actual control scalar appears in the parsed pattern syntax tree.

### 12.2 Resolution and network rules

- Verification MUST resolve schemas by `(id, digest)`, not by URI alone.
- The reference verifier MUST use a local schema catalog by default.
- The v0.2 reference verifier MUST perform no network schema retrieval. Hosted schemas are a distribution convenience: users or tools download them separately, verify their published digest, and place them in a local catalog before verification. A future network resolver requires a separate SSRF, TLS, proxy, redirect, decompression, timeout, and address-pinning contract.
- Every external `$ref` reachable from a critical profile MUST be present in the profile’s digest-pinned resource set or in the immutable Makoto core catalog.
- An unknown or unavailable critical profile is a verification failure.
- An unknown noncritical profile produces a warning and an `indeterminate` profile result, never a silent pass.
- The default trust policy does not turn an unknown noncritical profile into an overall denial. A trust policy that requires that exact profile `(id, digest, closureDigest, target, subjectName, mediaType)` does deny it. Consumer-required profiles MUST pin both root and closure digests and MUST NOT accept a producer-selected schema merely because it reuses a familiar URI. This preserves optional extensibility without letting a producer omit or substitute a consumer requirement.

### 12.3 Schema catalog

The schema catalog is a local, strict JSON document conforming to `catalog.schema.json`:

```json
{
  "version": "0.2",
  "resources": [
    {
      "id": "https://schemas.example.com/makoto/customer-public-v1.json",
      "digest": { "sha256": "..." },
      "path": "schemas/customer-public-v1.json"
    }
  ]
}
```

- The tuple `(id, digest.sha256)` MUST be unique.
- `path` is relative to the catalog file’s directory and MUST resolve within that directory tree.
- Absolute paths, invalid logical grammar, `..` traversal, symlink/hard-link escape, normalized collisions, duplicate paths, containment failure, and non-regular files are path-safety failures using `E_BUNDLE_UNSAFE_PATH` for a bundle catalog or invalid consumer configuration during preflight. The reference implementation MUST open catalog and bundle files relative to an already-open root directory without following symlinks and MUST validate the opened file descriptor, not rely on a check-then-open path test. `E_CATALOG_INVALID` is reserved for an absent declared bundle catalog or declared catalog-resource target, or for a safely opened catalog's structural schema, duplicate tuple, resource digest, `$id`, or core-shadowing failure.
- The verifier MUST read the resource bytes, verify their digest, parse them strictly, and confirm that the schema’s `$id` equals the catalog `id` before use.
- For a bundle catalog or declared schema resource, ordinary strict-JSON syntax/UTF-8/BOM/scalar/token failure uses `E_JSON_INVALID` at Step 4 and a duplicate key uses `E_JSON_DUPLICATE_KEY` at Step 4. Once strict parsing succeeds, catalog shape/tuple/digest/ID/shadowing failures use `E_CATALOG_INVALID`; a parsed schema resource that is not a supported profile schema fails through the applicable profile-resolution rule when selected.
- A catalog is a resolver, not a trust root. It need not be signed because each referenced schema is pinned either by consumer trust policy or, for producer-selected profiles, by authenticated producer evidence. Producer authentication does not turn a producer-selected schema into a consumer requirement.
- The reference verifier MUST automatically include the immutable Makoto v0.2 core catalog. A user catalog may repeat an exact core `(id, digest)` only when verified bytes are identical, in which case the duplicate is ignored; the same core ID with any other digest is invalid catalog configuration/evidence and cannot shadow or create a parallel core resource.
- Catalog entries MAY contain private identifiers and SHOULD NOT be logged beyond the minimum error context.

### 12.4 Validating actual data contents

Makoto metadata schemas and data-content schemas are separate.

- `target: statement` validates the decoded in-toto statement.
- `target: predicate` validates only the predicate object.
- `target: artifact` validates actual subject bytes.

The v0.2 reference verifier MUST support `target: artifact` when the signed profile reference has canonical media type `application/json` or a lowercase `application/*+json` subtype. v0.2 profile media types MUST be lowercase and contain no parameters. The verifier parses the exact bytes already checked by digest using strict RFC 8259 JSON: duplicate object names, invalid UTF-8, a byte-order mark, non-finite numbers, and nonstandard tokens are rejected. JSON numbers are interpreted as exact mathematical values: a finite JSON number with decimal coefficient `c` and base-10 exponent `e` denotes exactly `c x 10^e`; equality and `multipleOf` operate on reduced arbitrary-precision rational values, so `1`, `1.0`, and `1e0` are equal and `-0` equals `0`. No binary floating-point conversion may affect validation. Invalid JSON fails with `E_ARTIFACT_FORMAT` before schema evaluation.

The verifier MUST also support finite newline-delimited JSON with signed media type `application/x-ndjson`. Bytes are split on LF (`0x0a`); one CR (`0x0d`) immediately before an LF is removed from that line. A whitespace-only line contains only JSON whitespace bytes space (`0x20`) and tab (`0x09`) after that CR handling; those lines and the empty segment after a final LF are ignored. A lone CR is not a line separator. Every remaining line MUST be UTF-8 without a byte-order mark and is one JSON instance validated independently against the referenced profile. A final nonempty segment without LF is one line, and `maxNdjsonLineBytes` counts all bytes in that segment. A file with zero instances fails with `E_ARTIFACT_FORMAT`. Monolithic JSON artifacts likewise MUST be UTF-8 without a byte-order mark. All artifact profiles targeting one statement subject MUST declare the same canonical media type. For an ordinary artifact, profile-to-profile conflict and mismatch between optional manifest `artifacts[].mediaType` and the signed profile media type are evaluated at Step 13 before parsing. For a dataset-manifest subject, Step 8 compares the mandatory core profile media type, every other signed artifact-profile media type on that subject, and any final manifest media hint before parsing. Each signed profile participating in a disagreement receives `validation: "fail"`; the dataset subject is not parsed; and Step 8 emits `E_PROFILE_INVALID` with `graph-dependency-artifacts` ownership. This Step 8 result is final and Step 13 reuses it without rewriting any cached profile state. Step 11 never owns media-type disagreement. A malformed line fails with `E_ARTIFACT_FORMAT`; a parsed instance that violates the schema fails with `E_PROFILE_INVALID`. v0.2 does not define unbounded stream verification merely by supporting a finite NDJSON file.

`maxNdjsonLineBytes` is checked on every physical line segment before CR removal, whitespace-only classification, or JSON parsing. An over-limit whitespace-only line therefore returns the applicable resource-limit result; it is not ignored. Only an in-limit segment may then be classified blank and consume zero profile-evaluation units. Phase 0 pins blank lines at limit minus one, limit, and limit plus one, including CRLF.

One NDJSON profile record is processed fail-fast in ascending one-based physical line number after the exact blank-line rule above. Blank lines consume no `maxProfileEvaluations` unit and do not increment the zero-based nonblank `instanceIndex`. For each nonblank line, reserve its evaluation unit, strict-parse it, and, only if parsing passes, evaluate the schema. The worker stops at the first non-pass outcome: malformed bytes/JSON return `invalid` with `E_ARTIFACT_FORMAT`; a parsed schema-invalid instance returns `invalid` with `E_PROFILE_INVALID`; and any local or aggregate resource exhaustion returns `resource_limit`. No later line is opened, parsed, charged, or inspected, so an early schema-invalid line followed by potential exhaustion, an early invalid instance followed by malformed JSON, and multiple possible line failures all have the first physical-line outcome. Diagnostic context contains both `lineNumber` and `instanceIndex`; token count includes committed tokens through that first failure. A worker returns one result for the whole profile, and no bounded per-line result array crosses IPC. Phase 0 covers blank-line offsets and each mixed-failure ordering in both directions.

Trust policy MUST set `maxArtifactValidationBytes`; no value is implicit. The example policy selects 100 MiB, and the immutable bootstrap ceiling is 1 GiB per artifact for structured parsing and profile validation. This ceiling does not limit streaming digest verification of a larger opaque artifact. Exceeding the policy limit or ceiling fails a required artifact profile with `E_RESOURCE_LIMIT`. An optional noncritical artifact profile becomes `indeterminate` with `W_ARTIFACT_VALIDATION_LIMIT`. NDJSON MAY be validated incrementally within per-line and total-byte limits. The verifier MUST NOT load an unbounded document tree into memory.

Metadata profile evaluation occurs only after the containing statement is cryptographically verified and at least one selected authorization rule has already met its distinct-key threshold, creating a candidate rule. A manifest-listed statement with no such candidate retains its signed profile-reference records, but each has `resolution: "skipped"`, `validation: "skipped"`, and `prerequisiteChecks: ["authorization-thresholds"]`; final authorization supplies the denial. Eligible profile records have an empty `prerequisiteChecks` array. If at least one eligible metadata-profile record exists, the base evaluation aggregate ignores ineligible records and is `pass` when every eligible globally required evaluation passes and no eligible evaluated signed claim is false; the candidate-only aggregation carve-out below then overrides that base to `fail` when no candidate authorizes because its unresolved/resource constraint failed. If signed metadata-profile records exist but every one is threshold-ineligible, the top-level `metadata-profiles` check is `skipped` with `prerequisiteChecks: ["authorization-thresholds"]`; if the complete applicable metadata-profile population is empty, it is `not_checked` with an empty prerequisite array. Reachability is not a Step 7 eligibility condition: metadata profiles on an authorized manifest-listed statement are evaluated before Step 9 even if that statement later proves unreachable, and those records and diagnostics remain effective while Step 11 separately denies exact-set completeness. Evaluation remains resource-bounded: policy MUST limit total schema bytes, schema-resource count, schema-evaluation depth, regular-expression length, worker memory, and wall-clock evaluation time. The reference verifier MUST evaluate profiles in a terminable worker boundary so a pathological schema or regular expression cannot wedge the parent verifier; exceeding a bound produces `E_RESOURCE_LIMIT` for a globally required or producer-critical profile, a candidate-local rule failure for a candidate-only constraint, `W_ARTIFACT_VALIDATION_LIMIT` for an optional artifact profile, or `W_PROFILE_RESOURCE_LIMIT` for an optional statement/predicate profile.

A reachable critical artifact-target profile requires the exact target artifact bytes, even for a historical statement; absence fails with `E_ARTIFACT_MISSING`. When bytes for an otherwise optional historical artifact are absent, Step 12 emits exactly one `W_HISTORICAL_ARTIFACT_NOT_CHECKED` per absent artifact identity, owned by `artifact-bytes`, regardless of how many noncritical profiles target it; the corresponding Step 13 noncritical profile validations are `not_checked` and emit no second warning. A consumer `requiredProfiles` entry upgrades the matching reference to mandatory validation regardless of the producer's `critical` value.

Profile outcomes are fixed:

| Profile status | Unresolved, unsupported, missing schema/closure bytes, or resource limit | Resolved and instance invalid | Resolved and valid |
|---|---|---|---|
| Producer `critical: true` | `fail`, overall `deny` | `fail`, overall `deny` | `pass` |
| Producer `critical: false`, not otherwise required | profile `indeterminate` or `not_checked` with warning; overall may still `allow` | `fail`, overall `deny` because the signed claim is false | `pass` |
| Required by signed handoff manifest | `fail`, overall `deny` | `fail`, overall `deny` | `pass` |
| Globally required by consumer `requiredProfiles` | `fail`, overall `deny` | `fail`, overall `deny` | `pass` |
| Required only by one candidate authorization rule | that candidate fails; another candidate may authorize | `fail`, overall `deny` because the evaluated producer-signed claim is false | that candidate passes |

Manifest and global consumer `requiredProfiles` requirements upgrade the matching signed reference regardless of producer criticality. Candidate-rule digest constraints are candidate-local only when resolution, support, or resource availability prevents the candidate from establishing its requirement: that candidate is disqualified, while another candidate may authorize. Producer criticality remains global even when the same reference is also candidate-local. For a producer-critical, manifest-required, globally consumer-required, or currently evaluated candidate-required profile, unsupported artifact media maps to `E_ARTIFACT_FORMAT`, unresolved or unsupported schema resources to `E_PROFILE_UNRESOLVED`, resource exhaustion to `E_RESOURCE_LIMIT`, and an invalid evaluated instance to `E_PROFILE_INVALID`; candidate-only unavailability is placed in top-level `errors` only if no alternative candidate authorizes the statement. A parsed and evaluated producer-signed profile that violates its schema always uses `E_PROFILE_INVALID` and denies because the signed claim is false, independently of candidate selection. For an otherwise optional noncritical profile, unsupported media or unresolved resources produce `W_PROFILE_INDETERMINATE`; resource exhaustion produces `W_ARTIFACT_VALIDATION_LIMIT` for artifact targets and `W_PROFILE_RESOURCE_LIMIT` for statement or predicate targets. These warnings accompany `indeterminate` or `not_checked` status and are not placed in `errors`.

Per-profile fields and aggregate checks are deterministic:

| Condition | `resolution` | `validation` | Aggregate metadata/artifact-profile check |
|---|---|---|---|
| Resolved and valid | `pass` | `pass` | Remains `pass`. |
| Required unresolved/unsupported | `fail` | `skipped` with profile-local `resolution` prerequisite | `fail`; deny. |
| Optional noncritical unresolved/unsupported | `indeterminate` | `skipped` with profile-local `resolution` prerequisite | Aggregate remains `pass` with warning. |
| Required unsupported artifact media | `pass` when schema closure resolution completed | `fail` | Artifact-profile aggregate is `fail` with `E_ARTIFACT_FORMAT`. |
| Optional noncritical unsupported artifact media | `pass` when schema closure resolution completed | `indeterminate` | Aggregate remains `pass` with `W_PROFILE_INDETERMINATE`. |
| Media conflict; closure resolves | `pass` | `fail` with empty prerequisites | Artifact-profile aggregate is `fail` with `E_PROFILE_INVALID`. |
| Media conflict; closure is unresolved or unsupported | Required/critical: `fail`; optional noncritical: `indeterminate` | `fail` with empty prerequisites because the signed media contradiction was evaluated independently | Aggregate is always `fail` with `E_PROFILE_INVALID`; additionally emit the normal required resolution error or optional warning. |
| Media conflict; per-profile local limit prevents resolution | Required/critical: `fail` or `skipped` at the exact failing phase; optional noncritical: `indeterminate` or `skipped` | `fail` with empty prerequisites | Aggregate is always `fail` with `E_PROFILE_INVALID`; additionally emit exactly the normal local resource diagnostic/warning for work that actually started. |
| Required per-profile local resource limit | `pass` if resolution completed, otherwise `fail` | `fail` or `skipped` at the failing phase | `fail`; deny. |
| Optional noncritical per-profile local resource limit | `pass` if resolution completed, otherwise `indeterminate` | `indeterminate` or `skipped` | Aggregate remains `pass` with target-specific warning; later canonical profiles still run. |
| Invocation-wide profile/evidence aggregate exhaustion before closure begins | `skipped` | `skipped` | One global `E_RESOURCE_LIMIT`; owning aggregate is `fail`, this and later canonical profiles are skipped, and decision denies regardless of criticality. |
| Invocation-wide profile/evidence aggregate exhaustion during closure/resolution | Required/critical: `fail`; optional noncritical: `indeterminate`; already-completed resolution remains `pass` | `skipped` unless validation had already completed | One global `E_RESOURCE_LIMIT`; owning aggregate is `fail`, later canonical profiles are skipped, and decision denies regardless of criticality. |
| Invocation-wide profile/evidence aggregate exhaustion during parsing/validation | Completed resolution remains `pass` | Required/critical: `fail`; optional noncritical: `indeterminate`; a completed validation remains its completed value | One global `E_RESOURCE_LIMIT`; owning aggregate is `fail`, later canonical profiles are skipped, and decision denies regardless of criticality. |
| Optional target bytes absent | `skipped` | `not_checked` with `artifact-bytes` prerequisite | Aggregate remains `pass` with exactly one historical warning per absent artifact identity. |
| Required target bytes absent or any target digest failed | `skipped` | `skipped` with `artifact-bytes` prerequisite | Artifact-profile aggregate is `skipped`; artifact `profileStatus` is `skipped`; Step 12 artifact error already denies. |
| Supported media but malformed JSON/NDJSON, regardless of criticality | `pass` | `fail` | `fail` with `E_ARTIFACT_FORMAT`; deny because the signed validation target could not be evaluated as declared. |
| Parsed instance schema-invalid, regardless of criticality | `pass` | `fail` | `fail` with `E_PROFILE_INVALID`; deny. |

Target-artifact byte absence is not governed by the first table's closure-availability column. Required target absence follows the later per-profile table: resolution and validation are skipped behind `artifact-bytes`, Step 12 owns `E_ARTIFACT_MISSING`, and the existing artifact-byte denial is not duplicated as a profile failure. Optional historical target absence also takes byte-absence precedence: the verifier does not resolve its schema closure, records `resolution: "skipped"`, `validation: "not_checked"`, and `prerequisiteChecks: ["artifact-bytes"]`, and emits only the single `W_HISTORICAL_ARTIFACT_NOT_CHECKED` for the artifact identity even if the unavailable closure would independently have warned.

The local/aggregate distinction is closed. Per-profile local limits are `maxSchemaBytes`, `maxSchemaResources`, `maxSchemaEvaluationDepth`, `maxSchemaOperations`, `maxRegexLength`, the immutable 131,072 compiled-`makotoPattern`-state ceiling, `maxArtifactValidationBytes`, `maxNdjsonLineBytes`, `profileEvaluationTimeoutSeconds`, and `profileWorkerMemoryBytes`; exhausting one cannot consume another profile's remaining invocation allocation. The compiled-state ceiling uses the same required/critical error versus optional noncritical target-specific warning behavior as another local schema/regex limit. Invocation-wide evidence-work aggregates are `maxMetadataBytes`, structured-artifact invocation tokens, `maxProfileEvaluations`, cumulative active-worker time, and the artifact/snapshot/signature totals defined in Section 15. Exhausting one is a fatal completeness failure because later required work may be prevented and uses the phase-total table above; optional warning behavior applies only to a local limit when later canonical work can still proceed. `maxDiagnostics`, `maxReportRecords`, and `maxReportBytes` are exclusively Step 14 admission limits: they never stop profile/evidence work, never skip a later profile, and use only the Section 15 two-pass report-admission rule. Candidate-local suppression never hides aggregate evidence exhaustion.

Media disagreement is the sole v0.2 condition in which `validation: "fail"` is final even when `resolution` is not `pass`: the verifier can prove the signed parser contracts contradictory without schema bytes. After detecting the conflict from signed references and any manifest hint, it still performs each conflicting profile's ordinary closure resolution in canonical profile order, subject to the normal worker and aggregate bounds, solely to populate `resolution` and its separate diagnostic/warning. It never parses the artifact instance or overwrites the conflict validation. A conflict validation has an empty `prerequisiteChecks` array in every resolution state. The unconditional per-profile `E_PROFILE_INVALID` makes the artifact-profile aggregate fail; resolution/resource errors and warnings are additional only where the ordinary requiredness rules call for them.

Candidate-only constraint aggregation is a separate deterministic layer. If its schema is unresolved/unsupported, the profile record is `resolution: "fail"`, `validation: "skipped"`; if its worker limit is exceeded after resolution, it is `resolution: "pass"`, `validation: "fail"`. When another candidate authorizes, those candidate-local failures remain in the profile record, the metadata-profile aggregate remains `pass`, no top-level error is emitted for the losing candidate, and final authorization is `pass`. When no candidate authorizes, the metadata-profile aggregate and final authorization are `fail`, and the applicable `E_PROFILE_UNRESOLVED` or `E_RESOURCE_LIMIT` is emitted at Step 7 with `causedByCheck: "authorization"`; `metadata-profiles` may fail in this candidate-aggregation case without owning a second diagnostic. Globally required or producer-critical Step 7 profile failures remain owned by `metadata-profiles`. An evaluated invalid instance is not candidate-local: `E_PROFILE_INVALID` and metadata-profile failure deny even if another candidate would otherwise authorize. Conformance vectors cover all three cases.

The top-level `signatures` check measures Step 5 cryptographic verification, not Step 2 transport structure or Step 6 authorization thresholds. Its eligible population is every transport-valid envelope for which exact PAE payload bytes and an indexed identity were established and Step 5 is permitted to run. A malformed envelope/signature entry is outside this population and fails `parse-strictly`; it does not itself make `signatures` fail. When at least one eligible envelope exists, `signatures` is `fail` if any configured-key signature cryptographically fails and otherwise `pass`; a well-formed unknown-key signature contributes a record and warning but not a configured-key failure, so an envelope containing only unknown keys yields `signatures: "pass"` and later fails authorization. When the eligible population is empty because a Step 2/3 prerequisite failed, `signatures` is `skipped` with the sorted failed prerequisite set; it is `not_checked` only when a complete valid input establishes that no signature-bearing evidence population applies. Mixed malformed and eligible envelopes still run/fold every eligible Step 5 item while `parse-strictly` independently fails. Phase 0 pins all-malformed, mixed malformed/valid, unknown-only, configured-key-invalid, and empty-applicable populations. Mixed required and optional profile records follow the table: optional indeterminate records never mask a required failure and never make the overall bundle decision indeterminate.

Step 6 still evaluates every remaining cryptographically passing signature after a configured-key signature fails at Step 5. If the remaining valid authorized distinct-key set does not meet a selected threshold, the verifier emits both `E_SIGNATURE_INVALID` at Step 5 and `E_SIGNER_UNAUTHORIZED` at Step 6; if it does meet threshold, authorization may pass while the strict signature failure independently denies. Authorization is skipped only when transport/core parsing left no usable predicate or selector inputs, not merely because one signature was invalid.

JSON Schema does not natively validate CSV columns, Parquet logical schemas, images, or arbitrary binary contents. v0.2 MUST NOT imply otherwise. Future format adapters may expose a deterministic instance to a profile, but the adapter identity and transformation semantics must then be explicit.

For lowercase parameter-free JSON media types, `application/*+json` means subtype grammar `<nonempty RFC 6838 subtype prefix>+json`; `application/+json` is rejected, while `application/a+json` and `application/json+json` are accepted. Phase 0 vectors cover all three.

Optional historical byte absence is evaluated before media disagreement. If no bytes are supplied and no producer-critical, manifest-required, or consumer-required artifact profile makes those historical bytes mandatory, the verifier does not compare the signed media types for that artifact, does not resolve any targeting closure, records every targeting optional profile as `resolution: "skipped"`, `validation: "not_checked"`, `prerequisiteChecks: ["artifact-bytes"]`, and emits only `W_HISTORICAL_ARTIFACT_NOT_CHECKED`. Media disagreement becomes the unconditional validation failure described above only after target bytes are available or required. Required historical byte absence remains the Step 12 artifact failure and likewise does not manufacture a media-conflict diagnostic before bytes exist.

For a byte-available artifact with one signed unsupported media type rather than a conflict, the verifier MUST attempt ordinary closure resolution in canonical profile order before assigning the media outcome. If resolution passes, required/critical media produces `resolution: "pass"`, `validation: "fail"`, and `E_ARTIFACT_FORMAT`, while optional noncritical media produces `resolution: "pass"`, `validation: "indeterminate"`, and `W_PROFILE_INDETERMINATE`. If resolution fails or exhausts a resource, the profile follows the ordinary unresolved/resource row with validation skipped behind `resolution`; no separate unsupported-media diagnostic is emitted. This rule makes the stable `resolution` field independent of implementation short-circuiting without expanding the media-conflict exception.

### 12.5 Partitioned dataset manifests

A directory or table is not itself a finite byte sequence and MUST NOT be hashed through an implementation-defined directory traversal. A producer has two portable choices: name each finite partition as a subject, or create a dataset-manifest artifact.

The optional v0.2 dataset-manifest media type is `application/vnd.makoto.dataset-manifest.v0.2+json`:

```json
{
  "version": "0.2",
  "entries": [
    {
      "name": "year=2026/month=09/part-00000.parquet",
      "digest": { "sha256": "..." },
      "size": 48127,
      "mediaType": "application/vnd.apache.parquet"
    }
  ]
}
```

- `entries` MUST be non-empty, duplicate-free by name, and lexicographically sorted by UTF-8 name bytes.
- Names are logical relative names and MUST pass the bundle safe-path rules even when no partition bytes are bundled. Within one dataset manifest, names MUST also be pairwise distinct after NFC normalization and pairwise distinct after Unicode-15.0 full case folding of their NFC forms; equality is exact Unicode-scalar-sequence equality of the folded results.
- `size` and `mediaType` are optional metadata; the digest is required. `size`, when present, is a JSON integer from 0 through `9223372036854775807` inclusive and counts exact bytes.
- The manifest artifact itself is hashed as exact bytes and named as a normal statement subject.
- A dataset-manifest subject MUST carry a critical artifact-target profile reference whose ID, root digest, recomputed closure digest, and target subject exactly match the immutable core-catalog schema entry for `https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json`; the signed profile reference's media type MUST independently equal the prose-fixed `application/vnd.makoto.dataset-manifest.v0.2+json`. The catalog entry has no media-type member, and ID alone is insufficient.
- A transform MAY consume one dataset-manifest subject instead of enumerating every partition in `inputs`.
- A partition-pruned transform MAY consume a single entry using `inputs[].provenance.entryName`; the predecessor manifest bytes then become required verification material for that graph edge.
- When partition bytes are supplied for an entry in the report population defined by Section 16.3, the verifier MUST verify that supplied entry digest and its optional declared size; mismatch fails with `E_ARTIFACT_DIGEST` or `E_ARTIFACT_SIZE`. An entry in that population without supplied partition bytes has both `digestStatus: "not_checked"` and `sizeStatus: "not_checked"`, whether or not the manifest declared size; when bytes are supplied but the manifest omitted size, only `sizeStatus` is `not_checked`. Entries merely declared in the dataset manifest but absent from the Section 16.3 population produce no individual report record. The signed dataset-manifest artifact itself is still verified.
- Every `datasetEntries` mapping MUST reference such a validated dataset-manifest subject and one unique existing entry. Mapping an ordinary subject or an unknown entry fails `E_DATASET_MANIFEST_INVALID`; a supplied partition whose byte count conflicts with the manifest uses `E_ARTIFACT_SIZE`. Two mappings MUST NOT select the same complete entry identity; identity duplicates fail `E_CORE_SCHEMA`. Two bundle paths that resolve to the same opened physical file are a hard-link/alias violation and fail `E_BUNDLE_UNSAFE_PATH`, not a schema error.
- A dataset manifest proves the producer’s committed partition set. It does not prove that an object-store prefix contains no other objects.

## 13. Handoff manifest and bundle

### 13.1 Why a completeness anchor is required

A hash-linked signed graph can reveal a broken reference, but it cannot prove that an attacker did not present an older valid head or omit an entire valid branch. Completeness is always relative to something the consumer trusts.

An authenticated v0.2 bundle handoff requires a DSSE-signed manifest whose signer is authorized by consumer trust policy. The manifest binds the exact statement set, roots, heads, profiles, and handed-off artifacts. A missing manifest fails with `E_HANDOFF_REQUIRED`; a malformed envelope fails with `E_ENVELOPE_MALFORMED`; malformed JSON payload bytes fail with `E_JSON_INVALID`; an unauthorized signer fails with `E_SIGNER_UNAUTHORIZED`. A loose collection of statements may be examined with ordinary JSON/DSSE tools, but v0.2 defines no unauthenticated bundle-inspection command; `makoto envelope inspect` remains the single-envelope structural/digest utility in Section 16.1; it is not an authenticated handoff and cannot receive `allow` from `makoto verify bundle`.

Temporal freshness, rollback resistance, and independent selection are distinct consumer properties. The stable `freshness-*` report family is an umbrella for all three, not a claim that every method supplies time freshness. After the authorized manifest passes, the default handoff policy additionally requires at least one anchor method:

1. an expected manifest payload digest obtained through an independent authenticated channel; this binds the complete metadata, artifact selection, and graph but is rollback-resistant only when the channel or its store prevents rollback;
2. the complete expected statement-head set, with the same channel-dependent rollback limitation;
3. the complete expected final-artifact tuple set `(head, subjectName, artifactDigest)`; because each tuple names its head, an independently obtained exact set is a selection anchor even without a separately supplied expected-head flag, but it is not temporal freshness unless its channel is anti-rollback;
4. an exact consumer-generated expected nonce; an expected recipient MAY be required with it to bind the challenge to an audience, but recipient matching alone is not freshness; or
5. a consumer-policy `maxAgeSeconds` bound evaluated at the consumer-controlled evaluation time.

A nonce challenge supplies one-use replay resistance when generated and managed as required; `maxAgeSeconds` supplies temporal recency relative to the signed creation time and evaluation clock. A policy MAY explicitly set `allowReplayableHandoff: true` to accept an authorized manifest without any anchor method. The report then records freshness as `not_checked` and emits `W_FRESHNESS_NOT_CHECKED`. Without an authorized manifest, or without an accepted anchor unless that explicit opt-in is set, the verifier MUST NOT issue `allow`. Documentation MUST call expected digests/heads/artifact tuples selection or rollback anchors and MUST NOT promise temporal freshness without an anti-rollback channel property.

An authorized handoff manifest anchors an exact graph but does not by itself establish freshness: any older manifest that the same signer validly issued can be replayed. `issuedAt` is signer-asserted display metadata unless consumer policy applies an explicit maximum-age rule at a consumer-controlled evaluation time.

### 13.2 Handoff payload

The handoff DSSE `payloadType` is `application/vnd.makoto.handoff.v0.2+json`.

```json
{
  "version": "0.2",
  "bundleId": "urn:uuid:...",
  "issuedAt": "2026-09-16T16:03:00Z",
  "recipient": "example:downstream-team",
  "roots": [{ "sha256": "..." }],
  "heads": [{ "sha256": "..." }],
  "statements": [
    { "sha256": "..." },
    { "sha256": "..." },
    { "sha256": "..." }
  ],
  "artifacts": [
    {
      "name": "customers.public.json",
      "digest": { "sha256": "..." },
      "mediaType": "application/json",
      "head": { "sha256": "..." }
    }
  ],
  "requiredProfiles": [
    {
      "head": { "sha256": "..." },
      "id": "https://schemas.example.com/makoto/customer-public-v1.json",
      "digest": { "sha256": "..." },
      "closureDigest": { "sha256": "..." },
      "target": "artifact",
      "subjectName": "customers.public.json",
      "mediaType": "application/json",
      "scope": "eachMatchingFinalArtifact"
    }
  ],
"nonce": "optional consumer-generated challenge"
}
```

Requirements:

| Field | Required | Rules |
|---|---:|---|
| `version` | yes | Exact string `0.2`. |
| `bundleId` | yes | Section 10.4 canonical lowercase UUID grammar or absolute URI, nonempty and at most 4096 UTF-8 bytes; no additional version/variant-bit rule, nil UUID allowed, correlation only. |
| `issuedAt` | yes | Section 10.4 timestamp; signer asserted unless age policy applies. |
| `recipient` | no | Optional bounded audience string under the lexical rule below. |
| `roots` | yes | Nonempty sorted unique statement-digest objects. |
| `heads` | yes | Nonempty sorted unique statement-digest objects. |
| `statements` | yes | Nonempty sorted unique statement-digest objects. |
| `artifacts` | yes | Nonempty sorted unique final-artifact entries; each requires `name`, `digest`, and `head`, with optional `mediaType`. |
| `requiredProfiles` | yes | Sorted unique artifact-only requirements; may be empty. |
| `nonce` | no | Optional bounded replay-challenge string under the lexical rule below. |

- `roots`, `heads`, `statements`, and `artifacts` MUST be non-empty. Root, head, and statement identity is the lowercase `sha256` value. Artifact identity is `(head.sha256, name, digest.sha256)`; optional `mediaType` is not part of identity, so two artifact entries that differ only by media type are duplicates and invalid. A handoff required-profile identity is `(head.sha256, id, digest.sha256, closureDigest.sha256, "artifact", subjectName, mediaType, "eachMatchingFinalArtifact")`. Handoff requirements are artifact-only in v0.2. All identity tuples MUST be duplicate-free, and one `(head.sha256, id, subjectName)` selector MUST NOT name conflicting root/closure digests or media types.
- `bundleId` is a producer-selected correlation identifier, not an integrity or freshness anchor. It MUST be copied to the verification report for operator correlation and MUST NOT affect authorization or deduplication.
- `roots`, `heads`, and `statements` MUST each be sorted by the 64-character lowercase hexadecimal SHA-256 value using ASCII-byte comparison. `artifacts` MUST be sorted by `(head.sha256, name, digest.sha256)`, and `requiredProfiles` by their complete identity tuple, comparing every string component as UTF-8 bytes. Unsorted arrays fail handoff core validation with `E_CORE_SCHEMA`; array order still does not define lineage.
- Every head and root MUST be present in `statements`; violation is `E_MANIFEST_SET` at Step 11.
- The exact set reachable from all heads MUST equal the manifest’s statement set.
- The computed roots MUST equal the manifest roots.
- Every artifact entry MUST match one exact `(subject name, subject digest)` tuple of its declared head; matching only the name is insufficient. A name or digest mismatch is `E_MANIFEST_SET` at Step 11, before artifact-byte hashing.
- Every handed-off artifact subject MUST be terminal: no direct transformation input in the declared graph may consume that exact `(statement digest, subject name, artifact digest)` tuple. Violation is `E_MANIFEST_SET` at Step 11. An `entryName` edge consumes a manifest member, not the dataset-manifest artifact subject itself, so consuming one or more entries does not prevent the manifest artifact from being terminal and handed off; conformance vectors cover this case. Head status is therefore subject-aware. A statement with multiple subjects MAY be a handoff head for an unconsumed subject even when another subject from the same statement has descendants.
- The manifest `heads` set MUST equal the distinct statement digests referenced by `artifacts[].head`; violation is `E_MANIFEST_SET` at Step 11. Every head therefore owns at least one handed-off terminal subject. Other unconsumed subjects MAY exist but are not handed-off artifacts and do not add heads. Expected heads bind the complete signed statement payload, including all its subjects, but artifact selection remains delegated to the authorized handoff signer unless the consumer also supplies an expected manifest digest or expected artifact tuples.
- `mediaType`, when present, is a signed transport hint. Artifact-profile parser selection still comes from the profile reference signed in the head statement; a conflict fails with `E_PROFILE_INVALID` before artifact parsing.
- Every `requiredProfiles` entry MUST have `target: "artifact"` and `scope: "eachMatchingFinalArtifact"`, MUST match at least one manifest `artifacts` entry with the same `(head, subjectName)`, and MUST match a profile reference signed in that declared head by exact equality of the complete `(id, digest, closureDigest, target, subjectName, mediaType)` tuple. Producer `critical` is not part of requirement identity. Zero matching handed-off artifacts or absence of that exact signed head reference fails at Step 11 with `E_REQUIRED_PROFILE_MISSING`; manifest requirements are never vacuous. A consumer trust policy may require additional profiles, but a producer cannot satisfy a manifest requirement by naming an unsigned schema only in the handoff. Statement- and predicate-target profiles can still be producer-critical or authorization-rule constraints, but the v0.2 handoff manifest has no separate requirement shape for them.
- `recipient` is optional audience binding and `nonce` is an optional replay challenge. When present, each is a nonempty Unicode-scalar string of at most 4096 UTF-8 bytes with no NUL or control scalar; expected CLI/policy values obey the same bound. Policy MAY require either, but verification succeeds only when each required value exactly matches a consumer-supplied expected value; presence alone is insufficient.
- A nonce is effective only when the consumer generates at least 128 unpredictable bits, scopes it to one intended handoff/recipient, delivers it outside producer-controlled evidence, and marks it consumed after one accepted handoff. Makoto verifies exact equality but cannot enforce the consumer's generation or single-use store. Recipient matching is audience binding, not freshness by itself.
- When multiple heads are present, the consumer expected-head set and manifest head set are compared as duplicate-free sets and MUST be exactly equal. Any-match or subset semantics are forbidden.
- The manifest signature is separately verified and authorized.
- The SHA-256 digest of exact decoded manifest payload bytes is the handoff metadata digest presented to users as `manifestDigest`.
- The reference producer emits those mandatory orders, and verification first enforces them before performing set-based graph comparisons. No consumer may infer lineage from array order.

### 13.3 Reference bundle layout

```text
makoto-handoff/
├── bundle.json
├── manifest.dsse.json
├── attestations/
│   ├── <statement-payload-sha256>.dsse.json
│   └── ...
├── artifacts/
│   └── customers.public.json
├── schemas/
│   └── <catalog-managed schema files>
└── README.txt
```

`bundle.json` is an unsigned transport index and MUST NOT be trusted independently. It has `version: "0.2"`, a relative `manifest` path, an `attestations` array mapping each manifest statement digest to exactly one relative envelope path, an `artifacts` array mapping every manifest artifact tuple `(statement digest, subject name, artifact digest)` to exactly one relative file path, an optional `datasetEntries` array mapping each logical `(manifest statement digest, manifest subject name, entry name)` to one declared entry digest and relative partition path, and an optional relative `schemaCatalog` path. Verifiers accept absent `datasetEntries` as the empty set, but the reference producer always emits the member and uses `[]` when empty so deterministic bundle bytes have one spelling. Tuple arrays are unique; two dataset-entry mappings with the same logical tuple are duplicates even when their declared digests differ. Extra mappings to signed historical subjects or optional dataset entries are allowed only when their identities resolve inside the manifest statement set; they are reported but do not become handed-off artifacts. Other extra mappings are invalid. These tuples are the only valid ways to select bytes; a filename alone is not an identity.

The reference producer never derives bundle paths from subject or entry names. For each final, historical, or dataset-entry mapping, it computes SHA-256 over JCS bytes of that mapping's complete logical identity object, without its local `path`, and copies bytes to `artifacts/final/<identity-sha256>.bin`, `artifacts/historical/<identity-sha256>.bin`, or `artifacts/dataset-entries/<identity-sha256>.bin` respectively. Identity objects use the exact report identity members and JCS member names; Phase 0 fixtures publish each byte preimage. A duplicate destination digest for unequal identity preimages is an internal invariant failure exit 3; equal identity is already rejected or collapsed by the applicable uniqueness rule. Unsafe names therefore never become path segments, and input order/original filenames cannot change bundle bytes.

The preceding layout tree and `bundle.json` JSON example illustrate a verifier-valid third-party bundle only; their readable `abc.dsse.json` and `customers.public.json` paths are not reference-producer output and are excluded from deterministic producer-byte fixtures. Reference-producer fixtures use the identity-hashed paths below. The reference producer emits no `README.txt` or other unreferenced file; the positive reference report therefore has `unreferencedFiles: []`.

The three identity-hash preimages are literal closed objects: final `{"digest":<digest-object>,"statementDigest":<digest-object>,"subjectName":<string>}`; historical uses the same shape; dataset entry `{"entryName":<string>,"manifestStatementDigest":<digest-object>,"manifestSubjectName":<string>}`. Dataset mapping `digest` is deliberately excluded from logical identity and therefore from its preimage. RFC 8785 JCS of exactly these objects, without LF, is hashed.

For deterministic index bytes, `attestations` MUST be sorted by statement digest; `artifacts` by `(statementDigest.sha256, subjectName, digest.sha256)`; and `datasetEntries` by `(manifestStatementDigest.sha256, manifestSubjectName, entryName)`, using lowercase-hex ASCII ordering for digests and UTF-8 byte ordering for strings. Unsorted index arrays fail `E_CORE_SCHEMA`.

A structurally malformed or duplicate index tuple fails core bundle-schema validation. A well-formed mapping outside the signed manifest/reachable set, a manifest statement lacking its required index tuple, or a manifest artifact lacking its complete index tuple is recorded during indexing but evaluated only at Step 11, where it produces `E_MANIFEST_SET`. This deferral preserves signature/graph primary errors for corrupted reachable evidence. If a valid artifact tuple exists but its target file is absent or unreadable, Step 12 uses `E_ARTIFACT_MISSING` instead.

```json
{
  "version": "0.2",
  "manifest": "manifest.dsse.json",
  "attestations": [
    {
      "statementDigest": { "sha256": "..." },
      "path": "attestations/abc.dsse.json"
    }
  ],
  "artifacts": [
    {
      "statementDigest": { "sha256": "..." },
      "subjectName": "customers.public.json",
      "digest": { "sha256": "..." },
      "path": "artifacts/customers.public.json"
    }
  ],
  "datasetEntries": [],
  "schemaCatalog": "schemas/catalog.json"
}
```

Paths MUST remain within the bundle root; absolute paths, symlink escapes, duplicate paths, and `..` traversal are invalid. The bundle-directory argument itself MUST resolve to a real directory rather than a symbolic link. The descriptor-relative, no-follow open rules from Section 12.3 also apply to bundles. Every mapped digest MUST be recomputed before use. Unreferenced files are ignored and reported. Security decisions come from signed payloads, verified digests, schemas, and policy. A missing `bundle.json` uses `E_HANDOFF_REQUIRED` because no authenticated handoff can be selected without its transport index, even when an unrelated manifest file happens to exist somewhere in the directory.

Bundle and catalog paths use a host-independent logical grammar: UTF-8 NFC strings separated only by `/`; no empty, `.`, or `..` segments; no leading slash; no backslash, NUL, ASCII control, `<`, `>`, `:`, `"`, `|`, `?`, or `*` anywhere; no segment ending in ASCII space or `.`; no segment whose ASCII-case-insensitive basename before the first `.` is `CON`, `PRN`, `AUX`, `NUL`, `COM1` through `COM9`, `LPT1` through `LPT9`, `COM¹`, `COM²`, `COM³`, `LPT¹`, `LPT²`, or `LPT³`; no Windows drive prefix; and no first segment that begins with the anchored ASCII prefix `^[A-Za-z][A-Za-z0-9+.-]*:`. Thus `foo:bar` is rejected by the colon rule as well as the scheme-prefix rule. Segment comparison and index lookup use the exact NFC string. Unicode normalization and default full case folding use the vendored Unicode 15.0 tables for every normative normalization, fold, and collision operation; Python runtime tables MUST NOT be used for these decisions. Folded values collide only when their resulting Unicode scalar sequences are exactly equal; Makoto does not add a post-fold normalization step. A path is at most 1024 UTF-8 bytes, 64 segments, and 255 UTF-8 bytes per segment. For a bundle, file-count limits, UTF-8 validity, normalization, and collision checks cover every on-disk entry under the bundle root, including unreferenced files and directories; an invalid unreferenced name rejects the bundle when the bounded inventory completes. Section 15 defines deterministic fail-closed behavior when the inventory exceeds its entry ceiling before completeness can be established. The verifier enumerates raw directory-entry names through descriptor-relative handles, maps each unique raw entry to its NFC logical name after collision rejection, and opens the raw discovered entry associated with an index's exact NFC name; it never assumes the normalized spelling exists on disk. For a consumer or bundle schema catalog, the scan set is only the catalog file plus the distinct resource paths it declares; unrelated siblings or descendants of the catalog directory are never enumerated or charged, though declared paths are collision-checked against one another. A bundle containing paths that collide after full case folding of their NFC forms, or after NFC normalization of on-disk directory entries, MUST be rejected for cross-platform consistency. The reference implementation MUST reject hard-linked files, open every mapped file without following links, confirm the opened entry's normalized logical name matches the index, and copy its bytes exactly once into a verifier-controlled immutable snapshot while hashing. The final rescan is a Step 12 stability sub-operation, not unconditional cleanup. It runs exactly when Step 1 completed, at least one immutable artifact snapshot was created at Step 8 or Step 12, and all earlier prerequisites needed for a still-possible `allow` decision passed; an earlier denial or skipped `artifact-bytes` phase performs no rescan and retains its already defined check states. On the eligible path, after all permitted snapshots it performs one descriptor-relative final rescan and compares the sorted `(NFC logical path, entry type, opened file identity)` set with the first scan; any observable addition, removal, rename, type change, or physical-identity change fails `artifact-bytes` with Step 12 `E_BUNDLE_UNSAFE_PATH`. “Physical identity” means the strongest stable identifier exposed by the supported host API, such as POSIX device/inode; v0.2 does not claim to detect same-identity byte mutation or inode-identifier reuse between scans. Those races cannot change verification because all parsing, hashing, and validation use the already captured immutable snapshots rather than source inodes. Implementations need not retain one descriptor per inventory entry after recording its first-scan identity. Large artifacts may use a private read-only temporary file rather than memory. `maxMetadataBytes` accounting is defined in Section 15; artifact input and snapshot bytes use the separate limits there.

The minimum portable physical identity is `(st_dev, st_ino)` from descriptor `fstat` on POSIX and macOS, and `(volume serial number, 128-bit file ID)` from an opened handle on Windows. An implementation MAY record stronger generation/version fields but MUST NOT use them to make an input pass or fail differently from the minimum tuple. If the supported host cannot expose the applicable minimum tuple for an opened entry, verification exits 3 before relying on that entry; it never falls back to path spelling, size, or timestamps as identity. Phase 0 alias/rescan vectors run on both release operating systems and record the exact tuple source.

The allowed on-disk entry types anywhere beneath a bundle are real directories and regular files only. An unreferenced symlink, FIFO, socket, device, or other special entry fails Step 1 with `E_BUNDLE_UNSAFE_PATH`; it is never silently ignored. During Step 1, the descriptor-reported size of every regular file, referenced or not, is checked against the immutable 1 TiB bootstrap per-file ceiling as an inventory safety bound without reading bytes. Excess emits Step 1 `E_RESOURCE_LIMIT`. Later role-specific consumer limits for referenced metadata/artifacts, artifact aggregate, snapshot, and structured validation still apply; an unreferenced file is not charged to an aggregate byte budget. “Reject hard-linked files” means reject two or more bundle/consumer inventory entries whose opened physical file identity is equal. A regular bundle file with link count greater than one solely because of a name outside every scanned bundle/consumer inventory is accepted; external aliases cannot change the immutable snapshot. Both the initial scan and final rescan open or descriptor-stat every entry, including unreferenced regular files/directories, sufficiently to obtain the same physical identity tuple; implementations MUST NOT substitute path strings or omit identity for ignored entries.

Filesystem failures have one owner. “Absent” in the role-specific rules means absent from the completed Step 1 inventory: an absent manifest-envelope target uses `E_HANDOFF_REQUIRED`; an absent manifest-listed attestation target uses `E_MANIFEST_SET`; an absent declared bundle catalog or declared catalog resource uses `E_CATALOG_INVALID`; and an absent target for a structurally valid final, historical, or dataset-entry artifact mapping uses `E_ARTIFACT_MISSING`. Once Step 1 recorded a target as present, disappearance, replacement, permission loss, type change, symlink/hard-link or physical-alias discovery, containment failure, or descriptor/stat failure at the later consuming open is instead `E_BUNDLE_UNSAFE_PATH` at that consumer's step: Step 2 for the manifest or attestation envelope, Step 4 for the bundle catalog or schema resource, Step 8 for a dataset-manifest dependency, and Step 12 for final, historical, or dataset-entry bytes. A final stable-rescan change is likewise Step 12 `E_BUNDLE_UNSAFE_PATH`. This ownership is based on first-inventory state and the signed/indexed role, not the host operating system's particular open error number. No one condition emits more than one of those ownership codes.

The bundle need not contain source or intermediate data. It must contain every attestation needed for graph verification and every final artifact required by the handoff. An unavailable historical artifact is `not_checked` only when no producer-critical, manifest-required, or consumer-required artifact profile applies; otherwise absence is `E_ARTIFACT_MISSING` and denial. Dataset-manifest bytes needed for an `entryName` edge are always mandatory.

## 14. Consumer trust policy

The trust policy is consumer-owned configuration. It MUST remain outside signed producer evidence unless the consumer independently pins it.

The reference format contains:

- verification keys and algorithms;
- human-readable labels for keys;
- allowed predicate types per key;
- optional exact allowed source-kind and source-URI values;
- optional allowed profile IDs;
- required signature threshold per statement class;
- authorized handoff-manifest signers;
- required critical profiles for selected artifacts; and
- whether an expected head, recipient, or nonce is mandatory;
- parser and bundle resource limits; and
- optional key-authorization validity windows evaluated under the consumer’s clock.

Example:

```json
{
  "version": "0.2",
  "keys": {
    "sha256:1111111111111111111111111111111111111111111111111111111111111111": {
      "type": "ed25519",
      "publicKey": "base64-encoded DER SubjectPublicKeyInfo",
      "label": "demo ingestion",
      "validFrom": "2026-09-01T00:00:00Z",
      "validUntil": "2026-12-31T23:59:59Z"
    },
    "sha256:2222222222222222222222222222222222222222222222222222222222222222": {
      "type": "ed25519",
      "publicKey": "base64-encoded DER SubjectPublicKeyInfo",
      "label": "demo normalization"
    },
    "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff": {
      "type": "ed25519",
      "publicKey": "base64-encoded DER SubjectPublicKeyInfo",
      "label": "demo privacy transform"
    },
    "sha256:5555555555555555555555555555555555555555555555555555555555555555": {
      "type": "ed25519",
      "publicKey": "base64-encoded DER SubjectPublicKeyInfo",
      "label": "demo handoff"
    }
  },
  "rules": [
    {
      "id": "urn:makoto:policy-rule:demo-normalize",
      "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
      "operationTypes": ["urn:makoto:demo:operation:normalize"],
      "authorizedKeyIds": ["sha256:2222222222222222222222222222222222222222222222222222222222222222"],
      "minimumSignatures": 1
    },
    {
      "id": "urn:makoto:policy-rule:demo-origin",
      "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/origin"],
      "sourceKinds": ["urn:makoto:demo:source:synthetic-file"],
      "sourceUris": ["urn:makoto:demo:v0.2:source:customers-raw"],
      "authorizedKeyIds": ["sha256:1111111111111111111111111111111111111111111111111111111111111111"],
      "minimumSignatures": 1
    },
    {
      "id": "urn:makoto:policy-rule:demo-public-transform",
      "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
      "operationTypes": ["urn:makoto:demo:operation:public-safe"],
      "authorizedKeyIds": ["sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"],
      "minimumSignatures": 1,
      "profileConstraints": [
        {
          "id": "https://schemas.example.com/makoto/public-transform-metadata-v1.json",
          "digest": { "sha256": "..." },
          "closureDigest": { "sha256": "..." },
          "target": "predicate"
        }
      ]
    }
  ],
  "handoff": {
    "authorizedKeyIds": ["sha256:5555555555555555555555555555555555555555555555555555555555555555"],
    "minimumSignatures": 1,
    "requireExpectedManifest": false,
    "requireExpectedHead": true,
    "requireExpectedArtifacts": false,
    "requireRecipient": false,
    "requireNonce": false,
    "allowReplayableHandoff": false
  },
  "requiredProfiles": [
    {
      "id": "https://schemas.example.com/makoto/customer-public-v1.json",
      "digest": { "sha256": "..." },
      "closureDigest": { "sha256": "..." },
      "target": "artifact",
      "subjectName": "customers.public.json",
      "mediaType": "application/json",
      "scope": "eachMatchingFinalArtifact"
    }
  ],
  "limits": {
    "maxBundleFiles": 10000,
    "maxMetadataBytes": 104857600,
    "maxArtifactBytesPerFile": 10737418240,
    "maxAggregateArtifactBytes": 53687091200,
    "maxSnapshotBytes": 53687091200,
    "maxArtifactValidationBytes": 104857600,
    "maxJsonDepth": 128,
    "maxJsonNumberChars": 1024,
    "maxJsonExponentMagnitude": 10000,
    "maxSchemaBytes": 2097152,
    "maxSchemaResources": 256,
    "maxSchemaEvaluationDepth": 256,
    "maxSchemaOperations": 10000000,
    "maxRegexLength": 4096,
    "profileEvaluationTimeoutSeconds": 5,
    "profileWorkerMemoryBytes": 536870912,
    "maxNdjsonLineBytes": 1048576,
    "maxSignaturesTotal": 10000,
    "maxProfileEvaluations": 10000,
    "maxDiagnostics": 10000,
    "maxReportRecords": 20000,
    "maxReportBytes": 67108864
  }
}
```

A valid but unauthorized signature MUST fail policy. A missing rule MUST fail closed. The required top-level policy fields are `version`, `keys`, `rules`, `handoff`, `requiredProfiles`, and `limits`; `requiredProfiles` is required but may be an empty array. Top-level `rules` MUST be duplicate-free by `id` and sorted by `id` using UTF-8 bytes. Top-level `requiredProfiles` MUST be duplicate-free by the complete tuple and sorted by `(id, digest.sha256, closureDigest.sha256, target, subjectName, mediaType, scope)` using the Section 13.2 string-order rules; distinct digest-pinned versions with the same ID/media type may be conjunctively required. Each rule's `profileConstraints` array, when present, is likewise duplicate-free and sorted by `(id, target, digest-or-empty, closureDigest-or-empty)`; paired digest omission sorts before a supplied digest pair. The handoff `authorizedKeyIds` and every other scalar policy array are duplicate-free and sorted by UTF-8 bytes. The `limits` object requires every member shown in the example and defines no defaults; a consumer must choose explicit values within bootstrap ceilings. Human labels and asserted signer strings are display metadata only.

The policy JSON above is illustrative and intentionally uses placeholder key digests and public-key text; it is not a preflight-valid loadable policy. The checked-in demo policy required by Section 18 MUST contain real derivable SPKI bytes and recomputed key IDs and MUST pass policy preflight.

The handoff rule requires `authorizedKeyIds`, `minimumSignatures`, and all six booleans `requireExpectedManifest`, `requireExpectedHead`, `requireExpectedArtifacts`, `requireRecipient`, `requireNonce`, and `allowReplayableHandoff`; none has an implicit default. It MAY also contain both `maxAgeSeconds` and `maxFutureSkewSeconds`; they are either both absent or both present, and there is no implicit skew value. Each age value is a JSON integer from 0 through `315576000` inclusive. When `maxAgeSeconds` is present, the verifier compares signed `issuedAt` with the consumer evaluation time, rejects future-issued manifests beyond `maxFutureSkewSeconds`, and denies stale manifests with `E_HANDOFF_STALE`. `allowReplayableHandoff: true` is legal alongside required expectations but cannot override them; it matters only when no freshness method is otherwise required or supplied. Every `requireExpected*`, recipient, and nonce requirement needs exact consumer-supplied values; absence of a required consumer expectation is a completed evidence denial with its specific `E_EXPECTED_*`, `E_HANDOFF_RECIPIENT`, or `E_HANDOFF_NONCE` code, not invalid configuration. This bounds replay time but does not turn `issuedAt` into a trusted execution timestamp.

Age boundaries are inclusive: a manifest passes when `0 <= evaluationTime - issuedAt <= maxAgeSeconds`, or when it is future-dated by no more than `maxFutureSkewSeconds`; values beyond either bound fail with `E_HANDOFF_STALE`. All durations are integer SI seconds.

Rule evaluation is deterministic and order-independent:

Each statement rule has exactly `id`, `predicateTypes`, `authorizedKeyIds`, and `minimumSignatures`, plus optional `sourceKinds`, `sourceUris`, `operationTypes`, and `profileConstraints`. `id` is an absolute URI used for diagnostics and is unique within the policy. All array fields are non-empty and duplicate-free when present and use the canonical order above. `predicateTypes`, `sourceKinds`, and `operationTypes` members are absolute URIs under Section 10.4. `sourceUris` members are nonempty URI-reference strings under the same grammar as `source.uri`, so relative references are permitted and matched literally. `operationTypes` may select only the core transformation predicate; a rule whose predicate set contains no transformation while `operationTypes` is present is statically unsatisfiable. An authorization profile constraint contains `id`, `target` (`statement` or `predicate` only), and either both `digest` plus `closureDigest` or neither; artifact targets, `subjectName`, and `mediaType` are invalid in this rule shape and belong in consumer `requiredProfiles`. Every supplied member compares exactly with one signed profile reference. All profile constraints are conjunctive. `sourceKinds` and `sourceUris` are alternative sets within their field but conjunctive across fields: a matching origin must have a source kind in `sourceKinds` and, when `sourceUris` is present, a present source URI exactly equal as a JSON string to one listed value. A non-origin cannot select a rule with source constraints; an origin cannot select a rule with `operationTypes`. A matching transformation with `operationTypes` must have `operation.type` exactly equal to one listed URI. No URI normalization, glob, prefix, regular-expression, or decoded comparison occurs in v0.2.

An authorization `profileConstraint` without `digest` and `closureDigest` is only a condition on a producer-signed statement/predicate profile label; it does not establish trust in schema semantics, upgrade validation, or satisfy consumer `requiredProfiles`. It selects when at least one signed reference matches its exact `id` and `target`, regardless of that reference's digests. When multiple signed references share that label, every matching profile record lists the rule ID in `requiredByAuthorizationRuleIds`; no canonical witness is chosen, and label selection alone does not force closure resolution or validation that the profile's ordinary criticality/requirement state would not otherwise perform. A constraint with both digests is both a full-reference selector and a candidate-local validation requirement: the rule-selection item above requires one signed reference to match `id`, `target`, `digest`, and `closureDigest` exactly, while only closure resolution and instance validation are deferred to verification Step 7; only the exact matching record receives that rule ID. These rule-attribution IDs do not set the global `requiredByPolicy` boolean. Artifact requirements use the separately scoped global consumer `requiredProfiles` mechanism and set `requiredByPolicy: true`. Policy keys and rule IDs are unique; every key has exact `type: "ed25519"`; every authorized key ID MUST exist in `keys`; thresholds are positive integers no greater than the number of distinct authorized keys; when both are present, `validFrom` MUST be earlier than `validUntil`, while either omitted endpoint is unbounded; and every required-profile root/closure digest pair and scope is present. The `limits` object has exactly the twenty-two fields shown in the example: `maxBundleFiles`, `maxMetadataBytes`, `maxArtifactBytesPerFile`, `maxAggregateArtifactBytes`, `maxSnapshotBytes`, `maxArtifactValidationBytes`, `maxJsonDepth`, `maxJsonNumberChars`, `maxJsonExponentMagnitude`, `maxSchemaBytes`, `maxSchemaResources`, `maxSchemaEvaluationDepth`, `maxSchemaOperations`, `maxRegexLength`, `profileEvaluationTimeoutSeconds`, `profileWorkerMemoryBytes`, `maxNdjsonLineBytes`, `maxSignaturesTotal`, `maxProfileEvaluations`, `maxDiagnostics`, `maxReportRecords`, and `maxReportBytes`. Each is a JSON integer in its documented unit. All are at least 1 except that `maxJsonDepth` is at least 8, `maxReportRecords` is at least 64, and `maxReportBytes` is at least 65536; all MUST be no greater than their Section 15 bootstrap ceilings. `maxSchemaBytes` has the explicit aggregate-per-closure bootstrap maximum `268435456`, and `maxSchemaOperations` has the per-evaluation maximum `1000000000`. For v0.2, the complete static-unsatisfiability list is: `predicateTypes` contains neither core origin nor core transformation; source constraints are present without core origin; `operationTypes` is present without core transformation; source constraints and `operationTypes` occur in one rule; the signature threshold exceeds distinct authorized keys; a referenced key is absent; or a profile constraint has an illegal target/digest pairing. A rule that also lists extension predicates is valid only when at least one listed core predicate leaves the rule satisfiable; extension predicates never make a rule satisfiable by themselves because Section 11.1 excludes them from v0.2 bundle decisions. It MUST emit `W_POLICY_RULE_OVERLAP` when alternative rules overlap such that a less constrained rule subsumes a more constrained one. Duplicate members, conflicting requirements, impossible thresholds, invalid windows, unknown referenced keys, out-of-range limits, illegal array order, or a rule in that complete unsatisfiable set are invalid consumer configuration with exit code 2 before evidence evaluation. Valid-policy overlap warnings are retained through preflight and emitted in the completed verification report, including `--json`; they do not invalidate configuration because alternative authorization paths can be intentional.

1. A statement selects every rule whose `predicateTypes` contains the exact predicate type and whose optional source, operation-type, and signed-label profile constraints match under the rules above. One signed profile reference MAY satisfy multiple conjunctive constraints only when it independently matches every supplied member of each constraint.
2. Rules are alternatives, not cumulative. A selected rule becomes a candidate authorizing rule when it has signatures from at least `minimumSignatures` distinct authorized key IDs valid at evaluation time. Its digest-pinned profile constraints then become mandatory validation requirements for that candidate. The statement is authorized when at least one candidate rule has both its signature threshold and every digest-pinned constraint pass. A stricter selected rule that does not meet its threshold, or whose constraint is unavailable, does not impose that availability requirement through a different successful alternative. An evaluated false producer-signed profile remains a global `E_PROFILE_INVALID` under Section 12.4 and cannot be overridden by another rule. The report lists every successful `authorizingRuleId`. Processable envelopes already have unique key IDs, and threshold evaluation counts that distinct key-ID set; duplicate-key envelopes failed at Step 2.
3. An empty selected-rule set is denial. A partially matched rule grants nothing. Extra valid signatures neither help nor hurt unless a selected rule counts their distinct authorized keys.
4. The handoff uses the same threshold algorithm against the separate `handoff` rule.

For each statement report record, `candidateRuleIds` is the sorted set of selected rule IDs whose distinct-key threshold passed at Step 6, before any digest-pinned profile constraint is resolved or validated. A selector match whose threshold failed is not a candidate and is absent from this array. `authorizingRuleIds` is the sorted subset of `candidateRuleIds` whose digest-pinned constraints all passed after Step 7; it is empty when no candidate authorizes. Both arrays are duplicate-free and sorted by ID UTF-8 bytes. Phase 0 includes one selector match that fails threshold, one threshold-passing candidate that loses on a profile constraint, and one authorizing alternative so the three populations cannot be conflated.
5. Every consumer `requiredProfiles` entry is conjunctive and has `target: "artifact"`, `scope: "eachMatchingFinalArtifact"`, `id`, `digest`, `closureDigest`, `subjectName`, and `mediaType`. For every manifest artifact entry with that subject name, the artifact's declared head statement MUST contain the exact matching signed profile reference and that final artifact MUST validate successfully. Zero matching final artifacts or a matching head without the exact signed reference fails at Step 13 with `E_REQUIRED_PROFILE_MISSING`; if multiple heads hand off the same subject name, every matching final artifact must comply. A profile attached only to an intermediate or non-handed-off same-named subject never satisfies policy. A matching schema may be resolved from a bundle catalog only because its bytes match the consumer-pinned digest; the bundle catalog itself grants no trust.
6. v0.2 has no explicit deny-rule or first-match precedence. A future deny language requires a new trust-policy version.

Overlap lint is bounded, pairwise, syntactic, and mechanical. Consumer preflight accepts at most 1,024 statement rules and evaluates exactly `n * (n - 1)` directional `(A, B)` comparisons in ascending `(A.id, B.id)` order, excluding pairs where the IDs are equal. A policy above the rule-count ceiling is invalid consumer configuration and exits 2 before Step 1; it never emits a Step 0 or verification-time `E_RESOURCE_LIMIT`. The ceiling and complete comparison pass are part of policy preflight and cannot be weakened by consumer limits.

Rule `A` subsumes rule `B` only when: `A.predicateTypes` is a superset of `B`'s; `A.authorizedKeyIds` is a superset and `A.minimumSignatures <= B.minimumSignatures`; each optional `sourceKinds`, `sourceUris`, or `operationTypes` field is absent in `A` or, when present in `A`, is present in `B` and is a superset of `B`'s corresponding set; and every profile constraint in `A` matches at least one constraint in `B` under this per-member relation: `id` and `target` are exact, omitted root/closure digests in `A` match either paired digest state in `B`, and present digests in `A` match only the same exact root and closure digests in `B`. Thus omission is the universal set for overlap lint: omitted `A` subsumes supplied or omitted `B`, while supplied `A` never subsumes omitted `B`.

That subsumption is **strict** exactly when all preceding non-strict relations hold and at least one of these syntactic conditions holds: `A.predicateTypes` or `A.authorizedKeyIds` is a proper superset; `A.minimumSignatures` is lower; one optional selector field is absent in `A` but present in `B`; one optional selector field present in both is a proper superset in `A`; `B` has a profile constraint not used to match any constraint in `A`; or a matched constraint omits the digest pair in `A` and supplies it in `B`. No semantic URI relationship, schema implication, key equivalence, or data-dependent satisfiability is inferred. Only then emit `W_POLICY_RULE_OVERLAP` for ordered pair `(A.id, B.id)`.

Profile-constraint matching for that test is canonical and injective. Sort A and B constraints by `(id, target, digest-state, digest-or-empty, closureDigest-or-empty)`, where digestless sorts before digest-pinned and strings use UTF-8/ASCII rules. Process A in order; for each constraint, choose the first still-unused matching B constraint after sorting eligible B candidates by: exact same digest-state before digestless-A-to-pinned-B, then the full tuple above. If none exists, A does not subsume B. Strictness is computed only from this unique witness: unused B constraints and digestless-A-to-pinned-B matches trigger the stated strict conditions. No B constraint may satisfy two A constraints. Phase 0 pins identical-ID mixed digestless/pinned sets, reordered arrays, competing witnesses, and warning-ceiling counts.

Key revocation, certificate chains, identity federation, and transparency are out of scope for the v0.2 reference implementation. A local policy MAY remove a compromised key or constrain it with `validFrom` and `validUntil`. Those bounds are evaluated against the verifier’s current time or an explicit consumer-supplied evaluation time, never against the signer-asserted `event.occurredAt`. Backdating an event cannot restore authorization. Historical verification therefore requires an archived trust-policy snapshot or continued authorization of a retired public key; this is a conscious v0.2 operational limitation. A key can remain available for cryptographic verification while being unauthorized by the active policy.

The verifier establishes exactly one UTC `evaluationTime` during the fixed preflight sequence below unless the consumer supplies one explicitly. Key windows use the half-open interval `validFrom <= evaluationTime < validUntil`; an omitted bound is unbounded. The same instant drives all key-window and handoff-age checks and MUST be emitted in the report. Reproducing a time-sensitive decision requires supplying the recorded evaluation time and the same policy snapshot.

Preflight establishes time in this exact order: safe-open, snapshot, strict-parse, and core-schema-validate the consumer policy under bootstrap ceilings; parse and canonicalize an explicit consumer `evaluationTime` when present, otherwise read the system UTC wall clock once and truncate toward the past to an integer Unix second; then perform policy semantic/time-window validation, expected-value syntax and duplicate checks, the canonical expectation-object charge, consumer catalog/binding processing, and every remaining preflight operation. An implicit instant renders with `Z` and no fractional component. An explicit RFC 3339 instant preserves its exact mathematical fractional second after UTC conversion, removes trailing fractional zeros, and omits the decimal point only when the remaining fraction is zero; it is never truncated. The phrase “invocation evaluation time” refers to this establishment point, not process entry or completion of all preflight. Every key-window, age/skew, report, and accounting use shares that exact instant. A library implementation MUST use the same sequence and whole-second rule only for an implicit clock. Tests, reproducible verification, and boundary-sensitive consumers supply an explicit timestamp; Phase 0 pins nonzero fractions immediately before, at, and after key-window and age boundaries.

Each `keys` map value is a closed object with required `type` and `publicKey`, plus optional `label`, `validFrom`, and `validUntil`; unknown members are invalid configuration. The enclosing map key is the declared key ID and no duplicate `keyid` member exists inside the value.

Consumer `requiredProfiles` conflict preflight is complete and narrow. Exact duplicate requirement tuples are invalid duplicates. Two distinct entries are statically conflicting only when they have the same `subjectName` and different `mediaType`, because both are conjunctive over every same-named final artifact while Section 12.4 permits only one signed parser media type per subject; that policy exits 2. Different IDs or digests with the same media type are not preflight-conflicting because one head may sign and satisfy both schemas. Authorization-rule profile constraints remain candidate-local and are not compared across alternative rules. Every other incompatibility discovered only from producer evidence is an exit-1 verification denial, not invalid consumer configuration.

Overlap-warning discovery has its own immutable preflight ceiling of 10,000 warnings. Directional pairs are evaluated in ascending `(A.id, B.id)` order; if discovery would produce warning 10,001, the policy is invalid consumer configuration and exits 2 with no verification report and no partial warning output. `policy check --json` follows the same all-or-nothing rule. For a policy that stays within the warning ceiling, preflight completes all `n * (n - 1)` directional comparisons and retains the complete sorted warning set. This exit-2 condition occurs before the Step 0 diagnostic population exists and therefore never emits Step 0 `E_RESOURCE_LIMIT` or consumes the verification-time 100,000-diagnostic ceiling.

## 15. Verification algorithm

The reference verifier MUST perform checks in this order and MUST collect all safely discoverable failures rather than stopping after the first malformed item:

For every consuming open in Steps 2, 4, 8, and 12, the completed Step 1 inventory fixes absence ownership. A role target absent from that inventory uses the role-specific absence code. A target recorded present that later disappears, is replaced, becomes unreadable or wrongly typed, develops an alias/containment failure, or fails descriptor validation uses `E_BUNDLE_UNSAFE_PATH` at the consuming step. This rule controls any later shorthand phrase such as “target disappears before open.”

Aggregate profile-worker wall time is the sum of the individual monotonic intervals from immediately before each worker process creation through that worker's validated result and successful exit/reap. No time between workers—and therefore no graph, anchor, artifact-hashing, or report work in Steps 9–12—is charged to this aggregate. The aggregate remains bounded by the lesser of 300 seconds and `maxProfileEvaluations * profileEvaluationTimeoutSeconds`.

Before consumer policy can be parsed, immutable bootstrap ceilings apply: at most 20,000 filesystem entries; 16 MiB per raw metadata/index/policy/catalog/schema file; 256 MiB aggregate metadata accounting; 2,000,000 JSON structural/scalar tokens per metadata or schema document and 8,000,000 across the invocation; 1 TiB per artifact file; 2 TiB aggregate artifact input; 2 TiB aggregate immutable artifact snapshots; 1 GiB `maxArtifactValidationBytes` per structured artifact; JSON depth 256; 4096 schema resources per closure; schema-evaluation depth 1024; 65,536 Unicode scalars per regex-keyword occurrence; 60 seconds and 4 GiB per profile worker; 300 seconds cumulative active-worker time per invocation; 64 MiB per physical NDJSON line; 4096 characters per JSON number token; absolute decimal exponent at most 100000; 100,000 signature entries/verifications; 100,000 profile evaluations/worker launches; 100,000 diagnostics; 200,000 report detail records; 256 MiB serialized report bytes; path limits from Section 13.3; and base64 decoded lengths checked before allocation. A JSON token for these ceilings is one `{`, `}`, `[`, or `]`; one object-member name string; or one scalar string, number, `true`, `false`, or `null`; commas and colons add no token. The strict streaming tokenizer enforces file and aggregate token ceilings before allocating the corresponding object/member/scalar. Parsed consumer limits may only tighten the configurable ceilings; the token ceilings are immutable v0.2 bootstrap limits. `maxBundleFiles` counts every file, directory, and other discovered entry beneath the bundle root. `maxArtifactBytesPerFile`, `maxAggregateArtifactBytes`, and `maxSnapshotBytes` govern every provided final, historical, dataset-manifest, and dataset-entry artifact whether or not a profile applies; size accounting occurs before or while copying bytes into the immutable snapshot and stops at the first exceeded bound. `maxSchemaBytes` is aggregate per profile evaluation closure and counts the exact raw bytes of the root schema, every distinct declared non-core resource, every distinct immutable Makoto core resource reached by `$ref`, and every distinct vendored standard meta-schema reached during dialect meta-validation, each unique registry `(id, digest.sha256)` charged once; `maxSchemaResources` counts that same identity set. The signed `resources` closure descriptor still excludes immutable core and standard resources because it binds producer-selectable dependencies rather than verifier-selected resource cost. `maxSchemaEvaluationDepth` is per evaluation, `maxRegexLength` has the per-keyword decoded-scalar meaning in Section 12.1, `profileEvaluationTimeoutSeconds` and `profileWorkerMemoryBytes` are per profile worker, `maxArtifactValidationBytes` is per structured artifact, and JSON numeric limits apply before arbitrary-precision conversion. `maxNdjsonLineBytes` counts bytes after the preceding LF or byte zero and before the terminating LF, including a CR that will later be stripped; for an unterminated final line it counts from the last LF or byte zero through end of file. Schema-evaluation depth starts at 1 for the root schema evaluation and increments for each applicator child, reference target entry, or recursive re-entry; sibling evaluations reuse their parent's depth. The worker timeout uses a monotonic clock from immediately before process creation through validated receipt of its final result and successful child exit/reap, so interpreter startup and teardown are included. A child that returns a result but does not exit and reap before the deadline is terminated, reaped, and treated as the applicable timeout resource result; its returned result is discarded. Invocation aggregate profile time uses the cumulative active-worker sum defined above and is the lesser of 300 seconds and `maxProfileEvaluations * profileEvaluationTimeoutSeconds`; reaching it produces `E_RESOURCE_LIMIT` for the current profile and skips remaining profile work. `profileWorkerMemoryBytes` is the maximum virtual address space mapped by that worker process, including interpreter and native-library mappings; the parent configures an OS-enforced address-space/job-object limit before untrusted evaluation begins. Memory exhaustion and wall-clock timeout are operational resource results whose exact occurrence can vary by implementation/host; conformance fixtures remain below both and cross-implementation semantic equality assumes those resource assumptions are satisfied. Crossing time or memory bounds produces the applicable resource result from Section 12.4. Schema/regex evaluation and all untrusted structured-artifact parsing occur only inside that boundary, using streaming input and the linear-time evaluator defined in Section 12.1; the worker returns only the bounded status and diagnostic context, never the decoded artifact tree. Protocol, policy, catalog, bundle-index, and schema metadata remain parent-parsed only after the strict tokenizer has enforced the raw-byte, token, depth, number, and aggregate ceilings above.

`maxSchemaOperations` is required, is a JSON integer from 1 through the immutable bootstrap maximum 1,000,000,000, and applies to each charged `maxProfileEvaluations` unit. Consumer policy may tighten but not exceed that maximum. For a statement, predicate, or monolithic artifact profile, the unit covers closure dialect/meta-validation plus the one target-instance evaluation. For NDJSON, the first unit covers closure work plus the first nonblank instance and each later nonblank instance receives a fresh counter under its separately charged unit. Cached closure or evaluation work never refunds the logical count. The counter begins at zero; immediately before an operation, the worker fails that unit with the applicable resource-limit result when incrementing would exceed the configured value, and the operation is not performed.

For an ordinary organizational profile unit, `maxSchemaBytes`/`maxSchemaResources` accounting includes the exact `schemas/v0.2/profile-dialect.schema.json` bytes and its one resource identity selected by the profile root's `$schema`, even though that relationship is not a `$ref`. For the mandatory dataset-manifest direct-root exemption only, the Makoto profile-dialect resource is not used and is not charged; instead charge the exact immutable `dataset-manifest.schema.json` root plus the generic Draft 2020-12 dialect/meta resources actually selected or reached from that root, each distinct `(id, digest)` once. In both cases, then charge the producer/root resource, declared non-core resources when allowed, every Makoto core resource reached by `$ref`, and every vendored standard meta-schema reached by `$ref` or `$dynamicRef`, without double-charging an identity already counted. Verifier-selected dialect resources remain excluded from the producer-signed closure descriptor. Boundary fixtures set remaining bytes/resources immediately below, at, and above both the ordinary Makoto-dialect population and the dataset exemption population.

The Phase 0 streaming tokenizer uses this charge-on-completion state machine. Before scanning a prospective token, it checks raw-byte and token-capacity bounds. An opening or closing structural byte commits one token when that byte is consumed. A member-name string commits one token only after its closing quote, all UTF-8/escape/scalar checks, and its following optional JSON whitespace plus required colon have succeeded. A scalar string commits only after its valid closing quote; `true`, `false`, and `null` commit only after the full literal and a legal following delimiter or end of input; a number commits only after its complete RFC 8259 lexical form, number-character/exponent checks, and a legal following delimiter or end of input. The tokenizer checks capacity immediately before each commit; if no capacity remains, it returns resource limit without committing or allocating that token. An invalid or incomplete lexeme never commits a token. On duplicate object names, the second complete member-name token is committed and then duplicate detection fails before its value is read. Already committed tokens are never rolled back after a later syntax failure. The following traces are normative, where `N` is the count entering the shown source and the whole shown source is one document: `01` fails with count `N`; `1e` fails with `N`; `"\\q"` fails with `N`; `0 x` commits the complete root number and then trailing garbage fails with `N+1`; `[0` commits `[` and `0` then truncation fails with `N+2`; `{"a":0,"a":1}` commits `{`, the first name, `0`, and the duplicate second name then fails with `N+4`; and `{"a":0}x` commits all four valid document tokens before trailing garbage fails with `N+4`. Phase 0 includes exact per-document and invocation-boundary fixtures for each trace at limit minus one, limit, and limit plus one, and the dataset/profile worker `tokenCount` uses this same state machine.

For byte-level avoidance of doubt, the invalid-escape trace is exactly hexadecimal `22 5c 71 22` (quote, one reverse solidus, `q`, quote); the code-span escape spelling above is not permission to insert a second reverse solidus byte.

Worker-result metadata capacity is reserved before process creation, in canonical profile order. The parent temporarily reserves the complete bounded-result capacity—64 MiB for a dataset-manifest worker and 1 MiB for an ordinary profile worker—from the then-remaining consumer `maxMetadataBytes`; reservation is not yet a permanent charge, and workers remain sequential in v0.2. If the complete capacity cannot be reserved, no worker starts: the current profile takes `resource_limit`, one owning `E_RESOURCE_LIMIT` is emitted at its Step 7, 8, or 13 check, that owning aggregate fails, and every later canonical profile is skipped under that check. After a child exits, the parent reads at most reserved capacity plus one byte, validates the exact IPC bytes and internal result schema, permanently charges only the valid result's exact JCS byte length, and releases the unused reservation. A conforming child that cannot represent its evidence within the reserved capacity returns a minimal in-capacity `resource_limit` result. A child that writes more than the reservation, produces a result whose validated JCS bytes exceed it, or violates the result schema is a trusted-tool invariant failure with exit 3; it is not converted into evidence `E_RESOURCE_LIMIT`. Any later shorthand that says the IPC ceiling is exceeded refers to the conforming child's bounded `resource_limit` response before crossing this capacity, not acceptance of oversized IPC. Phase 0 covers exact remaining-metadata values of capacity minus one, capacity, and capacity plus one for both worker types, plus an intentionally oversized child result that must exit 3.

Structured-artifact token capacity is also reserved before launch. A monolithic JSON or dataset-manifest worker receives `min(536870912, remaining invocation structured-artifact tokens)`; an NDJSON worker receives all remaining invocation structured-artifact tokens and enforces the per-line ceiling separately; a statement/predicate-only worker reserves zero because those exact instances were parent-tokenized. Inability to reserve at least one token for a nonempty structured artifact is invocation-wide exhaustion and follows the fatal aggregate rule below. A valid IPC result permanently charges its reported `tokenCount` and releases the unused token reservation. If timeout, OS-enforced memory termination, or another operational kill prevents a valid result, the parent permanently charges the complete reserved structured-token capacity because the exact consumed count is unknowable; later work sees that deterministic remainder. The profile takes its applicable resource-limit state. Phase 0 uses a killable test worker to prove full-reservation charging and identical later-profile outcomes.

For dataset-manifest work, the bounded worker returns exactly one closed IPC object: `{"diagnostic":<null-or-diagnostic>,"entries":[{"digest":{"sha256":<64-lowercase-hex>},"name":<string>,"size":<decimal-string-or-null>}...],"phase":<"complete"|"parse"|"schema"|"semantic">,"status":<"pass"|"invalid"|"resource_limit">,"tokenCount":<nonnegative-integer>}`. A diagnostic is exactly `{"code":<stable-code>,"context":<the code-specific closed context object from diagnostic-map.json>}`. `status: "pass"` requires `phase: "complete"`, `diagnostic: null`, and the sorted unique pass `entries`; `status: "invalid"` requires phase `parse`, `schema`, or `semantic`, one `E_DATASET_MANIFEST_INVALID` diagnostic whose closed context names that trigger, and `entries: []`; `status: "resource_limit"` requires the exact phase in which the limit was hit, one `E_RESOURCE_LIMIT`, and `entries: []`. The parent maps invalid `parse` to mandatory-profile resolution `pass` and validation `skipped`, invalid `schema` to validation `fail`, and invalid `semantic` to validation `pass` plus failed dataset evidence, exactly matching Step 8. A resource limit in parse or schema leaves validation skipped; a semantic-phase resource limit retains the already completed validation pass. `tokenCount` is always present and is the exact number of structured-artifact JSON tokens consumed by that attempt: a pass reports the complete parsed document count, an invalid result reports the count consumed through deterministic failure discovery, and a resource-limit result reports the count successfully consumed before the next token would exceed the reserved bound. It is zero only when no structured-artifact token was consumed. The parent validates the complete object against the checked-in immutable internal schema `src/makoto/internal-schemas/dataset-worker-result.schema.json`, whose SHA-256 is asserted by `scripts/check.sh`, rejects a `tokenCount` above the capacity reserved before launch, and charges that count once to the invocation structured-artifact token budget. It also charges the complete exact JCS byte length—including `phase` and `tokenCount`—once to aggregate `maxMetadataBytes`. The 64 MiB IPC ceiling applies to that complete JCS object; the 200,000-entry ceiling applies to `entries`. If evaluation would require crossing either ceiling, a conforming child returns the bounded semantic-phase or current-phase `resource_limit` result before crossing it; actual oversized IPC remains exit 3 under the reservation rule. No status, count, phase, or diagnostic field is out-of-band or uncharged, the worker never returns arbitrary decoded artifact fields, and Steps 9 and 12 use only a validated pass index without reparsing dataset-manifest bytes.

Profile evaluation uses one canonical, non-short-circuit traversal plan so resource outcomes do not depend on host-library strategy. At each schema location, dispatch `if` first when present, immediately evaluate its child, then dispatch exactly the selected `then` or `else` child when present; omit the unselected branch entirely. After that conditional group, visit every remaining applicable keyword by UTF-8 keyword-name order, excluding `if`, `then`, and `else` because their complete dispatch occurred in the group. Schema arrays use signed array order; evaluation-bearing schema maps such as `properties` and `dependentSchemas` use UTF-8 member-name order; instance arrays use ascending index; and instance object members use UTF-8 name order. `$defs` is traversed only during load-time closure/schema validation in UTF-8 member-name order and is never dispatched or entered merely because it is present during instance evaluation; a `$defs` member is instance-evaluated only when reached through an applicator or reference. Every applicable sibling and every branch of `allOf`, `anyOf`, and `oneOf` is evaluated even after the boolean result is known; `not` evaluates its sole child; `contains` evaluates every array element; and every ordinary `$ref` target is entered at its canonical keyword position. Annotation collection for `unevaluatedItems` and `unevaluatedProperties` follows Draft 2020-12 over the complete preceding results. Resource charging and the first depth/operation failure follow that same traversal. Phase 0 vectors cover conditional keyword order, unused and referenced `$defs`, deep valid/invalid alternate branches, map reordering, `contains`, references, and unevaluated vocabularies.

Schema-operation units are abstract and independent of host-library optimizations. Charge one unit for each entry into a `(schema resource ID, schema JSON Pointer, instance JSON Pointer)` evaluation pair, including boolean schemas; one for each applicable keyword dispatched at that pair, including annotation-only keywords; one for each evaluation-bearing schema-array element, schema-map member, instance-array element, or instance-object member examined by that keyword; and one for each JSON node pair visited by `const`, `enum`, or `uniqueItems` deep equality. Load-only `$defs` traversal is charged to the enclosing profile unit as one operation per visited schema-map member and schema location but never creates an instance-evaluation pair unless referenced. Within a deep comparison, visiting an array element or object member value is one node-pair unit; comparing object name sets additionally costs one unit per key pair plus one per Unicode scalar examined in both keys through first difference or end; comparing a string costs one additional unit per Unicode scalar examined through first difference or end; and comparing a number costs one additional unit per character in both original strict-JSON number tokens. String-length and substring keywords charge one unit per instance Unicode scalar examined. Each exact numeric validation keyword additionally charges `1 + coefficient-digit-count(instance) + coefficient-digit-count(schema value) + absolute(exponent(instance) - exponent(schema value))` units before its arithmetic result. `makotoPattern` charges one unit for every NFA state configuration visited at each input-scalar position, including start/terminal/anchor/epsilon visits; duplicate configurations at the same position are visited once, active states are processed by ascending compiled state index, and unanchored search injects the start state before existing states at each position. Keyword dispatch and all these inner units are cumulative. Phase 0 publishes executable operation-count traces at limit minus one, limit, and limit plus one for boolean schemas, conditional dispatch, unused/referenced `$defs`, nested applicators, object-name equality, `contains`, `uniqueItems`, exact numbers, long strings, and `makotoPattern`; the reference counter oracle, not a host validator's private work metric, determines `E_RESOURCE_LIMIT`.

For operation charging, decompose one original strict-JSON number token without normalization. Remove an optional leading `-`; the coefficient spelling is every decimal digit before and after the optional decimal point, preserving all written zeros; `coefficient-digit-count` is that spelling's length. The exponent is the signed base-10 integer written after `e` or `E`, with omitted exponent equal to integer zero; exponent sign and leading zeros do not change its integer value. Thus `1.0` has coefficient `10` and exponent `0`; `1e0` has coefficient `1` and exponent `0`; `0.10` has coefficient `010` and exponent `0`; `-0` has coefficient `0` and exponent `0`; and `10e-1` has coefficient `10` and exponent `-1`. Deep-equality number-token character charging counts every byte of the two complete original tokens, including sign, decimal point, exponent marker, and exponent sign. Phase 0 publishes exact counts for those five spellings and cross-spelling equal-value pairs.

The default inner-operation rule closes every supported keyword not given a more specific rule: each scalar/cardinality/boolean value read from the instance or schema costs one unit, each membership or property-name lookup costs one unit, each schema/instance collection member examined costs one unit, and each annotation value or evaluated-location set member propagated/merged costs one unit. Thus `required` charges one lookup per required name after dispatch; `minProperties`/`maxProperties` and `minItems`/`maxItems` each charge one cardinality read; `properties`, `propertyNames`, `additionalProperties`, `dependentSchemas`, `unevaluatedProperties`, items applicators, and unevaluated-items processing charge each candidate member/index plus child entry; `minLength`/`maxLength` use the already specified complete scalar scan; numeric assertions use the exact numeric rule; `type` charges one instance-type read plus each allowed-type candidate examined; and annotation-only scalar keywords charge one value read after dispatch. A more specific rule replaces, rather than adds to, the corresponding default inner unit unless it explicitly says cumulative; entry-pair and keyword-dispatch units always remain cumulative. Phase 0's counter oracle MUST list every supported keyword with its dispatch unit, applicable default/specific inner rule, annotation/set propagation, and exact valid/invalid traces; an unlisted supported keyword blocks Phase 1.

“Applicable keyword” for operation charging means every lexically present keyword at the visited schema location that is defined by the active pinned vocabularies, regardless of the instance's JSON type; a type-inapplicable keyword dispatches its one unit, performs no inner units, and has its Draft-defined neutral result. Load-time-prohibited or unknown keywords never reach instance evaluation. Candidate loops never short-circuit after their boolean result is known: `enum` compares every candidate in signed array order; `uniqueItems` compares every pair `(i,j)` in lexicographic order with `0 <= i < j < length`; `required` examines every name in signed array order; `dependentRequired` examines trigger names by UTF-8 schema-map order and every dependency name in signed array order; type arrays, property maps, item arrays, `contains`, and every combinator use their existing canonical complete order. Deep equality compares types first; arrays compare length then elements ascending until the first unequal child; objects compare UTF-8-sorted name sets then values in that order until the first unequal child; each individual comparison may stop at its first determined inequality, but outer `enum`/`uniqueItems` candidate enumeration continues. String length scans the complete scalar sequence even after a bound is known. The `makotoPattern` evaluator continues through the complete instance scalar sequence and all canonical active configurations after the terminal state first proves a match; it remembers the true result but does not stop charging. Phase 0's coverage matrix MUST provide an exact operation-count trace for every supported keyword, not only representative examples, and Phase 0 cannot exit until the independent counter oracle and reference evaluator agree on all traces.

Compiled NFA state numbering is normative for operation order. During left-to-right AST compilation, allocate all split states for an alternation when that operator is entered, in left-associative source-branch order, then compile branches left to right; allocate a `?`, `*`, `+`, or generated optional/star split when that quantifier fragment is entered, then compile its copied atom; compile required/generated copies left to right; allocate each literal/dot/class/anchor state when its atom is visited; and allocate the sole terminal match state last. Concatenation and groups allocate none. The virtual unanchored-search start configuration is not one of the counted compiled states and is processed before state 0 at each input position. Split targets follow source/body before bypass/next order. Active compiled configurations are then processed by ascending state number. The state-count and operation traces expose these numbers, so no implementation may substitute a different numbering while claiming the same near-limit result.

Pattern execution has `length + 1` canonical input positions numbered `0` through `length` inclusive, where `length` is the instance Unicode-scalar count. Empty input therefore has the sole position 0. At each position, first inject the virtual unanchored-search start configuration, then compute/process epsilon and anchor closure in canonical state order and test the terminal match state. At positions strictly less than `length`, process consuming transitions for that position's scalar to seed the next position; at the final position `length`, perform no consuming transition but still process start, `^`/`$`, epsilon, and terminal configurations. `^` succeeds only at position 0 and `$` only at position `length`. Every injected/visited configuration is charged under the existing operation rule, including the final end position after an earlier match. Phase 0 pins empty and nonempty traces for `a{0}`, `a{0,0}`, `a{0,}`, `$`, `^$`, unanchored empty matches at the end of nonempty input, and anchored failures, with exact state/operation sequences.

The immutable aggregate bootstrap maximum for `maxSchemaBytes` is 268435456 bytes per profile closure; the 16 MiB raw-file ceiling still applies independently to every schema resource file.

JSON-token accounting is by strict parse attempt, with the logical identity including the profile evaluation so isolated workers never require a shared parsed tree. A physical metadata/schema file is charged once per opened physical identity; a decoded DSSE payload once per `(envelope physical identity, decoded payload digest)`; a monolithic structured-artifact snapshot once per `(artifact identity, profile identity)`; and each nonblank NDJSON line once per `(artifact identity, profile identity, physical line number)` while its tokens also contribute to the invocation aggregate. Reusing one schema resource within one closure never adds a second charge, but evaluating the same artifact against two distinct profiles performs and charges two deterministic parses. A cached mandatory dataset-manifest result reused at Steps 9, 12, and 13 is the same profile evaluation and is not parsed or charged again. Metadata and schema parsing has immutable ceilings of 2,000,000 tokens per document and 8,000,000 metadata/schema tokens per invocation. Structured-artifact parsing instead has immutable ceilings of 536,870,912 tokens per monolithic JSON artifact or nonblank NDJSON line and 1,073,741,824 structured-artifact tokens per invocation. Workers reserve the remaining structured-token capacity before launch, return their exact attempt count, and the parent permanently charges it under the worker-result rules. Phase 0 uses one artifact with two profiles plus mandatory-result reuse to pin two independent parse charges, fail-fast NDJSON line populations, and zero reuse charge for the identical cached profile result.

Structural parsing may enumerate signature entries only up to the immutable 100,000-entry bootstrap ceiling before manifest class and payload identity are known. It records their opened-envelope identity and original index without cryptographic work. After Step 4 has classified every safely enumerable envelope, the verifier sorts the recorded entries by the total-signature tuple and applies the consumer `maxSignaturesTotal` limit once, at Step 4, before Step 5. Overflow emits `E_RESOURCE_LIMIT` owned by `core-schemas`, leaves later signature/authorization-dependent work skipped with `core-schemas` as prerequisite, and never temporarily exceeds the bootstrap ceiling.

Resource accounting is exact. Each distinct physical metadata file successfully opened under the no-link rules is charged once at its raw byte length, even when identical bytes occur in another file; each decoded DSSE payload and each base64-decoded signature is additionally charged once at decoded length. Consumer metadata includes the policy, catalog files and resources, expected-value binding files, artifact-material binding files, dataset-entry binding files, and any other consumer JSON binding; the artifact bytes named by a binding are not metadata. Every parsed signature array entry counts once toward `maxSignaturesTotal`, including quarantined envelopes and known or unknown keys; each configured-key cryptographic attempt is part of that same bounded count. `maxProfileEvaluations` charges exactly one unit for a statement target, predicate target, or monolithic JSON artifact. For one NDJSON profile record with `N` nonblank instances, the maximum possible charge is `max(1, N)`; the exact charge is one for closure/zero-instance/format failure before line enumeration, otherwise the number of nonblank lines whose unit was reserved through the first fail-fast outcome. A 100-instance file failing on the third nonblank line therefore charges exactly three, not 100. The first nonblank line uses the fused closure reservation and the worker consumes one additional reserved unit immediately before each second or later nonblank line is opened. Inability to consume a later unit makes that unopened line and all remaining lines the applicable resource-limit outcome. Identical line bytes still count separately, and cache reuse never refunds a unit. Closure loading/caching and worker launch add no separate units; one worker is launched per profile record and may process its bounded NDJSON instances, so launches cannot exceed profile records. The reference verifier runs at most one profile worker at a time in canonical profile order; another implementation MAY parallelize only while enforcing the same aggregate concurrency ceiling of one v0.2 worker, so `profileWorkerMemoryBytes` is also the aggregate profile-worker-memory bound. Cached execution MAY reduce work but never reduces the charged logical count. JSON depth, token, number-token, exponent, and duplicate-key limits apply equally to protocol, schema, monolithic artifact, and NDJSON JSON. Every warning/error counts toward `maxDiagnostics`. Every element of `statements`, `profiles`, `artifacts`, `datasetEntries`, `unindexedEnvelopes`, `quarantinedStatements`, and `unreferencedFiles` is a report-detail record charged during the Step 14 admission pass defined below, not a gate on evidence discovery. A schema resource selected repeatedly by the same `(id, digest)` is charged once per profile closure, while distinct catalog paths containing identical bytes are still distinct raw-file charges. Parsed metadata-object overhead is bounded by the raw-byte, token, depth, and aggregate ceilings and is not charged again as synthetic bytes; decoded structured-artifact trees never enter the parent process. After bootstrap parsing, a tighter consumer `maxMetadataBytes` is applied to all consumer metadata already read; if it already exceeds the chosen value, configuration exits 2. Bundle metadata then adds to the same invocation total and excess produces `E_RESOURCE_LIMIT`. Consumer and bundle artifact sources are opened and copied only at their canonical Step 8 or Step 12 position; `maxArtifactBytesPerFile`, `maxAggregateArtifactBytes`, and `maxSnapshotBytes` apply before and during that copy. `maxAggregateArtifactBytes` charges source artifact bytes read; `maxSnapshotBytes` separately charges the immutable copies, so one artifact normally consumes its length in each independent budget. Limits are checked before the next logical byte allocation/write, and the first exceeded check's algorithm step is deterministic. Profile invalidity emits one stable `E_PROFILE_INVALID` per profile identity; individual keyword failures are non-normative human detail, so no cross-implementation validation-error truncation order affects the report. Phase 0 pins mid-file NDJSON failure charges before later-profile exhaustion boundaries.

Snapshot copying and streaming digest verification are governed only by `maxArtifactBytesPerFile`, `maxAggregateArtifactBytes`, and `maxSnapshotBytes`. Accounting uses a normative logical quantum of one source byte regardless of OS read-buffer or hashing chunk size. Before committing each logical byte from an implementation buffer, test whether that byte would cross any limit; when the same byte would cross more than one, the single `E_RESOURCE_LIMIT` context selects the first in the order above. That byte and every later buffered byte are not committed to any counter, hash state, or snapshot, and no second diagnostic is emitted for the same attempted byte. `maxArtifactValidationBytes` and `maxNdjsonLineBytes` are later bounded-parser/profile limits and never interrupt or roll back an otherwise permitted snapshot or digest. After the complete snapshot digest passes, Step 8 or Step 13 checks total snapshot length against `maxArtifactValidationBytes` before parser launch; only if that passes does NDJSON splitting enforce `maxNdjsonLineBytes`. Thus a snapshot exceeding both parser limits reports the total validation-byte limit first, while its already completed `digestStatus` remains unchanged. Phase 0 runs identical simultaneous-boundary vectors through at least 4 KiB, 1 MiB, and 32 MiB physical read buffers and requires identical counters and diagnostics.

Total signature accounting expands the preceding rule. Every parsed signature-array entry counts once, including the handoff, manifest-listed statements, unindexed envelopes whose signature array is structurally enumerable, and quarantined envelopes, regardless of known or unknown key or later verification eligibility. The accounting order is `(envelopeClass, payloadDigest-or-safePath, keyid, signatureIndex)`, with envelope classes ordered `handoff`, `manifest-listed`, `unindexed`, `quarantined`; the payload component is the 64-character lowercase hexadecimal digest when established and otherwise the NFC safe logical path; an absent or structurally unusable `keyid` sorts as the empty string, while a usable key ID sorts by UTF-8 bytes; and `signatureIndex` is the zero-based original array position, including when equal key IDs will later make an envelope malformed.

A raw signature-array entry is “structurally enumerable” exactly when the strict streaming tokenizer has established the unique top-level `signatures` member, consumed its array opener, and committed that element's complete JSON value under the charge-on-completion rules. For the required object form, its closing `}` token must have committed; an element truncated before closure, a value in an unestablished/duplicate/wrong-typed member, or an element beyond the first syntax failure does not count. A later syntax or envelope-schema failure never rolls back already committed entries. The accounting sort shorthand expands to `(envelopeClass, identityKind, identityValue, keyid, signatureIndex)`, where `identityKind` is `digest` before `path`, digest values use lowercase-hex ASCII bytes, and paths use NFC UTF-8 bytes. This tag prevents a 64-hex-looking path from tying a digest identity. Phase 0 traces partial first/later entries and limit boundaries.

`maxReportRecords` additionally counts every element in these nested variable-length collections: handoff signatures; expected heads; actual heads; expected artifacts; roots; each statement signature, `candidateRuleIds`, `authorizingRuleIds`, `coreSchemaPrerequisiteChecks`, `authorizationPrerequisiteChecks`, and `graphPrerequisiteChecks`; each profile `requiredByAuthorizationRuleIds` and `prerequisiteChecks`; each artifact `digestPrerequisiteChecks` and `profilePrerequisiteChecks`; and each dataset entry `digestPrerequisiteChecks` and `sizePrerequisiteChecks`. The fixed sixteen top-level check objects together with all of their prerequisite arrays form the non-truncatable report skeleton and do not count as report records. Fixed scalar/object fields, summaries, and diagnostic entries likewise do not count as report records; diagnostics have their own admission limit below.

Report admission is a two-pass Step 14 operation after all evidence work permitted by the non-report budgets has completed. The verifier first builds the complete internal semantic report, summaries, fixed checks/prerequisites, diagnostic candidates, and detail populations under immutable bootstrap bounds. Diagnostic candidates include retained Step 0 warnings and all later warnings/errors, are deduplicated only when their complete stable sort tuple is identical, and are sorted by the Section 16.3 diagnostic order. Because human `message` is not part of that tuple, the retained message for otherwise identical candidates is implementation-defined and MUST NOT appear in conformance comparisons. The verifier first projects the complete report with all diagnostics and detail. If it satisfies `maxDiagnostics`, `maxReportRecords`, and `maxReportBytes`, everything is admitted, no terminal resource diagnostic exists, and `reportTruncated` is false. Otherwise it enters truncation mode and reserves one fixed minimal Step 14 `E_RESOURCE_LIMIT` owned by `decision` in both diagnostic count and projected bytes. For diagnostic-prefix admission, the candidate report is exactly the fixed skeleton/scalars/summaries, the candidate ordinary diagnostic prefix, and the reserved terminal diagnostic, with every detail population empty; the omitted diagnostic suffix and all detail are absent from this projection. It retains the longest diagnostic prefix whose candidate report fits and whose ordinary length is at most `maxDiagnostics - 1`; the reservation then becomes the final diagnostic, `decision` fails, and `reportTruncated` is true. Because every ordinary diagnostic has step 0–13 and the terminal has Step 14, the retained diagnostics remain canonically sorted. Diagnostic admission never changes already computed evidence statuses or marks evidence work skipped. The immutable 100,000-candidate evidence-discovery ceiling also reserves one slot from the beginning: at most 99,999 ordinary candidates may exist. When an operation would create the 100,000th ordinary candidate, that ordinary candidate is suppressed, the 100,000th and final candidate is instead one `E_RESOURCE_LIMIT` owned by the current operation's step/check, and only dependent discovery stops. No further candidate is created, and that bounded resource candidate participates in the same Step 14 admission pass. After the merged admitted diagnostic sequence is fixed, entries are partitioned by their immutable error-or-warning class into top-level `errors` and `warnings`, preserving relative order from the merged sequence within each array and performing no second sort. A fixture covers same-step error and warning candidates, including the ASCII code ordering before partition.

After diagnostics are fixed, the verifier considers detail units in this exact global sequence, independent of JSON object-member order: (1) handoff signatures; (2) expected heads; (3) actual heads; (4) expected artifacts; (5) roots; (6) statement units; (7) profile units; (8) artifacts; (9) dataset entries; (10) unindexed envelopes; (11) quarantined statements; and (12) unreferenced files. The complete fixed checks and their prerequisite arrays are already present in the non-truncatable skeleton. Each population uses its Section 16.3 sort. A statement unit is its parent record plus all signature, rule-ID, and statement-prerequisite elements; a profile unit is its parent plus all authorization-rule and profile-prerequisite elements; an artifact or dataset-entry unit includes its parent plus its field-specific prerequisite elements. Parent units are atomic: the parent and all children are either admitted together or all omitted. Other entries are one atomic unit each. For each unit, both its full record charge and the `maxReportBytes` stable projection of the candidate admitted report MUST fit before it is admitted. The candidate admitted report consists of the fixed skeleton/scalars/summaries, the already admitted diagnostics including any reserved terminal, the already retained detail prefix, and the candidate unit; the omitted suffix is not part of that projection. The projection is RFC 8785 JCS bytes plus the required final LF. The retained detail is the longest prefix of this sequence that fits; the verifier never skips an oversized unit to retain a later smaller one. An implementation MAY use incremental byte accounting or another optimization only when it is proven to produce exactly the same admission decision as serializing each defined candidate report. At the first over-limit unit, the already reserved Step 14 terminal diagnostic is materialized (replacing any prior terminal with the same fixed tuple), `decision` fails, `reportTruncated` becomes true, and that unit plus the remaining suffix are omitted. Admission never retroactively changes computed evidence/check statuses and never produces a skipped status without its complete field-specific or top-level prerequisite array.

All summary counters are nullable. A counter is an integer, including zero, only when its entire logical population was safely computed; zero means a completed empty population. It is `null` whenever a failed prerequisite or resource truncation prevented computation of that population. Detail omission after a population was fully computed does not erase its integer summary. Phase 0 report-schema and truncation vectors MUST cover pre-reachability failure, a computed empty population, truncation before population discovery, truncation after discovery, and an atomic parent unit that does not fit.

After bootstrap parsing, the verifier reapplies the consumer policy `maxMetadataBytes`, `maxJsonDepth`, `maxJsonNumberChars`, and `maxJsonExponentMagnitude` to every consumer metadata file already read. Preflight validates each consumer catalog's own structure, safe resource paths, resource bytes/digests, and `$id` values, but it does not choose or load any profile closure: a profile closure is resolved only when a signed statement, authorization candidate, or consumer requirement selects it at Step 7, 8, or 13, after bundle-catalog resources are also available. Closure dialect, exact-membership, missing-resource, and `maxSchema*` failures therefore produce a completed evidence report and the applicable profile diagnostic; they never turn into exit 2 merely because some bytes came from a consumer catalog. Preflight validates declared consumer artifact sizes against `maxArtifactBytesPerFile`, `maxAggregateArtifactBytes`, and `maxSnapshotBytes` without copying their contents; the canonical Step 8/12 copy rechecks and charges actual bytes. Exceeding a self-declared metadata limit makes consumer configuration invalid and exits 2. A consumer artifact that already exceeds a chosen artifact limit is also invalid configuration and exits 2; a size race or excess discovered only during the canonical evidence copy is completed `E_RESOURCE_LIMIT` at Step 8 or 12. Step 0 overlap warnings are the sole preflight diagnostic population and are retained for canonical Step 14 admission; signature, profile-evaluation, report-detail, and report-byte populations otherwise begin with evidence evaluation.

CLI scalar expectations and equivalent programmatic collections have one portable accounting form. After syntax validation, duplicate rejection, and capture or parsing of the one canonical evaluation instant, the verifier constructs the closed logical object `{"evaluationTime":<canonical-timestamp>,"expectedArtifacts":<sorted array>,"expectedHeads":<sorted array>,"expectedManifest":<digest-or-null>,"expectedNonce":<string-or-null>,"expectedRecipient":<string-or-null>}` and charges its RFC 8785 JCS byte length once to consumer `maxMetadataBytes`; no final LF is added for this accounting. `evaluationTime` is the exact canonical Section 10.4 rendering that will appear in the report, whether explicitly supplied or captured at invocation start. For this accounting object, `expectedManifest` is either null or a digest object `{"sha256":"<64 lowercase hex>"}`; every `expectedHeads` element is that digest-object shape; and every `expectedArtifacts` element is exactly `{"digest":<digest object>,"head":<digest object>,"subjectName":<string>}`. CLI `sha256:<hex>` scalar spellings are converted to those logical digest objects before JCS accounting. Recipient/nonce strings retain the 4096-byte limits from Section 13.2. The combined `expectedHeads` plus `expectedArtifacts` population has an immutable bootstrap ceiling of 200,000 elements before policy parsing can tighten byte usage; exceeding it is invalid invocation exit 2. CLI order and library collection order do not affect the JCS charge or overflow result. Consumer material/catalog binding structures supplied through a library must likewise arrive as strict JSON bytes or be RFC 8785-serialized once, then are charged exactly like the corresponding CLI binding files.

The policy values MUST satisfy `maxDiagnostics >= 1`, `maxReportRecords >= 64`, and `maxReportBytes >= 65536` so a fixed denial skeleton always fits. `maxJsonExponentMagnitude` applies to the absolute value of the literal `e`/`E` exponent token after its optional sign, before coefficient normalization; a number with no exponent token has literal exponent zero. The verifier reserves capacity for one terminal `E_RESOURCE_LIMIT` diagnostic before admitting ordinary diagnostics or Step 14 detail records in canonical order. The security-relevant `maxReportBytes` projection is JCS over the report with every diagnostic `message` replaced by `""` and the `tool` object replaced by the schema-valid fixed shape `{ "name": "", "version": "" }`, followed by one LF; only that stable projection may trigger report truncation. Actual tool name/version values are truncated as needed, down to those empty strings, to keep actual JCS-plus-LF output within the same byte cap. Other human messages may likewise be truncated without changing decision, records, codes, or `primaryError`. Evidence-operation and diagnostic limits encountered before Step 14 stop only their remaining dependent work and mark it `skipped`; report-record/byte limits instead apply solely through the two-pass admission algorithm and do not change completed evidence statuses. Summary counters describe discovered logical totals when known; a counter whose population could not be safely discovered because an evidence limit stopped discovery is `null`, while Step 14 detail omission never erases a fully computed counter. The report skeleton, summaries, checks, reserved diagnostic, truncation flag, and minimal tool shape never count as detail records, but their projected bytes count toward `maxReportBytes`; Phase 0 vectors prove the fixed skeleton remains below the 65536-byte minimum. No implementation may silently omit a record without setting the flag and diagnostic.

All limit-bearing work uses canonical processing order, independent of CLI or filesystem enumeration order: consumer catalog resources by `(id, digest.sha256, NFC logical path)`; bundle entries by NFC logical path after a bounded inventory has been completed; decoded manifest-listed statements by statement digest; signatures by the total-signature tuple above; profile closures and evaluations by the report profile tuple, with each closure's resources by `(id, digest.sha256)`; artifact inputs/snapshots by `(lifecycleRole, artifactKind, statementDigest, subjectName, digest.sha256)`; and dataset entries by `(manifestStatementDigest, manifestSubjectName, entryName)`. Canonical order applies within the population processed by each algorithm step; it does not reorder steps. The initial bundle inventory is the sole exception needed to make the entry ceiling enforceable: directory enumeration counts entries without attaching item-specific diagnostic context and stops immediately upon discovering entry `maxBundleFiles + 1` or bootstrap entry 20,001. It emits one context-independent `E_RESOURCE_LIMIT` naming only the limit and observed lower bound, does not claim which logical path was canonically first beyond the limit, and skips all work requiring a complete inventory. Only an inventory that completed within the bound is normalized, collision-checked, sorted, and processed in canonical path order. In particular, required dataset-manifest snapshots at Step 8 precede the general artifact population at Step 12, and Step 12 reuses rather than recharges those snapshots. For every other aggregate bound, the current canonical item receives `E_RESOURCE_LIMIT` and remaining dependent items are `skipped` with that check as prerequisite. This order also determines the diagnostic context chosen for the first aggregate-limit failure.

**Consumer-configuration preflight occurs before Step 1.** Under bootstrap ceilings, the verifier first safe-opens, snapshots, strict-parses, and schema/semantically validates the policy; it then applies the selected consumer limits while processing the syntax/types of supplied command-line expected values, expected-value/binding JSON files, and consumer-supplied catalogs in canonical order. It safe-opens consumer artifact targets and records their descriptor identity/type/size but defers byte copying, hashing, and artifact-budget charging to Step 8 or 12. Invalid consumer configuration exits 2 without an evidence decision or verification report. This preflight includes recomputed key IDs, rule satisfiability, thresholds, windows, required policy members, resource ceilings, legal field combinations such as the paired age/skew fields, and duplicate/alias checks entirely among consumer inputs. Absence or mismatch of a syntactically valid policy-required expected value is deliberately not preflight-invalid; it becomes evidence denial at Step 11. Bundle-supplied catalogs remain untrusted evidence and are checked during evidence evaluation.

1. **Load safely.** Classify the supplied bundle-directory argument with a no-follow final-component stat before evidence evaluation. A nonexistent path or an existing real non-directory (regular file, FIFO, socket, device, or other special type) is invalid invocation and exits 2. A final-component symlink, including a dangling symlink, begins completed evidence evaluation and fails with `E_BUNDLE_UNSAFE_PATH`. A real directory that exists but cannot be safely opened, descriptor-statted, or inventoried because of permission or I/O failure likewise produces completed `E_BUNDLE_UNSAFE_PATH`. Ancestor components may follow the host's ordinary path resolution (for example macOS `/var`), but the verifier opens the resulting final directory descriptor once, records its physical identity, and performs every descendant operation descriptor-relative without following links; ancestor path spelling is never used for containment. Inside an opened real directory, require `bundle.json`, enforce file-count, the role-specific file-size accounting in Section 13.3, entry-type, and path rules, and return `E_HANDOFF_REQUIRED` when `bundle.json` is absent.
2. **Parse and validate transport structures.** Strict-parse `bundle.json`; if the object lacks a `manifest` member, use `E_HANDOFF_REQUIRED`, while a present wrong-typed member uses `E_CORE_SCHEMA` and a present unsafe logical path uses `E_BUNDLE_UNSAFE_PATH`. Validate the complete bundle transport schema and then perform its complete semantic pass before iterating any mapping or opening any indexed envelope: enforce exactly these semantic invariants: mandatory array sort orders; uniqueness of every path, complete index tuple, artifact-material identity, and dataset-entry logical identity; one index role per mapped path; no final/historical/dataset path reuse; and the bundle-versus-consumer artifact-material/dataset-entry duplicate comparisons from Section 16.1. No other Section 13.3 rule is a Step 2 semantic invariant: decoded payload/subject relationships are Step 4 or 11, schema-catalog content is Step 4, and consuming-open/tree-stability failures use their consuming step. Any such schema or semantic failure is `E_CORE_SCHEMA` at Step 2, establishes no manifest-listed set, leaves `statements`, `profiles`, and `unindexedEnvelopes` empty, and makes every later bundle-dependent check `skipped` with `core-schemas` as prerequisite. A strict parse failure of `bundle.json` likewise establishes no manifest-listed set and makes later bundle-dependent checks `skipped`, but their prerequisite is `parse-strictly`; envelope-local transport failures use the same prerequisite for only the dependent population. No valid-looking manifest path inside an invalid bundle index is followed. Only after that pass does the verifier locate and strict-parse each indexed envelope and validate its envelope transport schema before decoding. A safe manifest path whose target is absent returns `E_HANDOFF_REQUIRED`. Reject ordinary JSON syntax errors, invalid UTF-8, a byte-order mark, invalid string scalars, and nonstandard tokens with `E_JSON_INVALID`; reject duplicate keys with the more specific `E_JSON_DUPLICATE_KEY`; reject an empty signature array, malformed base64, lexically invalid payload types, lexically valid but unsupported payload types, and malformed envelope/signature structure with the exact Section 10.1 codes. Other bundle transport schema failure is `E_CORE_SCHEMA` at Step 2 and prevents indexing the invalid bundle structure.
3. **Index payloads.** Decode and strict-parse the structurally valid handoff envelope payload first, compute `manifestDigest`, then decode every structurally valid present attestation envelope in declared-digest order, calculate each exact payload digest, and compare it with the declared digest before strict-parsing the statement JSON. Step 2 transport schema already requires declared digest and path identities to be unique, so no second duplicate-digest rule exists at Step 3. A digest mismatch produces one `unindexedEnvelopes` record with `E_STATEMENT_DIGEST`, no statement record for that envelope, and is never cryptographically verified; it may leave a manifest identity missing for the Step 11 exact-set check. When the digest matches but strict statement JSON parsing fails, the payload identity is indexed and receives a full statement record: `predicateType` and `eventId` are null; `coreSchema`, `authorization`, and `graph` are `skipped` with their field-specific prerequisite arrays; and Step 5 MUST still verify the DSSE signature over the exact bytes. Record missing/extra index identities for Step 11 without emitting `E_MANIFEST_SET` yet. A declared safe attestation path whose target is physically absent produces one `unindexedEnvelopes` record with that path, `payloadTypeStatus: "not_checked"`, and `diagnosticCode: "E_MANIFEST_SET"`; a manifest identity with no index mapping has no path and produces no unindexed-envelope record. Both exact-set failures are emitted at Step 11.
4. **Validate decoded core payloads.** Validate the handoff payload, bundle-supplied catalog, and every strictly parsed handoff-listed statement/predicate/profile reference against immutable v0.2 schemas and Step 4 semantic rules. An absent safe bundle-catalog target or declared catalog resource is `E_CATALOG_INVALID` here. The manifest-listed selection set becomes established only when the handoff envelope and decoded payload passed Steps 2–4 structural/core validation. Before that point, every indexed statement is quarantined and later manifest-dependent checks are skipped. Once established, the selection set remains authoritative for safe processing even if the handoff signature or authorization later fails; those failures deny but do not erase full statement/profile records. A manifest-listed statement whose JSON failed at Step 3, whose core schema fails, or whose otherwise schema-valid content triggers `E_PREDICATE_SEMANTICS_UNSUPPORTED` or `E_PROFILE_TARGET_MISSING` at Step 4 remains a statement report record but is excluded from selector, authorization, profile, and graph-node indexes. Every Step 4 schema or semantic rejection sets that statement's `coreSchema: "fail"`; its signatures are still evaluated, while authorization and graph are `skipped` with `core-schemas` prerequisite and both rule-ID arrays are empty. A strict-parse failure instead has `coreSchema: "skipped"` and additionally names `index-payloads`. An unauthorized handoff's `requiredProfiles` never upgrades requiredness; every affected profile record sets `requiredByManifest: false`, because only a Step 6 authorized handoff grants those requirements authority. Statements indexed outside an established manifest set are quarantined: retain only safe path/digest metadata and do not run predicate, signature, authorization, profile, or graph checks on them before Step 11. Do not reevaluate the already-preflighted consumer policy/catalogs, and do not evaluate producer-supplied profile schemas yet.
5. **Verify signatures.** Validate DSSE signatures over exact payload bytes using exact configured `keyid` lookup for the handoff envelope and every manifest-listed statement envelope whose transport and payload digest were established, including a payload whose JSON/core schema is invalid. Quarantined envelopes are counted for resource limits but are not cryptographically verified.
6. **Check authorization thresholds.** Apply trust-policy selector/key/threshold portions only to core-valid manifest-listed statements and to the core-valid handoff manifest, counting distinct authorized keys and producing candidate authorizing rules. A core-invalid statement is skipped here and never emits `E_SIGNER_UNAUTHORIZED`. For an eligible statement, Step 6 runs even when Step 5 found an invalid configured-key signature: it evaluates the remaining cryptographically passing signatures and emits `E_SIGNER_UNAUTHORIZED` in addition to `E_SIGNATURE_INVALID` only when no selected threshold is met. The `authorization-thresholds` check fails when any eligible statement has no threshold-satisfying candidate or the handoff threshold fails; otherwise mixed eligible and prerequisite-skipped items fold exactly under the aggregate rule below. Handoff final authorization completes here because it has no profile constraints; statement authorization remains provisional until Step 7.
7. **Resolve metadata profiles and finalize statement authorization.** For each manifest-listed statement with at least one Step 6 candidate rule, resolve exact schema bytes, pin all resources by digest, and apply signed statement and predicate profiles within policy resource budgets. For a statement with no candidate, emit only skipped profile records as specified in Section 12.4 and do not load producer schema bytes. Evaluate each candidate's digest constraints and authorize the statement only if at least one candidate passes all of its mandatory constraints and no evaluated signed profile is false. Defer final-artifact profile matching until final handoff artifacts and heads are known. Outside-set quarantined statements never contribute profile records or reachable-profile counts.
8. **Prevalidate dataset-manifest artifacts.** Build the Step 8 candidate population before assuming dataset-profile validity. It is the duplicate-free union of subjects on final-authorized manifest-listed statements that are named by an authorized statement's `inputs[].provenance.entryName` predecessor tuple, a bundle or consumer `datasetEntries` mapping, a signed exact mandatory dataset-manifest profile reference, or a signed handoff-manifest `artifacts[]` entry whose optional `mediaType` is `application/vnd.makoto.dataset-manifest.v0.2+json`. A candidate's containing statement MUST have passed final Step 7 authorization. Reachability is deliberately not a Step 8 prerequisite because dataset membership is itself a Step 9 graph-edge input. For every candidate, first require the exact mandatory dataset profile identity from Section 12.5; an absent or wrong identity emits only `E_DATASET_MANIFEST_INVALID`, creates no synthetic profile record, and skips dataset byte parsing and graph use. For each identity-valid candidate whose bytes are supplied as a final `artifacts` mapping, historical material, consumer material, or are required by an `entryName` edge or `datasetEntries` mapping, create the immutable snapshot exactly once and verify its subject digest. Before parsing a dataset manifest, detect the complete Step 8 media-consistency population defined in Section 12.4. After the subject digest passes and that population is known, reserve and charge one fused `maxProfileEvaluations` unit per participating profile before any closure resolution. On conflict, set `validation: "fail"` with empty prerequisites on every conflicting signed profile record, then use each precharged unit for ordinary closure resolution in canonical order solely to populate its independent `resolution` and resolution/resource diagnostics. No artifact instance is parsed, the per-profile `E_PROFILE_INVALID` results are cached as final for Step 13, and graph use is skipped. When media is consistent, use the mandatory core profile's precharged unit for its checksum-pinned closure and bounded parser/evaluator; a missing or mismatched core registry is exit 3, while a policy byte/resource limit uses `E_RESOURCE_LIMIT` and no validation starts. The precharged attempt strict-parses the dataset bytes once. If strict JSON parsing fails, emit only `E_DATASET_MANIFEST_INVALID`; set the mandatory profile to `resolution: "pass"`, `validation: "skipped"`, and `prerequisiteChecks: ["graph-dependency-artifacts"]`. If parsing succeeds, evaluate the mandatory dataset schema exactly once: schema failure emits only `E_DATASET_MANIFEST_INVALID` and records `validation: "fail"` with an empty prerequisite array; schema success records `validation: "pass"`. After schema success, apply semantic ordering, name, path, and entry-digest lexical rules; every entry digest is exactly one lowercase 64-hex SHA-256 string inside its digest object. A semantic-only failure emits only `E_DATASET_MANIFEST_INVALID` while the already successful schema `validation` remains `"pass"`. The parsed entry index and complete mandatory-profile result are cached; the same schema is never evaluated a second time. Other signed dataset artifact profiles are deferred to Step 13 like ordinary artifact profiles. Step 13 reuses the mandatory cached result without another parse, worker, evaluation charge, or diagnostic. If Step 9 later finds the containing statement unreachable, this mandatory dataset-profile record retains its Step 8 result and any Step 8 diagnostic; it is the sole unreachable-artifact-profile exception to Step 13's ordinary skip rule, and Step 11 separately emits exact-set failure. For an unauthorized containing statement, Step 8 does not read dataset bytes or evaluate the profile; its profile/artifact/graph-dependent records are `skipped` with `authorization` prerequisite. Final-artifact mappings are valid Step 8 sources only when the handoff threshold passed; under a failed handoff threshold, the untrusted final mapping neither creates an artifact record nor authorizes a byte read. The snapshot and profile result are cached and MUST be reused at Steps 9, 12, and 13; later steps never reread or reevaluate it. Missing-byte precedence is role based: a dataset manifest required by any graph edge or dataset-entry mapping uses only `E_DATASET_MANIFEST_REQUIRED` at Step 8 even when it is also a final artifact; its artifact record has `digestStatus: "skipped"`, `artifact-bytes` is skipped for that record with `graph-dependency-artifacts` as prerequisite, and no secondary `E_ARTIFACT_MISSING` is emitted. A dataset manifest used only as a final artifact defers physical absence to `E_ARTIFACT_MISSING` at Step 12. A present target that is unsafe, permission-denied, wrongly typed, aliased, replaced, or cannot be statted uses `E_BUNDLE_UNSAFE_PATH` at Step 8. A manifest digest mismatch uses `E_ARTIFACT_DIGEST`. Entry membership for a graph edge is resolved at Step 9 so an absent named member uses `E_PREDECESSOR_SUBJECT`; membership for a standalone supplied partition is resolved at Step 12 so an absent named member uses `E_DATASET_MANIFEST_INVALID`.
9. **Build the graph.** Build the graph-node index only from core-valid, authorized, manifest-listed, nonquarantined statement payloads. A core-valid manifest-listed statement whose final Step 7 authorization failed has per-statement `graph: "skipped"` and `graphPrerequisiteChecks: ["authorization"]`. A consuming statement whose required `entryName` dependency failed at Step 8 has `graph: "skipped"` and `graphPrerequisiteChecks: ["graph-dependency-artifacts"]`; Step 8 owns the diagnostic, and Step 9 emits no duplicate graph error for that edge. Using the remaining usable manifest head set, compute the backward-reachable candidate node set during this step before event-ID uniqueness checks; two equal exact `event.id` strings inside that set emit `E_EVENT_ID_DUPLICATE`, while duplicates confined to manifest-listed but unreachable statements emit no event-ID diagnostic and later fail only the exact-set rule. A core-valid and authorized manifest-listed statement outside the backward-reachable set receives per-statement `graph: "not_checked"` with an empty `graphPrerequisiteChecks`; it is not a failed/dependent node, contributes no root/head/event-ID result, and later causes exact-set completeness failure at Step 11. A predecessor digest that identifies an outside-set, strict-parse-invalid, core-invalid, or unauthorized statement is unavailable as a graph node and uses `E_PREDECESSOR_MISSING`; `E_PREDECESSOR_SUBJECT` is reserved for a usable predecessor node that lacks the exact named subject or dataset entry. A manifest head excluded from the graph-node index makes the top-level `graph` check `skipped` under ordinary aggregate folding, with the failed statement's `core-schemas`, `authorization`, or `graph-dependency-artifacts` prerequisite as applicable; `roots-and-heads` is then `skipped` with `graph` as prerequisite. Step 11 still evaluates every independently decidable exact-set condition and fails `completeness-anchor` with `E_MANIFEST_SET` when the declared head/set cannot equal a valid reachable graph. Validate direct digest equality or prevalidated dataset membership, and reject missing nodes or cycles.
10. **Discover roots and heads.** Starting from every manifest head, traverse predecessor edges backward. The computed root set is exactly the reachable statements with zero predecessor edges. Every computed root and every manifest-declared root MUST be a core origin statement; a reachable or declared zero-predecessor non-origin uses `E_ROOT_INVALID`, while a nonzero-predecessor statement declared as a root also uses `E_ROOT_INVALID`. Derive terminal subject tuples from forward graph consumption. A selected head may have outgoing edges through a different subject. Exact manifest terminality, head/artifact derivation, and computed/manifest set comparisons occur at Step 11.
11. **Check handoff and freshness anchors.** Require an authorized manifest and validate its exact statement set, roots, heads, required profiles, and artifacts. Every cross-field violation listed in Section 13.2—including root/head presence, artifact-to-head exact name-plus-digest subject match, terminality, head derivation, and computed set mismatch—uses `E_MANIFEST_SET` here. A manifest artifact tuple with an absent subject name or mismatched signed subject digest is ineligible for Step 12 hashing: its artifact record has `digestStatus: "skipped"` and `profileStatus: "skipped"`, while the aggregate `artifact-bytes`/`artifact-profiles` check uses `completeness-anchor` as prerequisite under the folding rule; no secondary `E_ARTIFACT_DIGEST` is emitted. Compare the complete manifest head set with the one supplied complete expected-head set when present and every supplied or policy-required exact recipient/nonce expectation. All supplied or policy-required expectations MUST pass; disagreement is denial rather than fallback to another anchor. Indexed statements outside the exact reachable set are reported and fail the handoff with `E_MANIFEST_SET`. If no freshness method is supplied or policy-required and replayable handoff is allowed, report freshness as `not_checked`; if replayable handoff is not allowed, emit `E_FRESHNESS_REQUIRED`, set `freshnessMethod: "none"`, `freshnessStatus: "fail"`, and `freshness-anchors: "fail"`.
12. **Verify artifact bytes.** Stream SHA-256 over every provided final artifact whose exact manifest tuple passed Step 11 and compare it with the one matching terminal subject/manifest digest. A Step 11 name/digest mismatch is never hashed and never emits a secondary artifact-digest error. When handoff authorization has passed, also hash every structurally valid bundle historical mapping and every preflight-valid consumer `artifact-material` mapping not already snapshotted at Step 8, including mappings attached to listed but unreachable statements. When handoff authorization failed, hash only independently supplied preflight-valid consumer historical bindings outside the bundle; compare it with the named statement subject and make its verified snapshot available to eligible profiles. A consumer artifact binding that does not match exactly one manifest-listed statement subject tuple is rejected at Step 11 with `E_MANIFEST_SET` and is not hashed. For supplied `datasetEntries`, reuse the Step 8 validated dataset-manifest snapshot, match the logical `(manifestStatementDigest, manifestSubjectName, entryName)` identity to one unique existing member, require the mapping's declared digest to equal that member digest, stream the partition bytes, compare the bytes with that same member digest, and compare the exact byte count with the optional declared size. A consumer dataset-entry binding whose logical identity does not resolve uniquely or whose declared digest differs from the member uses `E_DATASET_MANIFEST_INVALID` here and is not hashed. A partition-byte digest mismatch after that mapping check uses `E_ARTIFACT_DIGEST`; a partition size mismatch uses `E_ARTIFACT_SIZE`. No mapping/consumer binding for an optional partition produces `not_checked`. A consumer binding whose target is absent at invocation is invalid configuration exit 2 during preflight and never reaches this step. `E_ARTIFACT_MISSING` at Step 12 instead covers an absent target for a structurally valid bundle final/historical/dataset-entry mapping, required historical material for which no bundle or consumer source was supplied. A missing final-artifact mapping is always Step 11 `E_MANIFEST_SET`; consumer `artifact-material` cannot repair it. A present target that cannot be safely opened or stably snapshotted uses `E_BUNDLE_UNSAFE_PATH`.
13. **Validate artifact profiles.** Evaluate a producer-supplied artifact profile when its containing statement's final `authorization` passed and either (a) the statement is reachable from a core-valid, authorized handoff's usable manifest head, or (b) Step 12 successfully hashed an explicit historical `artifact-material` source for that exact statement/subject/digest. When handoff authorization has passed, exception (b) applies to a structurally valid bundle historical mapping or a preflight-valid consumer historical binding, including material for a listed but unreachable statement. When handoff authorization failed, exception (b) applies only to a preflight-valid consumer historical binding outside the bundle. An untrusted final-artifact mapping never qualifies. The mandatory dataset-manifest core profile already evaluated at Step 8 remains the separate dependency exception there. An unauthorized profile record is `resolution: "skipped"`, `validation: "skipped"`, `prerequisiteChecks: ["authorization"]`; an authorized but manifest-listed unreachable ordinary artifact-profile record with no successfully hashed explicit historical source uses the same skipped fields with `prerequisiteChecks: ["graph"]`. No artifact record is created and no bytes are required solely because an unreachable statement carries an ordinary critical artifact profile; Step 11 exact-set completeness is the denial. For eligible reachable statements, enforce policy size limits, select parsers from signed media types, parse supported structured artifacts, and apply referenced JSON Schemas after byte-digest verification. A dataset-manifest core profile already evaluated at Step 8 contributes its cached record and status here without a second parse, worker, evaluation charge, diagnostic, or reachability rewrite. Enforce each consumer `requiredProfiles` entry against every matching final manifest artifact and its declared head; never search the graph for any same-named subject.
14. **Decide.** Apply the decision rules below and emit check-level results plus an overall `allow` or `deny` bundle decision.

In Step 8, the media-hint candidate is exactly a signed handoff-manifest final-artifact entry whose optional `artifacts[].mediaType` is `application/vnd.makoto.dataset-manifest.v0.2+json`. The closed unsigned `bundle.json.artifacts[]` mapping has no `mediaType` member and never supplies this candidate signal. Phase 0 includes a media-hint-only candidate with no mandatory signed profile and expects Step 8 `E_DATASET_MANIFEST_INVALID`.

“Participating profile” in Step 8 has one closed meaning. With no media conflict, only the exact mandatory core dataset-manifest profile participates, consumes a Step 8 fused unit, and is cached for no-charge Step 13 reuse; every other signed artifact profile on that subject is exclusively Step 13 work and receives no Step 8 unit. With a media conflict, the mandatory profile and every conflicting signed artifact profile participate, each consumes exactly one Step 8 fused closure unit, and every complete resolution/validation result is cached as final; Step 13 reuses all of those results and MUST NOT launch, parse, resolve, charge, or diagnose them again. Phase 0 pins both populations at the `maxProfileEvaluations` boundary.

Unit commitment has one owner. Every Step 8 phrase “reserve and charge” means the parent temporarily reserves one unit from its deterministic worker quota before work, but does not permanently decrement the invocation counter then. The worker request has required `mode: "full"` for the mandatory no-conflict parse/evaluation and `mode: "resolution-only"` for each media-conflict participant; resolution-only mode forbids artifact opening/parsing and returns the ordinary closed result with phase `resolution` or `complete`, `tokenCount: 0`, and `evaluationsConsumed: 1`. After validating the result, the parent permanently commits `evaluationsConsumed` exactly once and releases the reservation; it never adds a separate Step 8 charge. A kill commits the reserved quota under the existing kill rule. The worker request schema, both modes, and one-versus-double-charge boundary traces are checksummed Phase 0 artifacts.

Step 8 candidate-source authority is also closed. When handoff authorization passes, every candidate source named in Step 8 is eligible under its ordinary prerequisites. When a core-valid handoff fails authorization, its `artifacts[].mediaType` hints and every bundle `artifacts`/`datasetEntries` mapping are ignored and never trigger a snapshot or profile evaluation. A signed mandatory profile or reachable `entryName` edge on an independently authorized listed statement may still establish a logical candidate, but bytes may be supplied only by an independently preflight-valid consumer material/dataset-entry binding whose tuple matches that listed statement; absent such consumer material, byte-dependent Step 8 work is skipped with `authorization-thresholds`. A consumer mapping alone must match one authorized listed statement/subject before it can trigger work. If no core-valid handoff selection set exists, all dataset candidate work is skipped with the earlier handoff prerequisite. Phase 0 pins authorized, unauthorized-with-bundle-only, unauthorized-with-matching-consumer, and no-selection-set strata.

The normative check-to-step map is: `load-safely` → 1; `parse-strictly` → 2; `index-payloads` → 3; `core-schemas` → 2 and 4; `signatures` → 5; `authorization-thresholds` → 6; `metadata-profiles` → 7; `authorization` → 7; `graph-dependency-artifacts` → 8; `graph` → 9; `roots-and-heads` → 10; `completeness-anchor` and `freshness-anchors` → 11; `artifact-bytes` → 12; `artifact-profiles` → 13; and `decision` → 14. `diagnostic-map.json` MUST encode this check ownership, every owned code, and prerequisite/continuation edges.

Top-level aggregate status folding is uniform and occurs after all records for that check are known. “Required/eligible” means an item is inside that check's eligible folded population under its check-specific rules; it is not the union of required and threshold-ineligible records. A check is `fail` when any eligible folded item failed. Otherwise it is `skipped` when at least one eligible folded item was skipped because a prior check failed, even if another eligible item passed; its `prerequisiteChecks` is the sorted union of those failed prerequisites. Otherwise it is `pass` when at least one eligible folded item executed and every such item satisfied the check. It is `not_checked` when the complete applicable population is known to be empty or policy explicitly disables the check. Optional noncritical profile `indeterminate`/`not_checked` records and unknown-key signature records do not prevent the owning aggregate from passing; the profile-specific rules in Section 12.4 define the metadata-profile folded population and still turn an evaluated false signed claim into failure. `indeterminate` remains reserved for a future top-level verifier mode and is not emitted for a v0.2 bundle check. Singleton checks use the same rules with one item. The `decision` special case in Section 16.3 is `pass` when semantic aggregation and report admission complete, regardless of allow/deny, and `fail` only for a Step 14 report-budget `E_RESOURCE_LIMIT`.

For Step 11, “independently decidable exact-set condition” is not implementation discretion. Once the handoff is core-valid and authorized, declaration/index conditions always run: manifest root/head/statement subset and nonempty rules, index tuple presence and uniqueness, outside-set bundle mappings, artifact/required-profile head membership, and any mismatch already provable from signed digests/names. A manifest-listed statement excluded from the usable graph-node set by its own core, authorization, or Step 8 dependency failure makes valid reachable-set equality deterministically false and emits `E_MANIFEST_SET`; therefore the unauthorized-signer demo fixture has `completeness-anchor: "fail"`, not `skipped`, while its separate authorization failure remains. Derived reachable-set equality, computed roots/heads, terminality, and artifact-to-head subject matching run only when their graph/roots prerequisite produced the needed population. `completeness-anchor` fails when any declaration or derived condition is false; otherwise it is skipped with the exact graph or roots prerequisite when at least one required derived condition could not be computed; otherwise it passes. A known false declaration wins over an unavailable derived condition under the ordinary fail-before-skipped fold. `diagnostic-map.json` enumerates each condition, prerequisite, and continuation, and Phase 0 pins expected check statuses for authorization failure, graph resource skip, root failure, and an independently false index tuple.

Per-statement `graph` attribution is deterministic and separates reachability from validity. Starting from every usable manifest head, backward traversal follows every declared predecessor digest that resolves to an available usable graph node, regardless of either node's eventual graph result; an unavailable predecessor terminates only that edge. `statementsReachable` counts every available node encountered by this digest traversal. After the reached set is fixed, the verifier evaluates every reached statement's own edges in canonical order. A missing predecessor, wrong predecessor subject, input-digest mismatch, or membership defect makes the consuming statement `fail` and emits its own diagnostic even when another required predecessor is already failed or skipped; an own-edge defect therefore wins over inherited skip. A statement whose own edges all pass is `skipped` when any required predecessor's graph result is `fail` or `skipped`, and otherwise passes. A cycle fails every statement in the detected strongly connected component; a reached descendant outside the component with no independent edge defect is skipped by inheritance. At a join, one poisoned branch and one clean branch therefore skip the join only when the join's own edges are sound; an independent bad join edge fails it. Graph diagnostics name the consuming statement or sorted cycle-member set. Phase 0 includes a diamond, mixed clean/poisoned predecessors, an independent join-edge defect, traversal through an available graph-failed node to its ancestors, and a cycle with an outside descendant.

Filesystem enumeration order and CLI discovery order MUST NOT influence graph results. A “reordered step” attack means changing signed predecessor bindings. Rearranging on-disk files without changing indexed logical paths is harmless; shuffling any array whose schema requires canonical sorting is `E_CORE_SCHEMA`, not an equivalent valid input; rewiring a signed edge invalidates a signature or produces a graph mismatch.

Graph-edge evaluation never uses signed `inputs[]` occurrence order. For each reached transformation, derive one edge identity tuple `(predecessorStatementDigest, provenance.subjectName, provenance.entryName-or-null, local input name, input digest)` and sort edges by ASCII bytes for the two lowercase hexadecimal digests and UTF-8 bytes for strings, with null before string. The input-local-name-inclusive uniqueness rule makes the tuple duplicate-free. Evaluate every own edge in that order; within an edge, test predecessor-node availability, predecessor subject or dataset-member presence, then input-digest equality, stopping that edge at its first failed test while continuing later edges. Edge diagnostics, operation/resource consumption, multiplicity keys, and `primaryError` candidates follow this order. Phase 0 includes one transformation with three independently bad signed inputs whose wire occurrence order differs from this canonical order, plus the same semantic edges in alternate signed occurrence order, and pins the complete diagnostic sequence and limit boundaries.

Consumer historical-material bindings are membership-checked whenever a core-valid handoff payload establishes its signed statement selection set, even when the handoff later fails authorization. A binding whose `(statementDigest, subjectName, digest)` does not match exactly one listed signed statement subject emits Step 11 `E_MANIFEST_SET`, creates no artifact record, and is never opened or hashed; this declaration-only check does not grant authority to any untrusted manifest artifact mapping. If no core-valid handoff established a selection set, the binding check is skipped with `core-schemas` or the earlier handoff prerequisite. Phase 0 includes an unauthorized core-valid handoff with one matching consumer historical binding and one non-listed binding, pinning the matching continuation and the non-listed diagnostic.

Consumer `maxDiagnostics` is enforced only during Step 14 admission and never stops evidence work or changes evidence statuses. The earlier phrase “diagnostic limits encountered before Step 14” refers exclusively to the immutable 100,000-candidate discovery ceiling and its reserved final slot; report-record and report-byte limits likewise remain admission-only. Every Step 14 candidate recomputes `primaryError` from that candidate's actually admitted `errors` array after diagnostic-prefix selection; it is null if that candidate admits no error. The final report's `primaryError` is therefore always the code of its first admitted error under the stable diagnostic order, never a code retained from an omitted diagnostic.

Step 2 envelope classification is exhaustive. Strict JSON syntax/UTF-8/BOM/scalar/token and duplicate-key failures keep their specific JSON codes; a parsed string `payloadType` that fails the Section 10.1 lexical grammar uses `E_ENVELOPE_MALFORMED`; a lexically valid string that is not the exact type permitted at that index uses `E_PAYLOAD_TYPE`; every other envelope-object or signature-entry shape failure—including missing/extra members, wrong member types, an empty signature array, malformed key ID/base64/decoded length, or duplicate key ID—uses `E_ENVELOPE_MALFORMED`. `E_CORE_SCHEMA` at Step 2 applies to `bundle.json` and other non-envelope transport objects, never to envelope shape. A schema-valid parsed `bundle.json` containing any unsafe logical path uses `E_BUNDLE_UNSAFE_PATH`, establishes no manifest-listed set, and makes every later bundle-dependent check `skipped` with `parse-strictly` as prerequisite; no indexed path is followed.

Whenever `bundle.json` fails Step 2 for JSON, core-schema/semantic, or unsafe-path reasons, no envelope or mapped artifact is opened. `statements`, `profiles`, `artifacts`, `datasetEntries`, `unindexedEnvelopes`, `quarantinedStatements`, and `unreferencedFiles` are all empty completed report arrays. Summary values whose complete population is thereby known to be empty—such as signature/profile/artifact/detail counts—are integer zero; graph/root/head and manifest-derived counters whose computation required a valid bundle index are null. Phase 0 report vectors enumerate every summary field in this state rather than inferring nullability from implementation control flow.

Step 10 computes `summary.heads` from the subject-aware terminal set without trusting declared head cardinality: it is the number of distinct reachable statements that own at least one subject tuple with zero forward consumers and whose exact `(statement digest, subject name, subject digest)` tuple is named by a manifest artifact entry. A terminal but unhanded subject does not add a computed head; a declared artifact tuple that is nonterminal or mismatched does not add one and later fails Step 11. `summary.heads` is this computed intersection count whenever Step 10 completes, including mismatch reports; `actualHeads` remains the separately declared manifest head set.

`requiredByManifest` is an always-present boolean in every profile record. When the handoff is unauthorized or its requirements otherwise lack authority, the verifier sets `requiredByManifest: false`; the member is never omitted. For a strict-JSON-valid but core-invalid statement, `predicateType` is recovered only from top-level `predicateType`, while `eventId` is recovered only from `predicate.event.id`; each is populated independently when that exact local member is a string satisfying its field's lexical grammar; failure of any unrelated core member does not null them. A locally absent, wrong-typed, or lexically invalid one is null.

Every Step 8 mandatory dataset-manifest attempt follows the same fused-unit rule as every other profile: after the subject digest and complete media-consistency population are established, it reserves and charges exactly one `maxProfileEvaluations` unit before any mandatory closure lookup, dialect/meta-validation, parsing, or schema evaluation. If no unit remains, none of that work begins and `E_RESOURCE_LIMIT` owns the result. Dataset precedence is digest first: a subject-digest mismatch emits only Step 8 `E_ARTIFACT_DIGEST`, skips media comparison and parsing, and records the mandatory profile's resolution/validation as `skipped` with `prerequisiteChecks: ["graph-dependency-artifacts"]`; it charges no profile unit. Only after the subject digest passes does the Step 8 media-consistency pass run. For each profile in either the consistent or conflicting population—including the mandatory core profile—the precharged fused unit covers closure/dialect work and, when media is consistent and resolution succeeds, parsing plus one dataset-schema evaluation. A media conflict emits the defined Step 8 `E_PROFILE_INVALID`, sets every conflicting signed profile's validation to `fail`, and skips instance parsing, but each profile's precharged unit still performs ordinary closure resolution to populate its independent resolution state. A closure/resource failure after reservation consumes that unit. The exact mandatory core profile and its checksum-pinned closure are always locally registered; a missing/mismatched core registry is exit 3, not `E_PROFILE_UNRESOLVED`, while policy schema-byte/resource exhaustion is `E_RESOURCE_LIMIT`. Because a dataset manifest is monolithic JSON, there is no second instance/line unit. Parse, schema, semantic, conflict, and resource result states are otherwise those in Step 8.


Aggregate profile-worker wall-time exhaustion emits exactly one global `E_RESOURCE_LIMIT`, owned by the check evaluating the current canonical profile when the aggregate deadline is reached. Its multiplicity key is `(aggregate-profile-wall-time, current-profile-identity)`. That current record takes the applicable required or optional resource-limit state from Section 12.4; every later canonical profile prevented from starting is `resolution: "skipped"` and `validation: "skipped"` with the owning top-level check in `prerequisiteChecks`, and receives no duplicate diagnostic. The owning aggregate check fails, the overall decision denies, no remaining profile worker starts, and report admission continues.



The two authorization aggregates have closed, disjoint populations. `authorization-thresholds` contains the core-valid handoff when one exists plus every core-valid manifest-listed statement; a listed statement excluded by strict/core failure is outside this aggregate rather than a skipped threshold item. If no manifest-listed set can be established because the handoff transport/core prerequisite failed, the whole check is `skipped` with that earlier prerequisite. Otherwise the check fails when any member's distinct-key threshold fails, passes when its nonempty population all meets threshold, and is `not_checked` only when the complete eligible population is empty. Top-level `authorization` contains statements only—never the handoff—and contains every core-valid manifest-listed statement. Each such statement's item is its final Step 7 result, including a Step 6 threshold failure or candidate-profile failure; core-invalid listed statements are outside the population. The aggregate passes when its nonempty population all authorizes, fails when any final item fails, becomes skipped only when an aggregate prerequisite/resource condition prevents completion of an otherwise eligible final item, and is `not_checked` when the complete eligible population is empty. `handoff.authorization` remains solely in the handoff record and `authorization-thresholds` aggregate.

Graph traversal never continues through a predecessor unavailable from the usable graph-node index. The consuming edge receives `E_PREDECESSOR_MISSING` and that statement fails graph attribution. Other available predecessor edges on that same statement are still traversed and evaluated; reached descendants apply the own-edge-first/inherited-skip rule above. A statement or ancestor discoverable only through the unavailable node is not added to `statementsReachable`. Step 11 separately evaluates any resulting exact-set mismatch.

A manifest-declared core transformation or other non-origin root emits `E_ROOT_INVALID` at Step 10. Because every core-valid transformation has one or more inputs/predecessor edges, it cannot also be a computed zero-predecessor root; declaring it as a root therefore creates an independently real root-set mismatch and Step 11 also emits `E_MANIFEST_SET`. The wire-realizable fixture declares a normal transformation as the sole manifest root and expects both diagnostics, with Step 10 `E_ROOT_INVALID` first under diagnostic ordering. No impossible zero-predecessor transformation or suppression fixture is required.

`E_HANDOFF_REQUIRED` intentionally belongs to `load-safely` at Step 1 or `parse-strictly` at Step 2, according to Appendix C; it is not reassigned to `completeness-anchor`, because no authenticated handoff exists from which an anchor population could be established. After strict parsing establishes a top-level `bundle.json` object, absence of its `manifest` member is a preemptive Step 2 branch: emit only `E_HANDOFF_REQUIRED` for that object, do not run its remaining core-schema or semantic checks, establish no manifest population, and skip every dependent check with `parse-strictly` as prerequisite. A present wrong-typed `manifest` follows ordinary complete core-schema validation and may co-emit other Step 2 core errors. Phase 0 pins both branches and their exact `primaryError`.

### 15.1 Decision and check-status rules

Every check has one of `pass`, `fail`, `indeterminate`, `not_checked`, or `skipped`:

- `fail` means supplied evidence disproved or violated a requirement.
- `indeterminate` means an attempted optional conclusion could not be established from otherwise processable evidence; requiredness is evaluated separately and required uncertainty denies rather than producing an overall indeterminate bundle decision.
- `not_checked` means an optional check was deliberately not exercised, including absent optional artifact bytes and replay defenses explicitly waived by policy, or the complete applicable population was validly computed as empty. It MUST NOT be used for a required item in a nonempty applicable population or for a check whose prerequisite failed.
- `skipped` means a prerequisite failed; the report MUST identify the prerequisite check.

The Step 9 unreachable-statement rule is an explicit narrow exception to the general sentence that `not_checked` is not used for a required nonempty item: a core-valid, authorized, manifest-listed statement outside the backward-reachable set has `graph: "not_checked"` because no graph evaluation applies to it, while Step 11 separately treats its presence as exact-set failure. That state is not a waiver of completeness.

The overall decision is deterministic:

1. `deny` if any required top-level evidence check fails, including core structure, cryptography, authorization, graph, completeness/anchors, consumer-required profiles, required artifacts, replay defense, or resources. Invalid consumer policy/configuration never reaches this aggregation and exits 2 during preflight.
2. The value `indeterminate` is reserved in the v0.2 report enum for future verifier modes; `makoto verify bundle` never emits it. Missing evidence for a required conclusion is denial, while explicitly waived or optional checks are `not_checked`/`indeterminate` at the check or profile-record level without changing an otherwise valid bundle from `allow`.
3. Otherwise `allow` when every consumer-required check passes. Unknown or unevaluated producer-declared noncritical profiles and absent optional historical artifacts remain explicit warnings/check results but do not prevent `allow`. A missing or unauthorized manifest is `deny`. When freshness is required and no approved method is supplied, freshness is `fail`, the decision is `deny`, `primaryError` is `E_FRESHNESS_REQUIRED` unless an earlier failure wins, and exit code is 1. An authorized freshness-unanchored manifest may become `allow` only through explicit `allowReplayableHandoff` opt-in, which records freshness as `not_checked` with `W_FRESHNESS_NOT_CHECKED`.

The “default policy” phrase describes the mandatory reference verification posture, not implicit policy-field or limit values: unknown keys never count toward authorization, missing authorization rules fail, unknown critical profiles and missing critical artifact bytes fail, an authorized manifest is mandatory, freshness requires an approved method, one distinct authorized Ed25519 key is required per payload, and no network retrieval occurs. A well-formed unknown co-signature warns but does not poison an envelope whose authorized threshold is otherwise satisfied. A supplied policy may tighten these rules but MUST NOT turn a failed core, signature, digest, graph, or consumer-required-profile check into `allow`.

Consequently, a semantically clean evidence set is still denied if diagnostics or required report detail cannot fit the consumer's report budgets: the Step 14 resource error is fail-closed, not a presentation-only warning.

## 16. Reference CLI and library contract

The v0.2 reference implementation MUST use Python 3.11 or newer, be managed and locked with `uv`, and expose one canonical `makoto` command through `[project.scripts]` in the core `pyproject.toml`. Runtime dependencies include `cryptography` for key generation/serialization, `jsonschema` plus `referencing` as Draft 2020-12 infrastructure, and the pinned `rfc8785` package for JSON Canonicalization Scheme output. Phase 0 MUST run the strict positive/negative Ed25519 vectors against the exact pinned native verification backend. The reference implementation MAY rely on that backend only if every vector passes; otherwise it selects a maintained native strict-Ed25519 dependency or adds the minimal point-validation adapter required to pass. No implementation may infer compliance from a library name or replace the verification equation with weaker acceptance. The Makoto validation core still replaces float conversion and host regular expressions for exact rationals and `makotoPattern`. The reference implementation MUST NOT substitute a handwritten approximate JCS canonicalizer. Strict JSON loading, graph traversal, hashing, DSSE encoding, bundle safety, and CLI parsing use the Python standard library. The implementation MUST support CPython 3.11 and 3.12 on macOS and Linux.

Windows path grammar remains normative for portable bundle bytes, but Windows ACL, known-folder, and runtime behavior in Sections 16 and 22 apply only to an implementation that claims Windows runtime support. The v0.2 reference implementation and conformance matrix claim macOS/Linux only; their release is not blocked by an unexecuted Windows runtime gate.

The runtime boundary for `jsonschema` and `referencing` is narrow. They MAY validate immutable Makoto core schemas and support differential tests against ordinary Draft 2020-12 behavior. They MUST NOT determine the normative organizational-profile traversal order, operation/resource charging, exact rational arithmetic, `makotoPattern` evaluation, keyword-support classification, or deterministic diagnostic ownership; the bespoke bounded profile evaluator defined here owns those decisions.

### 16.1 Required commands

```text
makoto digest <artifact> [--json]

makoto key generate \
  --private-out <pkcs8-pem-path> \
  --public-out <spki-pem-path>

makoto key inspect --public <spki-pem-path> [--json]

makoto envelope inspect --envelope <envelope-path> [--json]

makoto envelope cosign \
  --envelope <envelope-path> \
  --key <private-key-path> \
  --out <envelope-path> [--force]

makoto attest origin \
  [--subject <name=path>]... [--subject-binding <binding.json>]... \
  --source-kind <uri> \
  [--source-uri <uri>] \
  [--source-metadata <binding.json>] \
  [--extensions <extensions.json>] \
  [--event-id <uri-or-uuid>] \
  [--occurred-at <rfc3339>] \
  [--profile <profile-ref-file>]... \
  [--schema-catalog <catalog.json>]... \
  --key <private-key-path> [--key <private-key-path>]... \
  --out <envelope-path> [--force]

makoto attest transform \
  [--subject <name=path>]... [--subject-binding <binding.json>]... \
  --input-binding <binding.json> [--input-binding <binding.json>]... \
  --operation-type <uri> \
  [--operation-name <string>] \
  [--operation-metadata <binding.json>] \
  [--extensions <extensions.json>] \
  [--event-id <uri-or-uuid>] \
  [--occurred-at <rfc3339>] \
  [--profile <profile-ref-file>]... \
  [--schema-catalog <catalog.json>]... \
  --key <private-key-path> [--key <private-key-path>]... \
  --out <envelope-path> [--force]

makoto handoff create \
  --head <envelope-path> [--head <envelope-path>]... \
  --attestations <directory> \
  --artifact-binding <binding.json> [--artifact-binding <binding.json>]... \
  [--artifact-material <binding.json>]... \
  [--dataset-entry-binding <binding.json>]... \
  [--required-profile-binding <binding.json>]... \
  [--schema-catalog <catalog.json>]... \
  [--external-profile <profile-ref-file>]... \
  [--bundle-id <uri-or-uuid>] \
  [--recipient <string>] [--nonce <string>] \
  [--issued-at <rfc3339>] \
  --key <private-key-path> [--key <private-key-path>]... \
  --out <bundle-directory> [--force]

makoto verify bundle <bundle-directory> \
  --policy <trust-policy.json> \
  [--schema-catalog <catalog.json>]... \
  [--artifact-material <binding.json>]... \
  [--dataset-entry-binding <binding.json>]... \
  [--expected-manifest sha256:<hex>] \
  [--expected-head sha256:<hex>]... \
  [--expected-artifact <binding.json>]... \
  [--expected-recipient <string>] \
  [--expected-nonce <string>] \
  [--evaluation-time <rfc3339>] \
  [--temp-parent <private-directory>] \
  [--timing] \
  [--json]

makoto schema validate <instance> \
  [--profile-reference <profile-ref-file> | --schema <uri-or-path>] \
  [--schema-digest sha256:<hex>] \
  [--schema-catalog <catalog>]... [--verbose]

makoto profile create \
  --schema-root <schema-path> \
  --target <statement|predicate|artifact> \
  [--subject-name <name> --media-type <type>] \
  --critical <true|false> \
  [--schema-catalog <catalog>]... \
  --out <profile-ref-file> [--force]

makoto policy check --policy <trust-policy.json> [--json]

```

At least one `--subject` or `--subject-binding` is required. `--subject` is repeatable and splits on the first `=`; the left side is the exact signed subject name and the right side is a local path resolved from the invocation working directory. Because that compact form cannot encode a name containing `=`, a subject-binding file has exactly `name` and `path` and permits every wire-valid subject name; its path is resolved from the binding file's directory. The combined subject-name set is duplicate-free. An input-binding file has exactly `name`, `path`, `predecessor`, `subjectName`, optional `entryName`, and conditionally required `predecessorMaterial`; `predecessor` is a local envelope path. When `entryName` is present, `predecessorMaterial` MUST be the local dataset-manifest artifact path, and `attest transform` verifies its subject digest, core dataset-manifest schema/profile identity, unique entry membership, and the input partition's digest/optional size before signing. Without `entryName`, `predecessorMaterial` is forbidden. A source-metadata binding is a nonempty closed object containing any subset of `name`, `mediaType`, `retrievedAt`, and `version` with the exact Section 11.3 types. An operation-metadata binding is a nonempty closed object containing optional `tool` and/or `parametersDigest`; `tool` is a nonempty closed object containing any subset of `name`, `version`, `uri`, and `digest` with the exact Section 11.4 types. An extensions file is one strict JSON object whose keys and values satisfy Section 11.2 and is inserted exactly as the predicate `extensions` object. An artifact-binding file identifies a final handoff artifact and has exactly `head`, `subjectName`, `path`, plus optional `mediaType`; `head` is a local envelope path and `mediaType`, when supplied, is copied to the manifest artifact entry. An artifact-material file supplies bytes needed for a historical critical profile or dataset-manifest edge and has exactly `statement`, `subjectName`, and `path`. A dataset-entry binding has exactly `manifestStatement`, `manifestSubjectName`, `entryName`, and `path`. A required-profile binding is artifact-only and has exactly `head`, `id`, `digest`, `closureDigest`, `target: "artifact"`, `subjectName`, `mediaType`, and `scope: "eachMatchingFinalArtifact"`; it MUST exactly match a profile reference in that head. Every relative path stored inside a binding file—including `path`, `predecessor`, `predecessorMaterial`, `head`, `statement`, and `manifestStatement`—is resolved from that binding file's containing directory, never the process working directory. Every digest-valued member in a producer or consumer binding JSON file uses the digest-object shape `{ "sha256": "<64 lowercase hex>" }`; the `sha256:<hex>` spelling is only for CLI scalar flags. These local paths are never copied into signed predicates. Repeated bindings are processed in command-line order for display only; graph meaning remains order-independent.

For `attest origin` and `attest transform`, the reference producer preserves the validated command-line occurrence order when constructing signed `subject`, `inputs`, and `profiles` arrays: compact flags and binding-file flags contribute at their exact positions in the relevant repeatable option stream. It does not sort those arrays. The deterministic demo invokes each command in one checked-in fixed order and therefore produces fixed bytes. These arrays are not protocol-sorted unless an explicit schema rule elsewhere says so; independent verifiers MUST accept every order that satisfies uniqueness and other core rules, and lineage semantics do not depend on array position. Handoff/index arrays that Sections 12.5, 13.2, and 13.3 explicitly require sorted remain sorted and are unaffected by this producer rule.

All producer and consumer binding files use the Section 10.4 strict-JSON contract: UTF-8 without BOM, duplicate-key rejection, valid Unicode scalars, exact closed object shapes, and bootstrap JSON depth/number limits. A violation is invalid invocation/configuration with exit 2 before producer signing or evidence evaluation. For a direct input binding without `entryName`, `attest transform` MUST hash the local input bytes and require equality with both the selected predecessor subject digest and the digest it will sign for the transformation input; mismatch exits 2 and no envelope is written.

`profile create` is the normative safe authoring path for a profile reference. It strict-loads the root path, takes `id` from its exact root `$id`, resolves and validates the complete non-core closure from the supplied catalogs, verifies every digest and dialect rule, builds the sorted `resources` array, computes root `digest` and JCS `closureDigest`, enforces artifact-only subject/media arguments, and atomically writes the complete closed `profile-reference.schema.json` object. It never copies schema bytes to the output or retrieves a network resource. `policy check` runs the complete Section 14 consumer-policy preflight without a bundle; exit 0 means valid, exit 2 uses the stable invalid-input tool error, `--json` emits `{"policyDigest":{"sha256":<hex>},"valid":true,"warnings":[]}` as JCS-plus-LF when there are no overlap warnings, and human success emits exactly `valid\n`.

Each `--profile` file is exactly one strict JSON object conforming to `profile-reference.schema.json`. When any is supplied to an attestation command, the command MUST resolve its root and complete resource closure from the supplied `--schema-catalog` inputs plus the immutable core catalog, verify every exact digest and `$id`, recompute `closureDigest`, perform the load-time dialect/reference checks from Section 12.1, and reject any mismatch before signing. A producer therefore cannot emit an unchecked or internally incomplete profile reference through the reference CLI. Private profile bytes remain local and are not automatically copied into the signed statement. After constructing the exact unsigned statement payload and hashing every subject, `attest origin` and `attest transform` MUST validate that statement, its predicate, and each targeted artifact against every supplied profile reference before signing; any unresolved closure, format failure, or invalid instance exits 2 and writes no envelope. The public authoring CLI therefore never signs a profile claim it knows is false. Conformance and attack fixtures that intentionally contain a valid signature over an invalid profile claim are built by the deterministic fixture constructor, not by weakening or bypassing this authoring command.

`--attestations` scans exactly the named directory's immediate regular files whose names end in `.dsse.json`, in UTF-8 byte-sorted filename order; it does not recurse or follow links. Every `--head` path MUST resolve to one of those selected files. Every selected envelope must belong to the exact graph reachable from a supplied head, duplicate statement payload digests fail, and disconnected selected envelopes fail creation rather than being silently omitted. Every supplied head MUST also be named by at least one `--artifact-binding`, and the distinct bound-head set MUST equal the supplied head set by SHA-256 digest of exact decoded statement payload bytes, never by path spelling or physical file identity; otherwise `handoff create` exits 2 without producing a bundle. Before constructing or signing the manifest, `handoff create` MUST safe-open every final `artifact-binding` and supplied historical/dataset material, copy each source into a private immutable producer snapshot while hashing, and use only those snapshots for all subsequent validation and bundle copying. It requires every final snapshot's exact `(head statement, subjectName, digest)` match, subject terminality and the complete computed roots/heads/statement set, rejects any optional manifest media-type conflict with the signed artifact profile, validates every required-profile binding by the exact tuple above, and validates every supplied historical/dataset snapshot under the same producer-side rules the verifier will apply. After copying from snapshots into the staged bundle, it rehashes every copied artifact/material file and compares it with the manifest/index digest before atomic output publication; source-path mutation after snapshot creation cannot change signed or copied bytes. Any mismatch is invalid producer input, exits 2, and leaves no bundle. `--artifact-material`, `--dataset-entry-binding`, and `--schema-catalog` provide the material needed to construct the corresponding optional bundle index entries.

Before suffix selection, `--attestations` requires every immediate directory-entry filename to be valid UTF-8 in NFC and to satisfy the Section 10.4 control-scalar and 255-byte filename-component bounds. Any invalid/non-NFC name or non-regular/link entry is invalid producer input with exit 2; it is not ignored or raw-byte sorted. The `.dsse.json` suffix test is then an exact ASCII-byte suffix test and selected names sort by their validated UTF-8 bytes. Phase 0 includes invalid UTF-8, canonically equivalent non-NFC, link, directory, and ordinary nonsuffix entries; only the ordinary valid nonsuffix file is safely ignored.

Signing-key cardinality is command-specific. `attest origin`, `attest transform`, and `handoff create` each require one or more `--key` values; `envelope cosign` requires exactly one `--key`; `key generate` and `profile create` have no signing-key requirement. Wherever multiple keys are accepted, they MUST resolve to distinct recomputed key IDs and a duplicate is invalid input. The producer signs the one exact payload with every supplied key and serializes signature entries in ascending `keyid` UTF-8 byte order, making threshold handoffs and statements directly producible without bundle surgery. `envelope cosign` accepts exactly the statement and handoff payload types from Section 10.1, structurally validates the envelope, payload type, canonical encodings, duplicate key IDs, and existing signature lengths, and rejects a new key ID already present; because it receives no trust policy, it does not cryptographically validate unknown existing signatures. It appends the new key's signature, self-verifies that signature, re-sorts the complete signature array by `keyid`, and writes a new envelope. Input and output MUST resolve to different files, even with `--force`, so the input is never mutated or path-replaced.

For repeated handoff-create `--schema-catalog` inputs, the producer strict-loads each catalog, sorts all entries by `(id, digest.sha256)`, collapses an identical tuple only when verified bytes are identical, rejects one tuple with conflicting bytes, and rejects a core ID with a non-core digest. It then computes the exact non-core schema-resource closure referenced by profiles on the selected graph plus any explicit `--required-profile-binding`; unrelated catalog entries are resolver inputs only and MUST NOT be exported. Each `--external-profile` file is a complete profile-reference object whose identity tuple MUST exactly match one signed reference in the selected graph; supplied identities are duplicate-free, and a missing match exits 2. For every selected embedded profile, export its non-core root schema and every declared non-core resource in that profile's signed `resources` closure; no declared resource may be omitted merely because it is not reached by the demo instance. Each selected non-core root/resource is copied once to bundle path `schemas/resources/<sha256>.schema.json`. Root and resource bytes reachable exclusively from external profiles are omitted and must be supplied by the receiver's authenticated catalog. If an external and embedded profile share a root or resource, the embedded use causes one copy, so the flag cannot make another selected profile incomplete. Because catalog paths are relative to `schemas/catalog.json`, each generated exported entry path is exactly `resources/<sha256>.schema.json`. One generated `schemas/catalog.json` containing only exported entries becomes the sole `bundle.json.schemaCatalog`; when no resource is exported, the bundle omits `schemaCatalog` and no empty catalog file is generated. Input catalog order, external-profile flag order, and original paths do not affect generated bytes. Exporting a whole input catalog requires a future explicit opt-in flag and is not supported in v0.2.

One supplied `--external-profile` identity externalizes every occurrence of that complete profile-reference identity across the selected graph and explicit required-profile bindings; it does not select one statement occurrence. At least one occurrence is required, duplicate flag identities are invalid, and all matching occurrences share the same omitted root/resource bytes. A different identity on another statement remains embedded unless separately externalized. Phase 0 includes one identity used by two statements and proves that one flag omits both occurrences deterministically.

`--head` and `--expected-head` are repeatable and each resulting set is duplicate-free. When expected heads are supplied, their one complete set MUST equal the manifest head set. A verifier expected-artifact binding has exactly `head`, `subjectName`, and `digest`, where `head` and `digest` are digest objects of shape `{ "sha256": "<64 lowercase hex>" }`, not local paths; the complete supplied set MUST equal the corresponding signed manifest artifact tuples. A verifier `--artifact-material` binding has exactly `statementDigest`, `subjectName`, `digest`, and `path` and supplies consumer-held historical or dataset-manifest bytes absent from the bundle; it cannot substitute for a missing final-artifact bundle mapping. Its declared digest is the expected named-subject digest and is checked before acceptance. A verifier `--dataset-entry-binding` has exactly `manifestStatementDigest`, `manifestSubjectName`, `entryName`, `digest`, and `path`. All digest members use the digest-object shape: statement digests identify signed payloads, while artifact/entry `digest` identifies the exact expected subject or member bytes. The verifier form never contains the producer-only local-envelope path `manifestStatement`. These bytes are immutable-snapshotted and checked identically to bundle material but do not alter the signed handoff or unsigned bundle index. `--expected-manifest` compares the exact decoded manifest payload digest. Every scalar digest CLI flag accepts only the literal `sha256:` followed by 64 lowercase hexadecimal characters. Every expected-value binding file, policy, consumer catalog, and consumer material file MUST be physically outside the bundle root and must not alias any bundle entry, so producer material cannot bootstrap its own trust anchor. Preflight snapshots consumer metadata, while artifact targets are safe-opened for identity/type/size only and copied at Step 8 or 12. Immediately after Step 1 establishes the bundle root and inventory, every policy, consumer catalog/resource, expected-value file, binding file, and consumer artifact handle is compared against every bundle handle/root; any containment or physical alias is Step 1 `E_BUNDLE_UNSAFE_PATH` owned by `load-safely`, exit 1 with a report. Whenever the consumer supplies an expected recipient or nonce, it MUST exactly match the signed manifest even when policy did not require it. A supplied string compared with an absent signed recipient or nonce is a mismatch. A missing policy-required value or any supplied mismatch produces a verification report, `deny`, exit code 1, and `E_HANDOFF_RECIPIENT` or `E_HANDOFF_NONCE`; it is not a CLI syntax error. `--evaluation-time` is consumer input for key-validity and optional handoff-age policy and MUST NOT be inferred from signer-asserted event timestamps.

Artifact-material identity is `(statementDigest.sha256, subjectName, digest.sha256)`, all three members being present in a consumer binding or bundle tuple before payload decoding. Consumer bindings must be duplicate-free. A consumer binding is permitted only when the bundle has no artifact mapping for that identity; the Step 2 bundle semantic pass compares these already-known tuples, and a duplicate bundle/consumer source fails completed verification with `E_CORE_SCHEMA` rather than choosing precedence. Dataset-entry mapping identity is instead the logical tuple `(manifestStatementDigest.sha256, manifestSubjectName, entryName)`; its declared `digest` is a value to compare with the uniquely resolved dataset-manifest member, not part of identity. A duplicate logical identity entirely within bundle `datasetEntries` mappings, or duplicated once in the bundle and once in consumer `--dataset-entry-binding` input, fails `E_CORE_SCHEMA` at Step 2 even when the declared digests differ; duplicates entirely among consumer bindings are the preflight exit-2 case below. Distinct identities may not resolve to the same physical file. The verifier compares physical identity from opened handles—POSIX device/inode or the Windows volume/file identifier—and never path strings alone. A physical alias entirely inside the bundle or between bundle and consumer material is Step 1 completed evidence failure `E_BUNDLE_UNSAFE_PATH`; preflight validates consumer binding syntax and safe opening but does not infer bundle mappings. Every accepted source is hashed once and produces one artifact report record; conflicting bytes fail `E_ARTIFACT_DIGEST`.

Duplicate identities entirely among consumer-supplied artifact-material or dataset-entry bindings are invalid consumer configuration and exit 2 during preflight, before the bundle is opened. Step 2 `E_CORE_SCHEMA` owns only a duplicate entirely inside `bundle.json` or a cross-source identity duplicated once in the valid bundle index and once in preflight-valid consumer bindings. Thus “within or across” above does not move consumer-consumer duplicates into evidence processing. Phase 0 pins exit/report presence for all three scopes.

Demo key files are Ed25519 PKCS#8 PEM private keys and SubjectPublicKeyInfo PEM public keys. Input accepts exactly one unencrypted PEM block with exact label `PRIVATE KEY` or `PUBLIC KEY` as appropriate, ASCII bytes, consistently LF or CRLF line endings, an optional final line ending, no leading/trailing text or second block, and canonical padded RFC 4648 base64 split into nonempty lines of at most 64 characters. After line concatenation, canonical base64 decoding and the strict DER rules in Section 10.3 apply. The sole accepted private-key DER is the 48-byte RFC 8410 PKCS#8 v1 `PrivateKeyInfo` sequence `302e020100300506032b657004220420 || 32-byte-private-seed`: version 0, Ed25519 OID `1.3.101.112`, absent algorithm parameters, outer private-key OCTET STRING containing one 32-byte inner OCTET STRING, no attributes, no public-key field, and no trailing DER. `OneAsymmetricKey` version 1 and every alternate wrapping are rejected. `key generate` emits exactly that private DER and the 44-byte SPKI DER from Section 10.3, with LF-only PEM, 64-character body lines except the final shorter line, and one final LF. The CLI rejects every other label, encrypted or non-Ed25519 key, noncanonical body, alternate DER, or extra block with exit code 2. Private-key creation uses an owner-only directory and file mode `0600` on POSIX; on Windows it creates the file with an ACL granting only the current user and system administrators. On macOS, the output parent, staged private-key file, and final private-key file MUST additionally have no extended ACL entry granting another principal access: inherited ACLs are cleared before seed generation and the staged and renamed final file are revalidated before success. Failure is operational exit 3, removes any staged/private output, and never prints key material. The implementation never weakens an existing restrictive mode. The private and public output targets of `key generate` MUST be distinct after NFC normalization and Unicode-15.0 full case folding of their containing-directory-relative names, in addition to being exact-path distinct; a collision exits 2 before staging either file. Production signing adapters may implement HSM/KMS-backed keys through the library signer interface, but they are not required for the reference release.

PEM input accepts any nonempty body-line wrapping from 1 through 64 base64 characters per line after enforcing consistent line endings; it need not use the generator's 64-character wrapping. “Noncanonical body” means a noncanonical RFC 4648 alphabet/padding/pad-bit spelling after line concatenation, not a shorter legal input line. Output remains fixed at generator-style 64-character lines for reproducibility. Phase 0 covers two different accepted wrappings of identical DER and rejected alphabet/padding variants.

`key inspect --json` emits exactly the closed JCS object `{"keyid":"sha256:<64 lowercase hex>","publicKey":"<RFC 4648 base64 of canonical DER SubjectPublicKeyInfo, with padding>","type":"ed25519"}` plus one LF. `envelope inspect --json` strict-parses one envelope and emits exactly `{"payloadType":<exact string>,"statementDigest":{"sha256":"<64 lowercase hex>"}}` for an in-toto statement or `{"manifestDigest":{"sha256":"<64 lowercase hex>"},"payloadType":<exact string>}` for a handoff, serialized as JCS plus one LF; it hashes exact decoded payload bytes and does not verify trust without a policy. Both JSON inspection modes use the reference deterministic JCS serializer and exactly one final LF, and Phase 0 fixtures compare their exact bytes. Their non-JSON human output is non-normative stdout with empty stderr on success. These are the normative safe paths for authoring policy keys and out-of-band expected digests. `makoto digest` continues to hash exact file bytes only. Successful `key generate`, `attest origin`, `attest transform`, `envelope cosign`, and `handoff create` write no stdout or stderr; their requested file/directory outputs are the success artifacts.

The verifier resolves the bundle root and every consumer-supplied path by opened descriptors before reading evidence and rejects policy, consumer catalog, expected-value binding, artifact-material, or dataset-entry binding files located inside the bundle root through path or physical alias. External consumer files may use absolute paths but must be regular non-link files opened no-follow, snapshotted once into the owner-only verifier directory, and rechecked for stable opened identity/size after copying. Symlink, hard-link ambiguity, replacement, or duplicate physical identity entirely among consumer files exits 2 during preflight; every containment or alias comparison against bundle material is deferred until the Step 1 bundle root and inventory are safely established, then uses completed-evidence `E_BUNDLE_UNSAFE_PATH`. Explicitly typing an in-bundle path does not convert producer material into consumer trust. A bundle catalog is always treated as untrusted evidence.

Creation commands with an `--out` flag reject an existing output path unless `--force` is explicitly supplied. Before reading or writing, every output target MUST be disjoint from every input and sibling output by exact resolved path, NFC-plus-full-case-folded parent-relative spelling, and physical identity when the target already exists; a collision exits 2. This includes signing keys, subjects, predecessor envelopes/material, profiles, catalogs, binding files, and attestation directories. `--force` never relaxes disjointness. File outputs are written to a same-directory temporary regular file, synced, and atomically renamed; `--force` may replace only an existing regular file, never a symlink or special file. `key generate` never overwrites either key path and therefore has no `--force`; both parents must be the same directory, both distinct targets must be absent, both files are staged before either final name is created, and a recoverable error removes only newly staged/generated files. A process or machine crash may leave one newly named key file, which is a documented incomplete operation that the next invocation detects and refuses to overwrite; no impossible two-file atomicity is claimed. `handoff create` builds a sibling temporary directory and renames it only after completion; even with `--force`, an existing nonempty output directory is rejected, while an existing empty real directory may be replaced. Verification never writes into the bundle and exposes no network-schema flag in v0.2. Timestamps default to the current UTC time; omitted event and bundle IDs are generated as the exact string `urn:uuid:` followed by a canonical lowercase RFC 4122 version-4 UUID using a cryptographically secure OS random source. Tests and the demo supply timestamps/IDs explicitly for deterministic fixtures.

The immutable core catalog is always active. Zero or more consumer `--schema-catalog` files and an optional bundle catalog are combined without precedence: duplicate non-core `(id, digest)` entries are allowed only when their verified bytes are identical, while distinct digests under one non-core ID remain distinct resources selected by the signed or policy-pinned digest. Exact identical core duplicates are ignored, and a core ID with another digest is invalid as defined in Section 12.3. `schema validate` requires exactly one of `--profile-reference` or `--schema`. `--schema-digest` is forbidden with `--profile-reference`; the reference already contains its digest. Profile-reference mode supplies the root and complete digest-pinned resource closure defined in Section 12.1 and validates `<instance>` directly as the declared target instance; an artifact reference's `subjectName` is retained for identity diagnostics but does not cause the standalone command to search a statement. For an artifact reference with `mediaType: "application/x-ndjson"`, the command splits and validates finite NDJSON exactly as Section 12.4 defines; for JSON artifact, statement, and predicate references it strict-parses one monolithic JSON instance. Standalone `--schema` mode always accepts one monolithic JSON instance. Its argument is a local path only when it begins `./`, `../`, `/`, a Windows drive prefix, or a UNC prefix; every other spelling must be an absolute URI. A POSIX relative filename containing `:` must therefore be prefixed with `./`. URI mode requires `--schema-digest`; local-path mode permits an optional `--schema-digest`, which must match the computed root digest when supplied. In both modes the root schema MUST declare the Makoto profile-dialect `$schema` and is evaluated as a profile-dialect resource against the supplied JSON instance. Profile-reference mode may resolve exactly its declared digest-pinned non-core closure plus immutable core resources. Bare `--schema` mode permits only fragment-local `$ref` plus immutable core references; any other external reference exits 2. Neither mode silently switches to generic host-library JSON Schema behavior, selects a transitive resource by URI alone, or uses ambient/network resolution.

`makoto schema validate` has no consumer policy and therefore applies the immutable Section 15 bootstrap ceilings directly: 16 MiB per schema resource, 256 MiB aggregate schema closure, 4096 resources, schema depth 1024, 1,000,000,000 schema operations per evaluation unit, regex length 65,536 scalars, JSON depth 256, 4096 number-token characters, exponent magnitude 100000, a 1 GiB instance-byte ceiling, and a 60-second/4-GiB worker boundary. Exit 0 means valid. Exit 1 means the supplied instance did not produce a valid instance result, including schema violation, malformed instance JSON, invalid instance UTF-8/BOM/scalars, duplicate instance keys, malformed or zero-instance NDJSON, or artifact-media parse failure. Exit 2 is restricted to invalid invocation or invalid schema/profile-reference/catalog configuration, including malformed schema/config JSON, bad schema closure/digest/dialect, illegal flag combinations, or a missing required configuration file. Exit 3 means a resource, timeout, memory, I/O-after-valid-open, or internal operational failure. No environment-specific validator default may raise those ceilings.

`makoto schema validate` writes exactly `valid\n` to stdout on exit 0 and exactly `invalid\n` on exit 1. With `--verbose`, non-normative validation detail is written only to stderr after that stdout result; without the flag stderr is empty on exit 0/1. `key inspect --json` and `envelope inspect --json` use the closed object fields already specified above and Phase 0 publishes positive/negative CLI fixtures for both; they are tooling contracts, not additional protocol schemas. `verify bundle --timing` writes one additional RFC 8785 JCS object plus LF to stderr after the normal completed stdout: `{"steps":{"1":<integer>,"10":<integer>,"11":<integer>,"12":<integer>,"13":<integer>,"14":<integer>,"2":<integer>,"3":<integer>,"4":<integer>,"5":<integer>,"6":<integer>,"7":<integer>,"8":<integer>,"9":<integer>},"totalNanoseconds":<integer>}`. Each value is elapsed monotonic time, absent/skipped steps are zero, the total begins immediately before Step 1 and ends after Step 14 report admission, and timing output is observational rather than a verification-report comparison surface.

These command and subcommand names, required flags, exit codes, and JSON report fields are normative for the v0.2 reference CLI. Implementation may add backward-compatible optional flags. Any breaking CLI change requires revision of this specification before code changes and an atomic update to tests, demo scripts, and website copy.

`makoto digest` writes exactly `sha256:<64 lowercase hex>` plus LF in human mode and exactly `{"sha256":"<64 lowercase hex>"}` plus LF using the deterministic JSON serializer in `--json` mode. All report timestamps, including consumer-supplied `--evaluation-time`, are parsed to an instant and re-rendered canonically rather than echoing input bytes: trailing fractional zeros are removed, and when no fractional digits remain both the decimal point and fraction are omitted (for example `.000Z` becomes `Z`).

For every repeatable identity-bearing flag, “duplicate-free” applies to supplied values after path/digest resolution: repeating the same `--head` or `--expected-head`, or supplying duplicate complete `--expected-artifact` identities, is invalid invocation exit 2. The CLI never silently deduplicates repeated values.

Every option documented as singleton is accepted at most once. Repeating `--policy`, `--expected-manifest`, `--expected-recipient`, `--expected-nonce`, `--evaluation-time`, `--temp-parent`, any output path, any scalar timestamp/ID/source/operation option, or another nonrepeatable option is invalid invocation exit 2; there is no first-wins or last-wins behavior. Phase 0 CLI vectors cover security-sensitive singleton duplication before any file is opened.


`policy check --json` additionally includes a sorted `warnings` array of closed objects `{ "code": "W_POLICY_RULE_OVERLAP", "ruleA": <id>, "ruleB": <id> }`; an empty array is present when none. Human mode still emits `valid\n` and writes each overlap warning as one ASCII-safe JCS line to stderr in the same sorted pair order. Overlap warnings do not change exit 0. No `--timing` object is emitted on exit 2 or 3. Consumer preflight is Step 0 and is deliberately excluded from both `totalNanoseconds` and the per-step map; timing begins only after preflight succeeds, immediately before Step 1.

Supplied expected-head and expected-artifact sets are either absent or nonempty. An explicitly present empty set in a library request or binding object is invalid consumer configuration exit 2; it is never equivalent to “method supplied,” never compared with the manifest, and never qualifies as freshness. The CLI repeatable flags represent absence by supplying no occurrence and a nonempty set by one or more occurrences, so it has no empty spelling. Library adapters MUST preserve that presence rule before constructing the canonical accounting object.

Every producer command uses one immutable-input generation. `attest origin` and `attest transform` safe-open and snapshot every subject/input artifact, predecessor envelope/material, profile reference, selected schema root/resource, binding, extensions object, and source/operation metadata input before hashing or validation; the digest, profile validation, statement construction, and signature all use only those snapshots. `handoff create` applies the same rule to every selected head/attestation envelope, profile reference, exported schema root/resource, catalog/binding input, and artifact/material input; manifest graph discovery, closure export, signing, and staged bundle copying all use only those snapshots. A loaded signing key is parsed once into a nonlogging signer object. Before atomic publication, each staged envelope, schema, index, and artifact is rehashed or byte-compared with the snapshot-derived expected bytes. A source mutation after snapshot creation cannot make a command validate one byte sequence and sign or copy another; snapshot/open/recheck failure exits 2 for invalid input discovered before generation begins or 3 for operational failure after a valid generation has begun, with no published output.

Ordinary profile workers use a closed IPC contract parallel to the dataset worker. They return exactly `{"diagnostic":<null-or-diagnostic>,"evaluationsConsumed":<nonnegative-integer>,"phase":<"complete"|"resolution"|"validation">,"status":<"pass"|"invalid"|"unresolved"|"resource_limit">,"tokenCount":<nonnegative-integer>}` validated against immutable `src/makoto/internal-schemas/profile-worker-result.schema.json`, whose digest is asserted by `scripts/check.sh`. Before launch, the parent reserves a positive `profileEvaluationQuota` no greater than the invocation's remaining `maxProfileEvaluations` units and passes that integer through the fixed worker request. The first fused closure/instance attempt consumes one; for NDJSON, each later nonblank physical line consumes one immediately before that line is opened, and the worker returns `resource_limit` without opening a line when no reserved unit remains. `evaluationsConsumed` is the exact number consumed through the reported outcome, is at most the reserved quota, and is at least one whenever closure work began. `pass` requires `phase: "complete"` and null diagnostic; `unresolved` requires `phase: "resolution"`; `invalid` requires `phase: "validation"`; and `resource_limit` uses the phase in which the bound was hit. Every non-pass result carries exactly one closed diagnostic object of the dataset-worker shape. `tokenCount` is the exact structured-artifact token count consumed in that attempt; it is zero for statement/predicate instances already parent-tokenized and for an artifact attempt that consumed no token. The parent validates the complete result, both reserved capacities, and JCS encoding; permanently charges `evaluationsConsumed` and `tokenCount`; releases unused reservations; charges the complete JCS byte length once to `maxMetadataBytes`; and enforces a 1 MiB complete-object ceiling including both counts and context. No decoded instance/schema tree crosses the boundary and no incremental quota channel exists. If timeout, OS-enforced memory termination, or another operational kill prevents a valid final object, the parent permanently charges the complete reserved profile-evaluation quota and structured-token capacity because exact consumption is unknowable, then maps the attempt to the applicable `E_RESOURCE_LIMIT`. Malformed IPC, an impossible field combination, a count above reservation, excess IPC bytes, or an unexplained child crash is a trusted-tool invariant failure and exits 3 after termination/reap. Phase 0 pins the request/result schemas, one/many/blank NDJSON counts, exact quota exhaustion, successful unused-reservation release, kill charging, and positive/negative IPC vectors for both worker types.

The quota choice above has one formula: because workers run sequentially, `profileEvaluationQuota` equals the invocation's complete remaining `maxProfileEvaluations` count at launch; zero remaining means no launch and immediate aggregate `E_RESOURCE_LIMIT`. The reservation is temporary, later canonical profiles see the returned unused remainder, and an operational kill intentionally consumes the entire then-remaining reservation. No implementation may choose a smaller quota from expected line count, file size, or local heuristics.

### 16.2 Library operations

The reference library SHOULD expose equivalents of:

- `digest_artifact(stream) -> Digest`
- `create_origin(request) -> Statement`
- `create_transform(request) -> Statement`
- `sign_dsse(payload_type, payload_bytes, signer) -> Envelope`
- `create_handoff(request) -> Envelope`
- `verify_bundle(request) -> VerificationReport`
- `validate_with_catalog(instance, profile_ref, catalog) -> ProfileResult`

Library callers MUST be able to supply generic artifact byte streams to digest and producer-authoring operations, keys through an interface rather than raw logging-prone strings, local schema resolvers, and trust-policy bytes programmatically. Generic streams are forbidden as `verify_bundle` evidence inputs because they cannot prove containment, physical aliasing, descriptor identity, or final tree stability. The normative `verify_bundle` request instead carries the same bundle-root and consumer binding/material paths as the CLI, or platform byte-source objects that expose safe no-follow open handles, stable physical identity, immutable snapshot creation, containment/alias comparison, and final-rescan participation with semantics identical to Sections 13.3 and 16.1. A byte array or ordinary file-like object does not satisfy that verifier interface. The normative `verify_bundle` semantics and report are identical to the CLI, and its request carries the original strict-JSON policy bytes so `policyDigest` is reproducible; a caller with an in-memory object must first serialize it with RFC 8785 and those canonical bytes become the reported policy input. In-memory expected values and binding collections use the same canonical accounting object, element ceilings, field bounds, duplicate rules, and `maxMetadataBytes` charges as CLI inputs; a library cannot bypass resource limits by avoiding OS argument or file-size limits. Python function names, request classes, exception classes, and convenience return types are non-normative in v0.2; only wire formats, verification decisions/reports, and the CLI contract are interoperability surfaces.

### 16.3 Output and exit codes

Handoff authorization is never represented ambiguously: when the handoff threshold is evaluated and not met, `handoff.authorization` is `fail`; it is `skipped` only when a transport/core prerequisite prevented threshold evaluation. A threshold failure also fails `authorization-thresholds` and skips authority-dependent handoff work.

The `freshnessMethod: "none"` truth table that gives all five method statuses `not_checked` applies only after handoff authorization passes. If handoff authorization is `fail` or `skipped`, `handoff.completeness`, `handoff.freshnessStatus`, all five `freshnessChecks` members, `recipientStatus`, and top-level completeness/freshness checks are `skipped` with `authorization-thresholds` or the earlier handoff prerequisite as applicable; `freshnessMethod` still reports the syntactically supplied/required population and is `none` when that population is empty. In this stratum `nonceStatus` remains exactly equal to `freshnessChecks.nonce`. Parsed `actualRecipient`/`actualNonce` values may still be reported, but no authority-dependent comparison runs.

When handoff authorization fails, “supplied historical mapping” means only an independently preflight-valid consumer `--artifact-material` binding outside the bundle. No mapping from the unsigned bundle `artifacts` array is classified as historical, opened, hashed, reported, or used for profile eligibility without an authorized handoff; path prefixes and untrusted manifest artifact claims cannot supply that lifecycle classification. Once handoff authorization passes, manifest final tuples classify final mappings and any other valid listed-subject artifact mapping may be processed as historical under the ordinary rules.

Dataset-entry report states are total and use this matrix. Every row contributes to the top-level `artifact-bytes` aggregate under Section 15 folding; any `fail` makes that aggregate fail, a prerequisite-blocked population may make it skipped, and a completed `not_checked` optional entry does not prevent pass:

| Dataset-entry condition | `digestStatus` / prerequisites | `sizeStatus` / prerequisites | Diagnostic and processing |
|---|---|---|---|
| Validated member; no bundle or consumer partition source | `not_checked` / `[]` | `not_checked` / `[]`, even when the member declares `size` | No diagnostic; optional bytes were not supplied. |
| Mapping-declared digest disagrees with the validated member digest | `fail` / `[]` | `skipped` / `["artifact-bytes"]` | Step 12 `E_DATASET_MANIFEST_INVALID`; do not open or hash the mapped target. The record retains the member digest and declared size. |
| Structurally valid mapping target was absent from the completed Step 1 inventory | `fail` / `[]` | `skipped` / `["artifact-bytes"]` | Step 12 `E_ARTIFACT_MISSING`; no bytes or size are inferred. |
| Mapping target was recorded present at Step 1 but is unsafe, unreadable, replaced, or disappears at consuming open | `fail` / `[]` | `skipped` / `["artifact-bytes"]` | Step 12 `E_BUNDLE_UNSAFE_PATH`; no bytes or size are inferred. |
| Current mapping crosses a per-file, aggregate-artifact, or snapshot limit before a complete stable copy exists | `fail` / `[]` | `skipped` / `["artifact-bytes"]` | One Step 12 `E_RESOURCE_LIMIT`; discard the incomplete hash/size attempt and skip later aggregate-dependent entries. |
| Entry is not begun because an earlier canonical entry exhausted an invocation aggregate | `skipped` / `["artifact-bytes"]` | `skipped` / `["artifact-bytes"]` | No second diagnostic; the earlier `E_RESOURCE_LIMIT` owns the aggregate failure. |
| Step 8 cannot establish a valid dataset-manifest subject digest/index | `skipped` / `["graph-dependency-artifacts"]` | `skipped` / `["graph-dependency-artifacts"]` | Step 8 owns its existing `E_ARTIFACT_DIGEST`, `E_DATASET_MANIFEST_INVALID`, `E_DATASET_MANIFEST_REQUIRED`, `E_PROFILE_INVALID`, `E_PROFILE_UNRESOLVED`, or `E_RESOURCE_LIMIT`; Step 12 does not open the partition or duplicate the diagnostic. `declaredSize` is null because no validated member was established. |
| Partition bytes are readable and hash to the wrong digest | `fail` / `[]` | Independently `pass` or `fail` / `[]` when member size is declared; otherwise `not_checked` / `[]` | Emit Step 12 `E_ARTIFACT_DIGEST`; also emit `E_ARTIFACT_SIZE` only when the independently counted byte length disagrees with a declared size. Digest failure does not erase an independently computable size result. |
| Partition digest passes | `pass` / `[]` | `pass` or `fail` / `[]` when size is declared; otherwise `not_checked` / `[]` | Emit only `E_ARTIFACT_SIZE` on size mismatch. |
| Final stable-tree rescan fails after digest and optional size completed | Retain the completed `pass` or `fail` / `[]` | Retain the completed `pass`, `fail`, or `not_checked` / `[]` | Emit Step 12 `E_BUNDLE_UNSAFE_PATH`; the artifact-bytes aggregate fails without erasing completed evidence fields. |

For every row, `digest` follows the precedence already defined for the shared logical record, and `declaredSize` is the validated member's canonical decimal string or null. A member and its size become established only after the subject digest, mandatory dataset-manifest profile resolution, strict artifact parsing, core dataset-manifest schema validation, unique entry-name resolution, and canonical member decoding all pass. A failure in any earlier phase leaves `declaredSize` null; a later edge-input or mapping-digest disagreement retains the already established size. A status of `skipped` always has the exact nonempty prerequisite array shown; `fail`, `pass`, and completed `not_checked` use an empty array. Mapping disagreement, absence, and unsafe-open failures are eligible artifact-byte failures even though no content hash completes.

Human output MUST provide a short check table, remediation-oriented failures, and a final decision line. Completed human output is written to stdout; completed `--json` mode writes only the report to stdout. Warnings that are already represented in a completed report are not duplicated on stderr. Every input-derived string in human terminal output—including producer evidence, bundle/catalog paths, consumer policy labels, expected values, and invocation bindings—MUST be rendered as an ASCII-only JSON string literal, escaping all non-ASCII scalars and control characters; implementations MUST NOT write such strings raw or interpret ANSI/OSC terminal sequences. `--json` MUST emit the stable versioned report as RFC 8785 JCS UTF-8 bytes followed by one LF. Appendix A is pretty-printed for readability and both its whitespace and object-member order are non-normative; its field values, shapes, and array orders remain normative examples. Demo report digests and website copies use the exact JCS-plus-LF bytes. The bundle decision value and final human decision line are limited to `allow` or `deny`; this does not prohibit the preceding human check table or the demo's derived PASS labels. The report schema reserves `indeterminate` for a future verifier mode. The report contains:

- `reportVersion`;
- `decision` (`allow` or `deny` for bundle verification; `indeterminate` remains reserved in the report schema);
- `reportTruncated`;
- `evaluationTime`, exact policy digest, and `policyDigestEncoding: "exact-input-bytes"`;
- immutable core-catalog digest and nullable signed `bundleId` for correlation;
- top-level expected/actual manifest digests, plus handoff signatures, authorization, completeness, and freshness method/status;
- expected and actual heads;
- `expectedArtifacts` for independently supplied final tuples and `artifacts` as the sole actual final/historical artifact record set;
- always-present nullable expected/actual recipient and nonce values plus their check statuses;
- roots and reachable statement count;
- manifest digest;
- final artifact digests;
- per-statement core schema, signature, authorization, and graph results;
- per-profile resolution and validation results;
- unindexable-envelope, quarantined outside-set statement, supplied dataset-entry, and unreferenced-file results;
- a nullable deterministic `primaryError` code;
- warnings and errors with stable codes; and
- tool version.

The verification-report schema is normative, not illustrative. `policyDigest` is SHA-256 over the exact consumer policy bytes passed to verification; `policyDigestEncoding` is always `exact-input-bytes`, including when an in-memory object was first serialized with RFC 8785. `coreCatalogDigest` is always present and is SHA-256 over the exact embedded release bytes of `schemas/v0.2/catalog.json`, not a reconstruction or canonicalized form. Scalar/digest availability is exact: `expectedRecipient`, `expectedNonce`, and report field `expectedManifestDigest` are null exactly when the consumer did not supply them; `manifestDigest` is null exactly when Step 3 could not establish exact decoded handoff payload bytes; and manifest-derived `bundleId`, `actualRecipient`, and `actualNonce` are null until strict parsing and core validation establish their typed values. A core-valid handoff that omits optional recipient or nonce reports the corresponding actual field as null; a strict-valid but core-invalid handoff also reports all three manifest-derived scalars as null; authorization failure after core validity does not erase established actual values. Collection fields are never null: `expectedHeads`, `expectedArtifacts`, `actualHeads`, `roots`, `statements`, `profiles`, `artifacts`, `datasetEntries`, `unindexedEnvelopes`, `quarantinedStatements`, `unreferencedFiles`, `warnings`, and `errors` use `[]` when their population is empty or could not be established. Their associated `not_checked` or `skipped` statuses distinguish unused from prerequisite-blocked populations. No placeholder scalar, digest, or collection member may be invented.

The `handoff` record includes `signatures`, `authorization`, `completeness`, `freshnessMethod`, `freshnessStatus`, and a `freshnessChecks` object with keys `expected-manifest`, `expected-heads`, `expected-artifacts`, `nonce`, and `max-age`, each holding one check status. Manifest signatures use the same signature-record shape as statements. `freshnessMethod` has the closed values `expected-manifest`, `expected-heads`, `expected-artifacts`, `nonce`, `max-age`, `multiple`, or `none`. It is `none` when no method was supplied/evaluated, the exact one method name when exactly one was supplied/evaluated, or `multiple` when two or more were supplied/evaluated, regardless of pass/fail. For an authorized handoff, each supplied or policy-required method is `pass` or `fail` from its comparison, and every method neither supplied nor required is `not_checked` even when another method runs. `freshnessStatus` is `fail` if any supplied or policy-required method fails. When the method is `none`, all five `freshnessChecks` members are `not_checked`; if replay opt-in applies, `freshnessStatus` and the top-level `freshness-anchors` check are `not_checked` with `W_FRESHNESS_NOT_CHECKED`, but if replay opt-in does not apply, `freshnessStatus` and `freshness-anchors` are `fail` with `E_FRESHNESS_REQUIRED`. In every other case, `freshnessStatus` is `pass` exactly when every supplied or required method passes. A required-but-absent method is represented by its named check as `fail` and therefore counts for `freshnessMethod`. Top-level `nonceStatus` MUST equal `freshnessChecks.nonce`; recipient is audience binding rather than a freshness method, so `recipientStatus` remains separate. This summary never hides the per-method results.

Every top-level `checks` entry has `id`, `status`, and `prerequisiteChecks`, where the last field is an empty array unless status is `skipped`. The closed ordered ID set is `load-safely`, `parse-strictly`, `index-payloads`, `core-schemas`, `signatures`, `authorization-thresholds`, `metadata-profiles`, `authorization`, `graph-dependency-artifacts`, `graph`, `roots-and-heads`, `completeness-anchor`, `freshness-anchors`, `artifact-bytes`, `artifact-profiles`, and `decision`, exactly as Appendix A. `authorization-thresholds` is Step 6; `metadata-profiles` and final `authorization` are Step 7. Step 11 emits separate completeness and freshness checks; neither silently aggregates the other. A skipped top-level status names every failed prerequisite top-level check ID that prevented execution, ordered by this same closed check-ID order; forward references are forbidden.

A profile record's one `prerequisiteChecks` array is validation-scoped: it explains why that record's `validation` is `skipped` or `not_checked`; its independent `resolution` value needs no prerequisite array. The profile array's distinct closed enum is ordered `authorization-thresholds`, `metadata-profiles`, `authorization`, `graph-dependency-artifacts`, `graph`, `artifact-bytes`, `artifact-profiles`, `resolution`. `metadata-profiles` and `artifact-profiles` are used only when aggregate worker/resource exhaustion in that owning check prevents a later canonical profile record from starting; `resolution` means that record's own resolution did not pass, so ordinary validation could not run. The array is empty whenever `validation` is `pass`, `fail`, or `indeterminate`; it is nonempty whenever `validation` is `skipped`, and may be empty for `not_checked` only where Sections 12.4 and 16.3 explicitly define a completed optional absence. Media disagreement remains the defined exception whose independently proven `validation: "fail"` has an empty array even when `resolution` is `skipped`, `fail`, or `indeterminate`.

Statement, artifact, and dataset-entry records use field-specific prerequisite arrays. Each is empty unless its associated status is `skipped`, and a skipped status MUST have a nonempty array. Their closed ordered enum is `index-payloads`, `core-schemas`, `signatures`, `authorization-thresholds`, `metadata-profiles`, `authorization`, `graph-dependency-artifacts`, `graph`, `completeness-anchor`, and `artifact-bytes`, in that order. A manifest artifact tuple made ineligible by Step 11 name/digest/head/terminality mismatch has both `digestStatus` and `profileStatus` equal to `skipped`, with `digestPrerequisiteChecks: ["completeness-anchor"]` and `profilePrerequisiteChecks: ["completeness-anchor"]`. These local markers are never placed in top-level `checks[].prerequisiteChecks`. `verification-report.schema.json` MUST close all three enums, conditional nonempty rules, and orders in Phase 0, with a fixture for that Step 11 record.

Every emitted diagnostic MUST contain `causedByCheck`. Every emitted `E_*` diagnostic makes that owning check status `fail`, except a candidate-local profile error suppressed because another authorization candidate succeeds, which is not emitted as a top-level diagnostic. A `W_*` diagnostic names the check that discovered or reports it but does not make that check fail; for example `W_POLICY_RULE_OVERLAP` may be owned by a passing `authorization-thresholds` check. A recipient-only mismatch therefore sets `recipientStatus: "fail"` and `freshness-anchors: "fail"` with `E_HANDOFF_RECIPIENT`; it does not change `freshnessMethod`, the five method-specific `freshnessChecks`, or `freshnessStatus`, because recipient remains audience binding rather than freshness. This failed check still denies. A nonce mismatch is itself a freshness-method failure and changes both the nonce fields and freshness status.

Check-valued fields use only `pass`, `fail`, `indeterminate`, `not_checked`, or `skipped`. A full statement record exists for every manifest-listed envelope whose exact payload bytes and matching payload digest were established, even when strict JSON or core schema later fails. It includes `digest`, nullable `predicateType` and `eventId`, `coreSchema`, ordered `coreSchemaPrerequisiteChecks`, `signatures`, sorted `candidateRuleIds`, sorted `authorizingRuleIds`, `authorization`, ordered `authorizationPrerequisiteChecks`, `graph`, and ordered `graphPrerequisiteChecks`; the nullable fields remain null if strict/core parsing could not establish them. For strict-JSON failure, `coreSchema`, `authorization`, and `graph` are `skipped` with `coreSchemaPrerequisiteChecks: ["index-payloads"]`, `authorizationPrerequisiteChecks: ["index-payloads"]`, and `graphPrerequisiteChecks: ["index-payloads"]`; signatures are evaluated, and both rule-ID arrays are empty. For core-schema failure, `coreSchema` is `fail` with an empty prerequisite array, signatures are evaluated, authorization and graph are `skipped` with `core-schemas` in their respective arrays, and selector/profile loading does not run. A core-valid statement whose signature threshold fails has authorization `fail` and graph `skipped` with `graphPrerequisiteChecks: ["authorization"]`. Step 9 defines graph-dependency and unreachable cases. An attestation envelope that cannot establish indexed payload bytes and its index-declared identity appears instead in `unindexedEnvelopes` with exactly `path`, `payloadTypeStatus` (`pass`, `fail`, or `not_checked`), and `diagnosticCode`. The handoff envelope never appears in `unindexedEnvelopes`; its failures are represented only by the always-present `handoff` fields, check statuses, and diagnostics. If several safely discoverable envelope-local diagnostics apply, `diagnosticCode` is the first under the normative diagnostic ordering; all applicable diagnostics may still appear in top-level `errors`. An indexed outside-set payload appears only in `quarantinedStatements` with exactly `path` and `digest`; it receives no parsed predicate, signature, authorization, profile, or graph result before Step 11. Each signature record includes `keyid`, `keyKnown`, and `cryptographic`; an unknown key has `keyKnown: false`, `cryptographic: "not_checked"`, and `W_SIGNATURE_UNKNOWN`. Every profile record includes its containing statement digest, `id`, root schema digest, closure digest, target, always-present nullable `subjectName` and `mediaType` (both null for statement/predicate targets and both strings for artifact targets), producer criticality, `requiredByManifest`, global `requiredByPolicy`, sorted `requiredByAuthorizationRuleIds`, `resolution`, `validation`, and ordered `prerequisiteChecks`.

Manifest failure population follows explicit boundaries. If `bundle.json` fails Step 2 schema/semantics, no envelope is opened, no manifest-listed set exists, and `statements`, `profiles`, `unindexedEnvelopes`, and `quarantinedStatements` are empty; all later bundle-dependent checks are skipped with the Step 2 prerequisite fixed above. If the bundle index passed but the handoff envelope/payload fails transport parsing, strict payload parsing, or core handoff schema validation, no manifest-listed set exists: every otherwise indexed statement is quarantined, `statements` and `profiles` are empty, and later manifest-dependent checks are skipped. When the handoff exact payload bytes were established but its JSON/core schema is invalid, its DSSE signatures are still cryptographically evaluated and reported; handoff authorization and all manifest-dependent checks are skipped. If the handoff core payload passed and its authorization threshold fails, its exact listed statement set exists but has no authority: listed statements receive all safe processing permitted by their own prerequisites and report records, outside-set statements remain quarantined, and the handoff failure forces `deny`. No manifest `artifacts` tuple is admitted to the report's artifact population, no final-only artifact path is opened or read, and no lifecycle role is inferred from that untrusted tuple. Step 12 still hashes every structurally valid supplied historical mapping whose statement identity can be established independently from a listed signed statement. Step 13 may evaluate an artifact profile on an independently authorized statement only when independently supplied historical material makes that subject eligible; it never treats an untrusted final mapping as that material. Untrusted handoff `requiredProfiles`, final-artifact selection, and consumer `requiredProfiles` scoped through that selection are not applied. `artifact-bytes` and `artifact-profiles` fold only from independently eligible historical work; when no such population exists they are `not_checked` with empty prerequisite arrays. In that threshold-failure state, `handoff.completeness`, `handoff.freshnessStatus`, `completeness-anchor`, `freshness-anchors`, and every method-specific freshness check are `skipped` with `authorization-thresholds` as prerequisite; `freshnessMethod` still reports the supplied/required method population, but no untrusted value comparison receives pass/fail. By contrast, when the handoff has one or more invalid configured-key signatures but its remaining valid authorized distinct-key set meets the handoff threshold, handoff authorization passes, the exact manifest set and requirements acquire authority, and Steps 7–13 including completeness/freshness MUST run; the `signatures` check independently fails and forces the overall decision to `deny`. A statement-only authorization failure likewise does not skip anchors when the handoff itself is authorized. Conformance vectors cover invalid bundle ordering, malformed envelope, malformed payload JSON, core-invalid payload with a valid and invalid signature variant, a handoff with a bad signature and unmet threshold, a mixed-signature handoff whose threshold still passes, an unauthorized handoff signer with historical-material continuation, and statement-only authorization failure.

The `artifacts` array is the sole actual-artifact collection; there is no duplicate `actualArtifacts` field. Its exact identity set is the duplicate-free union of: every final manifest artifact tuple only after handoff authorization passes; every historical statement subject named by a bundle or consumer artifact-material mapping whose statement is manifest-listed, whether reachable or unreachable; every reachable historical subject targeted by a signed producer-critical artifact profile even when its bytes are absent; and every reachable dataset-manifest subject required by a graph edge or dataset-entry mapping. Thus a missing historical subject required only by its critical signed profile still has an artifact record and can report `E_ARTIFACT_MISSING`, and an accepted mapping for an unreachable listed statement is hashed/reported even though exact-set completeness later denies. Every record includes orthogonal `lifecycleRole` (`final` or `historical`) and `artifactKind` (`ordinary` or `dataset-manifest`), `statementDigest`, nullable `head` (equal to `statementDigest` only when lifecycle is `final`), `subjectName`, digest, `digestStatus`, ordered `digestPrerequisiteChecks`, `profileStatus`, ordered `profilePrerequisiteChecks`, and integer `applicableProfileCount`. A handed-off dataset manifest is `lifecycleRole: "final"` and `artifactKind: "dataset-manifest"` without precedence ambiguity. Failure-state derivation is total: `artifactKind` is `dataset-manifest` only when a core-valid referenced statement has a unique subject with the artifact tuple's `subjectName` and that subject signs the exact mandatory dataset-manifest profile identity; the tuple's wrong digest does not hide that classification. If no such usable statement/subject exists, `artifactKind` is `ordinary`. `applicableProfileCount` is always an integer: it is the cardinality of the deduplicated union of signed artifact-profile references recoverable from that core-valid statement for the tuple's subject name and every authoritative manifest or consumer requirement selecting the tuple; requirements count even when the signed reference is missing, and an unrecoverable head with no selecting requirement yields zero. `profileStatus` is `skipped` when artifact bytes or statement authorization failed, with the exact failed phase in `profilePrerequisiteChecks`; otherwise `fail` if any applicable profile fails; otherwise `indeterminate` if any is indeterminate; otherwise `not_checked` if none was evaluated; otherwise `pass`. Applicable profiles are deduplicated by `(id, digest.sha256, closureDigest.sha256, target, subjectName, mediaType)` after merging the signed reference plus manifest and consumer requirement flags, so one profile required by both manifest and policy counts once. A missing signed reference still contributes one unit for each distinct requirement identity. In that case no synthetic profile record is fabricated, the artifact record has `profileStatus: "fail"`, and `E_REQUIRED_PROFILE_MISSING` identifies the unsatisfied requirement. Zero applicable profiles is `not_checked` with `W_ARTIFACT_UNPROFILED` only for final artifacts; historical material needed solely for graph membership does not warn. Each `datasetEntries` record has exactly `manifestStatementDigest`, `manifestSubjectName`, `entryName`, `digest`, nullable `declaredSize` as a decimal string, `digestStatus`, ordered `digestPrerequisiteChecks`, `sizeStatus`, and ordered `sizePrerequisiteChecks`. Its logical identity and sort tuple are `(manifestStatementDigest, manifestSubjectName, entryName)`; digest disagreement never creates a second record. Its exact record set is the duplicate-free union of entries named by reachable graph `entryName` edges, bundle-index `datasetEntries` mappings, and consumer dataset-entry bindings. `digest` is the validated dataset-manifest member digest when that member resolves; otherwise it is the sole mapping-declared digest when a mapping exists; otherwise it is the lexicographically smallest signed input digest among the reachable edges naming that logical identity. A transformation input digest that differs from the validated member digest emits `E_INPUT_DIGEST` for that edge while the shared record retains the member digest. A mapping digest that differs from the validated member digest emits `E_DATASET_MANIFEST_INVALID`, is not hashed, and likewise does not change the shared record digest. An edge-named entry with no supplied partition bytes is `not_checked` with an empty prerequisite array; a supplied mapping is checked. `sizeStatus` is `not_checked` with an empty prerequisite array when the dataset-manifest entry omitted `size`, whether or not bytes were supplied. Entries merely declared inside a dataset-manifest artifact but unused by that union produce no individual record. `unreferencedFiles` records only safe ignored regular files, not directories, with status `not_checked` and reason `unreferenced`, without producing a warning by itself. Thus the layout's `README.txt` is informational, not a verification defect.

`summary.statementsTotal` counts manifest-listed indexed statement payload digests; `quarantinedStatementsTotal` counts indexed outside-set payloads; `statementsReachable` counts usable graph nodes reached during Step 9 from the remaining usable manifest-declared head set, even when the handoff threshold prevents anchor authority; `statementsValid` counts `coreSchema: "pass"`; and `statementsAuthorized` counts `authorization: "pass"`. `signaturesTotal` counts every parsed signature-array entry charged to `maxSignaturesTotal`; `signaturesChecked` counts configured-key entries for which strict cryptographic verification ran; and `signaturesValid` counts those checked entries whose cryptographic result is `pass`, across handoff, listed, quarantined, and unindexed populations according to their eligibility. `manifestSignaturesRequired` is the policy handoff rule's `minimumSignatures`; `manifestSignaturesValid` counts distinct configured key IDs with a cryptographically passing handoff signature regardless of authorization window; and `manifestSignaturesAuthorized` counts the distinct IDs from that cryptographically valid set that are inside their policy window and appear in the policy handoff rule's `authorizedKeyIds`, capped only by set cardinality rather than the threshold. The report `handoff` record has no `authorizedKeyIds` member. Duplicate-key entries are malformed and never reach the manifest counters but remain included in `signaturesTotal` when structurally enumerable; their earlier resource accounting is defense in depth. `summary.roots` and `summary.heads` count the complete computed Step 10 root set and subject-aware terminal statement-head set respectively whenever `roots-and-heads` completed; they are `null` when a failed prerequisite prevented complete computation and are never counts of merely manifest-declared `actualHeads`. `artifactsDeclared` and `artifactsChecked` count authorized final manifest artifacts and their `digestStatus: "pass"`; both are zero when handoff authorization fails and no final population is admitted. `historicalMaterialsDeclared` and `historicalMaterialsChecked` count only historical artifact mappings and digest passes (a final dataset manifest remains final); `profilesDeclared` counts signed profile references on reachable statements; and `profilesValidated` counts `validation: "pass"` only within that same reachable population. These definitions apply equally to positive and failure reports. Phase 0 report vectors enumerate every summary field's exact integer-or-null value for each distinct Step 1–4 failure stratum, handoff-threshold failure, graph prerequisite failure, and completed negative case.

Each warning or error has exactly `code`, integer `step` from 1 through 14 for errors or 0 through 13 for warnings, a human `message`, a bounded schema-controlled `context` object, and required `causedByCheck`; context is potentially sensitive because allowed fields may include private profile IDs, subject names, recipient/nonce values, or logical paths and MUST be redacted or access-controlled by downstream logging systems. Step 0 is reserved for preflight warnings such as `W_POLICY_RULE_OVERLAP`, because preflight errors exit 2 without a report, and Step 14 is reserved for the terminal error. Messages are not stable API; codes and context field names are. All report JSON numbers, including context numbers, MUST be integers in the RFC 8785 interoperable range `-9007199254740991` through `9007199254740991`; larger exact sizes, offsets, and arbitrary-precision values use canonical base-10 strings with no leading zeros. `verification-report.schema.json` MUST define the allowed context members and required identifiers for every stable code; arbitrary context keys and artifact/schema contents are forbidden. Phase 0 MUST publish `testdata/v0.2/diagnostic-map.json`, mapping every stable code to its allowed algorithm step(s), exact trigger, context schema reference, prerequisite/continuation behavior, and error-or-warning class; prose Appendix C is the source table for that artifact. Dependency failures produce `skipped` records rather than invented secondary failures, and every skipped check includes nonempty `prerequisiteChecks`. `roots`, `expectedHeads`, and `actualHeads` sort by lowercase hexadecimal digest using ASCII bytes; expected artifacts sort by `(head digest, subjectName, artifact digest)`; statements by statement digest; signatures by `keyid`; profiles by `(statement digest, id, root schema digest, closure digest, target, subjectName-or-null, mediaType-or-null)`; artifacts by `(lifecycleRole, artifactKind, statementDigest, subjectName, digest)` with enum values compared as UTF-8 strings; dataset entries by `(manifestStatementDigest, manifestSubjectName, entryName)`; quarantined statements by `(digest, path)`; unindexed/unreferenced paths by UTF-8 bytes; top-level checks and their `prerequisiteChecks` arrays by the closed Section 15 check order; profile prerequisite arrays by their separate order above; and diagnostics by `(step, code, causedByCheck, RFC 8785 JSON Canonicalization Scheme bytes of context)`. All string comparisons use UTF-8 bytes unless a lowercase-hex rule is stated; null optional components compare before strings. `primaryError` is null when `errors` is empty; otherwise it is the code of the first admitted error under that exact ordering and is recomputed for every Step 14 candidate projection. The `decision` check is `pass` whenever deterministic semantic aggregation and report admission completed, regardless of the overall allow/deny result; it is `fail` only when a Step 14 report-budget `E_RESOURCE_LIMIT` truncated admission. It does not duplicate the decision value. Exit-code 2 or 3 failures occur outside a completed verification report. Appendix A is a complete positive example. `verification-report.schema.json` MUST encode this contract before Phase 0 exits.

Cross-implementation stable comparison surfaces are report-schema validity, decision, check statuses, `primaryError`, required diagnostic code sets, roots/heads/digests, every summary counter including its null-versus-integer state, and all fully computed evidence records. Human messages, tool metadata, and safely discoverable secondary diagnostics explicitly allowed by a fixture are not guaranteed byte-identical across implementations. Consumers SHOULD compare the stable surfaces and SHOULD NOT treat full-report byte inequality alone as an alert condition unless tool version and secondary-diagnostic policy are also pinned.

For `unindexedEnvelopes[].payloadTypeStatus`, `pass` means a string `payloadType` was parsed and exactly matched the type required at that index position; `fail` means a parsed string was present but unsupported/wrong; and `not_checked` means envelope parsing or field typing failed before an exact string comparison was possible.

Each `unindexedEnvelopes[]` record also has always-present nullable `diagnosticCode`. It is the first applicable envelope-local classification code under the normative diagnostic ordering: a Step 2 `E_JSON_INVALID`, `E_JSON_DUPLICATE_KEY`, `E_ENVELOPE_MALFORMED`, or `E_PAYLOAD_TYPE`; otherwise Step 3 `E_STATEMENT_DIGEST` when exact decoded payload bytes disagree with the indexed digest; otherwise Step 11 `E_MANIFEST_SET` for an index-declared safe attestation target that was absent from the completed Step 1 inventory. It is null only when none of those classifications applies. This field records classification before Step 14 diagnostic admission and therefore may name a code even when the corresponding diagnostic is later omitted by report-budget prefix selection; it does not assert that an `errors[]` entry was emitted. Phase 0 includes one vector for every allowed nonnull code and the null case.

The null cases are explicit. When a valid bundle index established the attestation path but the target recorded present at Step 1 becomes unsafe, unreadable, replaced, or unavailable at the Step 2 consuming open, the verifier creates the unindexed record with `payloadTypeStatus: "not_checked"` and `diagnosticCode: null` while top-level errors carries `E_BUNDLE_UNSAFE_PATH`. When the per-file or aggregate metadata/resource ceiling is reached after the indexed path population is established but before that envelope's payload classification, it likewise creates the record with both fields `not_checked`/null and emits the owning `E_RESOURCE_LIMIT`; later dependent envelopes may be skipped without fabricated records when their individual path processing never begins. If `bundle.json` itself failed or no index population was established, `unindexedEnvelopes` remains empty under the existing failure-population rule. These are the required null vectors.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Verification completed and policy decision is `allow`. |
| 1 | Verification completed and `makoto verify bundle` decision is `deny`; future modes may also use it for reserved `indeterminate`. |
| 2 | Invalid invocation or missing consumer configuration. |
| 3 | Unexpected internal/tool failure. |

For `digest`, key generation, attestation, co-signing, and handoff creation, exit 0 means the requested output completed; invalid/missing input files, invalid producer bindings, unsafe or existing output paths, unsupported key material, or invalid schema/evidence supplied for creation exit 2; unexpected I/O after a valid operation begins or an internal invariant failure exits 3. `schema validate` exits 0 for a valid instance, 1 for a completed invalid-instance result, 2 for invalid invocation/schema/catalog configuration, and 3 for internal failure. Bundle verification uses exit 1 for `deny`. Every command writes one UTF-8 RFC 8785 JCS object plus LF to stderr on exit 2 or 3 and writes nothing to stdout. Exit 2 uses the compact template `{"errorClass":"invalid-input","message":"<escaped message>"}` and exit 3 uses `{"errorClass":"internal","message":"<escaped message>"}`; the placeholder is replaced by one ASCII-only JSON-safe string before canonicalization. This tool-error shape is stable for the v0.2 reference CLI but is not a Makoto verification report and uses no protocol diagnostic code. Creation and mutation commands emit no success artifact after nonzero exit; a completed exit-1 `verify bundle` report is denial evidence, not a success artifact.

For `schema validate`, the detailed Section 16.1 classification controls this table: every instance syntax/encoding/duplicate-key/NDJSON-zero-instance/media parse failure is a completed exit-1 invalid-instance result; exit 2 is schema/profile/catalog/invocation configuration; and resource, timeout, memory, I/O-after-valid-open, or internal operational failure is exit 3.

The v0.2 error-code enum is closed to:

`E_BUNDLE_UNSAFE_PATH`, `E_JSON_INVALID`, `E_JSON_DUPLICATE_KEY`, `E_ENVELOPE_MALFORMED`, `E_PAYLOAD_TYPE`, `E_STATEMENT_DIGEST`, `E_CORE_SCHEMA`, `E_CATALOG_INVALID`, `E_PROFILE_UNRESOLVED`, `E_PROFILE_INVALID`, `E_PROFILE_TARGET_MISSING`, `E_REQUIRED_PROFILE_MISSING`, `E_SIGNATURE_INVALID`, `E_SIGNER_UNAUTHORIZED`, `E_PREDICATE_SEMANTICS_UNSUPPORTED`, `E_EVENT_ID_DUPLICATE`, `E_PREDECESSOR_MISSING`, `E_PREDECESSOR_SUBJECT`, `E_INPUT_DIGEST`, `E_DATASET_MANIFEST_INVALID`, `E_DATASET_MANIFEST_REQUIRED`, `E_GRAPH_CYCLE`, `E_ROOT_INVALID`, `E_HANDOFF_REQUIRED`, `E_MANIFEST_SET`, `E_FRESHNESS_REQUIRED`, `E_EXPECTED_MANIFEST`, `E_EXPECTED_HEAD`, `E_EXPECTED_ARTIFACT`, `E_HANDOFF_RECIPIENT`, `E_HANDOFF_NONCE`, `E_HANDOFF_STALE`, `E_ARTIFACT_MISSING`, `E_ARTIFACT_DIGEST`, `E_ARTIFACT_SIZE`, `E_ARTIFACT_FORMAT`, and `E_RESOURCE_LIMIT`.

The v0.2 warning-code enum is closed to `W_PROFILE_INDETERMINATE`, `W_PROFILE_RESOURCE_LIMIT`, `W_ARTIFACT_VALIDATION_LIMIT`, `W_HISTORICAL_ARTIFACT_NOT_CHECKED`, `W_SIGNATURE_UNKNOWN`, `W_FRESHNESS_NOT_CHECKED`, `W_ARTIFACT_UNPROFILED`, and `W_POLICY_RULE_OVERLAP`. Any new code requires a new `reportVersion`; implementation-defined codes are forbidden in a `0.2` report.

### 16.4 Reference implementation files and local gates

| Core path | Responsibility |
|---|---|
| `pyproject.toml` | Python 3.11+, locked runtime/dev dependencies, `makoto` entry point, pytest/ruff/mypy configuration. |
| `uv.lock` | Committed reproducible dependency lock. |
| `src/makoto/model.py` | Typed protocol models and strict JSON loading. |
| `src/makoto/digest.py` | Streaming exact-byte SHA-256. |
| `src/makoto/dsse.py` | DSSE PAE, Ed25519 signing, and verification. |
| `src/makoto/schema.py` | Core/profile/catalog resolution and validation. |
| `src/makoto/graph.py` | DAG construction, membership edges, roots, heads, and completeness. |
| `src/makoto/policy.py` | Trust-policy parsing and authorization decisions. |
| `src/makoto/bundle.py` | Safe bundle loading, handoff creation, and artifact mapping. |
| `src/makoto/report.py` | Versioned verification report and stable errors/warnings. |
| `src/makoto/cli.py` | Normative command contract and exit codes. |
| `src/makoto/bench.py` | Pinned benchmark fixture runner and result producer. |
| `src/makoto/bench_check.py` | Result-schema, fixture-digest, percentile, and threshold evaluator. |
| `tests/` | Unit, property, conformance, and CLI tests. |

The core repository MUST provide `scripts/check.sh`, which runs, in this order: `uv sync --locked --dev`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, `uv run pytest`, and the clean-clone demo smoke test. CI MUST invoke this exact script rather than restating its commands. It MUST also provide `scripts/release-check.sh`, which invokes `scripts/check.sh` and then the pinned benchmark command and threshold evaluator from Section 23.2. Benchmarks are a release-candidate gate, not a per-commit CI gate; Phase 4 and tag creation MUST run `scripts/release-check.sh`.

`handoff.completeness` always exactly equals the top-level `completeness-anchor` status, including `fail`, `skipped`, and `not_checked`; it is not a separate aggregation. Its prerequisite explanation remains in the top-level check object.

## 17. Hosted schemas and versioning

The canonical schema sources live in the core repository. The website hosts release copies.

Required public paths:

```text
https://usemakoto.dev/schema/v0.2/envelope.schema.json
https://usemakoto.dev/schema/v0.2/statement.schema.json
https://usemakoto.dev/schema/v0.2/origin.schema.json
https://usemakoto.dev/schema/v0.2/transform.schema.json
https://usemakoto.dev/schema/v0.2/profile-reference.schema.json
https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json
https://usemakoto.dev/schema/v0.2/catalog.schema.json
https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json
https://usemakoto.dev/schema/v0.2/handoff.schema.json
https://usemakoto.dev/schema/v0.2/bundle.schema.json
https://usemakoto.dev/schema/v0.2/trust-policy.schema.json
https://usemakoto.dev/schema/v0.2/verification-report.schema.json
https://usemakoto.dev/schema/v0.2/catalog.json
```

Schema responsibility is fixed as follows:

| Schema | Root type | Normative responsibility |
|---|---|---|
| `envelope` | object | DSSE transport fields, payload type, base64 payload, and signature entries. |
| `statement` | object | in-toto outer statement, SHA-256 subjects, predicate dispatch, and extension predicate allowance. |
| `origin` | object | Common event fields plus source fields and prohibition of predecessors. |
| `transform` | object | Operation, input artifacts, predecessor bindings, optional dataset entry membership, profiles, and extensions. |
| `profile-reference` | object | URI, root digest, closure digest, target, criticality, media type, subject, and sorted transitive resources. |
| `profile-dialect` | meta-schema | Makoto's Draft 2020-12-derived vocabulary set, unknown-keyword closure, and bounded-pattern dialect. |
| `catalog` | object | Offline `(id, digest) -> path` resource mappings. |
| `dataset-manifest` | object | Sorted finite partition entries and their digests. |
| `handoff` | object | Exact roots, heads, statement set, final artifacts, required profiles, recipient, and nonce. |
| `bundle` | object | Untrusted safe relative-path index with complete identity tuples. |
| `trust-policy` | object | Verification keys, authorization rules, digest-pinned required profiles, handoff/replay rules, evaluation-time behavior, and resource limits. |
| `verification-report` | object | Stable decision, checks, digests, results, warnings, errors, and tool identity. |

Every schema MUST close Makoto-owned objects with `additionalProperties: false` or `unevaluatedProperties: false`, except the explicitly extensible `extensions` map and JSON Schema instances supplied as profiles. Cross-field rules that JSON Schema cannot express, such as graph reachability, tuple uniqueness, lexicographic ordering, digest equality, and signer authorization, are semantic verifier requirements with conformance fixtures.

Rules:

- Every schema MUST declare JSON Schema Draft 2020-12 and a matching absolute `$id`.
- Every versioned URL MUST return HTTP 200, `application/schema+json` or `application/json`, and `Access-Control-Allow-Origin: *`. If the current Pages path cannot emit that header, the release MUST change the schema-hosting path rather than waive the gate.
- Released versioned schema bytes are immutable.
- Every versioned human-readable predicate, source-kind, vocabulary, and core walkthrough document required by this section is also byte-pinned in the sorted `documentation` array inside `schema/core-release.json`. Deployment compares each rendered UTF-8 response body with that release-index digest and rejects mutation under an existing versioned URL; a content change publishes the corresponding new immutable protocol/documentation version rather than overwriting bytes. This establishes CI-enforced byte parity, not authenticity by itself.
- The website deployment MUST compare hosted schema bytes with a pinned core release and fail on any digest mismatch. The checksum manifest from the immutable core release tag and commit pinned by the verifier or distributor is the distribution trust root for hosted schema bytes; URL location or TLS transport alone is not. Consumers import a hosted schema only after matching that authenticated release checksum or an independently pinned digest.
- Every Makoto-owned identifier in a protocol version family—core schema IDs, predicate types, profile dialect/vocabulary IDs, report/schema identifiers, and versioned media types—MUST use that family's immutable versioned URI/value and MUST NOT use `latest`. Externally controlled profile/resource IDs, `source.uri`, external `source.kind`, `operation.type`, and tool/recipe URIs remain opaque exact identifiers and MAY be versioned, unversioned, or URNs; Makoto does not rewrite or reject them merely for lacking a Makoto version segment. The built-in `https://usemakoto.dev/source/file` is the sole retained unversioned Makoto-owned source-kind exception and is byte-pinned as immutable documentation below.
- `/schema/latest.json` MAY remain a convenience alias for humans, but documentation MUST warn that it is not an immutable protocol identifier.
- Existing `/schema/v0.1.json` MUST remain unchanged and available.
- The v0.1 and v0.2 pages MUST state that the formats are incompatible.
- Predicate URIs MUST resolve to human-readable documentation and link to their JSON Schemas.
- The built-in source-kind URI `https://usemakoto.dev/source/file` MUST resolve to immutable human-readable documentation; every other core example URI used as a semantic identifier MUST either resolve under the same release gate or use a non-resolving URN intentionally.
- `https://usemakoto.dev/vocab/v0.2/bounded-pattern` MUST resolve to immutable human-readable vocabulary documentation defining `makotoPattern`, its load-time failures, and links to the profile dialect and conformance vectors. It is documentation, not a network dependency or catalog resource.

Protocol identifiers include the full compatibility version. The initial release uses predicate/schema/report value `0.2` at `/v0.2/` and protocol tag `v0.2.0`. A correction that changes validation or wire semantics publishes a complete new Makoto-owned identifier family: `/v0.2.1/` for every schema and predicate, the Makoto handoff `payloadType`, every core object `version`/`schemaVersion`, `reportVersion`, dataset-manifest media type, profile-dialect URI, custom-vocabulary URI, and protocol tag `v0.2.1`; it never edits `/v0.2/`. The generic in-toto statement-envelope `payloadType` remains `application/vnd.in-toto+json` across Makoto versions and is explicitly not a Makoto-owned identifier to rewrite. A multi-version verifier dispatches policy/bundle/handoff versions before deeper processing and then accepts only Makoto identifiers from that one family inside the verification. A tooling-only release that does not change accepted bytes or decisions uses the disjoint tag namespace `tool-v0.2.<n>` while continuing to emit protocol `0.2`; it never consumes a future protocol tag. A v0.2.1 verifier MAY also support 0.2 as a separately dispatched immutable protocol, but MUST NOT mix or treat their identifiers as aliases. A breaking shape or guarantee change uses v0.3.

The final website pin lives at `schema/core-release.json` and contains the closed fields and sorted schema, documentation, and downloadable-resource entry arrays defined below. `scripts/sync_core_release.py --working-tree` is a development-only parity mode: it mirrors checksum-validated local core bytes without creating or replacing a candidate or release pin. `scripts/sync_core_release.py --commit <sha> --candidate` is the Phase 3 staging mode: it writes `schema/core-candidate.json`, stages copies from that commit, and never creates `core-release.json`; `scripts/check_site.py --candidate` validates it, while deployment CI rejects any candidate pin. After the tag exists, `scripts/sync_core_release.py --tag v0.2.0` verifies the tag/commit, regenerates identical schema copies plus final `core-release.json`, and removes the candidate pin. `scripts/check_site.py` verifies JSON examples, schema bytes, `$id` values, local links, generated demo artifact digests, the complete release-index inclusion set, ordering, and response-body digests. Both scripts run through `uv`; `.github/workflows/deploy.yml` MUST run `uv run scripts/check_site.py` and reject a candidate pin before the existing GitHub Pages deployment step.

The core catalog instance is `schemas/v0.2/catalog.json`, has public distribution ID `https://usemakoto.dev/schema/v0.2/catalog.json`, maps exactly the twelve immutable `*.schema.json` resources listed in this section, and is itself digest-pinned in `schema/core-release.json`. The catalog instance has no `$id` member; hosted `$id` probes apply exactly to the twelve schema resources, while catalog deployment checks its distribution URL and pinned bytes instead. “Predicate resource” means the `origin.schema.json` or `transform.schema.json` selected by statement predicate dispatch; human-readable pages at predicate URIs are documentation and are never schema-catalog entries. The verifier embeds that exact release catalog and reports its digest.

`schema/core-release.json` is a normative website release index validated by the checked-in closed schema `schema/core-release.schema.json`. It is strict UTF-8 JSON without BOM or duplicate keys and has exactly this shape: `{"commit":<40-lowercase-hex>,"documentation":[{"digest":{"sha256":<64-lowercase-hex>},"path":<absolute-site-path>}...],"repository":"https://github.com/makoto-project/makoto","resources":[{"cors":<boolean>,"digest":{"sha256":<64-lowercase-hex>},"mediaType":<media-type>,"path":<absolute-site-path>}...],"schemas":[{"digest":{"sha256":<64-lowercase-hex>},"path":<absolute-site-path>}...],"tag":"v0.2.0","version":"0.2"}`. All three arrays are nonempty, duplicate-free by `path`, and sorted by path UTF-8 bytes; paths are globally unique across the arrays. Each path begins with exactly one `/`, uses the Section 13.3 logical segment grammar after that slash, and has no query or fragment. Each array entry is closed; the root object is closed. The file is serialized as RFC 8785 JCS plus exactly one LF.

The `schemas` array contains exactly every deployed file under `/schema/v0.2/` from the pinned release: all twelve immutable `*.schema.json` resources and `/schema/v0.2/catalog.json`; it excludes `core-release.json`, `core-release.schema.json`, aliases such as `latest.json`, candidate pins, and unrelated site JSON. A schema-entry digest is SHA-256 over the exact response/file bytes copied from the pinned core tag, with no parsing, newline conversion, decompression, or canonicalization.

The `documentation` array contains every immutable page body required by v0.2, at minimum `/spec/v0.2/`, `/predicate/v0.2/origin/`, `/predicate/v0.2/transform/`, `/vocab/v0.2/bounded-pattern/`, the retained unversioned `/source/file/`, and the core walkthrough `/demos/v0.2-end-to-end/`. It also contains any additional Makoto-owned human-readable identifier page that the release claims as immutable. A documentation digest is SHA-256 over the exact rendered UTF-8 HTTP response body after site generation and before transfer/content encoding, with no DOM normalization. CI renders each page once, hashes those bytes, writes the sorted index, then serves/probes the same bytes at the canonical trailing-slash directory-index paths; a redirect, templated mutation, slashless alias, or path spelling mismatch fails the release gate.

The `resources` array contains the raw normative specification, stable diagnostic map, v0.2 architecture/integration/migration documents, release checksum manifest and its schema, the deterministic demo manifest, and every file named by that demo manifest. `mediaType` is exactly one of `application/json`, `application/octet-stream`, or `text/markdown`; `cors` states whether the hosted response must include `Access-Control-Allow-Origin: *`. Every v0.2 resource sets `cors` true. The hosted probe first fetches `/schema/core-release.json` and requires byte equality with the reviewed local pin, then fetches every schema, documentation page, and resource with no redirects and verifies status, media type, CORS policy, and exact SHA-256 body digest.

The index does not self-authenticate. `repository`, `tag`, and `commit` MUST identify one immutable annotated or lightweight Git tag whose peeled commit equals `commit`; every schema digest MUST also match the checksum manifest contained in that core release. Because `schema/core-release.json` is mutable website-adjacent state, its documentation entries prove only deployment parity unless a consumer independently pins the website release artifact or repository revision that contains the index. A consumer MUST NOT bootstrap authenticity from the index and response bodies served by that same unpinned website; authenticity requires an independently obtained tag/commit, archive digest, transparency record, or equivalent distributor pin. Candidate mode uses the same closed shape in `schema/core-candidate.json` but replaces `tag` with null only in its separate candidate schema and can never deploy. Final mode rejects a dirty source tree, tag/commit disagreement, missing/extra schema or documentation entries, unsorted arrays, or any digest mismatch before replacing the candidate pin.

The canonical core release checksum manifest is `release/v0.2/checksums.json`, validated by the checked-in closed tooling schema `release/checksums.schema.json`. It has exactly `{"files":[{"digest":{"sha256":<64-lowercase-hex>},"path":<repository-relative-path>}...],"tag":"v0.2.0","version":"1"}`. `files` is nonempty, duplicate-free by path, and sorted by path UTF-8 bytes. Paths use NFC `/`-separated repository-relative logical names under the Section 13.3 grammar. The file is strict UTF-8 JSON without BOM or duplicate keys and is serialized as RFC 8785 JCS plus one LF.

Checksum-manifest `version: "1"` versions this tooling inventory shape, not the Makoto wire protocol; it is intentionally distinct from protocol `0.2`. A future checksum-shape revision increments this integer-string contract without rewriting released protocol identifiers or bytes.

The checksum inclusion set is exact: every regular file under `schemas/v0.2/`, `testdata/v0.2/`, `demos/v0.2-end-to-end/`, `docs/`, `scripts/`, `src/makoto/`, and `tests/`; exact files `spec/v0.2.md`, `release/checksums.schema.json`, `pyproject.toml`, `uv.lock`, `LICENSE`, and `README.md`; and no other path. Ignored `.work/`, tool caches, generated benchmark results not checked into `testdata`, the checksum manifest itself, and Git metadata are excluded. Each entry digest is SHA-256 over the exact Git blob/worktree bytes at the tagged commit, including any final LF, with no JCS reserialization, newline conversion, or archive transformation. Release generation runs from a clean checkout, derives the complete inclusion set, rejects missing/extra entries, and verifies every digest before tag creation and again from the peeled tag afterward. It additionally verifies that the eight standard-registry resource entries equal the IDs, lengths, and SHA-256 values in Section 12.1 and that both internal worker-result schema digests equal the constants asserted by `scripts/check.sh`.

`src/makoto/unicode/15.0.0/` contains exact vendored `UnicodeData.txt`, `CaseFolding.txt`, `CompositionExclusions.txt`, and `DerivedNormalizationProps.txt` inputs plus a closed sorted `unicode-catalog.json` that records each filename, Unicode version `15.0.0`, exact byte length, and SHA-256. NFC normalization and full case folding use only tables deterministically generated from those bytes; startup or `scripts/check.sh` rejects a catalog/input/generated-table mismatch. Phase 0 records upstream retrieval evidence and cross-checks normalization/case-fold vectors with the vendored version. The checksum inventory covers the portable v0.2 implementation, protocol schemas, documentation, tooling, tests, and conformance inputs named above; repository administration such as Git metadata and CI-provider configuration remains authenticated by the reviewed tag rather than duplicated in the manifest.

The checksum manifest does not self-authenticate; the independently pinned repository and reviewed Git tag target authenticate it. The release operator MUST verify that the tag names the reviewed commit, and the release archive MUST reproduce the same included bytes. Every `/schema/v0.2/` entry in website `schema/core-release.json` MUST map to and equal the corresponding `schemas/v0.2/` digest in this core checksum manifest. `scripts/release-check.sh` validates the closed schema, ordering, inclusion set, exact preimages, tag/commit relationship when a tag is present, and website-sync compatibility. Changing the checksum shape or inclusion set requires a tooling-contract revision; changing any included protocol byte after release requires the protocol version-family rules.

## 18. September 16 end-to-end demonstration

### 18.1 Story

The demo uses a small synthetic customer dataset. No real personal data is included.

1. **Source:** `customers.raw.json` contains synthetic customer IDs, email addresses, regions, ages, and consent values. An ingestion identity hashes the exact file and signs an origin statement with `source.kind: "urn:makoto:demo:source:synthetic-file"` and `source.uri: "urn:makoto:demo:v0.2:source:customers-raw"`.
2. **Normalize:** A deterministic tool with exact `operation.type: "urn:makoto:demo:operation:normalize"` trims and lowercases email fields, normalizes region codes, and normalizes consent values. It writes `customers.normalized.json` and signs a transformation that references the origin payload digest and input artifact digest.
3. **Make public-safe:** A second deterministic tool with exact `operation.type: "urn:makoto:demo:operation:public-safe"` removes direct identifiers, creates pseudonymous customer IDs, converts age to an age band, and emits `customers.public.json`. A distinct privacy-transform identity signs a second transformation referencing the normalization statement. That statement carries two critical private profile references: one `target: "predicate"` profile for required internal event/operation metadata and one `target: "artifact"` profile for final content constraints.
4. **Handoff:** A sender creates and signs a handoff manifest containing the exact three-statement set, origin root, final head, final artifact digest, and the artifact-target private profile requirement. The predicate-target profile remains required because it is producer-critical and is also an exact digest-pinned constraint on the consumer's final-transform authorization rule.
5. **Independent verification:** A receiver with only the bundle, public keys/trust policy, expected manifest digest, expected head, expected final-artifact tuple, and private schema catalog runs one command and receives an `allow` decision with every check shown. The checked-in receiver policy constrains the origin rule to the demo's exact `source.kind` and exact synthetic source URI, so “expected origin” is independently enforced rather than inferred merely from manifest selection. The positive handoff uses `--external-profile` for the private artifact profile, and the receiver supplies its catalog from a path physically outside the bundle; acceptance asserts that the bundle contains neither that schema resource nor a bundle catalog entry for it.

Demo generation is byte-deterministic. Every generated JSON file—including data artifacts, decoded statement/manifest payloads, outer DSSE envelopes, `bundle.json`, generated schema catalog, bindings, policy, and verification reports—uses UTF-8, keys sorted by Unicode code point, compact separators `,` and `:`, no ASCII escaping except required JSON escapes, and one final LF, except fields explicitly defined as RFC 8785 JCS output use JCS ordering with the same final LF. Signature arrays and every other semantically unordered array use their protocol-mandated order before serialization. Fixture event IDs, bundle ID, and timestamps are supplied explicitly through the CLI. Normalize trims leading/trailing ASCII space from email and region; lowercases ASCII `A`–`Z` in email; requires region to be exactly two ASCII letters and uppercases it; trims ASCII space from consent, lowercases ASCII `A`–`Z`, and maps exactly `yes|true|1` to `true` and `no|false|0` to `false`; every other value fails. Age input must be a JSON integer from 0 through 130 inclusive; booleans, decimals, strings, and out-of-range values fail. Make-public-safe removes raw customer ID and email, sets `customer_id` to the first 20 lowercase hexadecimal characters of SHA-256 over UTF-8 `"makoto-demo-v0.2:" + raw_customer_id`, emits exact `age_band` strings `0-17`, `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, or `65+` for the corresponding inclusive ranges, preserves normalized region and consent, and sorts output rows by `customer_id`. This pseudonymization is an auditable synthetic demo transform, not production de-identification.

Verification reports are excluded from the code-point-sorted fixture family in the preceding sentence and are always wholly serialized as RFC 8785 JCS plus LF under Section 16.3. Their appearance in the illustrative generated-file list does not apply the code-point convention. The serialization-order fixture asserts this distinction directly.

The raw artifact is one JSON array of objects with exactly `customer_id`, `email`, `region`, `age`, and `marketing_consent`; unknown or missing members fail. The first two identifiers and region/consent are strings; `customer_id` is nonempty and unique by exact Unicode-scalar sequence. The age token itself must match `0|[1-9][0-9]{0,2}` and have value at most 130, so `18.0`, `1e1`, and `-0` fail despite mathematical integrality. Normalize emits the same exact five fields, preserves row order, and writes Boolean consent. Duplicate raw IDs fail before output. Make-public-safe fails on a pseudonym collision, then sorts by `customer_id`; because collisions fail, no tie order exists. The checked-in raw fixture bytes and every generated artifact digest are conformance inputs, not prose-only examples. `bundle.json` is included in the same deterministic JSON serialization claim and uses the mandatory index-array ordering from Section 13.3.

Demo object-member sorting by Unicode code point is a producer-fixture convention. RFC 8785 ordering is used only where this specification explicitly invokes JCS, such as policy-object serialization and diagnostic-context sorting; implementations MUST NOT “unify” the two conventions.

The checked-in demo includes `fixtures/serialization-order.json` with sibling decoded member names U+E000 and U+10000. Its producer-fixture form orders U+E000 before U+10000 by Unicode code point; the companion JCS preimage orders U+10000 first because RFC 8785 compares UTF-16 code units (`D800 DC00` before `E000`). The demo generator asserts both exact byte sequences and their different digests. This supplementary-plane vector prevents an implementation from accidentally substituting JCS ordering for the demo serializer or code-point ordering for signed JCS preimages.

The two organizational profiles are private by convention even though the demo includes synthetic copies at `demos/v0.2-end-to-end/private-schemas/example.internal/public-transform-metadata-v1.schema.json` and `customer-public-v1.schema.json`. Their URI/digest mappings live in `demos/v0.2-end-to-end/receiver/catalog.json`. The predicate profile requires the final transformation's internal event and operation metadata. The artifact profile validates that final JSON contains only `customer_id`, `region`, `age_band`, and `marketing_consent`; rejects direct identifier fields; constrains identifier and region patterns; and sets `additionalProperties: false`.

### 18.2 Positive proof output

The verifier MUST visibly report:

- PASS — core schema validity;
- PASS — both private profiles resolved by URI and digest;
- PASS — private metadata and artifact constraints;
- PASS — DSSE signature validity for origin, transform 1, transform 2, and handoff;
- PASS — signer authorization for every signed payload;
- PASS — origin roots discovered;
- PASS — all predecessors present and artifact bindings equal;
- PASS — graph acyclic and exact manifest statement set present;
- PASS — expected manifest digest equals actual manifest metadata digest;
- PASS — expected head equals actual head;
- PASS — final data bytes equal terminal and manifest digests;
- ALLOW — overall trust-policy decision; and
- the manifest digest, which is the portable hash of final handoff metadata.

### 18.3 Mandatory negative cases

The demo test suite and webpage MUST show concise versions of five failures:

1. **Mutated final data:** edit one byte after signing; verification returns `E_ARTIFACT_DIGEST`.
2. **Edited signed metadata:** decode the final transformation payload, alter `operation.name`, and re-encode it without replacing the transformation signature. Recompute its payload digest, update the unsigned index, create and validly sign a replacement handoff manifest that lists the changed head and exact changed statement set, and update the independently supplied expected manifest/head/artifact values to that replacement. The edited transformation is therefore manifest-listed rather than quarantined, and its stale signature produces primary `E_SIGNATURE_INVALID` at Step 5. A separate fixture that changes payload bytes without updating the index MUST return `E_STATEMENT_DIGEST` at indexing.
3. **Removed or rewired step:** the webpage may present this as one story, but tests use two exact fixtures. Deleting a predecessor envelope and its unsigned index entry while leaving the signed descendant and manifest unchanged produces primary `E_PREDECESSOR_MISSING`; Step 11 also emits secondary `E_MANIFEST_SET`, and `completeness-anchor` is `fail`, never `skipped`, because the missing manifest/index identity is independently decidable. For the rewired-edge fixture, alter the final transformation's signed input binding without replacing its statement signature, then update the unsigned index, validly sign a replacement handoff manifest, and update the independent expectations exactly as in case 2; the manifest-listed stale statement signature produces primary `E_SIGNATURE_INVALID`. Reordering filesystem enumeration or other inputs explicitly defined as unordered MUST continue to pass; shuffling any manifest, bundle, or other array with mandatory canonical sorting MUST fail `E_CORE_SCHEMA`.
4. **Private schema violation:** reintroduce `email`, deterministically regenerate the final artifact, re-sign the affected transformation with its authorized key, and regenerate/re-sign the handoff with its authorized key while leaving the consumer-pinned private profile unchanged. All digests, signatures, authorization, graph, and anchors pass until artifact profile validation returns primary `E_PROFILE_INVALID`. The fixture is created by the repository's deterministic low-level fixture constructor, which signs the intentionally false claim directly; the public `attest transform` command MUST reject the same attempted profile violation.
5. **Unauthorized signer:** add the attacker's Ed25519 public key to policy `keys` so cryptographic verification can pass, but omit it from every matching rule's `authorizedKeyIds`. Regenerate the affected statement and downstream handoff consistently. The statement signature record is `pass`, authorization is `fail`, and primary error is `E_SIGNER_UNAUTHORIZED`.

Each fixture MUST supply its own independently recorded expected manifest digest, expected head set, and expected artifact set through the consumer interface. Fixtures that regenerate and re-sign evidence MUST update those independent values out of band so every anchor passes until the intended check. Each fixture stores `testdata/v0.2/negative/<case>/expected-report.json` with exactly `decision`, `primaryError`, `requiredErrorCodes`, `allowedAdditionalErrorCodes`, `requiredWarningCodes`, `allowedAdditionalWarningCodes`, and an exact map of check IDs to allowed statuses. The harness compares those fields as duplicate-free sets/maps, requires every actual diagnostic code to be in a required or allowed set, and ignores timestamps, messages, context values, tool version, and unrelated positive evidence fields. Full report-schema validity is checked separately. The demo MUST distinguish attacks against existing bytes from a malicious or nonconforming producer who signs new bytes.

For every negative fixture, each `allowedAdditionalErrorCodes` entry MUST be provably ordered after the fixture's required `primaryError` for every context permitted by `diagnostic-map.json`; otherwise that code is not allowed for that fixture. The diagnostic map's continuation edges MUST make the proof mechanical. If an independently discoverable code could sort before the intended primary, the fixture must require that earlier code as `primaryError` or define a failed prerequisite that makes it unreachable. This preserves exact `primaryError` across implementations even when safely discoverable secondary diagnostics vary. This expected-report shape and ordering proof are mandatory for every negative conformance vector in `testdata/v0.2/`, not only the seven demo fixtures.

### 18.4 Clone-and-run acceptance

From a clean checkout of `makoto-project/makoto`, the documented sequence MUST:

- install or run dependencies using the repository’s supported workflow;
- run the canonical byte-deterministic acceptance mode using checked-in, clearly marked insecure demo-only keys, fixed identifiers/timestamps, and the checked-in raw fixture;
- execute all three provenance events and the handoff;
- verify the positive bundle;
- execute all seven negative fixtures grouped into the five webpage attack stories;
- return nonzero if any expected result differs; and
- finish in under 60 seconds on both release baselines named in Section 23.2. The measured window begins immediately before `./scripts/demo-v0.2.sh --acceptance` starts its first cleanup/generation operation and ends only after positive/negative report comparisons and successful final cleanup complete. Dependency resolution/download is a separate prerequisite outside that window; interpreter startup and all subprocess startup are inside it. The script MUST print the monotonic elapsed duration and the two boundary labels it enforced. The named-runner stability remedy in Section 23.2 applies equally to this 60-second gate: instability requires an evidence-backed specification revision, never an ad hoc waiver.

The command MUST not require cloud credentials, a hosted service, Docker, or write access outside the demo work directory. It MUST clean up generated temporary files or place them in a documented ignored directory.

The fixed acceptance entry point is `./scripts/demo-v0.2.sh --acceptance`, run from the core repository root. It writes only beneath ignored `demos/v0.2-end-to-end/.work/`, removes that directory before and after a successful run, and retains it with an explicit path on failure for diagnosis. `scripts/check.sh` invokes this exact command.

The demo MAY also expose a separate `--fresh-keys` semantic mode. That mode generates new keys and therefore new statement, manifest, and report bytes; it must prove the same allow/deny semantics but is excluded from byte-digest comparisons, hosted artifact pins, and the 60-second canonical acceptance gate. Documentation MUST never describe fresh-key output as byte-deterministic.

## 19. Website requirements

The core v0.2 webpage must be the canonical narrative counterpart to the runnable repository demo. It must include:

- the source → normalize → public-safe → handoff → verify story;
- a small DAG visualization with signer identity and artifact digest at each node;
- exact clone-and-run commands copied from a tested script;
- collapsible statements, profiles, policy, manifest, and verification report;
- the positive result and five negative outcomes;
- explicit explanations of signature validity versus authorization and graph continuity versus completeness;
- links to every immutable hosted schema and predicate page; and
- a link to the exact tagged core-repository demo revision.

The page may use precomputed artifacts for display, but those artifacts MUST be generated by the same core demo and checked into or fetched from a pinned release. The web page MUST NOT claim that browser-only decoration is a live verifier.

Before release, the website repository MUST also:

- eliminate all broken internal and external links;
- remove or repair GitHub links that currently return 404;
- replace the website demo-06 link that points to a nonexistent core directory;
- make all examples validate against the version they claim;
- remove tracked `node_modules` content and ignore dependency directories;
- add the project’s actual license file and align website, core, and package license claims; and
- remove or qualify package-install commands for unpublished or unrelated PyPI/npm names.

## 20. Repository deliverables

### 20.1 Core repository

```text
schemas/v0.2/                     canonical JSON Schemas and catalog
spec/v0.2.md                      normative protocol text
src/makoto/                      reference CLI and library
src/makoto/internal-schemas/     checksum-asserted bounded-worker IPC schemas
src/makoto/standard-schemas/     checksum-asserted offline Draft 2020-12 registry
src/makoto/unicode/15.0.0/       checksum-asserted normalization/case-fold inputs
tests/                            schema, crypto, graph, policy, and CLI tests
testdata/v0.2/                    valid and invalid conformance fixtures
testdata/v0.2/diagnostic-map.json stable code/step/context/continuation contract
testdata/v0.2/coverage-matrix.json keyword/traversal/budget/diagnostic coverage gate
demos/v0.2-end-to-end/            September 16 producer/consumer proof
release/checksums.schema.json     closed core checksum-manifest schema
release/v0.2/checksums.json       exact tagged release byte inventory
LICENSE                           authoritative license
README.md                         accurate v0.2 quick start and status
```

The core repository MUST publish a tagged v0.2 release artifact containing schemas, conformance fixtures, and checksums. It MUST NOT publish to a language package registry as part of this milestone.

### 20.2 Website repository

```text
schema/v0.2/                      exact release schema and catalog copies
schema/core-release.schema.json  closed release-index validation schema
spec/v0.2/                        rendered protocol documentation
demos/v0.2-end-to-end/            core demo webpage
assets/                           graph and walkthrough assets
scripts/ or CI checks             schema parity and link verification
LICENSE                           license matching the core project
```

The website MUST pin the core release tag and schema digests used to generate its content.

## 21. v0.1 compatibility and migration

- v0.2 is not wire-compatible with v0.1.
- v0.1 schema URLs and documentation remain available and immutable.
- v0.1 objects MUST never be accepted as v0.2 through permissive coercion.
- The v0.2 release ships a non-normative field-mapping and guarantee-loss guide, not an automated migration command or a legacy-acceptance mode. Conversion ordering, inventory formats, marker profiles, and opt-in policy require a separate versioned migration specification.
- A v0.1 document MAY be preserved as an ordinary exact-byte input artifact to a newly signed v0.2 origin or transformation. That v0.2 signature attests only to the new observation or conversion event and the digest of the presented legacy bytes; it MUST NOT be reported as authentication of the historical v0.1 lineage or signer.
- The v0.2 reference verifier has no `legacyUnverified` marker, inventory allowlist, `authenticated-history` shortcut, or policy exception. Any future converter that adds those concepts needs new schemas, report fields, error codes, and conformance fixtures before its output can participate in an `allow` decision.
- Documentation MUST provide a field-mapping table and clearly list guarantees that cannot be carried forward, especially signer authenticity, authorization, graph completeness, and exact historical artifact binding.

The existing L1/L2/L3 pages remain labeled as v0.1 historical material. v0.2 MUST not market an “unforgeable” level. Until isolated evidence generation is specified, the v0.2 verifier reports concrete capabilities: structured, authenticated, authorized, artifact-bound, graph-complete, and anchored-complete.

## 22. Security and privacy requirements

### 22.1 Threats in scope

- Artifact mutation after attestation.
- Signed metadata mutation or envelope substitution.
- Missing, cyclic, or rewired provenance nodes.
- Replay of an older valid handoff when the consumer has an independently expected manifest/head/artifact set, age bound, or consumer-supplied nonce challenge, optionally recipient-bound. Recipient alone is not freshness.
- Valid signatures from unauthorized keys.
- Schema drift or substitution at a reused URI.
- Unknown or omitted critical profiles.
- Bundle path traversal, symlink or hard-link escape, file-change races, oversized inputs, deep JSON, duplicate keys, pathological schema evaluation, and malicious schema retrieval.
- Local denial of service when an attacker pre-creates, replaces, makes unavailable, or weakens the permissions of the predictable default temp-parent path; this is an availability risk, not a producer-evidence authenticity bypass.
- Leakage of source locators or extension fields through over-sharing.

### 22.2 Required mitigations

- Exact-byte SHA-256 bindings and DSSE verification.
- Consumer-owned trust policy.
- Digest-pinned schemas and offline-first catalogs.
- An authorized exact-set handoff manifest for graph completeness, plus an independently supplied expected manifest/head/artifact set, nonce challenge, or explicit age policy for freshness unless replayable handoff is deliberately allowed.
- Resource limits and safe path handling.
- No network retrieval in the v0.2 reference verifier.
- No arbitrary code execution from schema formats, extension fields, or bundles.
- Strict failure for malformed or invalid signatures claiming configured keys is a deliberate integrity posture; bundle corruption can already cause denial, and implementations MUST NOT silently repair ambiguous envelopes.
- Redaction-friendly optional source locator and organization-controlled extension payloads.
- Logs that omit artifact contents, private keys, and private-schema contents by default.
- Verifier-controlled snapshots and profile-worker temporary files live below one fixed private parent. By default, on POSIX the parent is `/tmp/makoto-v0.2-<decimal-uid>`; on Windows it is the path with segments `Makoto`, `v0.2`, and `temp` below the current user's `LocalAppData` known folder. A consumer MAY supply `--temp-parent <private-directory>` to recover from an unavailable or hostile default parent; the override MUST already exist, be physically outside and non-aliasing with the bundle and every consumer input, and pass the identical ownership/mode/type/no-link validation. Before creating an invocation child, the verifier safe-opens the selected parent, bundle root, and consumer-input roots only far enough to prove that the selected temp parent neither contains, is contained by, nor aliases the bundle root or any consumer input; a temp-parent collision is invalid configuration exit 2 and writes no temporary content. This preflight does not classify relationships between the bundle and consumer inputs: those comparisons remain the Step 1 completed-evidence `E_BUNDLE_UNSAFE_PATH`, exit-1 path defined in Sections 15 and 16.1. It then requires the selected parent to be a real directory owned by the current user with mode `0700` on POSIX or an ACL granting access only to the current user and system administrators on Windows; on macOS, the parent, invocation child, marker, snapshots, and worker files MUST additionally have no extended ACL entry granting access to another principal, and creation MUST clear inherited ACL entries before sensitive bytes are written; creation of the default or validation of either selected parent failing is operational exit 3 before evidence evaluation. Each invocation creates one child named `verify-<32 lowercase random hexadecimal characters>` with the same directory protection, then creates and syncs the no-follow regular marker `.makoto-verifier-temp-v0.2` with exact bytes `makoto-verifier-temp-v0.2\n` before any artifact bytes, schema bytes, payloads, or other sensitive temporary content are written. The invocation holds an exclusive advisory lock on that opened marker descriptor from creation until all workers have exited and cleanup finishes; POSIX uses a nonblocking-testable whole-file `flock`, and a claimed Windows runtime uses the equivalent exclusive file lock. Failure to acquire or retain the invocation's own lock is operational exit 3. Regular snapshot/worker files use mode `0600` or the equivalent ACL, are unlinked as soon as the platform permits, and the invocation child is removed on normal or handled-error exit before the marker lock is released. For a bundle argument whose no-follow final-component classification is a symlink, including a dangling symlink, or whose existing directory is permission-denied or otherwise not safely openable as a real directory, temp-parent preflight records a deferred bundle-root sentinel, omits containment/alias comparisons that require an opened bundle handle, and continues after validating the temp parent and consumer inputs. A nonexistent path or stable real non-directory is invalid invocation exit 2 and never creates the sentinel. The deferred condition MUST NOT become exit 2 or 3; Step 1 owns its completed-evidence E_BUNDLE_UNSAFE_PATH result and no bundle descendant is read.
- Startup cleanup is best-effort and bounded before evidence evaluation. It enumerates at most 4096 immediate child entries in the host-provided descriptor iteration order without claiming a global sorted prefix, retaining only names that match the exact `verify-<32 lowercase hexadecimal characters>` grammar. It then sorts that bounded matching subset by UTF-8 name bytes, attempts at most the first 16 candidates, traverses at most 10,000 entries and 1 GiB of regular-file bytes across all candidates, and stops after 2 seconds of monotonic elapsed time. Reaching any bound skips the remaining cleanup without failing verification or emitting a report diagnostic; cleanup order is intentionally operational and does not affect verification output. A candidate must be a real directory owned by the current user, contain a no-follow-opened regular marker named `.makoto-verifier-temp-v0.2` with fixed bytes `makoto-verifier-temp-v0.2\n`, and have both directory and marker modification times at least 24 hours older than the cleanup process's captured wall-clock time. Cleanup safe-opens the marker and MUST acquire the same exclusive lock nonblockingly before traversing or deleting; lock contention proves the invocation may still be live and skips that candidate regardless of age. The cleaner holds the acquired lock through descriptor-relative recursive deletion and marker removal, then releases it. After acquiring the lock, cleanup revalidates ownership/mode/type and recursively deletes only through descriptor-relative no-follow operations; any link, alias, failed stat, ownership/mode change, race, lock loss, or per-candidate bound exhaustion skips that candidate. It never searches arbitrary directories for marker files. Crash residue is treated as sensitive and its location is never printed at normal verbosity.

An attacker who can write the consumer's policy, expected-value, catalog, binding, or artifact source while the verifier is opening it is inside the consumer trust boundary and can replace the consumer's requested input. Makoto does not claim to authenticate such local inputs. Safe no-follow opens and immutable snapshots ensure that the exact bytes actually evaluated are stable and identified in the report; signed/digest-bound artifact sources must additionally match their expected digest. Consumer metadata is never reread after snapshotting.

Any exit-3 tool error caused by an unavailable, hostile, wrongly owned, or wrongly protected default temp parent MUST name `--temp-parent <private-directory>` as the remediation in its escaped message without echoing sensitive paths. The CLI still fails closed; the message exposes the already specified recovery path.

### 22.3 Privacy model

Makoto metadata can itself be sensitive. Source URIs, tool names, organization identifiers, row-level fields, and profile names may disclose internal systems or personal information. Producers SHOULD include only information needed by the recipient’s policy. Private profiles may be exchanged separately. The normative JSON report includes exact expected and actual recipient and nonce values when supplied, so reports containing them MUST be handled as sensitive evidence and MUST NOT be copied into general logs without deliberate redaction. A digest proves equality but does not hide low-entropy values from guessing attacks. Makoto does not encrypt data or metadata; encryption is a transport/storage concern.

## 23. Reliability, performance, and observability

### 23.1 Determinism and offline operation

- Verification of a complete local bundle MUST be deterministic and require no network access.
- Repeated verification of unchanged bundle bytes, policy, catalogs, expected values, explicit evaluation time, tool version, and satisfied resource assumptions MUST produce the same semantic decision, check statuses, error codes, roots, heads, and digests. Wall-clock timeout and OS-enforced worker-memory exhaustion can produce `E_RESOURCE_LIMIT` under host/runtime differences and are explicitly operational limits, not cross-host deterministic semantic results; conformance fixtures MUST remain below both. When evaluation time is omitted, the captured value is an additional input and MUST be reported rather than hidden.
- Human message wording may improve in patch releases; machine-readable report fields and codes require versioning.

### 23.2 Performance targets

Release benchmarks run on two named baselines: (1) GitHub Actions `ubuntu-24.04` x86-64 with 4 vCPU and 8 GiB RAM, and (2) macOS 15 on an Apple M2 with 8 GiB RAM. The targets below must pass on both with CPython 3.11; CPython 3.12 is a compatibility gate but not the performance baseline.

Phase 0 includes a native-backend spike that verifies the strict Ed25519 vector suite and measures 1,000 signatures on both baselines before the dependency and 2-second target are frozen. If no maintained native backend meets both exact semantics and the target, Phase 0 revises the target or dependency plan in this document; Phase 1 does not silently ship a pure-Python fallback against an impossible gate.

- Verify a 1,000-statement metadata graph, excluding artifact hashing, in at most 2 seconds at p95 over 20 local runs.
- Stream artifact hashing at at least 100 MiB/s for local uncompressed files, where 1 MiB is `2^20` bytes. This is a hashing-primitive gate: each sample starts immediately before the first timed read from an already safe-opened, pre-snapshotted warm-cache fixture descriptor and ends immediately after SHA-256 finalization; it excludes path resolution, safe-open, snapshot creation, final rescan, and report production. The reference implementation SHOULD issue read/write chunks no larger than 32 MiB per artifact; tests assert the configured maximum chunk size, but host RSS delta is not a release benchmark because allocator/native-library accounting is not portable.
- Verify the three-statement demo bundle in under 2 seconds for a fresh CLI invocation including process startup. The external harness starts its monotonic timer immediately before spawning `makoto verify bundle` and stops only after process exit and complete stdout/stderr capture; dependency setup, fixture generation, and filesystem-cache preparation occur before the timer.
- Keep every hosted core schema below 250 KiB and the combined v0.2 schema set below 2 MiB.
- Reject configured size/depth limits before unbounded allocation.

Benchmarks MUST record hardware, runtime version, warm/cold state, and fixture size. `testdata/v0.2/benchmarks/baselines.json` records the exact runner image/virtual CPU metadata for Ubuntu and the macOS machine model, chip, RAM, OS build, power mode, and provisioning commands; the release evidence links each result to that manifest. A substitute machine may provide additional comparative evidence but cannot silently replace a named release baseline. A missed performance target blocks release only if the reference benchmark reproduces it. If repeated GitHub-hosted runs show that the named runner class cannot provide a stable enforceable latency distribution, Phase 0 MUST revise this document to pin a more specific or self-hosted runner class, or revise the threshold with recorded evidence; it cannot silently waive individual failures.

The benchmark producer runs `uv run python -m makoto.bench --fixtures testdata/v0.2/benchmarks --samples 20 --json-out <result.json>`. It performs one uncounted warm-up plus 20 measured executions, for 21 total executions per case. Each 1,000-statement metadata sample starts immediately before a fresh public `verify_bundle` library invocation and ends after the JCS-plus-LF report bytes have been produced. It uses fresh verifier/request state and raw fixture policy, catalog, bundle index, envelope, expected-value, and artifact-binding bytes on every sample; it includes safe inventory, strict parsing, backend calls for all signatures, authorization, profile work present in the fixture, graph/root/head/anchor checks, report construction, and report serialization. It excludes dependency setup, the outer benchmark-process startup, fixture generation, and artifact-byte streaming; the metadata fixture uses checked-in path-backed zero-length artifact files inside the safe benchmark bundle, opened through the same identity-capable snapshot/rescan verifier byte-source interface as ordinary CLI evidence; their digest bookkeeping and filesystem checks still run. Native-library initialization performed lazily by the verifier is inside the first uncounted warm-up and outside measured samples, while every per-request key parse or verifier initialization remains inside. The demo-bundle target uses the external fresh-process boundaries above. `scripts/release-check.sh` then runs `uv run python -m makoto.bench_check --input <result.json> --thresholds testdata/v0.2/benchmarks/thresholds.json`. The thresholds file is strict versioned JSON containing the exact limits in this section and unit `MiB/s`; `bench_check` validates the result schema and fixture digests, uses nearest-rank p95 (19th ascending of 20) for maximum-latency gates and nearest-rank p05, explicitly the sample minimum (1st ascending of 20), for the minimum-throughput gate, without additional rounding. Thus any one measured warm-cache throughput miss fails that gate. It exits 0 only when every required baseline threshold passes, 1 on a measured threshold miss, and 2 on malformed/mismatched input. Benchmark fixture bytes and SHA-256 digests are checked in. Metadata runs use warm filesystem cache; the hashing benchmark reports both a cold best-effort cache-drop run where the OS permits it and the required warm-cache throughput using MiB. Browser and accessibility gates pin Playwright, Chromium, axe-core, retry count, and external-link allowlist versions in the repository lock/configuration.

### 23.3 Operational evidence

The CLI is not a service and has no availability SLA. It MUST provide:

- stable structured verification reports;
- optional verbose timing per verification phase;
- tool and schema versions;
- counts for statements, signatures, profiles, roots, heads, and checked artifacts; and
- actionable error context that identifies a digest or subject without dumping sensitive data.

“Short,” “remediation-oriented,” “actionable,” and “minimum context” are human-interface guidance, not conformance predicates. Mechanical privacy gates instead enforce the closed diagnostic context schema, ASCII-escaped evidence strings, the prohibition on private-key bytes, and the default prohibition on artifact contents and private-schema contents in terminal output, logs, diagnostics, and reports. Tests scan every success/error stream and report fixture for those forbidden byte classes; human wording may vary.

The hosted schema endpoint is a convenience, not a runtime dependency. Release verification MUST test HTTP status, content type, CORS, `$id`, and byte digest for every public schema URL.

Privacy stream/report tests use generated high-entropy ASCII canaries, not whole arbitrary artifact/schema blobs or vague byte classes. Each fixture injects distinct 32-byte random-equivalent fixed test canaries into a private key, artifact-only field, private-schema-only annotation, and safe diagnostic identifier. The release test scans stdout, stderr, reports, logs, and website-generated diagnostic assets for the exact raw canary plus its canonical base64, lowercase/uppercase hexadecimal, JSON-escaped, and percent-encoded spellings; it requires absence for key/artifact/schema canaries and presence only in the one explicitly allowed escaped diagnostic field for the identifier canary. Fixtures also include partial-prefix/suffix leak cases at lengths 8, 16, and 24 bytes. This mechanical gate tests the known fixture secrets and encodings; it does not claim to detect arbitrary semantic leakage.

## 24. Test strategy

### 24.1 Schema tests

- Every valid fixture validates against the exact hosted/core schema pair.
- Every invalid fixture fails for the expected reason.
- Core schemas permit namespaced extension values.
- Critical profile references require complete digest-pinned resources.
- `format` remains annotation-only; core URI fields use the explicit Section 10.4 semantic URI parser, while profile string-shape assertions use only the decoded `makotoPattern` grammar and vectors.
- Duplicate keys are rejected before JSON Schema evaluation.
- Duplicate subject names, noncanonical media types, BOMs, non-finite JSON numbers, and noncanonical DSSE base64 are rejected.
- Appendix A validates against `verification-report.schema.json`.

### 24.2 Cryptographic tests

- Published DSSE interoperability vectors.
- Ed25519 positive, corrupt signature, wrong key, wrong payload type, malformed base64, and multiple-signature cases.
- Statement digest remains stable when envelope formatting changes or an additional signature is added.
- Statement digest changes for any payload-byte change.
- No test treats a bare hash as a signature.
- Signature thresholds count distinct authorized keys, duplicate key IDs fail, unknown well-formed co-signatures warn without counting, and malformed or invalid configured-key signatures fail.

### 24.3 Graph property tests

- Linear chain, multiple roots, join, split, and disconnected extra node.
- One-statement positive handoff where a core origin is simultaneously root and head; no transformation is required by the protocol.
- Missing predecessor, wrong subject name, mismatched input digest, duplicate event ID, and duplicate statement payload use wire-level fixtures. Self-cycle and multi-node-cycle cases are internal graph-model unit tests because constructing digest-addressed wire cycles would require SHA-256 fixed points; cycle detection remains defense in depth and no impossible wire fixture is claimed.
- Random filesystem enumeration and attestation-discovery order yields the same graph; shuffling canonically sorted signed/index arrays fails `E_CORE_SCHEMA`.
- Reachable set exactly matches a trusted manifest.
- A normal transformation declared as a manifest root emits Step 10 `E_ROOT_INVALID` and independently makes the declared root set differ from the computed zero-predecessor origin set, so Step 11 also emits `E_MANIFEST_SET`. The wire fixture requires both diagnostics and proves their resulting `primaryError`/`allowedAdditionalErrorCodes` ordering; no impossible zero-predecessor transformation or suppression fixture exists.
- Older valid head is rejected when expected head differs.
- Multiple expected heads use exact set equality, and a split statement can be a head for one terminal subject while another subject continues downstream.

### 24.4 Policy tests

- Valid and authorized; valid but unauthorized; unknown key; insufficient threshold; wrong predicate authorization; wrong handoff signer; expired policy key; missing rule; and each `E_REQUIRED_PROFILE_MISSING` trigger (zero final-artifact selector match, missing head reference under consumer policy, and missing head reference under manifest requirement).
- Unknown critical profile denies; unknown noncritical profile yields `indeterminate` for that profile and follows explicit policy.
- A consumer-required profile ID with the wrong digest denies even when a producer signs and bundles the substitute schema.
- Evaluation-time boundaries, exact recipient/nonce checks, stale handoffs, replayable-handoff opt-in, and conflicting anchors. One exact vector supplies a passing expected-head method while policy simultaneously requires an absent expected-manifest method; it reports `freshnessMethod: "multiple"`, expected-head `pass`, expected-manifest `fail`, and aggregate freshness `fail`.

### 24.5 Artifact and profile tests

- One-byte mutation, newline change, JSON reformatting, and Unicode normalization all change exact-byte digest.
- Valid JSON content profile, invalid field, missing required field, forbidden direct identifier, invalid pattern, invalid JSON, and unsupported media type.
- Profile URI reuse with different bytes is rejected by digest.
- External `$ref` absent, digest mismatch, unpinned embedded resource, excessive evaluation depth, and prohibited ambient or network resolution.
- Recursive pinned schemas are accepted within limits; dynamic references, evaluation timeout, and missing critical artifact bytes fail with stable codes.

### 24.6 End-to-end and web tests

- Clean-clone demo on supported platforms.
- Positive case plus all seven mandatory negative fixtures across five story groups, with asserted exit codes and error codes.
- Hosted schema parity against a pinned core tag.
- Every checked-in JSON example validates against its declared schema.
- Internal link crawl with zero broken local targets.
- External link check with a documented allowlist only for rate-limited targets; intentionally unavailable or broken targets must be removed or replaced.
- Browser smoke test at 1440×900 and 390×844: page loads without console errors, every disclosure opens by keyboard, every schema/repository link has the expected target, and code blocks remain readable without page-level horizontal overflow.
- WCAG 2.2 AA accessibility check: zero axe-core critical or serious findings, visible focus on every interactive element, and text alternatives for the DAG. The keyboard-only traversal is a recorded manual release check, not an implied browser heuristic: from a fresh page load at 1440×900, the operator uses only Tab, Shift+Tab, Enter, Space, Escape, Home, End, and arrow keys to traverse the skip link, primary navigation, every walkthrough disclosure in DOM order, the copy/run controls, all five negative-story disclosures, every schema/repository link, and the footer; each control must receive visible focus, activate once, and return focus predictably. The release evidence stores the tested commit, browser/OS versions, timestamp, operator, and screen recording or timestamped checklist. Automated Playwright coverage separately asserts the same DOM order and activation targets.

The core test matrix is Ubuntu 24.04 and macOS 15 across CPython 3.11 and 3.12. The clean-clone acceptance run must pass on both operating systems. Website CI runs on Ubuntu 24.04; a pre-release macOS run verifies that copied commands and the core demo remain portable.

## 25. Release and migration plan

### Phase 0 — Freeze the contract

- Approve this project specification.
- Convert the normative model into JSON Schemas and conformance fixtures.
- Publish `testdata/v0.2/coverage-matrix.json` and fail Phase 0 unless it maps every supported schema keyword and schema-bearing traversal position, every resource-accounting boundary and simultaneous-limit precedence, every Appendix C `triggerId`, every cryptographic rejection rule, and every portable-path rule to at least one positive and one negative fixture where both outcomes are meaningful. A checked generator MUST extract every normative sentence containing `Phase 0`, `fixture`, `vector`, `pins`, `covers`, `includes`, or `test` into a source-obligation inventory; every extracted obligation MUST map to one or more matrix row IDs or to one closed, reviewer-approved not-applicable record with exact rationale. CI fails on an unmapped or stale extracted sentence. The gate MUST also cover every canonical ordering and cache/reuse boundary that can change a status, diagnostic, `primaryError`, or report byte.
- In that matrix, “where both outcomes are meaningful” means a wire-realizable condition. `E_GRAPH_CYCLE` trigger rows are the sole initial wire-negative exemption because a digest-addressed wire cycle requires a SHA-256 fixed point; they MUST instead map to a negative internal graph-model fixture and a positive acyclic wire fixture. Every exemption is a closed row with `wireNegative: "not-applicable"`, exact rationale, and required substitute fixture IDs; no implementation may add exemptions without revising this specification.
- Publish executable language-neutral pseudocode and traces for bounded-pattern parsing, Thompson-fragment construction, normative state numbering, search-start behavior, epsilon closure, transition evaluation, exact operation charging, and the exact state-count formula. In-memory representation is non-normative; state numbers, processing order, accepted language, linear-time behavior, counted-state ceiling, operation totals, and trace outcomes are normative and covered by vectors.
- Prove strict Ed25519 backend behavior, exact-rational JSON Schema evaluation, the custom `makotoPattern` parser/NFA evaluator, and enforceable profile-worker time/memory termination on both release operating systems with adversarial vectors.
- Prove the Section 16.2 verifier byte-source interface with instrumented platform tests: no-follow handle acquisition, stable physical identity, containment/alias rejection, immutable snapshot creation, mutation race, and final-rescan behavior MUST match the CLI path implementation on both release operating systems. An ordinary byte array/file-like adapter MUST be rejected as verifier evidence.
- Extend the Phase 0 performance spike beyond signature primitives: run the 1,000-statement baseline both profile-free and with a representative metadata profile on every statement, exercising canonical traversal and exact-rational evaluation before freezing the 2-second target or staffing estimate.
- Rebaseline implementation effort and dependencies around the bespoke canonical evaluator: a general-purpose `jsonschema` library MAY assist parsing or differential tests but cannot implement Makoto's normative traversal, operation charging, exact rational arithmetic, bounded-pattern NFA, or deterministic diagnostics by itself.
- If macOS or Ubuntu cannot enforce the specified worker-memory boundary without rejecting a baseline CPython worker, Phase 0 MUST revise the measurement model, native-helper plan, policy floor, or supported-platform matrix in this document before Phase 1; it MUST NOT ship a platform that always exits 3 or silently weaken the bound.
- Classify every normative MUST in the coverage matrix as externally observable conformance, instrumented implementation test, code-review/static-analysis obligation, or operational release evidence. Requirements such as no unrelated-key trial verification, no signature reserialization, the Thompson-NFA implementation strategy, and equivalent incremental report accounting need instrumented/unit or review evidence when no black-box vector can distinguish the internal method; the matrix MUST NOT invent an impossible wire fixture.
- Record protocol decisions in the core repository.

Exit: origin, transformation, profile, trust, graph, handoff, and verification semantics are represented by reviewed schemas and test vectors.

No implementation may claim Makoto v0.2 conformance or begin Phase 1 against prose alone. Phase 0 closes required fields, nullability, defaults, numeric ranges, object closure, tuple uniqueness, report diagnostics, and every semantic rule with schemas plus positive/negative fixtures; any ambiguity discovered while encoding them returns to this specification for resolution before the contract freezes. Phase 0 review MUST compare every schema and vector back to the complete prose and must record a cross-artifact consistency result; approval of this project plan cannot be cited as wire-protocol convergence.

### Phase 1 — Build the reference verifier first

- Implement strict parsing, schema resolution, DSSE/Ed25519 verification, trust policy, graph construction, anchor checks, artifact hashing, and JSON artifact profiles.
- Use handcrafted valid/invalid fixtures before building convenience generators.

Exit: verifier passes all conformance and attack fixtures and emits the stable report format.

### Phase 2 — Build producer tooling and demo

- Implement origin, transform, signing, and handoff commands.
- Implement deterministic synthetic transformations.
- Make positive and negative scenarios one-command reproducible.

Exit: a clean clone produces a fresh allowed handoff and all seven expected fixture denials across five story groups.

### Phase 3 — Prepare website against the core release candidate

- Stage schema and predicate documentation from the exact core candidate commit without publishing versioned URLs as released.
- Build the core walkthrough page from candidate-pinned demo artifacts.
- Repair broken links, examples, installation claims, and licensing.
- Run `uv run scripts/sync_core_release.py --commit <candidate-sha> --candidate`, review the generated candidate pin and schema diff, then run `uv run scripts/check_site.py --candidate` locally.

Exit: local link/schema checks pass against the unchanged candidate SHA and the website revision is ready to swap the candidate pin for the final tag; no public release claim or deployment is required yet.

### Phase 4 — Release rehearsal

- The release operator is a maintainer with write access to both repositories. This specification does not itself authorize a tag, push, merge, or deployment; the operator obtains explicit release approval before those external actions.
- Run the exact September 16 script on a clean machine/account context.
- Record terminal output and fallback screenshots.
- Record the exact candidate commit SHA, run `scripts/release-check.sh` from a clean checkout of that SHA, verify the checkout remains unchanged, and only then create immutable tag `v0.2.0` pointing to that same SHA.
- Run `uv run scripts/sync_core_release.py --tag v0.2.0` to replace the candidate pin with the verified tag/commit, review that only release-reference metadata changed, run the same site check locally, merge the website change to `main`, and let `.github/workflows/deploy.yml` publish `main` to `gh-pages` only after the check job succeeds.
- Run a post-deploy probe that compares every hosted schema byte digest with `schema/core-release.json`, checks status/content type/CORS, loads the v0.2 walkthrough, and follows its core tag link.

Exit: another person can follow the public page without private context and reproduce the allow decision and all seven fixture denials presented as five attack stories.

Rollback is documentation-safe: v0.1 remains immutable; v0.2 draft URLs are not promoted as stable until all release gates pass. Once v0.2 versioned schemas are declared released, their bytes cannot be rolled back or edited; corrections require v0.2.1 or v0.3 identifiers according to compatibility impact.

### 25.1 Dependency and effort plan

```text
Contract + schemas
    |
    v
Verifier + conformance fixtures
    |
    +----> Producer CLI ----> End-to-end demo ----> Release rehearsal
    |
    '----> Hosted schema pin + website cleanup ---> Website deployment
```

| Workstream | Estimate | Depends on | Exit evidence |
|---|---:|---|---|
| Normative schemas, crypto spike, and fixtures | 5–7 person-days | Approved spec | Schema suite, strict-backend evidence, and positive/negative fixtures. |
| Verifier, trust, graph, and report | 10–14 person-days | Schemas | Full conformance and attack tests. |
| Producer CLI, DSSE, and handoff | 4–6 person-days | Schemas; verifier interfaces | Fresh signed graph and bundle. |
| Synthetic transformations and demo harness | 3–4 person-days | Producer and verifier | One allow and seven fixture denials across five stories. |
| Website schema pin, walkthrough, and link/license cleanup | 3–4 person-days | Reviewed core candidate SHA | Local site gate and reviewable static page. |
| Cross-platform test, benchmark, security hardening, and rehearsal | 4–6 person-days | All preceding work | Ubuntu/macOS evidence and timed rehearsal. |

Total planning range is 29–41 person-days. Three engineers can parallelize producer, verifier, and website lanes after Phase 0 stabilizes their interfaces, but no lane may bypass the verifier-first acceptance dependency. The September 16 date is feasible only with that staffing and immediate Phase 0 closure; the scope must cut future integrations before cutting any positive or mandatory negative verification proof.

The September 16 feasibility statement and 29–41 person-day range are provisional planning inputs until Phase 0 records the strict-crypto, profile-heavy 1,000-statement, worker-lifecycle, and worker-memory spikes on both release baselines. A failed spike MUST update the date, staffing, target, dependency, or scope in this document before Phase 1; estimates are not acceptance evidence and cannot waive a measured gate.

## 26. Success metrics

v0.2 is successful when all of the following are true:

- 100% of examples declared valid validate against their declared core and profile schemas; every deliberately invalid fixture fails with its declared stable code.
- 100% of valid v0.2 statements and manifests use genuine digital signatures; zero bare hashes are labeled signatures.
- The reference verifier detects every mandatory negative case with the expected stable code.
- Two fresh-environment runs by someone other than the implementer complete from clone to final decision without undocumented steps.
- All versioned hosted schema URLs return expected status, content type, CORS header, `$id`, and byte digest.
- The website has zero broken internal links and zero known unqualified installation or license claims.
- The public walkthrough and repository demo use the same pinned artifacts and command sequence.
- A private profile's local catalog filename/path can be renamed, or its URI can remain unavailable publicly, while verification continues from an authorized local catalog; its signed `$id` itself is immutable identity and is not renamed.

Adoption counts, foundation acceptance, external integrations, and marketing reach are not v0.2 release criteria.

## 27. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Users interpret signed provenance as true provenance | False confidence | Separate signature, authorization, and execution claims in schema, CLI, and docs. |
| A valid chain is truncated or replayed | Consumer accepts stale/incomplete history | Require an authorized exact-set manifest for completeness and an independent expected manifest/head/artifact set, nonce (optionally recipient-bound), or age policy for freshness. |
| Extensibility becomes incompatible dialects | Makoto loses portable value | Keep a small immutable core, URI namespaces, digest-pinned profiles, and explicit criticality. |
| A permissive authorization rule overlaps a constrained rule | A policy author believes an alternative rule tightened access when it did not | Document that rules are alternatives, lint overlapping rules, and test the selected-rule set in policy fixtures. |
| JSON Schema is oversold as universal data validation | Binary/columnar claims are false | Normatively support JSON artifacts only in v0.2 and require future adapters. |
| Private schema resolution leaks internal URLs or enables SSRF | Security/privacy incident | Offline-only local catalogs and digest pinning; the v0.2 verifier has no network resolver. |
| Exact-byte hashing surprises users | Equivalent JSON reformats fail | Document byte semantics and require transformations for normalization/canonicalization. |
| Key files in a demo are mistaken for production practice | Insecure reuse | Label fixtures, scope them to demo policy, and document production key management as future integration. |
| Core and website drift again | Examples and hosted schema disagree | Core is authoritative; website pins a release and CI compares hashes. |
| v0.1 migration implies retroactive authenticity | Invalid historical trust | Ship no legacy-acceptance mode; treat preserved v0.1 bytes only as newly observed artifacts and state the lost guarantees. |
| The project overreaches before the live proof | September 16 demo is unreliable | Verifier-first sequence and explicit exclusion of integrations, streaming, L3, and governance. |

## 28. Locked v0.2 decisions and future considerations

These are implementation decisions, not open questions:

1. **Reference implementation:** Python 3.11+ managed with `uv`; protocol schemas and fixtures remain language-neutral.
2. **Multiple signatures:** supported by DSSE and policy; the demo requires one authorized signature per payload.
3. **Event ID uniqueness:** duplicates anywhere in one verified graph fail; no global registry exists.
4. **Handoff recipient and nonce:** optional in the schema and required only by explicit trust policy.
5. **Artifact media type:** parser selection is signed in an artifact-target profile reference. A general subject descriptor is deferred.
6. **Schema distribution:** the positive demo marks its synthetic organizational artifact profile external, proves that its schema bytes are absent from the handoff bundle, and verifies only because the receiver supplies the exact digest-pinned schema through a separate local catalog. The schema remains checked into the demo fixture tree for reproducibility but is never copied into the bundle.
7. **Release numbering:** `0.2` appears in predicates and schema paths; any validation-semantics correction uses a new immutable identifier rather than changing released bytes.

## 29. Definition of done

Makoto v0.2 is done only when:

- [ ] Normative schemas, predicate docs, trust policy, verification report, and conformance fixtures exist in the core repository.
- [ ] Origin and two transformations produce immutable in-toto Statement v1 payloads in DSSE envelopes with Ed25519 signatures.
- [ ] A DAG supports multiple roots, joins, and splits and rejects broken or cyclic graphs.
- [ ] Every profile reference is URI-namespaced, digest-pinned, and criticality-aware; ordinary `extensions` keys are URI-namespaced and their values are covered by the containing statement signature without a separate digest or criticality requirement.
- [ ] Private profiles resolve offline from a local catalog and can validate metadata plus a JSON artifact.
- [ ] A signed handoff manifest declares the exact roots, heads, statement set, final artifacts, and profiles.
- [ ] Independent verification checks structure, profiles, signatures, authorization, graph, anchor, and artifact bytes.
- [ ] Machine-readable output and stable error codes cover the positive case and seven negative fixtures across five demo stories.
- [ ] The complete demo runs from a clean core-repository clone in under 60 seconds on the Ubuntu and macOS release baselines, excluding first dependency download.
- [ ] The website hosts immutable v0.2 schemas and a core walkthrough built from the same pinned demo artifacts.
- [ ] v0.1 remains available and is clearly marked incompatible; migration does not manufacture historical authenticity.
- [ ] Broken links, invalid examples, fake package claims, tracked dependencies, and license inconsistencies are corrected.
- [ ] Local lint, schema, unit, property, end-to-end, link, browser, and accessibility gates pass.
- [ ] Two independent fresh-environment release runs, each performed by a witness who did not implement the demo, record OS, commit, exact commands, exit codes, and elapsed time from a fresh clone without undocumented assistance.
- [ ] Deployed schema URLs and webpage are verified after publication; local success alone is not release evidence.

## Appendix A — Required verification report example

```json
{
  "reportVersion": "0.2",
  "decision": "allow",
  "reportTruncated": false,
  "primaryError": null,
  "bundleId": "urn:uuid:55555555-5555-4555-8555-555555555555",
  "evaluationTime": "2026-09-16T16:04:00Z",
  "policyDigest": {
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "policyDigestEncoding": "exact-input-bytes",
  "coreCatalogDigest": {
    "sha256": "9999999999999999999999999999999999999999999999999999999999999999"
  },
  "manifestDigest": {
    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "expectedManifestDigest": {
    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "handoff": {
    "signatures": [
      {
        "keyid": "sha256:5555555555555555555555555555555555555555555555555555555555555555",
        "keyKnown": true,
        "cryptographic": "pass"
      }
    ],
    "authorization": "pass",
    "completeness": "pass",
    "freshnessMethod": "multiple",
    "freshnessChecks": {
      "expected-manifest": "pass",
      "expected-heads": "pass",
      "expected-artifacts": "pass",
      "nonce": "not_checked",
      "max-age": "not_checked"
    },
    "freshnessStatus": "pass"
  },
  "expectedHeads": [
    { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" }
  ],
  "actualHeads": [
    { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" }
  ],
  "expectedArtifacts": [
    {
      "head": { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" },
      "subjectName": "customers.public.json",
      "digest": { "sha256": "4444444444444444444444444444444444444444444444444444444444444444" }
    }
  ],
  "expectedRecipient": null,
  "actualRecipient": "example:downstream-team",
  "recipientStatus": "not_checked",
  "expectedNonce": null,
  "actualNonce": null,
  "nonceStatus": "not_checked",
  "roots": [
    { "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd" }
  ],
  "summary": {
    "statementsTotal": 3,
    "quarantinedStatementsTotal": 0,
    "statementsReachable": 3,
    "statementsValid": 3,
    "statementsAuthorized": 3,
    "signaturesTotal": 4,
    "signaturesChecked": 4,
    "signaturesValid": 4,
    "manifestSignaturesRequired": 1,
    "manifestSignaturesValid": 1,
    "manifestSignaturesAuthorized": 1,
    "roots": 1,
    "heads": 1,
    "artifactsDeclared": 1,
    "artifactsChecked": 1,
    "historicalMaterialsDeclared": 0,
    "historicalMaterialsChecked": 0,
    "profilesDeclared": 2,
    "profilesValidated": 2
  },
  "statements": [
    {
      "digest": { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" },
      "predicateType": "https://usemakoto.dev/predicate/v0.2/transform",
      "eventId": "urn:uuid:33333333-3333-4333-8333-333333333333",
      "coreSchema": "pass",
      "coreSchemaPrerequisiteChecks": [],
      "signatures": [
        {
          "keyid": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
          "keyKnown": true,
          "cryptographic": "pass"
        }
      ],
      "candidateRuleIds": ["urn:makoto:policy-rule:demo-public-transform"],
      "authorizingRuleIds": ["urn:makoto:policy-rule:demo-public-transform"],
      "authorization": "pass",
      "authorizationPrerequisiteChecks": [],
      "graph": "pass",
      "graphPrerequisiteChecks": []
    },
    {
      "digest": { "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd" },
      "predicateType": "https://usemakoto.dev/predicate/v0.2/origin",
      "eventId": "urn:uuid:11111111-1111-4111-8111-111111111111",
      "coreSchema": "pass",
      "coreSchemaPrerequisiteChecks": [],
      "signatures": [
        {
          "keyid": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
          "keyKnown": true,
          "cryptographic": "pass"
        }
      ],
      "candidateRuleIds": ["urn:makoto:policy-rule:demo-origin"],
      "authorizingRuleIds": ["urn:makoto:policy-rule:demo-origin"],
      "authorization": "pass",
      "authorizationPrerequisiteChecks": [],
      "graph": "pass",
      "graphPrerequisiteChecks": []
    },
    {
      "digest": { "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" },
      "predicateType": "https://usemakoto.dev/predicate/v0.2/transform",
      "eventId": "urn:uuid:22222222-2222-4222-8222-222222222222",
      "coreSchema": "pass",
      "coreSchemaPrerequisiteChecks": [],
      "signatures": [
        {
          "keyid": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
          "keyKnown": true,
          "cryptographic": "pass"
        }
      ],
      "candidateRuleIds": ["urn:makoto:policy-rule:demo-normalize"],
      "authorizingRuleIds": ["urn:makoto:policy-rule:demo-normalize"],
      "authorization": "pass",
      "authorizationPrerequisiteChecks": [],
      "graph": "pass",
      "graphPrerequisiteChecks": []
    }
  ],
  "profiles": [
    {
      "statementDigest": {
        "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
      },
      "id": "https://schemas.example.com/makoto/customer-public-v1.json",
      "digest": {
        "sha256": "3333333333333333333333333333333333333333333333333333333333333333"
      },
      "closureDigest": {
        "sha256": "8888888888888888888888888888888888888888888888888888888888888888"
      },
      "target": "artifact",
      "subjectName": "customers.public.json",
      "mediaType": "application/json",
      "critical": true,
      "requiredByManifest": true,
      "requiredByPolicy": true,
      "requiredByAuthorizationRuleIds": [],
      "resolution": "pass",
      "validation": "pass",
      "prerequisiteChecks": []
    },
    {
      "statementDigest": {
        "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
      },
      "id": "https://schemas.example.com/makoto/public-transform-metadata-v1.json",
      "digest": {
        "sha256": "7777777777777777777777777777777777777777777777777777777777777777"
      },
      "closureDigest": {
        "sha256": "6666666666666666666666666666666666666666666666666666666666666666"
      },
      "target": "predicate",
      "subjectName": null,
      "mediaType": null,
      "critical": true,
      "requiredByManifest": false,
      "requiredByPolicy": false,
      "requiredByAuthorizationRuleIds": ["urn:makoto:policy-rule:demo-public-transform"],
      "resolution": "pass",
      "validation": "pass",
      "prerequisiteChecks": []
    }
  ],
  "artifacts": [
    {
      "lifecycleRole": "final",
      "artifactKind": "ordinary",
      "statementDigest": { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" },
      "head": { "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" },
      "subjectName": "customers.public.json",
      "digest": { "sha256": "4444444444444444444444444444444444444444444444444444444444444444" },
      "digestStatus": "pass",
      "digestPrerequisiteChecks": [],
      "profileStatus": "pass",
      "profilePrerequisiteChecks": [],
      "applicableProfileCount": 1
    }
  ],
  "unindexedEnvelopes": [],
  "quarantinedStatements": [],
  "datasetEntries": [],
  "unreferencedFiles": [],
  "checks": [
    { "id": "load-safely", "status": "pass", "prerequisiteChecks": [] },
    { "id": "parse-strictly", "status": "pass", "prerequisiteChecks": [] },
    { "id": "index-payloads", "status": "pass", "prerequisiteChecks": [] },
    { "id": "core-schemas", "status": "pass", "prerequisiteChecks": [] },
    { "id": "signatures", "status": "pass", "prerequisiteChecks": [] },
    { "id": "authorization-thresholds", "status": "pass", "prerequisiteChecks": [] },
    { "id": "metadata-profiles", "status": "pass", "prerequisiteChecks": [] },
    { "id": "authorization", "status": "pass", "prerequisiteChecks": [] },
    { "id": "graph-dependency-artifacts", "status": "not_checked", "prerequisiteChecks": [] },
    { "id": "graph", "status": "pass", "prerequisiteChecks": [] },
    { "id": "roots-and-heads", "status": "pass", "prerequisiteChecks": [] },
    { "id": "completeness-anchor", "status": "pass", "prerequisiteChecks": [] },
    { "id": "freshness-anchors", "status": "pass", "prerequisiteChecks": [] },
    { "id": "artifact-bytes", "status": "pass", "prerequisiteChecks": [] },
    { "id": "artifact-profiles", "status": "pass", "prerequisiteChecks": [] },
    { "id": "decision", "status": "pass", "prerequisiteChecks": [] }
  ],
  "warnings": [],
  "errors": [],
  "tool": { "name": "makoto", "version": "0.2.0" }
}
```

## Appendix B — Adversarial review record

This appendix is historical and non-normative. It records what changed at each review round, so older bullets may describe superseded designs. The current numbered sections, Appendices A/C, and eventually the Phase 0 schemas/vectors take precedence over every historical summary below.

### Invalidated prior review

A previous appendix recorded review by GPT-4o and Gemini 3.6 Flash. The user explicitly invalidated that model set and ordered a restart. None of its critiques, agreement claims, round counts, or quality scores are evidence for this specification. Technically sound text already present in the draft was retained, but every retained decision was re-evaluated independently in the fresh review below.

### Verified current reviewers and routes

- **Claude Fable 5:** exact identifier `claude-fable-5`, Claude CLI `2.1.239`, print mode, effort `high`, no fallback. Installed help explicitly listed the full identifier and an exact-model smoke test succeeded before review.
- **Sol 5.6 xHigh:** exact identifier `gpt-5.6-sol`, Codex CLI `0.149.0`, reasoning effort `xhigh`, read-only/ephemeral execution, no fallback. An exact-model smoke test succeeded before review. User configuration was isolated so an unrelated broken Cloudflare MCP could not alter or block the reviewer route.

An attempted Sol collaboration session failed during unrelated MCP initialization before a model session existed; it produced no review and is not counted. Gemini 3.7 Flash was not needed for the minimum Fable-plus-Sol review set and was not invoked, so no availability or review claim is made for it.

Both counted reviewers read the complete pre-revision document independently. Fable used a protocol/security lens; Sol used a verifier/interoperability lens. Preserve-intent instructions protected the source-first, append-only, extensible JSON Schema mission and the explicit exclusion of Docling integration, community, and governance work.

### Round 1 accepted findings and revisions

- **Consumer profile substitution:** required profiles now pin schema digest and artifact media type in consumer policy; a producer-controlled bundle catalog cannot satisfy an ID-only requirement with permissive replacement bytes.
- **Replay and handoff semantics:** an authenticated bundle now requires an authorized exact-set manifest, while freshness separately uses expected manifest/head/artifact values, a nonce, an age policy, or explicit replay acceptance. Recipient is audience binding only; required values are compared, not merely present.
- **Multi-head and split semantics:** head flags are repeatable, expected heads use exact set equality, and subject-level terminality supports one split output continuing while another is handed off.
- **Signature thresholds and key lookup:** thresholds count distinct authorized keys; v0.2 key IDs are exact SPKI digests; duplicate, malformed, unknown, unsupported, and invalid extra signatures have defined behavior.
- **Profile evaluation safety:** producer-supplied profiles are evaluated only after signature verification and authorization, inside explicit schema/regex/error/time limits and a terminable worker boundary.
- **Graph determinism:** subject names are unique, reachable extension predicates fail closed without a semantic adapter, and dataset-manifest membership is validated before graph construction.
- **Strict wire and JSON behavior:** DSSE v1 PAE/base64/Ed25519 bytes, artifact JSON/NDJSON parsing, media types, JSON Schema resource closure, recursion, and format behavior are normative.
- **Deterministic trust and reporting:** the verifier captures or accepts one evaluation time, key-window boundaries are defined, policy matching fields are exact, decision aggregation is explicit, and the complete report contract plus conforming example are specified.
- **CLI completeness:** normative commands now expose repeated heads, deterministic IDs/timestamps, overwrite behavior, required-profile bindings, expected manifest/head/artifact values, recipient/nonce, evaluation time, and digest-qualified offline schema selection.
- **Portable bundle safety:** archives are deferred; path grammar, case collisions, hard links, descriptor-relative no-follow reads, race resistance, and aggregate metadata limits are explicit.
- **Legacy scope:** v0.2 does not invent an underspecified migration acceptance mode. Legacy bytes may be newly observed as ordinary artifacts, but historical v0.1 signer authenticity is never manufactured.
- **Negative-case precision:** edited metadata has an exact mutation recipe and primary stable error, while profile-substitution, distinct-key threshold, multi-head, replay, evaluation-time, strict parser, and resource-limit fixtures were added to the test plan.

### Rejected or deferred findings

- **Remove cycle detection because digest-addressed cycles are computationally infeasible:** rejected. Keeping deterministic cycle detection is cheap defense in depth and protects implementations from malformed indexes or future digest algorithms.
- **Give `deny` and `indeterminate` different process exit codes:** deferred as a preference. Machine consumers have the stable JSON decision; v0.2 retains a compact nonzero verification-failure code.
- **Add arbitrary CSV, Parquet, image, and binary semantic validators:** deferred. v0.2 hashes all finite byte artifacts but normatively validates JSON and finite NDJSON only.
- **Add workload identity, public revocation, Sigstore, transparency logs, or certificate federation:** deferred. These integrations do not belong in the September 16 minimal reference path.
- **Treat newline, compression, or semantic-equivalent reserialization as one artifact:** rejected. v0.2 intentionally binds exact bytes; normalization is an attested transformation.
- **Change the already-specified performance sampling solely because a reviewer requested it:** no change. Section 23.2 already requires p95 over 20 runs and records platform, warm/cold state, runtime, and fixture size.
- **Sol reviewer metadata claiming the Fable result was unavailable:** rejected as reviewer speculation outside its isolated input. Controller evidence verified Fable CLI/model availability and captured its completed review.

### Round 2 accepted findings and revisions

- **Final-artifact profile scope:** consumer-required profiles are restricted to artifact targets with `eachMatchingFinalArtifact` scope, enforced against every matching final manifest artifact and its declared head after graph discovery. Intermediate same-named subjects cannot satisfy policy.
- **Freshness truth table and metadata hash:** an authorized manifest is mandatory; independent expected manifest digest, expected head/artifact tuples, nonce, or age policy establish freshness/selection, while recipient alone is only audience binding. Explicit replay acceptance warns.
- **Outcome and report completeness:** profile criticality/requirement outcomes, handoff signatures/authorization/freshness, counts, expected metadata/artifacts, status aggregation, and stable diagnostics are now normative and represented in Appendix A.
- **Resource and snapshot safety:** immutable bootstrap ceilings, field units, offline-only schema resolution, Unicode/path limits, and verifier-controlled immutable byte snapshots close resource, SSRF, and in-place mutation gaps.
- **Interoperable profiles and lexical rules:** the JSON Schema vocabulary/resource closure, portable regex subset, dynamic-reference exclusion, strict URI/UUID/media-type/timestamp/Unicode rules, and recursive-schema behavior are specified.
- **Policy validity:** thresholds, referenced keys, time windows, required-profile scope, exact rule matching, overlapping-alternative risk, replay requirements, and invalid-configuration behavior are explicit.
- **Terminal output selection:** manifest heads derive exactly from handed-off terminal artifact tuples; consumers can independently pin manifest metadata or artifact tuples when trusting only the handoff signer is insufficient.
- **Deterministic demo and fixtures:** fixed transforms/serialization/IDs, exact primary and allowed secondary failures, supplied partition verification, benchmark procedure, and pinned standards/catalog inputs are specified.
- **Network scope reduction:** automatic network schema retrieval was removed from v0.2. Hosted immutable schemas remain required distribution artifacts and are imported into authenticated offline catalogs before verification.

### Round 2 rejected or phase-gated findings

- **Require every final JSON Schema file inside this project-planning document:** phase-gated, not ignored. Phase 0 must produce and review every schema and conformance vector before protocol freeze or any conformance claim; Phase 1 cannot start from prose alone.
- **Treat wall-clock resource exhaustion as cross-host deterministic:** rejected as physically unachievable. Semantic decisions are deterministic when declared resource assumptions are satisfied; a safety timeout is explicitly an operational `E_RESOURCE_LIMIT` outcome and conformance fixtures remain below it.
- **Make recipient matching itself a freshness guarantee:** rejected. Recipient is audience binding; only nonce, independently expected metadata/artifacts/heads, or a consumer age rule constrains replay.

### Round 3 accepted findings and revisions

- **Payload dispatch and digest domains:** statement and handoff DSSE payload types now dispatch separately; typed enclosing fields, schemas, and payload types prevent a bare SHA-256 value from being interpreted across object domains.
- **Ed25519 interoperability:** RFC 8410 SPKI/PKCS#8, exact 44-byte public-key DER, canonical policy base64, lowercase recomputed key IDs, and strict invalid-configuration behavior replace the earlier incomplete RFC 5280 reference and contradictory unsupported-algorithm path.
- **Private-profile demo truthfulness:** the final transform now carries two distinct private profiles, one for predicate metadata and one for artifact content. The policy, handoff scope, positive proof, and verification-report counts reflect both targets.
- **Handoff and freshness shapes:** manifest-required profiles are artifact-only with a fixed scope and identity tuple; expected artifacts independently qualify as a complete selection/freshness method; per-method report statuses prevent the summary from concealing simultaneously exercised anchors.
- **Optional-profile outcomes:** warning diagnostics now represent unresolved, unsupported, or resource-limited optional noncritical profiles; `E_*` codes are reserved for required checks or a false evaluated signed claim.
- **Consumer preflight:** policy, expected values, keys, limits, and consumer catalogs are validated before evidence loading. Invalid configuration exits 2 and cannot be confused with evidence denial.
- **Portable schema semantics:** exact Draft 2020-12 vocabularies, unknown-keyword behavior, RFC 3986 `$ref` resolution, a complete bounded regular-expression grammar, exact mathematical JSON-number semantics, and a linear-time evaluator requirement replace host-dependent behavior.
- **Resource and terminal safety:** per-file, aggregate, snapshot, number, worker-memory, and structured-validation limits now cover profile-free artifacts and dataset entries; all terminal rendering of evidence-controlled strings is ASCII JSON-escaped.
- **Failure-report completeness:** nullable unavailable values, unindexable envelopes, core-catalog digest, manifest/policy requirement flags, unknown-key signatures, profile aggregation, exact summary counts, dataset/unreferenced-file records, deterministic primary error, and per-code context schemas are normative.
- **Producer and release tooling:** co-signing, historical/profile material, dataset entries, deterministic attestation discovery, safe output replacement, a separate benchmark-bearing release gate, and complete negative-fixture expected anchors are specified.
- **Demo reproducibility:** region, consent, age input, exact age-band strings, fixture-specific independent anchors, and exact expected-report locations close byte-generation and acceptance ambiguity.

### Round 3 rejected or phase-gated findings

- **Treat the approved project specification alone as a frozen independently implementable protocol:** rejected as a category error and retained as an explicit Phase 0 gate. Approval starts schema/vector encoding; no implementation or interoperability claim is allowed until prose, immutable schemas, report schema, and conformance vectors pass cross-artifact review.
- **Sol's isolated note that the Fable smoke test was unavailable:** rejected as reviewer speculation outside its supplied input. Controller evidence verified Claude CLI `2.1.239`, exact `claude-fable-5`, and captured the complete Fable review.

### Round 4 accepted findings and revisions

- **Freshness decision:** absence of required freshness now deterministically fails with `E_FRESHNESS_REQUIRED` and denial; specifically required anchors retain their more specific codes, while explicit replay acceptance is `not_checked` plus warning.
- **Policy profile constraints:** digest-pinned authorization constraints are mandatory validation requirements for statement, predicate, or artifact targets and set `requiredByPolicy`; ID-only constraints remain label selectors only.
- **Schema dialect:** profiles declare an immutable Makoto Draft 2020-12-derived dialect/meta-schema, rather than claiming generic Draft 2020-12 while changing regex semantics. Literal and nested-quantifier grammar is explicit, and all non-root `$id` values are forbidden.
- **Strict Ed25519:** canonical point decoding, prime-order checks for `A` and `R`, scalar bound, exact verification equation, and rejection of cofactored/ZIP-215 variants are algorithmic. The implementation plan acknowledges custom strict-point and validation layers beyond stock libraries.
- **Ordering and diagnostics:** every handoff and bundle-index array has mandatory ordering with `E_CORE_SCHEMA` on violation. Appendix C plus `diagnostic-map.json` fixes code steps/triggers/context/continuation, and skipped checks name prerequisites.
- **CLI and release correctness:** key generation no longer claims impossible two-file atomicity; co-sign input/output identity is forbidden; expected-artifact types, consumer historical material, all command exit classes, non-normative Python API details, candidate-SHA tagging, and benchmark evaluation are defined.
- **Artifact/report completeness:** final and historical material share one typed actual-artifact record model; reachable/historical summary counts, separate freshness checks, primary error, and deterministic fixture comparison are explicit.
- **Resource and dataset behavior:** raw/decoded/cache/snapshot accounting, tighter-limit retroactivity, evaluation depth, worker limits, dataset core-profile identity, size range, entry mapping failures, and historical-byte hashing are defined.
- **Adopter edge cases:** catalog scans ignore unrelated consumer-directory contents; event IDs, year range, policy-outside-bundle enforcement, extension ownership, warning scope, demo input shape/lexical ages/collisions, bundle determinism, and MiB units are explicit.

### Round 4 rejected or phase-gated findings

- **Count missing Phase 0 schemas/vectors as an unresolved defect in the project plan:** phase-gated, not dismissed. This document authorizes their creation and explicitly forbids implementation/conformance claims until cross-artifact review passes; reviewer agreement on the plan cannot substitute for those deliverables.
- **Require identical complete secondary diagnostic sets after every corrupted input:** rejected as unnecessarily brittle. Decision, primary error, report schema, required/allowed code sets, and check-status constraints are portable; safely discoverable secondary detail is bounded by the published dependency map.

### Round 5 accepted findings and revisions

- **Failure precedence and evidence quarantine:** all exact-set/index mismatches now resolve at Step 11, while malformed envelopes, invalid signatures, missing predecessors, missing artifact bytes, and wrong artifact bytes retain their earlier, more specific primary errors. Statements outside the signed manifest set are quarantined until that comparison and cannot affect authorization, graph, profile, or reachable-summary results.
- **Profile requirement and authorization closure:** `E_REQUIRED_PROFILE_MISSING` now distinguishes an absent signed profile reference from schema resolution or validation failure. Candidate rules are finalized only after their digest-pinned statement/predicate constraints validate; ID-only constraints remain selectors. The illustrative policy now defines non-overlapping rules and distinct keys for origin, normalization, public-safe transformation, and handoff.
- **Profile-dialect composition:** organizational schema resources use the digest-pinned Makoto profile dialect, while referenced immutable Makoto core resources retain their own declared dialect. Core resources cannot be shadowed, and the complete resource closure remains offline and digest-pinned.
- **Deterministic resource and path behavior:** canonical processing order, bootstrap ceilings, exact accounting, path grammar, collision handling, schema closure order, artifact snapshot order, and bounded regex/number semantics are fixed independently of host enumeration behavior.
- **Report and diagnostic completeness:** artifact `lifecycleRole` is separate from `artifactKind`; quarantined statements have explicit detail and summary fields; bundle verification emits only `allow` or `deny`; signature structure and cryptographic failures have distinct triggers; and Appendix C aligns every stable code with its algorithm step.
- **Runnable-demo and release precision:** the contract requires seven negative fixtures organized into five public attack stories, deterministic identifiers/timestamps/bindings/reports, a verifier-first phase sequence, and candidate-versus-release schema publication gates.

### Round 5 rejected or phase-gated findings

- **Treat the absent Phase 0 schemas and vectors as proof that this project plan cannot proceed:** phase-gated. Their absence prevents an interoperability or conformance claim, not approval to encode them. Phase 0 must cross-review the prose, schemas, report schema, diagnostic map, and vectors as one contract before Phase 1 begins.
- **Emit an overall `indeterminate` decision from bundle verification:** rejected for v0.2. Required uncertainty denies; optional unavailable checks remain explicit `indeterminate` or `not_checked` records without changing an otherwise valid bundle from `allow`.

### Round 6 accepted findings and revisions

Round 6 reviewed exact input SHA-256 `a6035300c1887b375cfae36703f3163d6dbe38699f5c877e4cd052332ae339a3` through Claude CLI `claude-fable-5` and Codex CLI `gpt-5.6-sol` at `xhigh`, independently and under the pressed whole-document verifier/interoperability lens.

- **Reachable signature attack fixtures:** edited-metadata and rewired-edge fixtures now replace and validly sign the handoff/independent expectations while retaining the stale statement signature. The changed statement remains manifest-listed and reaches Step 5 instead of being quarantined.
- **Standards-correct profile dialect:** the portable bounded regex is now the custom `makotoPattern` keyword. Standard Draft 2020-12 `pattern` is not redefined, profile resources cannot declare `$vocabulary`, quantified character classes are legal, and anchor placement is root-level and testable.
- **Candidate-local authorization:** digest-pinned authorization constraints now carry `requiredByAuthorizationRuleIds`; unavailability disqualifies only that candidate, while an evaluated false producer-signed profile remains a global integrity denial. Statements without a cryptographically eligible candidate never load producer profile schemas.
- **Dataset staging and errors:** each dependency dataset manifest is snapshotted, hashed, and core-validated once at Step 8 and reused later. Graph membership, mapping identity, manifest digest, partition digest, and partition size each have one owning diagnostic.
- **Total strict parsing:** `E_JSON_INVALID` covers syntax, UTF-8, BOM, scalar, and token failures; duplicate keys and envelope structure retain their more specific codes. Missing bundle and referenced-manifest cases have distinct Step 1/2 behavior.
- **Stable report contract:** JCS-plus-LF serialization, failed freshness-method semantics, all record shapes, complete sort tuples, prerequisite order, candidate-rule requirement fields, JCS-safe numeric domains, truncation signaling, and no-manifest failure population are now explicit.
- **Bounded aggregate work:** policy and bootstrap ceilings now cover total signatures, profile evaluations/worker launches, diagnostics, report records, and serialized report bytes with reserved deterministic resource-limit reporting.
- **Operational closure:** manifest requirements cannot be vacuous; root derivation is algorithmic; physical aliases use opened-file identity; all input-derived terminal strings are escaped; key/snapshot permissions and cleanup are specified; binding path bases and standalone profile validation are defined; and the canonical deterministic demo is separated from fresh-key mode.
- **Feasibility correction:** Phase 0 must prove the pinned native strict-Ed25519 backend and benchmark before Phase 1. The estimate is now 29–41 person-days with three-way parallelism rather than an implausible 18–24 person-days.

### Round 6 rejected or phase-gated findings

- **Call missing Phase 0 artifacts a defect in the plan itself:** phase-gated, not ignored. This specification deliberately authorizes creation and cross-review of schemas, diagnostic maps, and vectors before implementation or conformance claims.
- **Remove exact-byte hashing, strict Ed25519, offline resolution, cycle defense, or artifact-only handoff requirements:** rejected; no reviewer supplied concrete harm that outweighed the locked v0.2 intent.
- **Sol metadata saying the Fable route produced no output:** rejected as isolated reviewer speculation. The review controller captured the complete Fable 5 critique quoted in the same Round 6 result; both reviews count, but their findings—not their claims about controller state—are evidence.

### Round 7 accepted findings and revisions

- **Authorization safety and reporting:** a new Step 6 `authorization-thresholds` check is the real prerequisite for skipped metadata profiles; all profile records now carry prerequisite arrays. Artifact profiles likewise require final statement authorization. Exact `operationTypes` selectors prevent the normalization key from bypassing the privacy-transform rule.
- **Manifest processing boundary:** only transport/core-valid handoff payloads establish the manifest-listed set. Once established, bad or unauthorized handoff signatures deny without erasing full statement processing; earlier failures quarantine all indexed statements. Conformance vectors cover each stratum.
- **Schema and transport dispatch:** envelope schemas validate transport only; the verifier performs decoded semantic dispatch. Bundle/envelope transport structure is validated before indexing, and missing, wrong-typed, unsafe, malformed, and core-invalid paths/objects have disjoint diagnostics.
- **Profile and policy closure:** candidate-only failure aggregation, `makotoPattern` schema/instance/control semantics, operation selectors, overlap subsumption, NDJSON evaluation units, and JSON resource limits are explicit.
- **Handoff, dataset, and graph reports:** the handoff field table fixes requiredness/lexical bounds; dataset-entry records are the exact union of graph and supplied mappings; per-statement graph attribution and the check-to-step/code map are normative.
- **Filesystem and CLI safety:** raw-to-NFC lookup, stable final tree rescan, consumer/bundle alias classification, producer dataset-manifest membership validation, standalone schema flag combinations, and one fixed demo entry point are specified.
- **Version and history boundaries:** semantic patch versions replace the complete identifier family without mixing; Appendix B is explicitly historical and non-normative.

### Round 7 rejected or phase-gated findings

- **Treat Phase 0's not-yet-created schemas/vectors as a contradiction in this project plan:** phase-gated as before. Their creation and cross-artifact review is the Phase 0 exit gate, not evidence that Phase 0 cannot begin.
- **Require wire-level SHA-256 cycle fixtures:** rejected as computationally unconstructible; cycle handling remains covered at the internal graph-model layer.

### Round 8 accepted findings and revisions

- **Deterministic reports and limits:** roots and expected/actual heads have exact digest ordering; report-size decisions use a stable projection that excludes human message/tool spelling; identical NDJSON lines still charge separately; diagnostic enums are closed.
- **Cross-field and error ownership:** all handoff terminality/head/artifact/set violations use `E_MANIFEST_SET` at Step 11; decoded-payload JSON errors use Step 3; missing versus broken optional partition mappings are distinct.
- **Failure-state closure:** required profiles skipped after missing/bad artifact bytes have exact profile/artifact/check statuses and prerequisites; candidate-only diagnostic suppression is reflected in Appendix C.
- **Trust and profile boundaries:** expected-value files cannot originate inside or alias the bundle; non-artifact profiles forbid subject/media locators; unauthorized manifests do not grant profile requirements; reachable event-ID scope is explicit.
- **Dataset and graph behavior:** graph predecessor lookup excludes quarantined statements; every supplied dataset manifest receives semantic validation and one reusable snapshot; dataset-entry consumer bindings are reachable through the verifier CLI.
- **Operational portability:** consumer-file safe opening, portable key/envelope inspection commands, worker containment evidence, disjoint tool/protocol tags, fixed cleanup markers, and external-link criteria are explicit.

### Round 8 rejected or phase-gated findings

- **Treat absent Phase 0 artifacts as a blocker to authorizing Phase 0:** phase-gated; it remains a blocker to Phase 1/conformance, exactly as the status and release plan state.
- **Count Sol's claim that Fable returned no result:** rejected as controller-state speculation; the controller captured and presented the complete Fable critique in the same result.

### Round 9 accepted findings and revisions

- **Freshness closure:** the no-method/no-replay case now has the exact required tuple `freshnessMethod: "none"`, `freshnessStatus: "fail"`, `freshness-anchors: "fail"`, and `E_FRESHNESS_REQUIRED`; replay opt-in remains the sole `not_checked` path.
- **Dataset-entry identity and population:** producer bindings retain local envelope paths, verifier bindings are digest-addressed and include the expected entry digest, and records cover only reachable edge references plus supplied bundle/consumer bindings rather than every manifest declaration.
- **Bounded deterministic reporting:** nested signature, head/root, expected-artifact, rule-ID, and prerequisite populations count toward `maxReportRecords`; total signatures have one cross-envelope tuple; retained records are a canonical prefix with explicit truncation semantics.
- **Filesystem and temporary-file ownership:** absent evidence, unsafe present targets, wrong types, aliases, permission/stat failures, and replacement races have disjoint codes. Cleanup is confined to a fixed validated private parent and descriptor-relative matching children.
- **Profile and policy closure:** missing required signed references count as applicable artifact requirements without synthetic profile records; age/skew and schema ceilings are bounded; parsed limits are reapplied to their own policy/catalog inputs.
- **Version, ordering, and diagnostics:** the generic in-toto payload type is exempt from Makoto semantic-patch rewriting; step-local ordering explicitly preserves Step 8 before Step 12; every diagnostic pair has one owning check.
- **Interoperability cleanups:** UUID identity is exact-string based, `coreCatalogDigest` hashes exact embedded catalog bytes, absent entry size is `not_checked`, degenerate ASCII ranges are defined, supplied recipient/nonce mismatches deny, and standalone schema dialect behavior is explicit.

### Round 9 rejected or phase-gated findings

- **Treat not-yet-created Phase 0 schemas, vectors, and diagnostic-map artifacts as a blocker to authorizing Phase 0:** phase-gated, not ignored. Their absence blocks Phase 1 and every conformance claim; creating and cross-reviewing them is Phase 0's purpose.
- **Count a reviewer's claim that another approved reviewer did not run:** rejected as controller-state speculation when the controller captured that review's complete output and exact model/route evidence.

### Round 10 accepted findings and revisions

- **Consumer-owned profile semantics:** every signed profile now carries a recomputed `closureDigest` over the root plus complete sorted non-core dependency set. Consumer, handoff, and digest-bearing authorization requirements pin that closure, preventing producer substitution of weaker transitive schemas under an unchanged root.
- **Step and path ownership:** Step 8 now owns unsafe dataset-manifest sources, dual-role missing manifests use graph-dependency precedence without a second artifact-missing error, and consumer/bundle alias checks have one completed-evidence exit path.
- **Deterministic truncation:** report detail has one explicit global admission sequence, atomic parent units, a shared record/byte-prefix rule, and nullable counters where computation never completed; zero is reserved for a completed empty population.
- **Unauthorized handoff reporting:** completeness and freshness fields/checks are skipped with exact prerequisites when the handoff is unauthenticated, while a statement-only authorization failure does not suppress an authenticated anchor evaluation.
- **Pattern and platform closure:** negated classes have an exact Unicode-scalar complement, range endpoint escapes are fixed, and portable paths reject Windows-reserved characters, names, and terminal normalization hazards.
- **CLI and operational closure:** binding JSON is strict, direct transform inputs are checked before signing, standalone schema validation has fixed limits/exits, cleanup creates its marker before sensitive files, and temporary-parent failure is exit 3.
- **Diagnostic/report closure:** recipient-only mismatches explicitly fail `freshness-anchors` without pretending recipient is freshness; event-ID reachability is computed at Step 9; duplicate declared statement identities are owned by transport schema; manifest decode order, signature counters, additional-error ordering, and stable report comparison surfaces are explicit.

### Round 10 rejected or phase-gated findings

- **Treat absent Phase 0 schemas, vectors, and diagnostic-map artifacts as a blocker to beginning Phase 0:** phase-gated. They remain hard blockers to Phase 1 and every conformance claim.
- **Sol's statement that the Fable route did not reach a model session:** rejected as reviewer speculation. The same controller run captured the complete Fable 5 whole-document critique immediately before Sol's output, with exact route/model evidence.

### Round 11 accepted findings and revisions

Round 11 reviewed exact input SHA-256 `2fffd0b3c89d90e30e4bb1bfa8cad860b2ae61c2b834ad5484ff56b9bf5019fb` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the verifier-implementer/interoperability lens.

- **Partial-evidence state machine:** digest-matched but strict/core-invalid statement payloads now have exact record, signature, authorization, profile, and graph states; only core-valid statements enter selector and graph indexes, and unusable predecessor nodes have one error.
- **Aggregate and diagnostic ownership:** multi-item check folding and empty populations are fixed; `causedByCheck` is required; candidate-only Step 7 errors have one owner; warning ownership does not fail a check; profile-local prerequisites have a separate closed enum.
- **Report limits:** record/byte admission is an exact two-pass Step 14 prefix algorithm over a completed semantic report, JCS-plus-LF byte accounting is explicit, and truncation no longer invents skipped evidence work.
- **Consumer and filesystem boundaries:** all consumer metadata receives explicit preflight accounting, artifact copying is deferred to Step 8/12, every consumer/bundle alias is owned at Step 1, missing catalogs have one code, duplicate dataset-entry sources fail closed, and a validated `--temp-parent` override prevents fixed-parent squatting from permanently disabling verification.
- **Profile and predicate interoperability:** profile closure is a load-time exact static `$ref` closure without unused supersets, duplicate anchors fail, v0.2 bundle decisions accept only core predicates, and all normative Unicode work uses vendored 15.0 tables.
- **Dataset and artifact closure:** mandatory dataset-manifest profile evaluation runs and charges once at Step 8 and is reused later; dataset-entry name collisions are portable; the actual-artifact report population includes required-but-missing historical material; unsupported media states are explicit.
- **CLI and output closure:** attestation authoring validates profile closures before signing, subject binding supports names containing `=`, standalone NDJSON behavior is fixed, normal/report stdout and exit-2/3 stderr shapes are fixed, and both artifact and dataset consumer/bundle duplicates have exact behavior.
- **Adopter-facing precision:** origin expectation is enforced in the demo policy, the bounded-pattern vocabulary has a public documentation endpoint, string bounds are explicit, the 60-second measurement window is fixed, and local concurrent mutation of consumer-owned trust inputs is named as outside Makoto's authentication claim.

### Round 11 rejected or phase-gated findings

- **Replace the linear-time `makotoPattern` implementation requirement with timing alone:** rejected. The bounded regular language plus adversarial vectors are the interoperability surface, while the no-backtracking implementation requirement is retained as a security constraint even though complexity cannot be proven by one black-box vector.
- **Treat Sol's closing statement that Fable was unavailable as review evidence:** rejected as controller-state speculation. The controller captured Fable's complete 2,106-line whole-document critique immediately before Sol's output in the same successful review run.

### Round 12 accepted findings and revisions

Round 12 reviewed exact input SHA-256 `4a6c601c1db038d4f6652f96bd9ccc7c2857c49c1055040f9108b23610e8d471` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, again using the verifier-implementer/interoperability lens.

- **Transport and Step 4 states:** empty signature arrays have one transport code; invalid bundle indexes establish no manifest population; handoff signatures remain inspectable for core-invalid payloads; extension predicates and missing artifact-profile targets have exact statement-record continuation.
- **Manifest and artifact precision:** manifest artifacts match exact name-plus-digest subjects, ordinary media conflicts are Step 13, unauthorized handoffs have fixed artifact/profile continuation, and unreachable listed statements/material have explicit graph, hashing, report, and summary behavior.
- **Configuration/evidence boundary:** catalogs are structurally checked in preflight but profile closures resolve only during evidence evaluation; missing consumer paths exit 2 while missing required/bundle material reports Step 12; consumer artifact bindings now carry their expected digest so Step 2 duplicate identity is executable.
- **Report and operational closure:** Appendix A uses `not_checked` for an empty Step 8 population, report-byte projection retains a minimal schema-valid tool object, total signature counters are defined, timing has a testable optional interface, and profile-worker time/memory measurement is exact.
- **Reference producer completeness:** source/operation metadata, extensions, artifact media type, profile-file shape, and every wire-valid subject name now have documented CLI authoring paths; standalone schema output is fixed.
- **Portability and safety:** ancestor symlink semantics, one-sided key windows, UUID grammar, Windows claim scope, bounded crash cleanup, producer-only private-key handling, and unterminated NDJSON accounting are explicit.
- **Fixture correctness:** the negative-story text now distinguishes harmless unordered discovery from arrays whose canonical order is mandatory.

### Round 12 rejected or phase-gated findings

- **Treat Windows ACL behavior as an untested reference-release MUST:** narrowed rather than accepted. Portable path rejection remains core; Windows runtime/ACL requirements apply only when an implementation claims Windows support, while v0.2 reference conformance remains macOS/Linux.
- **Treat the reviewer-route note that neither approved route ran as evidence:** rejected as controller-state speculation. The same successful controller result contains the complete Fable and Sol whole-document reviews and exact parent route evidence.

### Round 13 accepted findings and revisions

Round 13 reviewed exact input SHA-256 `e008547578b38ef61e678b6eca0e8b3116e958880171722a6448c275a49d237b` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh` under the same pressed whole-document lens.

- **Report admission:** fixed checks plus prerequisites are a non-truncatable skeleton; Step 0 and later diagnostics use one canonical reserved-terminal admission pass under both diagnostic and byte budgets; detail truncation cannot create invalid skipped checks and explicitly denies fail-closed.
- **Profile closure and artifact reachability:** `$ref` discovery traverses only schema-bearing keyword positions with exact root/self/cycle behavior; unreachable artifact profiles have one skipped state and never manufacture required bytes or artifact records.
- **Artifact continuation:** invalid manifest name/digest tuples and mistargeted consumer material have exact Step 11/12 codes, hashing continuation, record statuses, and no duplicate digest errors; optional malformed JSON/NDJSON is a false signed claim and denies deterministically.
- **Catalog and filesystem closure:** strict bundle-catalog/schema JSON errors are owned at Step 4; every bundle entry type is closed; external-only hard links are accepted while in-inventory physical aliases fail; final rescan obtains identity for every entry.
- **Resource portability:** aggregate profile wall time is bounded, memory/time exhaustion is explicitly operational, and Phase 0 must revise the worker-memory/platform contract rather than deadlock macOS or silently weaken enforcement.
- **Lexical and CLI details:** class escaping, bounded quantifiers, bundle UUID grammar, repeated-flag duplicates, dataset-entry empty spelling, key-object closure, payload-type status, and source-pinned example policy are exact.

### Round 13 rejected or phase-gated findings

- **Remove the strict `[L]R` Ed25519 check because a separate black-box vector cannot isolate it:** rejected. The defense-in-depth check remains locked even where one implementation detail cannot be independently distinguished by conformance output.
- **Treat Sol's closing note that Fable did not run as convergence evidence:** rejected as controller-state speculation. The same controller result contains Fable's complete no-release-blocker review immediately before Sol's complete review.

### Round 14 accepted findings and revisions

Round 14 reviewed exact input SHA-256 `ca2e4720012c8bdd5a63333ce2bf760fa75444a531abe83786607ddd65dc00d2` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed verifier-implementer/interoperability lens.

- **Record-state closure:** statement, artifact, and dataset-entry status fields now have field-specific prerequisite arrays; authorization failure, dataset-manifest dependency failure, unusable heads, strict-parse failure, and unreachable statements have exact graph/report states.
- **Handoff signature continuation:** a mixed-signature handoff whose remaining valid authorized keys meet threshold continues through manifest authority, completeness, freshness, and profile checks while the strict signature failure independently denies. An unmet handoff threshold still skips authority-dependent work.
- **Filesystem and resource determinism:** over-limit bundle discovery uses one context-independent bounded-inventory failure before canonical sorting; snapshot rescans claim only host-observable path/type/identity changes; Step 14 projects the precise retained-prefix candidate report and permits provably equivalent incremental accounting.
- **Producer and consumer input safety:** creation outputs are disjoint from every input and sibling output; key targets must also be normalization/case-fold distinct; every handoff head needs a final artifact binding; scalar and in-memory expectation collections receive exact JCS byte/count accounting.
- **Policy and profile closure:** policy arrays have canonical order, uniqueness, conflict, and complete static-unsatisfiability rules; known prohibited profile keywords are explicitly unsupported rather than instance-invalid; dangling-range pattern cases receive vectors.
- **Artifact and diagnostic ownership:** consumer historical material cannot replace a missing final-artifact mapping; missing attestation targets have one unindexed-record population; optional historical absence warns once at Step 12; recipient/nonce comparison against an omitted signed value and every affected Appendix C trigger are exact.
- **Operational and benchmark precision:** temp-parent preflight is separated from Step 1 bundle/consumer alias evidence; the example policy is labeled non-loadable; creation-output failure language, diagnostic-message deduplication, metadata benchmark boundaries, and hosted-runner variance handling are explicit.

### Round 14 rejected or phase-gated findings

- **Treat the not-yet-produced Phase 0 schemas, diagnostic context schemas, and vectors as a blocker to beginning Phase 0:** phase-gated, not ignored. Their absence blocks Phase 1, protocol freeze, and conformance; producing and cross-reviewing them is the defined Phase 0 task.
- **Treat Sol's closing claim that neither approved route ran as review evidence:** rejected as controller-state speculation. The controller performed fresh exact-model smoke tests and captured both complete Round 14 outputs from the approved routes.

### Round 15 accepted findings and revisions

Round 15 reviewed exact input SHA-256 `40e1bd00bab039a4113fecd0f3f80c43626caec5ea157d902757082985cc64a0` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the same pressed whole-document lens.

- **Diagnostic-map and admission closure:** ownership uniqueness is keyed by `(code, step, triggerId)` rather than an overbroad pair; the evidence diagnostic ceiling reserves its own resource slot; diagnostic-stage and detail-stage byte projections each name their exact candidate report.
- **Manifest and graph report precision:** `manifestDigest` is present whenever exact decoded handoff bytes exist; summary head/root counts are graph-computed and nullable on incomplete computation; unauthorized predecessors are included in the exact Appendix C trigger.
- **Pattern and dataset precedence:** decoded versus JSON-source backslash spelling and chained range behavior are explicit; direct dataset-manifest core validation precedes and is reused by the mandatory profile record, eliminating duplicate schema evaluation/codes; final dataset media conflicts are a Step 8 exception.
- **Policy and input closure:** top-level rules sort by ID, scalar arrays have executable ordering, source kinds are absolute URIs, source locators are URI-references, and Step 2 explicitly includes bundle/consumer duplicate-identity comparisons.
- **Filesystem and catalog privacy:** every bundle-root type has an exit/report classification; Step 1 has an immutable per-file inventory bound; catalog-relative generated paths are exact; handoff creation exports only selected profile closures; crash cleanup bounds enumeration before sorting.
- **Developer and release evidence:** generated IDs use one `urn:uuid:` spelling; demo determinism covers every generated JSON file; inspection/creation success streams are exact; benchmark modules, chunk-size guidance, URI test mechanisms, and privacy conformance boundaries are explicit.

### Round 15 rejected or phase-gated findings

- **Rename the `decision` check because pass-on-deny is counterintuitive:** preference only. The stable field is already explicit and renaming would add churn without changing semantics.
- **Treat qualitative UX wording as a protocol blocker:** narrowed. Human wording remains guidance, while closed diagnostic contexts, forbidden secret/content classes, and stream scans provide the mechanical boundary.
- **Treat Sol's closing claim that Fable was unreachable as evidence:** rejected as controller-state speculation. The controller captured Fable's complete Round 15 review before Sol's complete output.

### Round 16 accepted findings and revisions

Round 16 reviewed exact input SHA-256 `7ab78c4071e4289e465e176731a81b8722f778e1d0dabd6ca333d0129a295b90` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed verifier-implementer/interoperability lens. Fable completed in the paired controller run; Sol timed out at the controller's original 1,500-second limit and was rerun alone against the unchanged hash with a 3,600-second limit. Both complete outputs are included as independent Round 16 evidence.

- **Profile dialect and pattern closure:** every profile resource now validates against the exact dialect meta-schema at load time; known ill-typed keywords are unsupported; schema-bearing keyword positions are split by map, array, and single-schema shape; and unescaped class hyphens plus non-ASCII range endpoints have exact behavior and vectors.
- **Profile state and diagnostic ownership:** all-threshold-ineligible and truly empty metadata-profile populations have distinct top-level states; Step 7 explicitly evaluates authorized listed metadata profiles before reachability; candidate-only evaluated-invalid profiles are owned by `metadata-profiles`; optional historical absence warns once per artifact.
- **Catalog, requirements, and signatures:** declared catalog/resource absence is unambiguously `E_CATALOG_INVALID`; manifest profile requirements match the complete signed tuple; creation commands support deterministic repeated-key threshold signatures; `envelope cosign` accepts only the two v0.2 payload types.
- **Dataset and failed-handoff closure:** the Step 8 mandatory dataset-profile reachability exception is explicit; direct dataset schema failure has one diagnostic; dataset-entry report/mapping identity is the logical statement/subject/entry tuple with deterministic digest precedence; an unauthorized handoff creates no final-artifact population and authorizes no final-only byte read.
- **Resource and cryptographic precision:** Ed25519 hash reduction is explicitly little-endian; schema budgets count exact root, non-core, and reached core resources; metadata token ceilings and worker-only structured-artifact parsing bound parent allocation; timeout includes child exit/reap; cleanup uses a held liveness lock.
- **Producer and release gates:** handoff creation validates final bytes, graph/terminality, media, requirements, and optional mappings before signing; hashing and fresh-CLI benchmark boundaries are executable; p05 is plainly the sample minimum; PEM acceptance/generation and manual keyboard evidence are portable contracts; human output may contain its table while the decision remains `allow|deny`.
- **Phase 0 diagnostic closure:** every trigger row must define a deterministic multiplicity key, including edge, statement, profile, artifact/dataset, and graph-SCC identities, before Phase 1.

### Round 16 rejected or phase-gated findings

- **Treat the intentionally absent Phase 0 schemas and vectors as a blocker to approving this Phase 0 project specification:** phase-gated, not ignored. Their absence remains a hard blocker to Phase 1, release, and any protocol-conformance claim; producing and cross-reviewing them is Phase 0's explicit exit gate.
- **Treat Sol's closing claim that Fable produced no usable result as review evidence:** rejected as controller-state speculation. The controller captured Fable's complete Round 16 review before the first Sol timeout, and the retry used the identical frozen input.
- **Reformat non-normative Appendix A solely for indentation preference:** deferred as preference-only; strict parsing, schema validation, and JCS output—not display indentation—are the conformance surfaces.

### Round 17 accepted findings and revisions

Round 17 reviewed exact input SHA-256 `2bb7ed0a397892ae9c9ab6209155e5055f776613b85012cf74575348e3d17d6b` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens.

- **Admission and report closure:** consumer `maxDiagnostics` is admission-only while the immutable candidate ceiling is discovery-time; every candidate recomputes `primaryError`; warnings end at Step 13; all-threshold and Step-2 failure populations, counters, unsafe-path prerequisites, always-present manifest flags, and locally recoverable core-invalid statement fields are exact.
- **Graph and dataset closure:** `summary.heads` has one subject-aware manifest-intersection formula; dataset workers return only a bounded validated entry index; digest/media/profile precedence and precharged invalid validation attempts are explicit; parent steps never reparse the artifact tree.
- **Schema and resource determinism:** applicator, map, array, reference, conditional, contains, and unevaluated traversal is canonical and non-short-circuit; JSON tokens are charged once by exact source identity across metadata, schemas, monolithic artifacts, and NDJSON; signature limits are applied after bounded Step 4 classification.
- **Transport and key precision:** every envelope failure class has one code and owner; private keys use one exact 48-byte PKCS#8 form; URI-or-UUID anti-bypass applies to bundle IDs; actual control scalars and escaped tab/newline/carriage-return pattern atoms are distinguished.
- **Authoring and deterministic CLI:** `profile create` emits a complete validated closure digest/reference; `policy check` provides standalone preflight; schema path-versus-URI and verbose behavior are exact; bundle artifact destinations hash logical identity rather than unsafe names.
- **Policy and operational closure:** statically conflicting consumer artifact requirements have one preflight predicate; default-temp failure names its safe remedy; a mixed supplied/required freshness-method vector and a canonical keyboard witness are required.

### Round 17 rejected or phase-gated findings

- **Treat missing Phase 0 schemas, diagnostic map, and vectors as a blocker to approving the project specification that authorizes Phase 0:** phase-gated, not ignored. They remain hard blockers to Phase 1, release, and every conformance/interoperability claim.
- **Treat Sol's closing claim that Fable did not run as evidence:** rejected as controller-state speculation. The same controller captured Fable's complete Round 17 output and Sol's complete output against the identical frozen hash.
- **Require a rewrite or relax locked security decisions:** rejected; neither reviewer found a mission or locked-architecture defect.

### Round 18 accepted findings and revisions

Round 18 reviewed exact input SHA-256 `eb2d3654d92ec7784e59f427bd7f5c1ccdb3ea78c9e0a2608fd5028a7c779f19` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens.

- **Bundle identity closure:** readable third-party bundle paths are labeled as verifier-valid examples rather than deterministic reference-producer output, whose identity-hashed destinations remain normative.
- **Policy and profile closure:** required-profile conflict preflight now uses the complete requirement tuple; profile-reference mode permits exactly its digest-pinned non-core closure; policy-check overlap warnings are explicit; and aggregate folding applies only to each check's eligible population.
- **Dataset and budget closure:** Step 8 resolves, precharges, and evaluates each mandatory dataset profile once; aggregate worker exhaustion is globally fail-closed; bounded dataset IPC has one metadata-byte charge; and metadata/schema token ceilings are separate from structured-artifact ceilings.
- **Cryptographic and media precision:** identity-hash preimages are literal JCS objects; Ed25519 rejects identity-point `A` and `R`; `application/*+json` has exact subtype semantics; and handoff completeness exactly equals the corresponding top-level check.
- **Developer and release hardening:** inspection outputs are exact closed objects; the bounded-pattern NFA has a deterministic compiled-state ceiling; hosted schema checks identify their authenticated checksum root; demo-key obligations are project-enforceable; and the source-kind documentation URL is part of the hosted release gate.

### Round 18 rejected or phase-gated findings

- **Treat reviewer claims about the other route's controller state as evidence:** rejected. The controller captured both complete independent outputs against the same frozen Round 18 input; neither reviewer can observe the controller's other subprocess.
- **Treat missing Phase 0 schemas, vectors, and implementation evidence as proof that this project specification cannot authorize Phase 0:** phase-gated, not ignored. They remain hard blockers to Phase 1, release, and any conformance claim.

### Round 19 accepted findings and revisions

Round 19 reviewed exact input SHA-256 `32623d5cf082d26dded3e0f74b1e2a5b7c7a349d40093b0e77691c5bbf31a7bd` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fable reported no remaining written release blocker; Sol reported five contradiction-grade blockers. The controller captured both complete outputs against the identical 2,371-line input.

- **Dataset-profile state machine:** Step 8 now distinguishes strict-parse failure, schema failure, semantic-only failure, and media conflict; each has one exact profile state, charge, prerequisite, diagnostic, and cache rule.
- **Media and diagnostic closure:** dataset media conflicts finalize for every conflicting profile at Step 8; ordinary conflicts remain Step 13; Appendix C defines every trigger and multiplicity key; cached mandatory results are never rewritten.
- **Artifact and worker closure:** malformed final tuples have total `artifactKind` and `applicableProfileCount` derivation; aggregate worker exhaustion emits one diagnostic and deterministic skipped dependents; simultaneous artifact-limit crossings have fixed precedence.
- **Profile evaluator boundary:** load-time dialect/meta-schema work runs in the bounded worker with explicit accounting; the dataset core-schema root has one narrow exemption; content keywords are annotation-only; and the Phase 0 coverage matrix is a release gate.
- **Producer/privacy/report hardening:** authoring commands validate profile claims before signing; handoff creation can deterministically omit private profile resources for receiver-only catalogs; macOS ACLs and Windows superscript device names are covered; unavailable report fields have exact null/empty representations; and the diagnostic map joins the frozen checksummed protocol tuple.
- **Conformance precision:** every negative vector uses the `primaryError` continuation proof, envelope payload-type schema/semantic ownership is fixed, inspection objects are literal JCS shapes, Step 0 timing is excluded explicitly, and the stability promise is narrowed to wire/CLI surfaces.

### Round 19 rejected or phase-gated findings

- **Treat Sol's closing claim that Fable's exact-model route failed as evidence:** rejected as controller-state speculation. The controller verified both exact models immediately before launch and captured Fable's complete Round 19 review before Sol's output in the same paired run.
- **Treat acknowledged native-crypto or worker-memory feasibility spikes as prose blockers:** phase-gated, not ignored. Phase 0 must revise this document if either spike fails; no implementation or release may waive those gates.
- **Remove deliberate graph-cycle or strict subgroup defense-in-depth because some wire fixtures are mathematically unreachable:** rejected. Internal-model/unit evidence remains required and the limitations are stated honestly.

### Round 20 accepted findings and revisions

Round 20 reviewed exact input SHA-256 `6b09226533113c7d32e7b95725b56510ea036053b77b050c887c1b49510079d6` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fable reported no written release blocker and three material precision risks; Sol reported seven written-contract blockers. The paired controller captured both complete outputs against the identical 2,401-line input.

- **Media-state closure:** media disagreement has a complete conflict-by-resolution/resource matrix, remains an unconditional validation failure, and performs bounded resolution only to populate independent resolution evidence.
- **Reference and dataset closure:** `$ref` targets must be visited meta-validated schema locations; Step 8 candidate discovery precedes mandatory dataset-profile identity validation; and dataset entry digests have one semantic lexical layer.
- **Resource and filesystem closure:** NDJSON charges exactly `max(1, N)` profile units; snapshot/digest limits are disjoint from parser/profile limits; simultaneous-limit precedence is exact; and final tree rescan has one Step 12 eligibility rule after early failures.
- **Exact output and reporting:** digest and timing JSON literals now match compact JCS byte order; profile subject/media fields are always-present nullable members; and the handoff envelope is excluded explicitly from `unindexedEnvelopes`.
- **Library and secret boundary:** verifier evidence uses path or identity-capable immutable byte sources rather than generic streams; generated macOS private keys clear and verify ACLs; and bounded-pattern Phase 0 artifacts include executable construction/evaluation traces.
- **Hosted and adopter precision:** required documentation bodies are checksum-pinned; the demo source identifier is an intentional URN; handoff head equality is by statement payload digest; nested `event.id` recovery names its exact path; expected-value accounting shapes and zero-bound patterns are explicit.

### Round 20 rejected or phase-gated findings

- **Treat Sol's closing claim that Fable's exact-model route produced no session as evidence:** rejected as controller-state speculation. The paired controller captured Fable's complete Round 20 review before Sol's complete output, and both exact-model smoke tests passed before the round.
- **Treat the absent Phase 0 artifacts as a new blocker in this project-plan review:** phase-gated, not ignored. They remain mandatory before Phase 1, protocol freeze, or any conformance claim.

### Round 21 accepted findings and revisions

Round 21 reviewed exact input SHA-256 `17762c8daf6ec7fcb3e849da2464400168392a419e2fc9eeb36a98cecfceea10` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fable found one release blocker in a corrupted payload-type sentence; Sol found that same corruption plus eight additional contract blockers. The paired controller captured both complete outputs against the identical 2,423-line input.

- **Payload and report repair:** the payload-type grammar is restored as one exact alphabet with lexical-invalid versus supported-type ownership; the report field is consistently `expectedManifestDigest`; and compact JCS output remains literal.
- **Artifact-profile continuation:** Step 13 directly names the bundle/consumer historical-material exception after failed handoff authorization or reachability, while untrusted final mappings never qualify.
- **Step 8 closure:** early optional-profile warnings have legal Step 8 diagnostic rows; nonexistent historical media hints are removed; every conflicting profile consumes exactly one fused closure unit; and mandatory/non-mandatory conflict charging is identical.
- **Worker and benchmark closure:** dataset IPC is one literal closed charged object with a pinned internal schema; the metadata benchmark uses compliant path-backed identity-capable sources; and generic verifier streams remain forbidden.
- **Producer and filesystem safety:** handoff creation snapshots before signing/copying and rehashes staged output; a bad bundle-root final component is deferred from temp preflight to Step 1; key and temp ACL protections remain aligned.
- **Pattern, diagnostics, and release precision:** bounded-quantifier split accounting and zero-bound state counts are exact; anchor/nested-`$schema` vectors are required; admitted diagnostics are partitioned without resort; DSSE `message` is explicitly PAE; hosted catalog probes and two-run release witnesses are aligned.

### Round 21 rejected or phase-gated findings

- **Treat Sol's closing claim that Fable was unavailable as evidence:** rejected as controller-state speculation. The paired controller captured Fable's complete Round 21 output before Sol's complete output, and the exact-model smoke test passed before launch.
- **Treat the absent Phase 0 artifact suite as a new written-plan blocker:** phase-gated, not ignored. Phase 0 artifacts remain mandatory before implementation freeze, Phase 1, or conformance.

### Round 22 accepted findings and revisions

Round 22 reviewed exact input SHA-256 `f04209c169151c2fe0ad98a2291fb49ea3d6341a21bddf83b798e6b3585830a8` through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. The paired controller captured both complete outputs against the identical frozen input. The reviewers found additional written-contract gaps; this revision reconciles them before the next whole-document round.

- **Profile-state closure:** target-byte absence now takes precedence over closure resolution; candidate-only aggregation explicitly overrides the base metadata aggregate; profile prerequisite enums include aggregate metadata/artifact-profile exhaustion; and the single profile prerequisite array is validation-scoped so media contradiction can fail independently of resolution.
- **Dataset-worker and report closure:** the closed dataset IPC object has a mandatory, status-defined, fully charged `tokenCount`; dataset-entry records now have a total matrix for no bytes, mapping disagreement, missing/unsafe targets, Step 8 dependency failure, digest failure, and independently computable size.
- **Policy and identifier precision:** overlap lint has a fixed preflight rule/comparison ceiling, exit-2 overflow, and exact syntactic strict-subsumption predicate; version-family requirements now apply only to Makoto-owned identifiers while external profile/source/operation URIs remain opaque.
- **Filesystem ownership:** first-inventory state deterministically separates role-specific absence from Step 2/4/8/12 consuming-open `E_BUNDLE_UNSAFE_PATH` failures, and Appendix C requires distinct trigger rows.
- **Release-index contract:** `schema/core-release.json` now has a normative path, closed schema/shape, JCS encoding, sorted arrays, complete inclusion sets, exact byte-digest procedure, the exact walkthrough path, and the retained `/source/file` documentation entry.
- **Producer and CLI precision:** reference output contains no `README.txt`; embedded profiles export their root and every declared non-core resource; signing-key cardinality is command-specific; `schema validate` distinguishes invalid instances from invalid schema/configuration and operational limits; `policy check --json` always carries its closed warnings array; and consumer expectation accounting includes `evaluationTime`.
- **Scope and implementation truthfulness:** in-toto/DSSE interoperability is outer-format compatibility rather than acceptance of every foreign semantic convention; Step 8 owns dataset dependency failures; `jsonschema` is limited to core/differential assistance rather than the normative profile evaluator; Phase 0 includes a profile-heavy 1,000-statement spike and the closed graph-cycle wire-fixture exemption.

### Round 22 rejected or phase-gated findings

- **Treat a reviewer's claim about the other route's controller state as evidence:** rejected. The controller captured both approved exact-model outputs against the same frozen input; neither isolated reviewer can observe the other subprocess.
- **Treat the intentionally not-yet-produced Phase 0 schemas, diagnostic map, coverage matrix, vectors, or implementation measurements as proof that this project specification cannot authorize Phase 0:** phase-gated, not ignored. Their absence remains a hard blocker to Phase 1, release, interoperability, and every conformance claim.

### Round 23 accepted findings and revisions

Round 23 reviewed exact input SHA-256 `1db262fdab5f65d5965100b192a8abd72e246a2c9f37b304dd0a17139c761587` (2,501 lines) through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Both exact-model smoke tests passed immediately before launch, and the paired controller captured both complete outputs against the same frozen input. Fable found one release blocker and three material risks; Sol independently found the shared blocker plus additional state-machine blockers and material risks.

- **Step 2 ownership:** unsafe logical paths and physical aliases are explicitly excluded from the Step 2 `E_CORE_SCHEMA` blanket. Step 1 owns in-inventory aliases, and later path/alias failures use consuming-step `E_BUNDLE_UNSAFE_PATH`.
- **Root and graph continuation:** a transformation declared as the same computed/declared root emits only Step 10 `E_ROOT_INVALID`; independent root-set mismatch still emits Step 11 `E_MANIFEST_SET`. Traversal stops at unavailable nodes, and the unreachable-statement `not_checked` exception is explicit.
- **Profile state:** optional historical byte absence precedes media comparison; single unsupported media always performs ordinary closure resolution before its deterministic media outcome; aggregate worker time counts active worker lifecycles rather than unrelated graph/hash work.
- **Bundle and handoff strata:** stable real non-directory bundle roots exit 2 while unsafe directory/symlink opens become Step 1 evidence failure; unauthorized/no-method freshness statuses and recipient/nonce statuses are total; unauthorized handoffs never classify unsigned bundle artifact mappings as historical.
- **Policy and expectations:** overlap discovery has an all-or-nothing 10,000-warning preflight cap; supplied expected head/artifact sets are absent or nonempty, with explicit empty sets invalid.
- **Authorization aggregates:** `authorization-thresholds` has only the core-valid handoff plus core-valid listed statements; top-level final `authorization` has statements only, with complete empty/fail/pass/skipped rules.
- **Producer and worker boundaries:** all producer-influencing bytes use one immutable snapshot generation; ordinary profile workers now have a closed, checksum-asserted, byte-capped IPC contract and exact crash/resource classifications.
- **Release evidence:** the core tag now has a normative closed checksum manifest with exact path, inclusion set, serialization, preimages, and website relationship; feasibility and estimates remain provisional pending Phase 0 spikes; privacy tests use exact canary encodings rather than vague byte classes.

### Round 23 rejected or phase-gated findings

- **Sol's closing claim that Fable failed before a model session:** rejected as controller-state speculation. The same controller had already captured Fable's complete Round 23 critique, beginning with exact section references and ending with its verified findings; both routes count.
- **Treat missing Phase 0 artifacts as a blocker to authorizing Phase 0:** phase-gated, not ignored. Their absence remains a hard blocker to Phase 1, release, interoperability, and conformance, exactly as the document states.
- **Relax exact-byte hashing, strict Ed25519, offline resolution, cycle defense, or the bespoke bounded evaluator:** rejected; neither reviewer identified a mission-level defect requiring those locked decisions to change.

### Round 24 accepted findings and revisions

Round 24 reviewed exact input SHA-256 `576d138f69bfe92234afcd08050f96281c2533aad19970dacb9d2fc5773ac588` (2,567 lines) through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. The paired controller captured both complete outputs against the same frozen input. Both reviewers found remaining written-contract blockers, so Round 24 did not converge.

- **Step and diagnostic ownership:** stale Step 2 safe-path/physical-identity semantics were removed from `E_CORE_SCHEMA`; Step 12 no longer misclassifies a disappearing target as absence; unauthorized-handoff historical-material behavior is folded into Steps 12–13; and extra bundle mappings remain explicitly owned by Step 11 `E_MANIFEST_SET`.
- **Graph and report closure:** traversal now continues through every available node regardless of graph result, own-edge defects beat inherited skip, joins and cycles have total propagation rules, `statementsReachable` has one digest-traversal population, and diamond/mixed-defect vectors are mandatory. `candidateRuleIds`, unindexed-envelope classification codes, and full-report comparison guidance now have exact meanings.
- **Bounded parsing and workers:** malformed JSON token charging has a charge-on-completion algorithm and boundary traces; `maxRegexLength` is per decoded keyword occurrence; worker IPC capacity is pre-reserved from metadata budget before launch; oversized child output is exit 3; and both worker-result schemas are release-checksummed.
- **Offline dialect registry:** all eight Draft 2020-12 root/meta resources have fixed IDs, vendored paths, byte lengths, SHA-256 digests, offline resolution rules, resource accounting, release-checksum inclusion, and network-disabled vectors.
- **Producer and serialization determinism:** signed subject/input/profile arrays preserve validated CLI occurrence order rather than gaining an unstated protocol sort, while the fixed demo command order preserves deterministic bytes. A supplementary-plane fixture distinguishes Unicode-code-point fixture ordering from RFC 8785 UTF-16 ordering.
- **Hosted-release truthfulness:** mandatory documentation paths use no trailing slash, the inclusion list is “at minimum,” the core checksum no longer creates a Git-commit fixed point, and mutable adjacent `schema/core-release.json` is CI parity evidence whose authenticity requires an independent website or repository pin.

### Round 24 rejected or phase-gated findings

- **Sol's claim that Fable failed before a model session:** rejected as controller-state speculation. The paired controller captured Fable's complete Round 24 output before Sol's complete output; both exact routes count.
- **Treat the absent Phase 0 implementation artifacts as evidence that the project specification cannot authorize Phase 0:** phase-gated, not ignored. The registry files, schemas, diagnostic map, coverage matrix, vectors, tooling, fixtures, hosted probes, and runnable demo remain hard gates before Phase 1, release, or interoperability claims.

### Round 25 accepted findings and revisions

Round 25 reviewed exact input SHA-256 `64f7b9dbb57c306bc7ac779a0ac9ef98900e77de6e08378ca07146aa10d72940` (2,609 lines) through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fresh exact-model smoke tests passed immediately before launch, and the paired controller returned both complete outputs against the same frozen input. Fable found one release blocker and four material risks; Sol independently found the shared blocker plus five additional written-contract blockers and adopter risks. Round 25 did not converge.

- **Report and signature population:** `unindexedEnvelopes[].diagnosticCode` now covers its exact Step 2/3/11 population; malformed transport envelopes have empty signature-detail arrays while still charging enumerable entries to defensive totals; and dataset-entry mapping digest disagreement is present in Appendix C.
- **Deterministic evaluator bounds:** the trust-policy wire contract now has required `maxSchemaOperations`, a one-billion bootstrap ceiling, exact abstract operation units, canonical counting order, standalone-tool behavior, and boundary vectors. Core schemas may not reintroduce host-dependent standard regex.
- **Worker and NDJSON closure:** dataset IPC carries parse/schema/semantic phase and maps each phase to the required Step 8 state; killed workers deterministically consume their complete reserved token capacity; finite NDJSON stops on the first non-pass physical line; and one-result IPC remains sufficient.
- **Local versus aggregate exhaustion:** optional warnings apply only to per-profile local limits. Invocation-wide exhaustion always emits global `E_RESOURCE_LIMIT`, fails the owner, skips later work, and denies regardless of the current profile's criticality.
- **Anchor and policy selector precision:** Step 11's independently decidable conditions and fail-before-skip fold are enumerated; the unauthorized-signer fixture pins completeness failure; digest-bearing rule constraints must full-match before candidate selection; diagnostic contexts must embed multiplicity keys exactly.
- **Producer and adopter closure:** repeated-role/self-join inputs are legal through local-name-inclusive identity; one external-profile flag applies to all identical occurrences; invalid/non-NFC attestation filenames and duplicate singleton CLI flags are rejected; the PAE zero-length spelling, checksum tooling version, and decision enumeration are explicit.
- **Registry provenance:** the eight table byte identities are authoritative for v0.2, and Phase 0 must retain independent retrieval evidence rather than circularly comparing only vendored files with the same table.

### Round 25 rejected or phase-gated findings

- **Sol's closing claim that Fable's smoke test failed with `ENOTFOUND`:** rejected as false controller-state speculation. The current-turn smoke test printed `claude-fable-5: verified`, and the paired controller returned Fable's complete Round 25 critique before Sol's output. Both approved routes count.
- **Treat native Ed25519 feasibility, profile-heavy latency, worker-memory enforcement, or absent Phase 0 artifacts as already-proven:** rejected as a completion claim, not ignored as risk. They remain explicit Phase 0 evidence gates and keep dates/estimates provisional.

### Round 26 accepted findings and revisions

Round 26 reviewed exact input SHA-256 `ff9e10430f3ba30f6c6312a026da9635249c931e7fcfde52aa34b4dcdfc423da` (2,654 lines) through Claude CLI `claude-fable-5` at high effort and Codex CLI `gpt-5.6-sol` at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fresh exact-model smoke tests passed immediately before launch, and the paired controller returned both complete outputs against the same frozen input. Fable found no release-blocking written defect and five material clarifications; Sol found six written-contract blockers, concentrated in trusted meta-schema semantics and deterministic evaluator/resource accounting. Round 26 did not converge.

- **Schema-resource identity and dialect closure:** schema resource IDs are fragmentless, with trailing `#` and nonempty fragments forbidden; trusted pinned meta-schemas have canonical `$dynamicRef`/`$dynamicAnchor` behavior; and the profile-dialect schema is explicitly charged to both schema byte and resource budgets.
- **Deterministic evaluator accounting:** `maxSchemaOperations` now covers exhaustive keyword processing, type-inapplicable keyword dispatch, complete ordering for `enum`, `uniqueItems`, `required`, and dependencies, normative NFA state numbering, no early stop after pattern match, and required Phase 0 per-keyword operation traces. The compiled-NFA ceiling is classified as a per-profile local limit.
- **Graph and dataset continuation:** the impossible transformation-root suppression case is removed; the wire-realizable fixture requires both Step 10 `E_ROOT_INVALID` and independent Step 11 `E_MANIFEST_SET`. Step 8's media-hint candidate is the signed handoff manifest's `artifacts[].mediaType`, never unsigned bundle-index metadata.
- **Duplicate and signature accounting:** consumer-versus-consumer duplicate bindings are invalid configuration exit 2, while bundle-internal and bundle-versus-consumer duplicates remain Step 2 evidence failures. Signature enumeration follows charge-on-completion parsing, and the canonical signature sort identity distinguishes digest-backed from path-backed entries.
- **Report and policy closure:** every summary counter is a stable comparison surface; `unindexedEnvelopes[].diagnosticCode` has exact null cases; label-only authorization constraints select every same-`(id,target)` signed reference regardless of digest and attribute all matches; manifest-derived `actualNonce` follows the same availability rule as other handoff scalars; and report output is wholly RFC 8785 JCS plus LF.
- **Release, CLI, and demo precision:** Unicode 15.0 runtime inputs join the checksummed release inventory; implicit evaluation time truncates to whole UTC seconds; arbitrary valid PEM input wrapping is distinguished from the fixed generator form; dataset-entry `sizeStatus`, Appendix A ordering, `patternProperties` scope, deterministic demo-report serialization, and the local default-temp-parent availability threat are explicit.

### Round 26 rejected or phase-gated findings

- **Sol's closing speculation that the Fable route failed:** rejected as controller-state speculation. The paired controller returned Fable's complete Round 26 critique, and fresh exact-model smoke tests passed for both approved routes.
- **Treat Phase 0 artifacts and feasibility measurements as already complete:** rejected as a completion claim, not as a risk. The operation traces, schemas, release inventory, diagnostic map, coverage matrix, vectors, strict-Ed25519 proof, worker containment evidence, benchmarks, hosted probes, and runnable demo remain hard Phase 0 gates.

### Round 27 accepted findings and revisions

Round 27 reviewed exact input SHA-256 `11fddbfab4aa654d172f16b395ab73e9c18c037b1bd59d75fb2c8f6706269f15` (2,700 lines) through Claude CLI `claude-fable-5` 2.1.239 at high effort and Codex CLI `gpt-5.6-sol` 0.149.0 at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fresh exact-model smoke tests passed immediately before launch, and the paired controller returned both complete outputs against the same frozen input. Fable found no release-blocking mission/prose defect but identified four material risks, including one concrete Step 8 charging inconsistency. Sol found eight concrete written-contract blockers, one explicit Phase 0 release gate, and four material risks. Round 27 did not converge.

- **Trusted meta-schema correctness:** `$dynamicRef` now uses Draft 2020-12 outermost-wins dynamic scope. The only two standard `pattern` values present in the trusted release inventory have exact direct predicates, operation charges, invariant behavior, and vectors; host regex is not used. Vendored standard/Unicode bytes require an independent reviewer fetch separate from the person who vendors or computes the table.
- **Deterministic schema-operation oracle:** conditional dispatch has explicit precedence without contradicting UTF-8 sibling order; unused `$defs` is load-only; object-name deep equality is charged; original number-token decomposition and five boundary spellings are exact; and every new path is required in counter traces.
- **Profile-unit and worker accounting:** Step 8 reserves the same fused closure/instance unit before resolution in consistent and conflict branches. Ordinary-worker IPC adds bounded `evaluationsConsumed`, a parent-reserved quota, deterministic unused-reservation release, and full-reservation charging after an operational kill, making multi-line NDJSON enforceable without an incremental channel.
- **Preflight and limit closure:** implicit `evaluationTime` has one exact capture point after structural policy validation and before semantic/accounting work. Evidence-work aggregates have phase-total record states, while diagnostic/report limits are Step 14 admission-only. Artifact copying uses one-byte logical accounting independent of physical read-buffer size.
- **Graph, envelope, and handoff totals:** graph edges have one canonical identity/order and within-edge check order; malformed envelopes are outside the Step 5 population with total mixed/empty aggregate statuses; missing `bundle.json.manifest` preempts other object validation with one code; and non-listed consumer historical bindings are deterministically rejected even after an unauthorized but core-valid handoff establishes the signed selection set.
- **Adopter and evidence hardening:** expected digests/heads/artifacts are selection or rollback anchors rather than temporal freshness absent an anti-rollback channel; diagnostic context is bounded but potentially sensitive; Phase 0 mechanically extracts every prose fixture/vector obligation into the coverage matrix; and the platform verifier byte-source interface receives an explicit instrumented test surface.

### Round 27 rejected or phase-gated findings

- **Treat missing Phase 0 artifacts as a defect in the project specification that authorizes Phase 0:** phase-gated, not ignored. Their absence blocks implementation freeze, Phase 1, conformance, interoperability, and release exactly as Sections 1 and 25 state; it does not prevent approval of the specification whose Phase 0 work is to create and cross-check them.
- **Sol's closing claim that the Fable route timed out:** rejected as false controller-state speculation. The paired controller returned Fable's complete Round 27 critique first, including its verdict, exact section checks, material findings, advisories, questions, and conclusion. Both approved exact-model routes count.
- **Treat host-sensitive performance/worker behavior as proven:** rejected as a completion claim, not as a material risk. The named two-platform Phase 0 spikes and revision-before-Phase-1 rule remain mandatory.

### Round 28 accepted findings and revisions

Round 28 reviewed exact input SHA-256 `cb8cd0fb7764821cc469a2c7fb700be4d7456cf0831fe1ec1a9d84026679fac8` (2,728 lines) through Claude CLI `claude-fable-5` 2.1.239 at high effort and Codex CLI `gpt-5.6-sol` 0.149.0 at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fresh exact-model smoke tests passed immediately before launch, and the paired controller returned both complete outputs against the same frozen input. Fable found no release blocker and three material risks; Sol found eight written-contract blockers and five material risks. Round 28 did not converge.

- **Dataset/profile phase ownership:** no-conflict Step 8 charges only the mandatory dataset profile; conflicting profiles are evaluated/cached once at Step 8; other profiles are exclusively Step 13 work. Unauthorized handoffs quarantine bundle dataset mappings and manifest media hints while permitting only exact independently supplied consumer material for authorized listed statements.
- **Worker and token accounting:** NDJSON fail-fast charge is the number of units consumed through the first outcome, not total file lines; every worker receives the exact complete remaining profile-evaluation quota; structured-artifact tokens are charged per artifact/profile parse attempt, avoiding any shared-tree or double-charge ambiguity.
- **Time and schema budgets:** explicit fractional evaluation times preserve their exact instant while implicit time is whole-second; the dataset direct-root exemption excludes the unused Makoto profile dialect and charges its actual generic dialect/meta resources.
- **NFA and dataset-entry totals:** pattern execution includes positions zero through end, including empty input and end-position unanchored injection; the dataset-entry matrix now covers current resource exhaustion, later aggregate skip, and final-rescan failure without erasing completed fields.
- **Report/adopter precision:** manifest authorized-signature counters explicitly reference the policy handoff rule; mixed freshness methods make unused methods `not_checked`; Step 11-ineligible artifact record prerequisites are exact; all failure strata receive summary vectors; dataset media type is prose-fixed rather than a catalog field; source URIs are nonempty when present; and generated report numbers are outside consumer input-number limits.
- **Filesystem and terminology:** portable physical identity has minimum POSIX/macOS and Windows tuples with exit-3 behavior when unavailable; guarantee wording names manifest heads; and nonce wording consistently says consumer-generated.

### Round 28 rejected or phase-gated findings

- **Sol's closing claim that Fable failed with `ENOTFOUND`:** rejected as false controller-state speculation. The paired controller returned Fable's complete Round 28 review, including its no-blocker verdict, exact audits, three material risks, advisories, questions, and conclusion. Both approved exact-model routes count.
- **Normative constants and feasibility are unverified until Phase 0:** phase-gated, not dismissed. Independent standard/Unicode retrieval, strict cryptography, worker containment, byte-source behavior, performance, schemas, oracles, and vectors remain hard gates before freeze, Phase 1, conformance, or release.
- **Require a new stable warning code for every digestless label selector:** deferred as an adopter-policy design change. The selector semantics and all-match attribution are explicit; Phase 0 policy documentation must emphasize that label-only selectors are not digest restrictions without expanding the closed v0.2 warning enum during prose reconciliation.

### Round 29 accepted findings and revisions

Round 29 reviewed exact input SHA-256 `ae5b15e1a9392d5390655232aaaa30001fa4e2b23f03079eac3facd738a361b2` (2,758 lines) through Claude CLI `claude-fable-5` 2.1.239 at high effort and Codex CLI `gpt-5.6-sol` 0.149.0 at `xhigh`, using the pressed whole-document verifier-implementer/interoperability lens. Fresh exact-model smoke tests passed immediately before launch, and the paired controller returned both complete outputs against the same frozen input. Fable found no release blocker and four material risks; Sol identified three written-contract blockers plus the acknowledged Phase 0 release gate. Round 29 did not converge.

- **Schema-operation closure:** every supported keyword now has a default inner-operation rule for scalar/cardinality reads, membership lookups, collection examinations, and annotation/evaluated-set propagation, with specific overrides and a complete per-keyword oracle gate.
- **Step 8 single-owner accounting:** precharge is a temporary parent reservation; worker `evaluationsConsumed` is the sole permanent commit. Full and resolution-only request modes close media-conflict behavior without artifact parsing or double charge.
- **Deterministic overlap witnesses:** profile constraints use one sorted injective matching algorithm with exact preferred matches, unused-member strictness, and mixed digestless/pinned vectors.
- **NDJSON line bounds:** every physical segment, including whitespace-only lines, is checked against `maxNdjsonLineBytes` before blank classification, with CRLF boundary fixtures.

### Round 29 rejected or phase-gated findings

- **Treat absent Phase 0 artifacts as a defect in the specification authorizing Phase 0:** phase-gated. Their absence remains a hard blocker to implementation freeze, Phase 1, interoperability, conformance, and release, not to approval of this project plan.
- **Sol's claim that neither exact reviewer produced a valid review:** rejected as false controller-state speculation. The paired controller returned Fable's complete Round 29 no-blocker review and Sol's complete Round 29 critique against the same frozen SHA.
- **Move historical Appendix B out of the protocol document:** rejected as preference under the locked retention decision; it remains explicitly non-normative and current numbered sections prevail.

### Current convergence status

Round 29 did not establish two-model agreement on the written project specification, and the accepted findings above materially changed the whole document. A pressed full-document Round 30 by exact `claude-fable-5` at high effort and `gpt-5.6-sol` at `xhigh` is required before claiming no remaining written project-specification blocker. Even reviewer agreement cannot establish wire-protocol convergence; schemas, `diagnostic-map.json`, the coverage matrix, conformance vectors, tooling, fixtures, hosted URLs, and the runnable demo remain Phase 0–4 evidence gates.

## Appendix C — Stable diagnostic trigger map

The table fixes each stable diagnostic's algorithm position and primary trigger. `testdata/v0.2/diagnostic-map.json` expands every row into exact context members and prerequisite/continuation edges. When one code has multiple allowed steps, the emitted diagnostic carries the step at which that concrete condition was evaluated. `E_RESOURCE_LIMIT` always uses the earliest step whose next bounded read, allocation, snapshot write, or worker evaluation would exceed a limit.

The consuming-open trigger is part of the `E_BUNDLE_UNSAFE_PATH` row at each listed step: Step 2 owns a manifest/attestation target recorded present at Step 1 that later cannot be safely opened; Step 4 owns the analogous catalog/resource target; Step 8 owns the analogous dataset-manifest target; and Step 12 owns the analogous final, historical, or dataset-entry target plus the stable rescan. The role-specific absence rows apply only when the target was absent from the completed Step 1 inventory. Phase 0 `diagnostic-map.json` MUST encode those four separate trigger IDs and owners rather than collapsing them into an OS-error-dependent rule.

Every expanded diagnostic-map row keyed by `(code, step, triggerId)` MUST name exactly one owning top-level check, and every emitted diagnostic MUST set `causedByCheck` to that row's owner. Multiple trigger rows MAY share one `(code, step)` pair when their trigger classes require different owners; `triggerId` is a stable unique ASCII identifier in `diagnostic-map.json`, not a report field. Ownership is: Step 0 `authorization-thresholds` for the preflight overlap warning as a reporting owner only; Step 1 `load-safely`; Step 2 `core-schemas` only for `E_CORE_SCHEMA` and otherwise `parse-strictly`; Step 3 `index-payloads`; Step 4 `core-schemas`; Step 5 `signatures`; Step 6 `authorization-thresholds`; Step 7 `metadata-profiles` for globally required or producer-critical profile resolution/validation/resource diagnostics and for every evaluated-invalid profile including a candidate-only one, but `authorization` for a candidate-only resolution/resource diagnostic emitted because no candidate ultimately authorizes; Step 8 `graph-dependency-artifacts`; Step 9 `graph`; Step 10 `roots-and-heads`; Step 11 `completeness-anchor` for `E_MANIFEST_SET` and `E_REQUIRED_PROFILE_MISSING`, and `freshness-anchors` for every expected-value, recipient, nonce, age, or freshness diagnostic; Step 12 `artifact-bytes`; Step 13 `artifact-profiles`; and Step 14 `decision`. Candidate-only ownership is chosen from the concrete trigger row, so one emission never has both Step 7 owners; `metadata-profiles` may also fail from aggregation without owning a duplicate diagnostic. A multi-step `E_RESOURCE_LIMIT` or warning inherits the owner of the bounded operation at its concrete trigger row. Every Phase 0 trigger row MUST also define a deterministic `multiplicityKey` composed only from stable report-context fields: one diagnostic is emitted per distinct multiplicity key, repeated discovery of the same key is deduplicated, and distinct keys are not collapsed merely because code and step match. The map MUST define edge identity for edge failures, statement digest for statement failures, profile identity for profile failures, artifact/dataset logical identity for material failures, and one canonical SCC identity—the ascending member-digest array—for each graph-cycle diagnostic. Phase 0 MUST reject any row with no exact multiplicity key, any `(code, step, triggerId)` row with zero or multiple owners, or any duplicate `triggerId`, so diagnostic counts, `checks[]`, `prerequisiteChecks`, and `causedByCheck` cannot diverge.

Every component of a trigger row's `multiplicityKey` MUST be an always-present member of that row's closed diagnostic `context` schema with the identical value and type. Therefore discovery-time multiplicity dedup and Step 14 complete-sort-tuple dedup coincide for same-row candidates; two distinct multiplicity keys cannot collapse into one `(step, code, causedByCheck, JCS context)` tuple. Phase 0 mechanically verifies this embedding for every row and rejects a diagnostic map whose context omits or transforms a key component.

| Code | Step | Exact trigger |
|---|---:|---|
| `E_BUNDLE_UNSAFE_PATH` | 1, 2, 4, 8, 12 | An on-disk bundle entry fails during the Step 1 scan; any consumer policy/catalog/expected/binding/material handle is contained in or aliases the established bundle inventory at Step 1; a parsed bundle-index logical path fails at Step 2; a parsed bundle-catalog resource path fails at Step 4; a dataset-manifest source fails safe opening/snapshot at Step 8; or a later artifact open/final stable rescan detects an observable path/type/physical-identity change at Step 12. This code exclusively owns logical grammar, permission denial, wrong entry type, link/alias, normalization collision, failed descriptor/stat operation, containment, observable replacement race, and tree-stability failures. Same-identity mutation after snapshot is outside the rescan claim and cannot alter evaluated snapshot bytes. Absence instead uses the role-specific handoff, catalog, manifest-set, or artifact-missing code. |
| `E_RESOURCE_LIMIT` | 1–14 | A required bootstrap, consumer, snapshot, numeric, signature/profile-operation, report-record, diagnostic, serialized-report, schema, worker, or evaluation bound is exceeded. A candidate-only profile limit emits this error only when no alternative candidate authorizes. |
| `E_HANDOFF_REQUIRED` | 1, 2 | In an existing bundle directory, `bundle.json` is absent (Step 1), or its parsed object lacks the `manifest` member or the safe referenced manifest envelope is physically absent (Step 2). A present wrong-typed member is `E_CORE_SCHEMA`; an unsafe path is `E_BUNDLE_UNSAFE_PATH`; a nonexistent bundle-directory argument exits 2 before evidence evaluation. |
| `E_JSON_INVALID` | 2, 3, 4 | Transport/index JSON fails at Step 2, a decoded DSSE payload fails at Step 3, or a bundle catalog/declared schema resource fails at Step 4, due to ordinary syntax, invalid UTF-8, a byte-order mark, invalid Unicode scalar, or nonstandard token; duplicate keys use `E_JSON_DUPLICATE_KEY`. |
| `E_JSON_DUPLICATE_KEY` | 2, 3, 4 | Strict parsing finds a duplicate object key in transport/index JSON (Step 2), a decoded payload (Step 3), or a bundle catalog/declared schema resource (Step 4). |
| `E_ENVELOPE_MALFORMED` | 2 | A DSSE `payloadType` string fails the exact Section 10.1 lexical grammar, or any envelope/signature-entry shape fails after strict JSON: missing/extra members, wrong member types, empty `signatures`, malformed key ID/base64/decoded length, or duplicate key ID. Strict-JSON/duplicate-key failures retain their JSON codes; a lexically valid but unsupported payload type uses `E_PAYLOAD_TYPE`. |
| `E_PAYLOAD_TYPE` | 2 | A DSSE `payloadType` passes the exact Section 10.1 lexical grammar but is not the exact statement or handoff value allowed at that index location. |
| `E_STATEMENT_DIGEST` | 3 | An indexed statement digest/path declaration differs from SHA-256 of decoded payload bytes. |
| `E_MANIFEST_SET` | 11 | A manifest statement/artifact lacks its required complete index tuple; a manifest-listed attestation target is physically absent; a bundle mapping/statement or consumer artifact-material identity lies outside the signed manifest statement/subject set; root/head presence, exact artifact-to-head name-plus-digest subject match, subject terminality, or head derivation fails; or computed statement/root/head/artifact sets differ. A manifest artifact or consumer binding with no exact signed subject match is skipped before hashing and emits no secondary artifact-digest code. A valid artifact tuple whose byte target is physically absent uses `E_ARTIFACT_MISSING` at Step 12; a present unsafe target uses `E_BUNDLE_UNSAFE_PATH`; present wrong bytes use the applicable digest code. |
| `E_CORE_SCHEMA` | 2, 4 | `bundle.json` or another non-envelope transport object fails schema or the complete bundle semantic ordering/identity/tuple pass after strict parsing (Step 2), including duplicate bundle/consumer artifact or dataset-entry logical identities compared during that Step 2 semantic pass; or a decoded core evidence object fails its immutable schema or semantic closure (Step 4). Unsafe logical paths and physical aliases are expressly excluded and use `E_BUNDLE_UNSAFE_PATH` at Step 1 or the consuming step. Envelope shape is exclusively `E_ENVELOPE_MALFORMED`; missing/unsafe manifest paths retain their specific Step 2 codes. |
| `E_CATALOG_INVALID` | 4 | A declared safe bundle catalog or declared catalog resource is absent, or a safely opened bundle catalog has invalid structural schema/tuple/ID, shadows core, or its declared resource bytes do not match its entry. Unsafe logical paths, containment, links, entry types, aliases, and normalization collisions use `E_BUNDLE_UNSAFE_PATH`; consumer-catalog analogues exit 2 during preflight. |
| `E_PREDICATE_SEMANTICS_UNSUPPORTED` | 4 | A manifest-listed statement uses any non-core predicate type; v0.2 bundle decisions cannot install alternate graph semantics. |
| `E_PROFILE_TARGET_MISSING` | 4 | A signed artifact-profile reference on an otherwise core-valid statement identifies zero statement subjects. Duplicate subjects fail core validation before this semantic check. Structurally missing target members are `E_CORE_SCHEMA`. |
| `E_SIGNATURE_INVALID` | 5 | A configured-key evidence signature fails strict Ed25519 point encoding/decoding, subgroup, scalar, or equation verification after its transport fields, base64, key ID, and decoded length already passed Step 2; those transport failures remain `E_ENVELOPE_MALFORMED`. |
| `E_SIGNER_UNAUTHORIZED` | 6 | The selected-rule set is empty, valid distinct signatures do not satisfy any selected statement-rule threshold, or the handoff threshold fails. Candidate rules that later fail digest-pinned profile validation use the underlying Step 7 profile error, not this code. |
| `E_PROFILE_UNRESOLVED` | 7, 8, 13 | A globally required profile/dialect/resource closure is absent, unsupported, or forbidden, including an unknown keyword or the known-but-prohibited profile keywords listed in Section 12.1; Step 8 includes the mandatory core dataset-manifest profile. A candidate-only unresolved constraint emits this error only when no alternative candidate authorizes; a losing candidate's suppressed failure remains record-local. |
| `E_PROFILE_INVALID` | 7, 8, 13 | At Step 7, a resolved statement or predicate instance violates its signed schema. At Step 13, a parsed ordinary artifact violates its signed schema, two signed artifact profiles on one ordinary subject declare different canonical media types, or an ordinary final manifest media hint differs from a signed profile media type. At Step 8, the corresponding media-type conflicts for a dataset-manifest subject are detected before parsing. Schema-invalid dataset-manifest bytes use only `E_DATASET_MANIFEST_INVALID`. Schema violations emit once per profile identity; a profile-to-profile media disagreement emits once per conflicting signed profile identity; a manifest-hint disagreement emits once per signed profile identity that conflicts with the hint. Each row in `diagnostic-map.json` fixes that profile identity as the multiplicity key and the continuation/cache behavior. |
| `E_REQUIRED_PROFILE_MISSING` | 11, 13 | A manifest requirement lacks its exact signed head reference (Step 11), or a consumer final-artifact selector matches zero artifacts or a matching head lacks its exact signed reference (Step 13). |
| `E_DATASET_MANIFEST_INVALID` | 8, 12 | Dataset-manifest JSON/core schema/profile identity or mapping target is invalid (Step 8); or a supplied standalone partition mapping names no unique existing member, or its mapping-declared digest disagrees with the uniquely validated member digest (Step 12). The Step 12 digest-disagreement target is not opened or hashed. Manifest artifact digest mismatch uses `E_ARTIFACT_DIGEST`; graph-edge missing membership uses `E_PREDECESSOR_SUBJECT`; partition byte-size mismatch uses `E_ARTIFACT_SIZE`. |
| `E_DATASET_MANIFEST_REQUIRED` | 8 | An `entryName` edge or supplied dataset-entry mapping lacks required dataset-manifest bytes; this Step 8 role takes precedence when the same manifest is also a final artifact, so no Step 12 `E_ARTIFACT_MISSING` is added. |
| `E_EVENT_ID_DUPLICATE` | 9 | Two reachable statements carry the same exact `event.id`. |
| `E_PREDECESSOR_MISSING` | 9 | A transformation names a predecessor unavailable in the usable manifest graph-node index, including an absent, outside-set, strict-parse-invalid, core-invalid, or unauthorized statement. |
| `E_PREDECESSOR_SUBJECT` | 9 | The core-valid predecessor node exists but does not contain the exact named subject/entry. |
| `E_INPUT_DIGEST` | 9 | A direct or entry-based predecessor artifact digest differs from the transformation input digest. |
| `E_GRAPH_CYCLE` | 9 | Graph traversal finds a self-cycle or multi-node cycle. |
| `E_ROOT_INVALID` | 10 | A reachable zero-predecessor statement or manifest-declared root is not a core origin, or a manifest-declared root has a predecessor. A core-valid transformation always has a predecessor, so declaring it as a root also produces the independent Step 11 `E_MANIFEST_SET` root-set mismatch; both diagnostics are expected. |
| `E_FRESHNESS_REQUIRED` | 11 | No specific `requireExpected*`/nonce/age rule already supplies a more specific error, no approved freshness method is present, and replayable handoff is not allowed. |
| `E_EXPECTED_MANIFEST` | 11 | A supplied/required expected manifest digest is absent or differs from actual. |
| `E_EXPECTED_HEAD` | 11 | A supplied/required complete expected-head set is absent or differs from actual. |
| `E_EXPECTED_ARTIFACT` | 11 | A supplied/required complete expected-artifact set is absent or differs from actual. |
| `E_HANDOFF_RECIPIENT` | 11 | A policy-required expected recipient is absent, or any supplied expected recipient differs from the signed recipient; a supplied string compared with an omitted signed field differs. |
| `E_HANDOFF_NONCE` | 11 | A policy-required expected nonce is absent, or any supplied expected nonce differs from the signed nonce; a supplied string compared with an omitted signed field differs. |
| `E_HANDOFF_STALE` | 11 | `issuedAt` is older than maximum age or farther in the future than allowed skew. |
| `E_ARTIFACT_MISSING` | 12 | A valid bundle final/historical/dataset-entry mapping names a physically absent byte target, or required historical material has no bundle or consumer source. A missing final-artifact mapping is Step 11 `E_MANIFEST_SET` and cannot be supplied by consumer `artifact-material`. A consumer binding whose path is absent at invocation is invalid configuration exit 2; it does not emit this report code. A present target that cannot be safely opened, typed, statted, or stably snapshotted uses `E_BUNDLE_UNSAFE_PATH`. |
| `E_ARTIFACT_DIGEST` | 8, 12 | A Step 8 graph-dependency dataset manifest, or Step 12 final/historical/partition artifact, differs from its bound SHA-256. |
| `E_ARTIFACT_SIZE` | 12 | A supplied partition's exact byte count differs from its optional manifest size. |
| `E_ARTIFACT_FORMAT` | 13 | Artifact bytes fail their signed supported-media parser, regardless of producer criticality, or a required profile uses unsupported media. Malformed supported JSON/NDJSON is a false signed validation target and denies even for an otherwise optional noncritical profile. |

| Warning | Step | Exact trigger |
|---|---:|---|
| `W_POLICY_RULE_OVERLAP` | 0 | A valid less-constrained alternative authorization rule subsumes a more-constrained rule. |
| `W_SIGNATURE_UNKNOWN` | 5 | A structurally valid signature names no configured key; it is not cryptographically evaluated or counted toward authorization. |
| `W_PROFILE_INDETERMINATE` | 7, 8, 13 | An optional noncritical profile is unresolved or unsupported; Step 8 is used when dataset-subject media conflict requires early resolution of an optional artifact profile. |
| `W_PROFILE_RESOURCE_LIMIT` | 7 | An optional noncritical statement/predicate profile exceeds a bound. |
| `W_ARTIFACT_VALIDATION_LIMIT` | 8, 13 | An optional noncritical artifact profile exceeds a bound; Step 8 is used when dataset-subject media conflict requires early bounded resolution. |
| `W_HISTORICAL_ARTIFACT_NOT_CHECKED` | 12 | Optional historical artifact bytes are absent; emit exactly once per absent artifact identity, not once per targeting profile. |
| `W_FRESHNESS_NOT_CHECKED` | 11 | Policy explicitly accepts a replayable handoff and no freshness method runs. |
| `W_ARTIFACT_UNPROFILED` | 13 | A final artifact has zero applicable artifact profiles. |
