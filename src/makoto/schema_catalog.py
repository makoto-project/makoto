"""Deterministic construction of immutable Makoto core schema catalogs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from makoto.protocol import require_protocol_version

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

SCHEMA_NAMES_BY_VERSION = {
    "0.2": SCHEMA_NAMES,
    "0.3": SCHEMA_NAMES + ("record-declaration", "record-inclusion-proof"),
}


def schema_directory(repository_root: Path | None = None, *, version: str = "0.2") -> Path:
    require_protocol_version(version)
    root = repository_root or Path(__file__).resolve().parents[2]
    return root / "schemas" / f"v{version}"


def build_catalog(
    repository_root: Path | None = None, *, version: str = "0.2"
) -> dict[str, object]:
    directory = schema_directory(repository_root, version=version)
    resources: list[dict[str, object]] = []
    for name in SCHEMA_NAMES_BY_VERSION[version]:
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
    return {"version": version, "resources": resources}


def serialize(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )


def write_catalog(repository_root: Path | None = None, *, version: str = "0.2") -> Path:
    output = schema_directory(repository_root, version=version) / "catalog.json"
    output.write_bytes(serialize(build_catalog(repository_root, version=version)))
    return output
