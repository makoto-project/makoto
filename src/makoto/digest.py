"""Exact-byte SHA-256 helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

CHUNK_SIZE = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_chunks(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(stream: BinaryIO, *, chunk_size: int = CHUNK_SIZE) -> str:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    def chunks() -> Iterable[bytes]:
        while chunk := stream.read(chunk_size):
            yield chunk

    return sha256_chunks(chunks())


def sha256_path(path: Path, *, chunk_size: int = CHUNK_SIZE) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream, chunk_size=chunk_size)


def digest_object(hex_digest: str) -> dict[str, str]:
    if len(hex_digest) != 64 or any(
        character not in "0123456789abcdef" for character in hex_digest
    ):
        raise ValueError("SHA-256 digest must be 64 lowercase hexadecimal characters")
    return {"sha256": hex_digest}
