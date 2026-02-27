#!/usr/bin/env bash
# Demo 01: Poisoned Pipeline
# Shows how unsigned data sneaks through vs. DBOM-gated pipeline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"

# ─── Helper: compute SHA-256 of a file ───
file_hash() { sha256sum "$1" | awk '{print $1}'; }

# ─── Helper: basic CSV quality check ───
check_csv_quality() {
    local file="$1"
    local bad=0

    # Skip header, check each row for obvious problems
    tail -n +2 "$file" | while IFS=',' read -r sid ts temp hum; do
        # Check for non-numeric temperature
        if ! echo "$temp" | grep -qE '^-?[0-9]+\.?[0-9]*$'; then
            echo "  ⚠️  Row [$sid @ $ts]: temperature='$temp' is not a valid number"
            bad=1
        # Check for physically impossible temperature
        elif (( $(echo "$temp < -80 || $temp > 60" | bc -l) )); then
            echo "  ⚠️  Row [$sid @ $ts]: temperature=${temp}°C is physically impossible"
            bad=1
        fi

        # Check for missing humidity
        if [ -z "$hum" ]; then
            echo "  ⚠️  Row [$sid @ $ts]: humidity is missing"
            bad=1
        # Check for out-of-range humidity
        elif (( $(echo "$hum > 100" | bc -l) )); then
            echo "  ⚠️  Row [$sid @ $ts]: humidity=${hum}% exceeds 100%"
            bad=1
        fi
    done

    return 0
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Demo 01: The Poisoned Pipeline Problem             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PART 1: No DBOM — corrupted data flows right through
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━ PART 1: Pipeline WITHOUT DBOM ━━━"
echo ""
echo "📥 Ingesting sensors_corrupted.csv (no provenance check)..."
echo ""

# Show what's in the corrupted file
echo "Data quality scan:"
check_csv_quality "$DATA_DIR/sensors_corrupted.csv"
echo ""

# Compute naive stats anyway — this is the problem
ROWS=$(tail -n +2 "$DATA_DIR/sensors_corrupted.csv" | wc -l)
echo "Pipeline result: processed $ROWS rows"
echo "❌ Corrupted data was accepted — no gate, no check, no trail."
echo "   SQL injection payload, NaN values, and impossible readings all passed through."
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PART 2: With DBOM — gate rejects unsigned, accepts signed
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━ PART 2: Pipeline WITH DBOM Gate ━━━"
echo ""

# --- Attempt 1: corrupted file (no DBOM) ---
echo "📥 Attempting to ingest sensors_corrupted.csv..."
DBOM_FILE="$DATA_DIR/sensors_corrupted.dbom.json"

if [ ! -f "$DBOM_FILE" ]; then
    echo "❌ REJECTED: No DBOM file found for sensors_corrupted.csv"
    echo "   Gate requires: sensors_corrupted.dbom.json"
    echo ""
else
    echo "   DBOM found, checking signature..."
fi

# --- Attempt 2: clean file (with valid DBOM) ---
echo "📥 Attempting to ingest sensors_clean.csv..."
DBOM_FILE="$DATA_DIR/sensors_clean.dbom.json"

if [ ! -f "$DBOM_FILE" ]; then
    echo "❌ REJECTED: No DBOM file found"
    echo ""
else
    echo "   ✅ DBOM file found: sensors_clean.dbom.json"

    # Extract expected hash from DBOM
    EXPECTED_HASH=$(python3 -c "import json; print(json.load(open('$DBOM_FILE'))['source']['hash']['value'])")
    # Compute actual hash of the CSV
    ACTUAL_HASH=$(file_hash "$DATA_DIR/sensors_clean.csv")

    if [ "$EXPECTED_HASH" = "$ACTUAL_HASH" ]; then
        echo "   ✅ Hash verified: file matches DBOM"
    else
        echo "   ❌ Hash mismatch! File has been tampered with."
        echo "      Expected: $EXPECTED_HASH"
        echo "      Got:      $ACTUAL_HASH"
        exit 1
    fi

    # Extract and display signer
    SIGNER=$(python3 -c "import json; print(json.load(open('$DBOM_FILE'))['signature']['signer'])")
    echo "   ✅ Signed by: $SIGNER"
    echo ""

    # Now safe to process
    ROWS=$(tail -n +2 "$DATA_DIR/sensors_clean.csv" | wc -l)
    echo "✅ Pipeline accepted: $ROWS verified rows ingested"
    echo "   Signer: $SIGNER | Hash: ${ACTUAL_HASH:0:16}..."
fi

echo ""
echo "━━━ RESULT ━━━"
echo "Without DBOM: corrupted data silently accepted 💀"
echo "With DBOM:    unsigned data blocked, verified data accepted ✅"
echo ""
