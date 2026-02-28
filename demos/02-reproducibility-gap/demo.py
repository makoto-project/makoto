#!/usr/bin/env python3
"""Demo 02: The Reproducibility Gap
Shows how missing provenance makes experiments unreproducible,
and how DBOM lineage solves it.
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(SCRIPT_DIR, "datasets")


def part1_no_lineage():
    """Part 1: Researcher has a CSV but no idea where it came from."""
    print("━━━ PART 1: Without DBOM — The Mystery Dataset ━━━")
    print()

    csv_path = os.path.join(DATASET_DIR, "experiment_v2.csv")

    # Read and show the data
    with open(csv_path) as f:
        lines = f.readlines()

    print(f"📄 Found: experiment_v2.csv ({len(lines) - 1} rows)")
    print(f"   Columns: {lines[0].strip()}")
    print()

    # The questions nobody can answer
    print("❓ Questions the reviewer is asking:")
    print("   • Which version of the raw data is this?")
    print("   • Were outliers removed? By what method?")
    print("   • Who prepared this file?")
    print("   • Can I get back to the original instrument readings?")
    print()
    print("❌ No answers. The paper cites 'experiment_v2.csv' — that's it.")
    print("   Reviewer rejects: 'insufficient provenance for reproducibility'")
    print()


def part2_with_lineage():
    """Part 2: Same CSV, but now with a DBOM sidecar."""
    print("━━━ PART 2: With DBOM — Full Lineage ━━━")
    print()

    dbom_path = os.path.join(DATASET_DIR, "experiment_v2.dbom.json")

    with open(dbom_path) as f:
        dbom = json.load(f)

    print(f"📄 Found: experiment_v2.dbom.json")
    print(f"   DBOM ID: {dbom['id']}")
    print(f"   Created: {dbom['created_at']}")
    print()

    # Show source
    src = dbom["source"]
    print(f"📦 Source:")
    print(f"   URI:    {src['uri']}")
    print(f"   Hash:   {src['hash']['value'][:16]}...")
    print(f"   Format: {src['format']}")
    print()

    # Show signature
    sig = dbom["signature"]
    print(f"🔏 Signature:")
    print(f"   Signer: {sig['signer']}")
    print(f"   Algorithm: {sig['algorithm']}")
    print()

    # Show lineage — the key differentiator
    print(f"🔗 Lineage ({len(dbom['lineage'])} steps):")
    for step in dbom["lineage"]:
        print(f"   Step {step['step']}: {step['description']}")
        print(f"           Tool: {step['tool']}")
        print(f"           Input:  {step['input_hash'][:16]}{'...' if len(step['input_hash']) > 16 else ''}")
        print(f"           Output: {step['output_hash'][:16]}...")
        print()

    # Verify the chain is connected
    print("🔍 Chain verification:")
    chain_ok = True
    for i in range(1, len(dbom["lineage"])):
        prev_out = dbom["lineage"][i - 1]["output_hash"]
        curr_in = dbom["lineage"][i]["input_hash"]
        if prev_out == curr_in:
            print(f"   ✅ Step {i} → Step {i+1}: hashes link correctly")
        else:
            print(f"   ❌ Step {i} → Step {i+1}: BROKEN CHAIN")
            chain_ok = False

    # Verify final output matches source hash
    final_hash = dbom["lineage"][-1]["output_hash"]
    source_hash = dbom["source"]["hash"]["value"]
    if final_hash == source_hash:
        print(f"   ✅ Final output matches source hash")
    else:
        print(f"   ❌ Final output does NOT match source hash")
        chain_ok = False

    print()
    if chain_ok:
        print("✅ Full provenance chain verified — every question answered.")
        print("   Reviewer accepts: 'lineage is complete and verifiable'")
    else:
        print("❌ Lineage chain has gaps")
    print()


def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          Demo 02: The Reproducibility Gap                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    part1_no_lineage()
    part2_with_lineage()

    print("━━━ RESULT ━━━")
    print("Without DBOM: 'which version?' is unanswerable 💀")
    print("With DBOM:    full lineage from instrument to analysis ✅")
    print()


if __name__ == "__main__":
    main()
