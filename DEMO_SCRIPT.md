# Makoto Demo Script: 20-Minute Decision-Maker Meeting

**Audience:** Champions selling to implementers + decision makers
**Setup:** Terminal open, repo cloned, font size 18+

---

## Opening (2 min)

> **Say:** "Let me show you what happens to data pipelines without provenance — and how a single JSON sidecar fixes it."

> **Point:** Open the root README briefly to show the 5-demo table.

> **Say:** "Each of these is a real scenario. I'll walk through three that match your situation, but they all run in under 3 minutes if you want to try them yourself."

---

## Demo 05: AI Dataset Verification (4 min) — Start here, strongest hook

> **Say:** "Let's start with the scariest one. Your ML team downloads a training dataset. Is it the real thing?"

```bash
cd demos/05-ai-dataset-verification
python3 demo.py
```

**Stage directions:**
- Part 1 prints: pause on "No way to know. Training proceeds on blind trust."
- Part 2 prints: point at the ✅ hash match and signer line
- Part 3 prints: **this is the money shot** — point at ❌ HASH MISMATCH

> **Say:** "One label changed. One byte. Caught instantly. Without this, your model silently learns wrong."

> **Pause for reaction.** Let them absorb.

---

## Demo 01: Poisoned Pipeline (4 min)

> **Say:** "Same idea, but for operational data. Sensor readings coming from a partner — what if they're corrupted?"

```bash
cd ../01-poisoned-pipeline
./run.sh
```

**Stage directions:**
- Part 1: point at the SQL injection payload and NaN values flowing through
- Part 2: point at "REJECTED: No DBOM file found" — that's the gate
- Then point at the successful verification flow

> **Say:** "The gate is three things: does a DBOM exist, does the hash match, who signed it. That's it."

---

## Demo 04: Config Postmortem (4 min)

> **Say:** "This one is for the ops folks. Someone changes a config at 3am. Monday morning, throughput drops 95%."

```bash
cd ../04-config-postmortem
python3 demo.py
```

**Stage directions:**
- Part 1: point at "No record of who changed it or why"
- Part 2: point at the instant trace — all five ✅ lines

> **Say:** "Two minutes to resolution instead of two hours. And it's the same DBOM schema — source, signature, lineage."

---

## The Schema (2 min)

> **Open** `dbom_schema.json` or show the format from the root README.

> **Say:** "Three sections. Source: where is the data and what's its hash. Signature: who vouches for it. Lineage: how was it produced. That's the entire spec."

> **Point:** "It's a JSON sidecar. It travels with the data. No database, no service, no vendor lock-in."

---

## GitHub Action (2 min)

> **Say:** "Integration is a 5-line workflow file."

> **Open** `demos/03-github-action/example-workflow.yml`

> **Point:** at the `uses: makoto-project/makoto/demos/03-github-action@main` line

> **Say:** "Every push that touches a data file generates a DBOM automatically. Zero manual work."

> **Optional:** Run locally to show it working:

```bash
cd ../03-github-action
python3 generate_dbom.py ../01-poisoned-pipeline/data/sensors_clean.csv
cat sensors_clean.csv.dbom.json
```

---

## Close (2 min)

> **Say:** "Three things to remember:"
>
> 1. "A DBOM is a JSON sidecar — source, signature, lineage"
> 2. "It catches tampering, traces changes, and proves provenance"
> 3. "It integrates in minutes — one GitHub Action, no new infrastructure"

> **Say:** "All five demos are in the repo. Each runs with one command. Try them, share them with your team."

> **Ask:** "Which of these scenarios is closest to what you're dealing with right now?"

---

## Objection Handling

**"We already have data versioning (DVC/LakeFS)"**
> "Great — DBOM complements those. DVC tracks *which* version. DBOM tracks *how it was produced* and *who vouches for it*. They're the 'what' and the 'why'."

**"This is just checksums"**
> "Checksums verify integrity. DBOM adds identity (who signed) and lineage (how it got here). A checksum tells you the file hasn't changed. DBOM tells you it *should* be trusted."

**"How does this scale?"**
> "It's a JSON file. No service, no database, no runtime dependency. It scales the same way your data scales — it's just a sidecar."

**"What about real cryptographic signing?"**
> "Schema version 0.1 uses hash-based signatures for simplicity. The schema is extensible — v0.2 adds GPG/Sigstore signing. Start simple, add crypto when your compliance team asks for it."
