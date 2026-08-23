"""Checksum-asserted offline JSON Schema Draft 2020-12 registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes


class StandardRegistryError(RuntimeError):
    """Raised when immutable verifier-owned standard resources drift."""


@dataclass(frozen=True)
class StandardResourceIdentity:
    identifier: str
    path: str
    digest: str
    byte_length: int


STANDARD_RESOURCES = (
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/applicator",
        "meta/applicator.json",
        "bf273b26f9f735b93ece78f2b61b36676e1d122ce78ab37ad5a2e45dfa1ca2b1",
        1560,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/content",
        "meta/content.json",
        "a10456605b2b5bb12a1b4dcfc0300f02f54d3e8bb3646bed7724583866627682",
        423,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/core",
        "meta/core.json",
        "21f79d143fab1f180245c331e5657057045b36794d41fe151e6e4fed65035299",
        1471,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/format-annotation",
        "meta/format-annotation.json",
        "5c79404f831dd905c0f40fefac7c6f3e51bf3729b4a876a5c2020178d97f3bcc",
        342,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/meta-data",
        "meta/meta-data.json",
        "c664d438a84d58889c8edecd248ce2f945a4bc0e3b087323b11303dc136abfbe",
        794,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/unevaluated",
        "meta/unevaluated.json",
        "fc99f32188da41689a9382af174dd42e8b255e4374965c157b8286556b4ab2bc",
        406,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/meta/validation",
        "meta/validation.json",
        "e921c5b79264d3689af01c1af1ffdf692e09f1c45df90a0f08eb7288c9acdeab",
        2735,
    ),
    StandardResourceIdentity(
        "https://json-schema.org/draft/2020-12/schema",
        "schema.json",
        "41da76f5afb7ce062d248f762463a92f7ca47e4e0f905b224ba6afeef91ded0f",
        2452,
    ),
)


def standard_registry_directory() -> Path:
    return Path(__file__).parent / "standard-schemas" / "draft-2020-12"


def verify_standard_registry(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Verify the closed catalog, exact bytes, digests, lengths, and resource IDs."""

    root = directory or standard_registry_directory()
    catalog_bytes = (root / "catalog.json").read_bytes()
    if catalog_bytes.startswith(b"\xef\xbb\xbf"):
        raise StandardRegistryError("standard registry catalog contains a UTF-8 BOM")
    try:
        catalog = json.loads(catalog_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StandardRegistryError("standard registry catalog is not strict JSON") from error
    if not isinstance(catalog, dict) or catalog_bytes != canonical_json(catalog) + b"\n":
        raise StandardRegistryError("standard registry catalog is not canonical JCS plus LF")

    expected_catalog = {
        "version": "2020-12",
        "resources": [
            {
                "bytes": identity.byte_length,
                "digest": {"sha256": identity.digest},
                "id": identity.identifier,
                "path": identity.path,
            }
            for identity in STANDARD_RESOURCES
        ],
    }
    if catalog != expected_catalog:
        raise StandardRegistryError("standard registry catalog inventory differs from v0.2")

    expected_files = {"catalog.json", *(item.path for item in STANDARD_RESOURCES)}
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise StandardRegistryError("standard registry file inventory differs from v0.2")

    resources: dict[str, dict[str, Any]] = {}
    for identity in STANDARD_RESOURCES:
        exact_bytes = (root / identity.path).read_bytes()
        if len(exact_bytes) != identity.byte_length:
            raise StandardRegistryError(f"standard resource length mismatch: {identity.identifier}")
        if sha256_bytes(exact_bytes) != identity.digest:
            raise StandardRegistryError(f"standard resource digest mismatch: {identity.identifier}")
        try:
            value = json.loads(exact_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StandardRegistryError(
                f"standard resource is not strict JSON: {identity.identifier}"
            ) from error
        if not isinstance(value, dict) or value.get("$id") != identity.identifier:
            raise StandardRegistryError(f"standard resource ID mismatch: {identity.identifier}")
        resources[identity.identifier] = value
    return resources
