#!/usr/bin/env python3
"""Validate and byte-pin the trusted bounded-worker IPC contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator

from makoto.schema import strict_json_loads

ROOT = Path(__file__).resolve().parents[1]
INTERNAL = ROOT / "src" / "makoto" / "internal-schemas"
EXPECTED = {
    "dataset-worker-result.schema.json": (
        "2f55af5ac29bc2e89ca9af73b8956c14c01da88aec64217fe88389c1de5ed992"
    ),
    "profile-worker-result.schema.json": (
        "e43ef2835191a132b63e51571c913ac4a87bc20ff1c9f247a88e7c562c766cad"
    ),
}


def main() -> int:
    actual_names = {path.name for path in INTERNAL.glob("*.schema.json")}
    if actual_names != set(EXPECTED):
        raise SystemExit(
            f"internal schema set mismatch: expected {sorted(EXPECTED)}, got {sorted(actual_names)}"
        )
    for name, expected_digest in EXPECTED.items():
        raw = (INTERNAL / name).read_bytes()
        actual_digest = hashlib.sha256(raw).hexdigest()
        if actual_digest != expected_digest:
            raise SystemExit(
                f"internal schema digest mismatch for {name}: "
                f"expected {expected_digest}, got {actual_digest}"
            )
        value = strict_json_loads(raw)
        if not isinstance(value, dict):
            raise SystemExit(f"internal schema is not an object: {name}")
        Draft202012Validator.check_schema(value)
    print("internal worker schemas valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
