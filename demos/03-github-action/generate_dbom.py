#!/usr/bin/env python3
"""Makoto DBOM Generator
Generates a Data Bill of Materials JSON file for any data file.
Designed to run in CI — stdlib only, no dependencies.
"""

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone


def compute_sha256(filepath):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_format(filepath):
    """Guess file format from extension."""
    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    return ext if ext else "unknown"


def generate_dbom(filepath, signer=None, source_uri=None, description=None):
    """Generate a DBOM JSON document for the given file."""
    file_hash = compute_sha256(filepath)

    # Default signer to GITHUB_ACTOR if in CI
    if not signer:
        actor = os.environ.get("GITHUB_ACTOR", "unknown")
        signer = f"github:{actor}"

    # Default source URI to GitHub repo reference
    if not source_uri:
        repo = os.environ.get("GITHUB_REPOSITORY", "local")
        ref = os.environ.get("GITHUB_SHA", "HEAD")[:8]
        source_uri = f"github:{repo}/{filepath}@{ref}"

    if not description:
        description = f"Auto-generated DBOM for {os.path.basename(filepath)}"

    dbom = {
        "schema_version": "0.1",
        "id": f"dbom-{uuid.uuid4()}",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "uri": source_uri,
            "hash": {"algorithm": "sha256", "value": file_hash},
            "format": detect_format(filepath),
        },
        "signature": {
            "algorithm": "sha256",
            "value": file_hash,
            "signer": signer,
        },
        "lineage": [
            {
                "step": 1,
                "description": description,
                "tool": f"makoto-action v0.1",
                "input_hash": "n/a",
                "output_hash": file_hash,
            }
        ],
    }

    return dbom


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_dbom.py <file> [--signer <id>] [--output <path>]")
        sys.exit(1)

    filepath = sys.argv[1]
    signer = None
    output_path = None

    # Parse optional args
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--signer" and i + 1 < len(args):
            signer = args[i + 1]
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        else:
            i += 1

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    dbom = generate_dbom(filepath, signer=signer)

    # Default output: same name with .dbom.json extension
    if not output_path:
        output_path = filepath + ".dbom.json"

    with open(output_path, "w") as f:
        json.dump(dbom, f, indent=2)

    print(f"✅ DBOM generated: {output_path}")
    print(f"   File:   {filepath}")
    print(f"   Hash:   {dbom['source']['hash']['value'][:16]}...")
    print(f"   Signer: {dbom['signature']['signer']}")


if __name__ == "__main__":
    main()
