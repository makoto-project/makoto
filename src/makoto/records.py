"""Format-neutral Makoto v0.3 record Merkle commitments and proofs."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from makoto.digest import digest_object
from makoto.schema import CoreValidationError, strict_json_loads, validate_core

RECORD_MERKLE_ALGORITHM = "rfc6962-sha256-record-digest-v1"


class RecordProofError(ValueError):
    """A record declaration or inclusion proof is invalid."""


def _hash_leaf(record_digest: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + record_digest).digest()


def _hash_node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def record_digests_from_declaration(
    declaration: Mapping[str, Any],
    *,
    entry_bytes: bytes | None,
    repository_root: Path,
) -> tuple[bytes, ...]:
    """Resolve producer-declared byte ranges or record hashes without parsing data."""

    try:
        validate_core(
            "record-declaration",
            declaration,
            repository_root=repository_root,
            protocol_version="0.3",
        )
    except CoreValidationError as error:
        raise RecordProofError(str(error)) from error
    if declaration["kind"] == "recordHashes":
        return tuple(bytes.fromhex(item["sha256"]) for item in declaration["hashes"])
    if entry_bytes is None:
        raise RecordProofError("byte-range declarations require the exact entry bytes")
    digests: list[bytes] = []
    for index, record_range in enumerate(declaration["ranges"]):
        offset = record_range["offset"]
        length = record_range["length"]
        end = offset + length
        if end > len(entry_bytes):
            raise RecordProofError(f"byte range {index} exceeds the entry byte length")
        digests.append(hashlib.sha256(entry_bytes[offset:end]).digest())
    return tuple(digests)


def load_record_declaration(path: Path, *, repository_root: Path) -> dict[str, Any]:
    parsed = strict_json_loads(path.read_bytes())
    if not isinstance(parsed, dict):
        raise RecordProofError("record declaration must be a JSON object")
    value = cast(dict[str, Any], parsed)
    validate_core(
        "record-declaration",
        value,
        repository_root=repository_root,
        protocol_version="0.3",
    )
    return value


def merkle_root(record_digests: Sequence[bytes]) -> bytes:
    if not record_digests:
        raise RecordProofError("a record Merkle tree requires at least one record")
    level = [_hash_leaf(digest) for digest in record_digests]
    while len(level) > 1:
        level = [
            _hash_node(level[index], level[index + 1]) if index + 1 < len(level) else level[index]
            for index in range(0, len(level), 2)
        ]
    return level[0]


def merkle_audit_path(record_digests: Sequence[bytes], record_index: int) -> tuple[bytes, ...]:
    if not 0 <= record_index < len(record_digests):
        raise RecordProofError("record index is out of range")
    level = [_hash_leaf(digest) for digest in record_digests]
    index = record_index
    path: list[bytes] = []
    while len(level) > 1:
        sibling = index - 1 if index & 1 else index + 1
        if sibling < len(level):
            path.append(level[sibling])
        level = [
            _hash_node(level[position], level[position + 1])
            if position + 1 < len(level)
            else level[position]
            for position in range(0, len(level), 2)
        ]
        index //= 2
    return tuple(path)


def record_commitment(record_digests: Sequence[bytes]) -> dict[str, Any]:
    return {
        "algorithm": RECORD_MERKLE_ALGORITHM,
        "recordCount": len(record_digests),
        "root": digest_object(merkle_root(record_digests).hex()),
    }


def create_record_inclusion_proof(
    *,
    record_digests: Sequence[bytes],
    record_index: int,
    manifest_statement_digest: str,
    manifest_subject_name: str,
    entry_name: str,
    entry_digest: str,
    byte_range: Mapping[str, int] | None = None,
    repository_root: Path,
) -> dict[str, Any]:
    if not 0 <= record_index < len(record_digests):
        raise RecordProofError("record index is out of range")
    proof: dict[str, Any] = {
        "version": "0.3",
        "algorithm": RECORD_MERKLE_ALGORITHM,
        "manifestStatementDigest": digest_object(manifest_statement_digest),
        "manifestSubjectName": manifest_subject_name,
        "entryName": entry_name,
        "entryDigest": digest_object(entry_digest),
        "recordIndex": record_index,
        "recordCount": len(record_digests),
        "recordDigest": digest_object(record_digests[record_index].hex()),
        "auditPath": [
            digest_object(item.hex()) for item in merkle_audit_path(record_digests, record_index)
        ],
    }
    if byte_range is not None:
        proof["byteRange"] = dict(byte_range)
    validate_core(
        "record-inclusion-proof",
        proof,
        repository_root=repository_root,
        protocol_version="0.3",
    )
    return proof


def verify_record_inclusion_proof(
    proof: Mapping[str, Any],
    *,
    expected_root: str,
    record_bytes: bytes | None = None,
    repository_root: Path,
) -> None:
    try:
        validate_core(
            "record-inclusion-proof",
            proof,
            repository_root=repository_root,
            protocol_version="0.3",
        )
    except CoreValidationError as error:
        raise RecordProofError(str(error)) from error
    record_digest = bytes.fromhex(proof["recordDigest"]["sha256"])
    if record_bytes is not None and hashlib.sha256(record_bytes).digest() != record_digest:
        raise RecordProofError("record bytes do not match recordDigest")
    index = proof["recordIndex"]
    last = proof["recordCount"] - 1
    value = _hash_leaf(record_digest)
    audit_path = iter(proof["auditPath"])
    for sibling_value in audit_path:
        sibling = bytes.fromhex(sibling_value["sha256"])
        if index & 1 or index == last:
            value = _hash_node(sibling, value)
            if index == last:
                while index and not index & 1:
                    index >>= 1
                    last >>= 1
        else:
            value = _hash_node(value, sibling)
        index >>= 1
        last >>= 1
    if last != 0:
        raise RecordProofError("audit path is too short for recordCount")
    if value.hex() != expected_root:
        raise RecordProofError("record inclusion proof does not match the manifest root")
