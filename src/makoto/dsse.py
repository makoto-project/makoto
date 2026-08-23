"""DSSE PAE plus the strict Makoto v0.2 Ed25519 profile."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from makoto.digest import sha256_bytes

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
SQRT_MINUS_ONE = pow(2, (P - 1) // 4, P)
IDENTITY = (0, 1)
BASE_Y = (4 * pow(5, P - 2, P)) % P
_BASE_X_SQUARED = ((BASE_Y * BASE_Y - 1) * pow(D * BASE_Y * BASE_Y + 1, P - 2, P)) % P
_BASE_X = pow(_BASE_X_SQUARED, (P + 3) // 8, P)
if (_BASE_X * _BASE_X - _BASE_X_SQUARED) % P != 0:
    _BASE_X = (_BASE_X * SQRT_MINUS_ONE) % P
if _BASE_X & 1:
    _BASE_X = P - _BASE_X
BASE = (_BASE_X, BASE_Y)
SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
SUPPORTED_PAYLOAD_TYPES = frozenset(
    {
        "application/vnd.in-toto+json",
        "application/vnd.makoto.handoff.v0.2+json",
    }
)
_PAYLOAD_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}$")


class DsseError(ValueError):
    """Raised when DSSE or key material is malformed."""


class SignatureVerificationError(DsseError):
    """Raised when a strict Ed25519 verification fails."""


@dataclass(frozen=True)
class SigningKey:
    private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> SigningKey:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, seed: bytes) -> SigningKey:
        if len(seed) != 32:
            raise DsseError("Ed25519 seed must be exactly 32 bytes")
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    @classmethod
    def from_pem(cls, data: bytes) -> SigningKey:
        try:
            key = serialization.load_pem_private_key(data, password=None)
        except (TypeError, ValueError) as error:
            raise DsseError("private key is not unencrypted PKCS#8 PEM") from error
        if not isinstance(key, Ed25519PrivateKey):
            raise DsseError("private key is not Ed25519")
        return cls(key)

    def public_key_bytes(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def public_spki(self) -> bytes:
        return SPKI_PREFIX + self.public_key_bytes()

    def private_pkcs8_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_spki_pem(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def keyid(self) -> str:
        return keyid_from_spki(self.public_spki())

    def sign(self, message: bytes) -> bytes:
        return self.private_key.sign(message)


def pae(payload_type: str, payload: bytes) -> bytes:
    try:
        payload_type_bytes = payload_type.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise DsseError("payload type is not Unicode scalar text") from error
    return b" ".join(
        (
            b"DSSEv1",
            str(len(payload_type_bytes)).encode("ascii"),
            payload_type_bytes,
            str(len(payload)).encode("ascii"),
            payload,
        )
    )


def validate_payload_type(payload_type: str, *, require_supported: bool = True) -> None:
    """Validate the exact Makoto v0.2 DSSE payload-type grammar and allowlist."""

    if _PAYLOAD_TYPE.fullmatch(payload_type) is None:
        raise DsseError("payload type is not a lowercase parameter-free media type")
    if require_supported and payload_type not in SUPPORTED_PAYLOAD_TYPES:
        raise DsseError("payload type is not supported by Makoto v0.2")


def canonical_b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def canonical_b64decode(value: str, *, expected_length: int | None = None) -> bytes:
    try:
        ascii_value = value.encode("ascii", errors="strict")
        decoded = base64.b64decode(ascii_value, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise DsseError("value is not canonical RFC 4648 standard base64") from error
    if canonical_b64encode(decoded) != value:
        raise DsseError("value is not the canonical base64 spelling")
    if expected_length is not None and len(decoded) != expected_length:
        raise DsseError(f"decoded value must be exactly {expected_length} bytes")
    return decoded


def keyid_from_spki(spki: bytes) -> str:
    if len(spki) != 44 or not spki.startswith(SPKI_PREFIX):
        raise DsseError("public key is not canonical Ed25519 SubjectPublicKeyInfo")
    _decode_prime_order_point(spki[len(SPKI_PREFIX) :])
    return f"sha256:{sha256_bytes(spki)}"


def public_key_from_spki(spki: bytes) -> bytes:
    keyid_from_spki(spki)
    return spki[len(SPKI_PREFIX) :]


def spki_from_pem(data: bytes) -> bytes:
    try:
        key = serialization.load_pem_public_key(data)
    except ValueError as error:
        raise DsseError("public key is not SubjectPublicKeyInfo PEM") from error
    if not isinstance(key, Ed25519PublicKey):
        raise DsseError("public key is not Ed25519")
    spki = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    keyid_from_spki(spki)
    return spki


def _inverse(value: int) -> int:
    if value % P == 0:
        raise SignatureVerificationError("invalid Edwards25519 denominator")
    return pow(value, P - 2, P)


ExtendedPoint = tuple[int, int, int, int]


def _to_extended(point: tuple[int, int]) -> ExtendedPoint:
    x, y = point
    return x, y, 1, x * y % P


def _extended_add(left: ExtendedPoint, right: ExtendedPoint) -> ExtendedPoint:
    """Complete extended-coordinate addition for Edwards25519 (a = -1)."""

    x1, y1, z1, t1 = left
    x2, y2, z2, t2 = right
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = 2 * D * t1 * t2 % P
    d = 2 * z1 * z2 % P
    e = b - a
    f = d - c
    g = d + c
    h = b + a
    return e * f % P, g * h % P, f * g % P, e * h % P


def _from_extended(point: ExtendedPoint) -> tuple[int, int]:
    x, y, z, _t = point
    inverse_z = _inverse(z)
    return x * inverse_z % P, y * inverse_z % P


def _add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    return _from_extended(_extended_add(_to_extended(left), _to_extended(right)))


def _scalar_multiply(scalar: int, point: tuple[int, int]) -> tuple[int, int]:
    result = _to_extended(IDENTITY)
    addend = _to_extended(point)
    while scalar:
        if scalar & 1:
            result = _extended_add(result, addend)
        addend = _extended_add(addend, addend)
        scalar >>= 1
    return _from_extended(result)


def _encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    encoded = y | ((x & 1) << 255)
    return encoded.to_bytes(32, "little")


def _decode_prime_order_point(encoded: bytes) -> tuple[int, int]:
    if len(encoded) != 32:
        raise SignatureVerificationError("Edwards25519 point must be 32 bytes")
    encoded_integer = int.from_bytes(encoded, "little")
    sign = encoded_integer >> 255
    y = encoded_integer & ((1 << 255) - 1)
    if y >= P:
        raise SignatureVerificationError("noncanonical Edwards25519 y coordinate")
    y_squared = y * y % P
    x_squared = ((y_squared - 1) * _inverse(D * y_squared + 1)) % P
    x = pow(x_squared, (P + 3) // 8, P)
    if (x * x - x_squared) % P != 0:
        x = x * SQRT_MINUS_ONE % P
    if (x * x - x_squared) % P != 0:
        raise SignatureVerificationError("Edwards25519 point is not on the curve")
    if x == 0 and sign == 1:
        raise SignatureVerificationError("invalid sign bit for zero x coordinate")
    if (x & 1) != sign:
        x = P - x
    point = (x, y)
    if _encode_point(point) != encoded:
        raise SignatureVerificationError("noncanonical Edwards25519 point encoding")
    if point == IDENTITY:
        raise SignatureVerificationError("identity Edwards25519 point is forbidden")
    if _scalar_multiply(L, point) != IDENTITY:
        raise SignatureVerificationError("Edwards25519 point is not prime order")
    return point


def strict_verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> None:
    if len(public_key) != 32:
        raise SignatureVerificationError("Ed25519 public key must be 32 bytes")
    if len(signature) != 64:
        raise SignatureVerificationError("Ed25519 signature must be 64 bytes")
    public_point = _decode_prime_order_point(public_key)
    encoded_r = signature[:32]
    signature_point = _decode_prime_order_point(encoded_r)
    scalar = int.from_bytes(signature[32:], "little")
    if scalar >= L:
        raise SignatureVerificationError("noncanonical Ed25519 scalar")
    challenge = (
        int.from_bytes(
            hashlib.sha512(encoded_r + public_key + message).digest(),
            "little",
        )
        % L
    )
    left = _scalar_multiply(scalar, BASE)
    right = _add(signature_point, _scalar_multiply(challenge, public_point))
    if left != right:
        raise SignatureVerificationError("Ed25519 signature equation failed")


def sign_envelope(
    payload_type: str,
    payload: bytes,
    key: SigningKey | Sequence[SigningKey],
) -> dict[str, object]:
    """Sign exact payload bytes with one or more distinct keys.

    Signature order is canonical by key ID so producer argument order cannot
    change envelope bytes.
    """

    validate_payload_type(payload_type)
    keys = [key] if isinstance(key, SigningKey) else list(key)
    if not keys:
        raise DsseError("at least one signing key is required")
    key_ids = [item.keyid() for item in keys]
    if len(key_ids) != len(set(key_ids)):
        raise DsseError("signing key IDs must be unique")
    message = pae(payload_type, payload)
    signatures = sorted(
        ({"keyid": item.keyid(), "sig": canonical_b64encode(item.sign(message))} for item in keys),
        key=lambda item: item["keyid"].encode(),
    )
    return {
        "payloadType": payload_type,
        "payload": canonical_b64encode(payload),
        "signatures": signatures,
    }


def verify_envelope_signature(
    envelope: dict[str, object],
    *,
    public_spki: bytes,
    signature_index: int = 0,
) -> None:
    payload_type = envelope.get("payloadType")
    payload_text = envelope.get("payload")
    signatures = envelope.get("signatures")
    if not isinstance(payload_type, str) or not isinstance(payload_text, str):
        raise DsseError("envelope payload fields are malformed")
    validate_payload_type(payload_type)
    if not isinstance(signatures, list) or not 0 <= signature_index < len(signatures):
        raise DsseError("signature index is unavailable")
    payload = canonical_b64decode(payload_text)
    seen_keyids: set[str] = set()
    for candidate in signatures:
        if not isinstance(candidate, dict) or set(candidate) != {"keyid", "sig"}:
            raise DsseError("signature entry is malformed")
        candidate_keyid = candidate.get("keyid")
        candidate_signature = candidate.get("sig")
        if not isinstance(candidate_keyid, str) or not isinstance(candidate_signature, str):
            raise DsseError("signature entry is malformed")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_keyid) is None:
            raise DsseError("signature key ID is malformed")
        if candidate_keyid in seen_keyids:
            raise DsseError("signature key IDs must be unique")
        seen_keyids.add(candidate_keyid)
        canonical_b64decode(candidate_signature, expected_length=64)
    entry = signatures[signature_index]
    if not isinstance(entry, dict):
        raise DsseError("signature entry is malformed")
    keyid = entry.get("keyid")
    signature_text = entry.get("sig")
    expected_keyid = keyid_from_spki(public_spki)
    if keyid != expected_keyid or not isinstance(signature_text, str):
        raise DsseError("signature key ID does not match the supplied public key")
    signature = canonical_b64decode(signature_text, expected_length=64)
    strict_verify_ed25519(public_key_from_spki(public_spki), signature, pae(payload_type, payload))
