"""Typed authoring primitives for immutable Makoto v0.2 evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, cast

from makoto.canonical import canonical_json
from makoto.digest import digest_object, sha256_bytes, sha256_stream
from makoto.dsse import SigningKey, sign_envelope
from makoto.schema import validate_core

STATEMENT_PAYLOAD_TYPE = "application/vnd.in-toto+json"
HANDOFF_PAYLOAD_TYPE = "application/vnd.makoto.handoff.v0.2+json"
ORIGIN_PREDICATE_TYPE = "https://usemakoto.dev/predicate/v0.2/origin"
TRANSFORM_PREDICATE_TYPE = "https://usemakoto.dev/predicate/v0.2/transform"


@dataclass(frozen=True)
class Artifact:
    name: str
    data: bytes
    media_type: str | None = None

    @classmethod
    def from_stream(
        cls,
        name: str,
        stream: BinaryIO,
        *,
        media_type: str | None = None,
    ) -> Artifact:
        return cls(name=name, data=stream.read(), media_type=media_type)

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        name: str | None = None,
        media_type: str | None = None,
    ) -> Artifact:
        with path.open("rb") as stream:
            return cls.from_stream(name or path.name, stream, media_type=media_type)

    def digest(self) -> dict[str, str]:
        return digest_object(sha256_bytes(self.data))

    def stream_digest(self) -> dict[str, str]:
        from io import BytesIO

        return digest_object(sha256_stream(BytesIO(self.data)))


@dataclass(frozen=True)
class Attestation:
    statement: dict[str, Any]
    payload: bytes
    envelope: dict[str, object]

    def digest(self) -> dict[str, str]:
        return digest_object(sha256_bytes(self.payload))

    def subject(self, name: str) -> dict[str, Any]:
        subjects = cast(list[dict[str, Any]], self.statement["subject"])
        matches = [subject for subject in subjects if subject["name"] == name]
        if len(matches) != 1:
            raise ValueError(f"attestation does not contain exactly one subject named {name!r}")
        return matches[0]


@dataclass(frozen=True)
class TransformationInput:
    name: str
    artifact: Artifact
    predecessor: Attestation
    predecessor_subject_name: str
    entry_name: str | None = None

    def as_dict(self) -> dict[str, object]:
        predecessor_subject = self.predecessor.subject(self.predecessor_subject_name)
        artifact_digest = self.artifact.digest()
        if self.entry_name is None and predecessor_subject["digest"] != artifact_digest:
            raise ValueError("input bytes do not match the selected predecessor subject digest")
        provenance: dict[str, object] = {
            "statementDigest": self.predecessor.digest(),
            "subjectName": self.predecessor_subject_name,
        }
        if self.entry_name is not None:
            provenance["entryName"] = self.entry_name
        return {"name": self.name, "digest": artifact_digest, "provenance": provenance}


@dataclass(frozen=True)
class Handoff:
    manifest: dict[str, Any]
    payload: bytes
    envelope: dict[str, object]

    def digest(self) -> dict[str, str]:
        return digest_object(sha256_bytes(self.payload))


def _subject(artifact: Artifact) -> dict[str, object]:
    return {"name": artifact.name, "digest": artifact.digest()}


def _sign_statement(
    statement: dict[str, Any],
    key: SigningKey | Sequence[SigningKey],
    repository_root: Path,
) -> Attestation:
    validate_core("statement", statement, repository_root=repository_root)
    payload = canonical_json(statement)
    envelope = sign_envelope(STATEMENT_PAYLOAD_TYPE, payload, key)
    validate_core("envelope", envelope, repository_root=repository_root)
    return Attestation(statement=statement, payload=payload, envelope=envelope)


def create_origin(
    *,
    artifacts: list[Artifact],
    event_id: str,
    occurred_at: str,
    source_kind: str,
    signing_key: SigningKey | Sequence[SigningKey],
    repository_root: Path,
    source_uri: str | None = None,
    source_name: str | None = None,
    source_media_type: str | None = None,
    retrieved_at: str | None = None,
    source_version: str | None = None,
    profiles: list[dict[str, object]] | None = None,
    extensions: dict[str, object] | None = None,
) -> Attestation:
    if not artifacts:
        raise ValueError("an origin requires at least one subject artifact")
    source: dict[str, object] = {"kind": source_kind}
    optional_source = {
        "uri": source_uri,
        "name": source_name,
        "mediaType": source_media_type,
        "retrievedAt": retrieved_at,
        "version": source_version,
    }
    source.update({name: value for name, value in optional_source.items() if value is not None})
    predicate: dict[str, object] = {
        "schemaVersion": "0.2",
        "event": {"id": event_id, "occurredAt": occurred_at},
        "source": source,
    }
    if profiles is not None:
        predicate["profiles"] = profiles
    if extensions is not None:
        predicate["extensions"] = extensions
    statement: dict[str, Any] = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [_subject(artifact) for artifact in artifacts],
        "predicateType": ORIGIN_PREDICATE_TYPE,
        "predicate": predicate,
    }
    return _sign_statement(statement, signing_key, repository_root)


def create_transform(
    *,
    artifacts: list[Artifact],
    inputs: list[TransformationInput],
    event_id: str,
    occurred_at: str,
    operation_type: str,
    signing_key: SigningKey | Sequence[SigningKey],
    repository_root: Path,
    operation_name: str | None = None,
    tool: dict[str, object] | None = None,
    parameters_digest: dict[str, str] | None = None,
    profiles: list[dict[str, object]] | None = None,
    extensions: dict[str, object] | None = None,
) -> Attestation:
    if not artifacts:
        raise ValueError("a transformation requires at least one subject artifact")
    if not inputs:
        raise ValueError("a transformation requires at least one input")
    operation: dict[str, object] = {"type": operation_type}
    if operation_name is not None:
        operation["name"] = operation_name
    if tool is not None:
        operation["tool"] = tool
    if parameters_digest is not None:
        operation["parametersDigest"] = parameters_digest
    predicate: dict[str, object] = {
        "schemaVersion": "0.2",
        "event": {"id": event_id, "occurredAt": occurred_at},
        "operation": operation,
        "inputs": [input_artifact.as_dict() for input_artifact in inputs],
    }
    if profiles is not None:
        predicate["profiles"] = profiles
    if extensions is not None:
        predicate["extensions"] = extensions
    statement: dict[str, Any] = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [_subject(artifact) for artifact in artifacts],
        "predicateType": TRANSFORM_PREDICATE_TYPE,
        "predicate": predicate,
    }
    return _sign_statement(statement, signing_key, repository_root)


def create_handoff(
    *,
    statements: list[Attestation],
    roots: list[Attestation],
    final_artifacts: list[tuple[Artifact, Attestation]],
    bundle_id: str,
    issued_at: str,
    signing_key: SigningKey | Sequence[SigningKey],
    repository_root: Path,
    required_profiles: list[dict[str, object]] | None = None,
    recipient: str | None = None,
    nonce: str | None = None,
) -> Handoff:
    if not statements or not roots or not final_artifacts:
        raise ValueError("handoff requires statements, roots, and final artifacts")
    statement_digests = sorted(
        (statement.digest() for statement in statements), key=lambda item: item["sha256"]
    )
    root_digests = sorted((root.digest() for root in roots), key=lambda item: item["sha256"])
    artifacts: list[dict[str, Any]] = []
    for artifact, head in final_artifacts:
        subject = head.subject(artifact.name)
        if subject["digest"] != artifact.digest():
            raise ValueError("final artifact bytes do not match the selected head subject")
        item: dict[str, object] = {
            "name": artifact.name,
            "digest": artifact.digest(),
            "head": head.digest(),
        }
        if artifact.media_type is not None:
            item["mediaType"] = artifact.media_type
        artifacts.append(item)
    artifacts.sort(
        key=lambda item: (
            str(item["head"]["sha256"]),
            str(item["name"]).encode(),
            str(item["digest"]["sha256"]),
        )
    )
    head_digests = sorted(
        {str(item["head"]["sha256"]) for item in artifacts},
    )
    manifest: dict[str, Any] = {
        "version": "0.2",
        "bundleId": bundle_id,
        "issuedAt": issued_at,
        "roots": root_digests,
        "heads": [digest_object(value) for value in head_digests],
        "statements": statement_digests,
        "artifacts": artifacts,
        "requiredProfiles": required_profiles or [],
    }
    if recipient is not None:
        manifest["recipient"] = recipient
    if nonce is not None:
        manifest["nonce"] = nonce
    validate_core("handoff", manifest, repository_root=repository_root)
    payload = canonical_json(manifest)
    envelope = sign_envelope(HANDOFF_PAYLOAD_TYPE, payload, signing_key)
    validate_core("envelope", envelope, repository_root=repository_root)
    return Handoff(manifest=manifest, payload=payload, envelope=envelope)
