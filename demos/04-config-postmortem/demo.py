#!/usr/bin/env python3
"""Demo 04: Config Postmortem
Shows how config changes without audit trails create mystery incidents,
and how DBOM audit entries make them instantly traceable.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "config_demo.db")


def setup_db(conn):
    """Create a simple config table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)
    # Seed with initial config
    conn.execute("""
        INSERT OR REPLACE INTO app_config (key, value, updated_at)
        VALUES ('max_batch_size', '1000', '2025-01-01T00:00:00Z')
    """)
    conn.execute("""
        INSERT OR REPLACE INTO app_config (key, value, updated_at)
        VALUES ('retry_limit', '3', '2025-01-01T00:00:00Z')
    """)
    conn.execute("""
        INSERT OR REPLACE INTO app_config (key, value, updated_at)
        VALUES ('timeout_seconds', '30', '2025-01-01T00:00:00Z')
    """)
    conn.commit()


def part1_no_audit(conn):
    """Part 1: Config change with no trail — mystery outage."""
    print("━━━ PART 1: Config Change WITHOUT DBOM ━━━")
    print()

    # Show current config
    print("📋 Current config:")
    for row in conn.execute("SELECT key, value FROM app_config ORDER BY key"):
        print(f"   {row[0]} = {row[1]}")
    print()

    # Someone changes the config — no trail
    print("🔧 Someone changes max_batch_size: 1000 → 50")
    conn.execute("""
        UPDATE app_config SET value = '50', updated_at = '2025-01-15T03:22:00Z'
        WHERE key = 'max_batch_size'
    """)
    conn.commit()
    print()

    # Monday morning: pipeline is slow
    print("🚨 Monday morning: pipeline throughput dropped 95%!")
    print()
    print("❓ Incident questions:")
    print("   • What changed?")
    print("   • Who changed it?")
    print("   • Why was it changed?")
    print("   • What was the previous value?")
    print()

    # All we can see is current state
    print("🔍 Investigation (all we have):")
    row = conn.execute(
        "SELECT value, updated_at FROM app_config WHERE key = 'max_batch_size'"
    ).fetchone()
    print(f"   max_batch_size = {row[0]} (updated: {row[1]})")
    print(f"   ❌ No record of who changed it or why")
    print(f"   ❌ No record of the previous value")
    print(f"   ❌ Mean time to resolution: hours of git-blame and Slack archaeology")
    print()


def part2_with_audit(conn):
    """Part 2: Same change, but with DBOM audit entry."""
    print("━━━ PART 2: Config Change WITH DBOM Audit ━━━")
    print()

    # Reset config for the demo
    conn.execute("""
        UPDATE app_config SET value = '1000', updated_at = '2025-01-01T00:00:00Z'
        WHERE key = 'max_batch_size'
    """)
    conn.commit()

    # Create DBOM audit table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_dbom (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            config_key TEXT,
            old_value TEXT,
            new_value TEXT,
            reason TEXT,
            signer TEXT,
            hash TEXT
        )
    """)
    conn.commit()

    print("📋 Current config:")
    for row in conn.execute("SELECT key, value FROM app_config ORDER BY key"):
        print(f"   {row[0]} = {row[1]}")
    print()

    # Same change — but now with DBOM audit entry
    old_value = "1000"
    new_value = "50"
    reason = "Reducing batch size to debug memory spike in worker-03"
    signer = "github:aronchick"
    change_time = "2025-01-15T03:22:00Z"

    # Build the DBOM entry for this config change
    import hashlib
    change_str = f"{old_value}→{new_value}|{reason}|{signer}|{change_time}"
    change_hash = hashlib.sha256(change_str.encode()).hexdigest()

    dbom_entry = {
        "schema_version": "0.1",
        "id": f"dbom-{uuid.uuid4()}",
        "created_at": change_time,
        "source": {
            "uri": "config://app/max_batch_size",
            "hash": {"algorithm": "sha256", "value": change_hash},
            "format": "config-change",
        },
        "signature": {
            "algorithm": "sha256",
            "value": change_hash,
            "signer": signer,
        },
        "lineage": [
            {
                "step": 1,
                "description": reason,
                "tool": "config-manager v1.0",
                "input_hash": hashlib.sha256(old_value.encode()).hexdigest(),
                "output_hash": hashlib.sha256(new_value.encode()).hexdigest(),
            }
        ],
    }

    print(f"🔧 Changing max_batch_size: {old_value} → {new_value}")
    print(f"   📝 DBOM audit entry created automatically")
    print()

    # Apply the change with audit
    conn.execute(
        "UPDATE app_config SET value = ?, updated_at = ? WHERE key = 'max_batch_size'",
        (new_value, change_time),
    )
    conn.execute(
        """INSERT INTO config_dbom (id, created_at, config_key, old_value, new_value, reason, signer, hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            dbom_entry["id"],
            change_time,
            "max_batch_size",
            old_value,
            new_value,
            reason,
            signer,
            change_hash,
        ),
    )
    conn.commit()

    # Monday morning: same alert, different outcome
    print("🚨 Monday morning: same alert — pipeline throughput dropped 95%!")
    print()
    print("🔍 Investigation (with DBOM):")
    audit = conn.execute(
        """SELECT created_at, config_key, old_value, new_value, reason, signer
           FROM config_dbom WHERE config_key = 'max_batch_size'
           ORDER BY created_at DESC LIMIT 1"""
    ).fetchone()

    print(f"   ✅ Changed at:  {audit[0]}")
    print(f"   ✅ Key:         {audit[1]}")
    print(f"   ✅ Old value:   {audit[2]}")
    print(f"   ✅ New value:   {audit[3]}")
    print(f"   ✅ Reason:      {audit[4]}")
    print(f"   ✅ Changed by:  {audit[5]}")
    print()
    print("   Resolution: revert max_batch_size to 1000, debug memory issue separately")
    print("   ✅ Mean time to resolution: 2 minutes")
    print()


def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          Demo 04: The Config Postmortem                    ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Clean up any previous run
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    try:
        setup_db(conn)
        part1_no_audit(conn)
        part2_with_audit(conn)

        print("━━━ RESULT ━━━")
        print("Without DBOM: hours of forensics to find one config change 💀")
        print("With DBOM:    instant trace — who, what, when, why ✅")
        print()
    finally:
        conn.close()
        # Clean up the demo database
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)


if __name__ == "__main__":
    main()
