"""Typed, deterministic parsing for Makoto v0.2 dataset-manifest artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from jsonschema import Draft202012Validator

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


@dataclass(frozen=True)
class DatasetManifestIndex:
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
    schemas = load_core_schemas(repository_root)
    validator = Draft202012Validator(schemas["dataset-manifest"], registry=build_registry(schemas))
    schema_errors = sorted(
        validator.iter_errors(parsed), key=lambda error: list(error.absolute_path)
    )
    if schema_errors:
        message = "; ".join(error.message for error in schema_errors)
        raise DatasetManifestError("schema", message)
    semantic_errors = semantic_violations("dataset-manifest", parsed)
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
        )
        for entry in value["entries"]
    )
    return DatasetManifestIndex(
        entries=entries,
        members=MappingProxyType({entry.name: entry for entry in entries}),
    )
