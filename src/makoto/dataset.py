"""Typed, deterministic parsing for versioned dataset-manifest artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from jsonschema import Draft202012Validator

from makoto.protocol import infer_protocol_version
from makoto.schema import (
    CoreValidationError,
    StrictJsonError,
    build_registry,
    load_core_schemas,
    semantic_violations,
    strict_json_loads,
)


class DatasetManifestError(ValueError):
    """A dataset manifest could not establish a trusted partition index."""

    def __init__(self, phase: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase


@dataclass(frozen=True)
class DatasetEntry:
    name: str
    digest: str
    size: int | None
    media_type: str | None
    record_count: int | None
    record_root: str | None


@dataclass(frozen=True)
class DatasetManifestIndex:
    protocol_version: str
    entries: tuple[DatasetEntry, ...]
    members: Mapping[str, DatasetEntry]

    def member(self, name: str) -> DatasetEntry | None:
        return self.members.get(name)


def parse_dataset_manifest(
    exact_bytes: bytes,
    *,
    repository_root: Path,
) -> DatasetManifestIndex:
    """Strict-parse and validate one exact dataset-manifest byte sequence once."""

    try:
        parsed = strict_json_loads(exact_bytes)
    except StrictJsonError as error:
        raise DatasetManifestError("parse", str(error)) from error
    if not isinstance(parsed, dict):
        raise DatasetManifestError("schema", "dataset manifest root must be an object")
    protocol_version = infer_protocol_version("dataset-manifest", parsed)
    schemas = load_core_schemas(repository_root, protocol_version=protocol_version)
    validator = Draft202012Validator(schemas["dataset-manifest"], registry=build_registry(schemas))
    schema_errors = sorted(
        validator.iter_errors(parsed), key=lambda error: list(error.absolute_path)
    )
    if schema_errors:
        message = "; ".join(error.message for error in schema_errors)
        raise DatasetManifestError("schema", message)
    semantic_errors = semantic_violations(
        "dataset-manifest", parsed, protocol_version=protocol_version
    )
    if semantic_errors:
        semantic_error = CoreValidationError(semantic_errors)
        raise DatasetManifestError("semantic", str(semantic_error)) from semantic_error
    value = cast(dict[str, Any], parsed)
    entries = tuple(
        DatasetEntry(
            name=entry["name"],
            digest=entry["digest"]["sha256"],
            size=entry.get("size"),
            media_type=entry.get("mediaType"),
            record_count=(
                entry["recordMerkle"]["recordCount"] if "recordMerkle" in entry else None
            ),
            record_root=(
                entry["recordMerkle"]["root"]["sha256"] if "recordMerkle" in entry else None
            ),
        )
        for entry in value["entries"]
    )
    return DatasetManifestIndex(
        protocol_version=protocol_version,
        entries=entries,
        members=MappingProxyType({entry.name: entry for entry in entries}),
    )
