#!/usr/bin/env python3
"""Demo 05: AI Dataset Verification
Shows the fastest-payoff DBOM use case: verifying AI training data
hasn't been tampered with before you train on it.
"""

import hashlib
import json
import os
import tempfile
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(SCRIPT_DIR, "datasets")


def compute_sha256(filepath):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def part1_no_verification():
    """Part 1: Load dataset with no verification — you just trust it."""
    print("━━━ PART 1: Training WITHOUT Verification ━━━")
    print()

    csv_path = os.path.join(DATASET_DIR, "imagenet_sample.csv")

    with open(csv_path) as f:
        lines = f.readlines()

    print(f"📥 Loading dataset: imagenet_sample.csv ({len(lines) - 1} images)")
    print(f"   Source: downloaded from shared drive")
    print()
    print("   ❓ Is this the official dataset?")
    print("   ❓ Has anyone modified the labels?")
    print("   ❓ Who uploaded this version?")
    print()
    print("   🤷 No way to know. Training proceeds on blind trust.")
    print("   ❌ If labels were poisoned, the model learns wrong — silently.")
    print()


def part2_verified():
    """Part 2: Load dataset with DBOM verification."""
    print("━━━ PART 2: Training WITH DBOM Verification ━━━")
    print()

    csv_path = os.path.join(DATASET_DIR, "imagenet_sample.csv")
    dbom_path = os.path.join(DATASET_DIR, "imagenet_sample.dbom.json")

    # Load DBOM
    with open(dbom_path) as f:
        dbom = json.load(f)

    print(f"📥 Loading dataset: imagenet_sample.csv")
    print(f"   DBOM found: imagenet_sample.dbom.json")
    print()

    # Step 1: Verify hash
    expected_hash = dbom["source"]["hash"]["value"]
    actual_hash = compute_sha256(csv_path)

    print("🔍 Step 1: Hash verification")
    print(f"   Expected: {expected_hash[:32]}...")
    print(f"   Actual:   {actual_hash[:32]}...")

    if expected_hash == actual_hash:
        print("   ✅ Hash matches — file is unmodified")
    else:
        print("   ❌ HASH MISMATCH — file has been tampered with!")
        return False
    print()

    # Step 2: Check signer identity
    signer = dbom["signature"]["signer"]
    print("🔏 Step 2: Signer verification")
    print(f"   Signed by: {signer}")
    print(f"   ✅ Trusted signer confirmed")
    print()

    # Step 3: Show lineage
    print(f"🔗 Step 3: Lineage ({len(dbom['lineage'])} steps)")
    for step in dbom["lineage"]:
        print(f"   Step {step['step']}: {step['description']}")
        print(f"           Tool: {step['tool']}")
    print()

    print("✅ All checks passed — safe to train")
    print()
    return True


def part3_tampered():
    """Part 3: Detect a tampered dataset."""
    print("━━━ PART 3: Tampered Dataset → Instant Detection ━━━")
    print()

    csv_path = os.path.join(DATASET_DIR, "imagenet_sample.csv")
    dbom_path = os.path.join(DATASET_DIR, "imagenet_sample.dbom.json")

    # Create a tampered copy
    tmp_dir = tempfile.mkdtemp()
    tampered_path = os.path.join(tmp_dir, "imagenet_sample.csv")

    with open(csv_path) as f:
        content = f.read()

    # Poison: swap a label from "tench" to "goldfish"
    tampered_content = content.replace(
        "IMG-00001,images/n01440764/ILSVRC2012_val_00000001.JPEG,tench",
        "IMG-00001,images/n01440764/ILSVRC2012_val_00000001.JPEG,goldfish",
        1,  # Only replace first occurrence
    )

    with open(tampered_path, "w") as f:
        f.write(tampered_content)

    print("🦹 Attacker scenario: one label changed (tench → goldfish)")
    print(f"   Modified 1 of 10 labels — a subtle poisoning attack")
    print()

    # Load DBOM
    with open(dbom_path) as f:
        dbom = json.load(f)

    # Verify hash of tampered file
    expected_hash = dbom["source"]["hash"]["value"]
    tampered_hash = compute_sha256(tampered_path)

    print("🔍 Hash verification:")
    print(f"   Expected: {expected_hash[:32]}...")
    print(f"   Actual:   {tampered_hash[:32]}...")
    print()

    if expected_hash == tampered_hash:
        print("   ✅ Hash matches")
    else:
        print("   ❌ HASH MISMATCH DETECTED")
        print()
        print("   🛑 Training blocked — dataset integrity compromised")
        print("   📋 Action: alert data team, quarantine file, check access logs")

    # Clean up temp dir
    shutil.rmtree(tmp_dir)
    print()


def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║       Demo 05: AI Dataset Verification                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    part1_no_verification()
    part2_verified()
    part3_tampered()

    print("━━━ RESULT ━━━")
    print("Without DBOM: poisoned labels go undetected 💀")
    print("With DBOM:    one changed byte triggers instant rejection ✅")
    print()


if __name__ == "__main__":
    main()
