"""Immutable Makoto protocol identifier families."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_PROTOCOL_VERSIONS = ("0.2", "0.3")


def require_protocol_version(version: str) -> str:
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ValueError(f"unsupported Makoto protocol version {version!r}")
    return version


def schema_id(version: str, name: str) -> str:
    require_protocol_version(version)
    return f"https://usemakoto.dev/schema/v{version}/{name}.schema.json"


def predicate_type(version: str, kind: str) -> str:
    require_protocol_version(version)
    if kind not in {"origin", "transform"}:
        raise ValueError(f"unsupported Makoto predicate kind {kind!r}")
    return f"https://usemakoto.dev/predicate/v{version}/{kind}"


def handoff_payload_type(version: str) -> str:
    require_protocol_version(version)
    return f"application/vnd.makoto.handoff.v{version}+json"


def dataset_manifest_media_type(version: str) -> str:
    require_protocol_version(version)
    return f"application/vnd.makoto.dataset-manifest.v{version}+json"


def protocol_version_from_statement(statement: Mapping[str, Any]) -> str:
    predicate = statement.get("predicate")
    if not isinstance(predicate, Mapping):
        raise ValueError("statement predicate is not an object")
    version = predicate.get("schemaVersion")
    if not isinstance(version, str):
        raise ValueError("statement predicate has no protocol version")
    require_protocol_version(version)
    expected = {
        predicate_type(version, "origin"),
        predicate_type(version, "transform"),
    }
    if statement.get("predicateType") not in expected:
        raise ValueError("statement mixes Makoto protocol identifier families")
    return version


def infer_protocol_version(schema_name: str, instance: object) -> str:
    if not isinstance(instance, Mapping):
        return "0.2"
    if schema_name == "statement":
        predicate = instance.get("predicate")
        if isinstance(predicate, Mapping) and isinstance(predicate.get("schemaVersion"), str):
            return require_protocol_version(str(predicate["schemaVersion"]))
    if schema_name in {"origin", "transform"}:
        version = instance.get("schemaVersion")
        if isinstance(version, str):
            return require_protocol_version(version)
    if schema_name == "verification-report":
        version = instance.get("reportVersion")
        if isinstance(version, str):
            return require_protocol_version(version)
    if schema_name == "profile-dialect":
        dialect = instance.get("$schema")
        if isinstance(dialect, str):
            for version in SUPPORTED_PROTOCOL_VERSIONS:
                if dialect == schema_id(version, "profile-dialect"):
                    return version
    if schema_name == "profile-reference":
        identifier = instance.get("id")
        media_type = instance.get("mediaType")
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            if isinstance(identifier, str) and f"/v{version}/" in identifier:
                return version
            if media_type == dataset_manifest_media_type(version):
                return version
    version = instance.get("version")
    if isinstance(version, str):
        return require_protocol_version(version)
    return "0.2"
