"""Deterministic construction of the Makoto v0.2 core schema catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA_NAMES = (
    "bundle",
    "catalog",
    "dataset-manifest",
    "envelope",
    "handoff",
    "origin",
    "profile-dialect",
    "profile-reference",
    "statement",
    "transform",
    "trust-policy",
    "verification-report",
)


def schema_directory(repository_root: Path | None = None) -> Path:
    root = repository_root or Path(__file__).resolve().parents[2]
    return root / "schemas" / "v0.2"


def build_catalog(repository_root: Path | None = None) -> dict[str, object]:
    directory = schema_directory(repository_root)
    resources: list[dict[str, object]] = []
    for name in SCHEMA_NAMES:
        path = directory / f"{name}.schema.json"
        raw = path.read_bytes()
        parsed = json.loads(raw)
        resources.append(
            {
                "id": parsed["$id"],
                "digest": {"sha256": hashlib.sha256(raw).hexdigest()},
                "path": path.name,
            }
        )
    resources.sort(key=lambda resource: str(resource["id"]).encode())
    return {"version": "0.2", "resources": resources}


def serialize(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )


def write_catalog(repository_root: Path | None = None) -> Path:
    output = schema_directory(repository_root) / "catalog.json"
    output.write_bytes(serialize(build_catalog(repository_root)))
    return output
