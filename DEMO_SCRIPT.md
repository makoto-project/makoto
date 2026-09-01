# Makoto Demo Script: 20-Minute Decision-Maker Meeting

**Audience:** Champions selling to implementers + decision makers
**Setup:** Terminal open, repo cloned, `uv sync --locked --dev` already run, font size 18+

**Status to state plainly if asked:** the protocol is under public review. It is not a tagged
release, and there is no published package. Everything below runs from this source checkout.

---

## Opening (2 min)

> **Say:** "Data arrives from somewhere. Before you use it, you want three answers: where did it
> start, what happened to it on the way, and who is standing behind those claims. Most stacks
> can't answer any of them once the file has moved twice."

> **Say:** "I'm going to run one command. It builds a producer, signs a history, hands it off, and
> then verifies it as a receiver who trusts none of the producer's systems. It takes three seconds."

---

## The whole thing, once (4 min)

```bash
./scripts/demo-v0.2.sh --acceptance
```

**Stage directions:**

- It creates source data, signs an origin, applies two transformations, signs the handoff.
- Point at `positive: ALLOW (all checks pass)`.
- Then let the seven denials scroll. **This is the money shot** — each one is a distinct attack
  that gets its own diagnostic code, not a generic failure.
- Point at the elapsed line at the bottom. Three seconds, no cloud credentials, no service, no
  Docker.

> **Say:** "Everything after this is just me showing you what those lines mean."

---

## The record itself (3 min)

> **Say:** "Here is the envelope every claim travels in."

```bash
uv run makoto envelope inspect --envelope \
  demos/v0.2-end-to-end/generated/positive-bundle/attestations/56b7be4394fe09c62ec7a3d5763cecc251e9696f267f35b2acc717b0d170a27a.dsse.json
```

> **Point:** at `"payloadType": "application/vnd.in-toto+json"` and the single signing key id.

> **Say:** "That's an in-toto statement in a DSSE envelope — the same signature format your
> security team already verifies for software artifacts. We did not invent a new one."

> **Say:** "Each transformation names its predecessor by digest. You cannot quietly reattach a
> step to a different past, because the link is inside the signed payload."

> **Optional, if they want to see the statement body:** usemakoto.dev shows the origin and the
> transformation that consumes it side by side, with the two linking digests highlighted.

---

## Verify as the receiver (4 min)

> **Say:** "The sender transfers only the bundle. The receiver keeps its own trust policy, its own
> schema catalog, and its own expectation of the final bytes — outside that bundle."

```bash
uv run makoto verify bundle demos/v0.2-end-to-end/generated/positive-bundle \
  --policy demos/v0.2-end-to-end/generated/receiver/policy.json \
  --schema-catalog demos/v0.2-end-to-end/generated/receiver/catalog.json \
  --expected-manifest sha256:b83a5cd1870b8ce1f2931650611f0a19deed0796c0f262e4632efc17981f695c \
  --expected-head sha256:962be71738a0146642d27c87fba3c7338b0f2bb764b113b16867bb4808b11977 \
  --expected-artifact demos/v0.2-end-to-end/generated/receiver/expected-artifact.json \
  --evaluation-time 2026-09-16T16:00:00Z \
  --json
```

> **Point:** at `"decision":"allow"` and the list of separately reported checks.

> **Note for the presenter:** those three `--expected-*` values are the freshness anchor. Drop them
> and this same bundle is denied, which is the point of the next section — do not trim them from
> the command to save screen width.

> **Say:** "Sixteen checks, not one badge. Structure, cryptography, authorization, profiles,
> graph, completeness, freshness, and bytes are all reported separately, because they fail
> separately."

---

## The two distinctions that sell it (3 min)

> **Say:** "Two things get conflated everywhere else, and this is where the value is."

```bash
uv run python -c "import json; d = json.load(open('demos/v0.2-end-to-end/generated/reports/unauthorized-signer.json')); print(d['decision'], d['primaryError'])"
```

> **Say:** "That attacker's signature is cryptographically **valid**. The key is even present in
> the receiver's policy file. It's denied anyway, because no rule authorized that key for that
> claim. **Authenticity is not authorization.** A valid signature from the wrong party is still
> the wrong party."

> **Say:** "The second one: a complete, correctly signed handoff from last quarter can be replayed
> at you today. **Completeness is not freshness.** The receiver pins the manifest, head, and
> artifact it expects — so a stale-but-perfect bundle still fails."

---

## Private rules, no central registry (2 min)

> **Say:** "Your data rules are your business. You should not have to publish them to a standards
> body to enforce them."

> **Point:** the `private-schema-violation` denial from the run above.

> **Say:** "The producer re-signed the bytes cleanly. The receiver's own JSON Schema — resolved by
> URI plus exact digest, never fetched from the producer — rejected it for reintroducing a direct
> identifier. The rule never leaves your organization."

---

## Close (2 min)

> **Say:** "Three things to remember:"
>
> 1. "Evidence travels with the data — origin, every transformation, and who signed each one."
> 2. "The receiver decides. Trust policy, schemas, and expected bytes are all yours, not the
>    sender's."
> 3. "It's a file format and a verifier. No service, no database, no vendor in the data path."

> **Ask:** "Which handoff in your pipeline would you most want to be able to prove?"

---

## What to say when it doesn't apply

Be straight about the boundary. It closes more than it costs.

Makoto does not certify that a source told the truth, prove the claimed code actually ran,
establish data quality, prevent disclosure, grant regulatory compliance, or discover copies nobody
recorded. It makes participating handoffs verifiable and missing evidence visible.

---

## Objection Handling

**"We already have data versioning (DVC/LakeFS)"**
> "Those track *which* version. This tracks *how it was produced* and *who vouches for it*, in a
> form a third party can check without access to your systems. They compose — version the data,
> attest the handoff."

**"This is just checksums"**
> "A checksum proves the bytes didn't change. It can't tell you where they came from, which step
> produced them, or whether whoever signed was allowed to. Run the `unauthorized-signer` case —
> every hash in it is correct and it is still denied."

**"We have a data catalog / lineage tool already"**
> "Those describe lineage inside your platform, from your platform's own logs. This is evidence
> that survives leaving the platform. The test is whether a recipient outside your trust boundary
> can verify it. That is the whole design goal."

**"How does this scale?"**
> "It's files. Statements are small and verification is local — no service in the data path,
> nothing to run at your throughput."

**"What about real cryptographic signing?"**
> "Ed25519 over DSSE, with in-toto statement payloads. Signatures prove key control; a separate
> receiver-owned policy decides whether that key was authorized for that claim. Those are
> deliberately two different questions."

**"Is this production-ready?"**
> "The protocol is under public review and is not a tagged release. What exists today is a
> specification, hosted schemas, a reference implementation, and the conformance run you just
> watched. If you want a say in the wire format, this is the moment to bring us a real handoff."
