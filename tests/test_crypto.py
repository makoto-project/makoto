from __future__ import annotations

import io

import pytest

from makoto.canonical import CanonicalizationError, canonical_json
from makoto.digest import digest_object, sha256_bytes, sha256_stream
from makoto.dsse import (
    DsseError,
    L,
    SignatureVerificationError,
    SigningKey,
    canonical_b64decode,
    keyid_from_spki,
    pae,
    sign_envelope,
    strict_verify_ed25519,
    verify_envelope_signature,
)


def test_exact_byte_sha256_streaming_matches_one_shot() -> None:
    data = b"source bytes\r\nwith exact newlines\n"
    assert sha256_stream(io.BytesIO(data), chunk_size=3) == sha256_bytes(data)
    assert digest_object(sha256_bytes(data)) == {"sha256": sha256_bytes(data)}
    assert sha256_bytes(data) != sha256_bytes(data.replace(b"\r\n", b"\n"))


def test_rfc8785_canonical_json() -> None:
    assert canonical_json({"z": 1, "a": "誠"}) == '{"a":"誠","z":1}'.encode()
    with pytest.raises(CanonicalizationError):
        canonical_json({"notFinite": float("nan")})


def test_dsse_pae_exact_bytes() -> None:
    assert pae("application/vnd.in-toto+json", b"{}") == (
        b"DSSEv1 28 application/vnd.in-toto+json 2 {}"
    )


def test_sign_and_strictly_verify_dsse_envelope() -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    payload = canonical_json({"_type": "https://in-toto.io/Statement/v1"})
    envelope = sign_envelope("application/vnd.in-toto+json", payload, key)
    assert envelope["signatures"] == [
        {
            "keyid": key.keyid(),
            "sig": envelope["signatures"][0]["sig"],  # type: ignore[index]
        }
    ]
    assert key.keyid() == keyid_from_spki(key.public_spki())
    verify_envelope_signature(envelope, public_spki=key.public_spki())


def test_multi_signatures_are_distinct_and_canonically_ordered() -> None:
    first = SigningKey.from_seed(bytes(range(32)))
    second = SigningKey.from_seed(bytes(reversed(range(32))))
    payload = b'{"source":"exact bytes"}'

    envelope = sign_envelope("application/vnd.in-toto+json", payload, [second, first])

    assert [item["keyid"] for item in envelope["signatures"]] == sorted(  # type: ignore[index]
        [first.keyid(), second.keyid()]
    )
    for key in (first, second):
        index = next(
            index
            for index, item in enumerate(envelope["signatures"])  # type: ignore[union-attr]
            if item["keyid"] == key.keyid()
        )
        verify_envelope_signature(envelope, public_spki=key.public_spki(), signature_index=index)


def test_multi_signing_rejects_empty_or_duplicate_keys() -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    with pytest.raises(DsseError, match="at least one"):
        sign_envelope("application/vnd.in-toto+json", b"{}", [])
    with pytest.raises(DsseError, match="unique"):
        sign_envelope("application/vnd.in-toto+json", b"{}", [key, key])


def test_rfc8032_first_ed25519_vector() -> None:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    public_key = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    signature = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    key = SigningKey.from_seed(seed)
    assert key.public_key_bytes() == public_key
    assert key.sign(b"") == signature
    strict_verify_ed25519(public_key, signature, b"")


def test_payload_mutation_invalidates_signature() -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    envelope = sign_envelope("application/vnd.in-toto+json", b'{"value":1}', key)
    envelope["payload"] = "eyJ2YWx1ZSI6Mn0="
    with pytest.raises(SignatureVerificationError):
        verify_envelope_signature(envelope, public_spki=key.public_spki())


def test_wrong_key_is_not_trial_verified() -> None:
    signer = SigningKey.from_seed(bytes(range(32)))
    other = SigningKey.from_seed(bytes(reversed(range(32))))
    envelope = sign_envelope("application/vnd.in-toto+json", b"{}", signer)
    with pytest.raises(DsseError, match="key ID"):
        verify_envelope_signature(envelope, public_spki=other.public_spki())


@pytest.mark.parametrize(
    "payload_type",
    ["text/plain", "Text/Plain", "application/json; charset=utf-8", "x/y", "☃/☃"],
)
def test_signing_rejects_malformed_or_unsupported_payload_types(payload_type: str) -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    with pytest.raises(DsseError, match="payload type"):
        sign_envelope(payload_type, b"{}", key)


def test_verifier_rejects_malformed_sibling_and_duplicate_key_ids() -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    envelope = sign_envelope("application/vnd.in-toto+json", b"{}", key)
    envelope["signatures"].append({"keyid": key.keyid(), "sig": "AB=="})  # type: ignore[union-attr]
    with pytest.raises(DsseError, match="unique|exactly 64"):
        verify_envelope_signature(envelope, public_spki=key.public_spki())


def test_noncanonical_scalar_is_rejected() -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    message = b"message"
    signature = key.sign(message)
    malformed = signature[:32] + L.to_bytes(32, "little")
    with pytest.raises(SignatureVerificationError, match="scalar"):
        strict_verify_ed25519(key.public_key_bytes(), malformed, message)


def test_identity_public_key_and_r_are_rejected() -> None:
    identity = b"\x01" + bytes(31)
    key = SigningKey.from_seed(bytes(range(32)))
    signature = key.sign(b"message")
    with pytest.raises(SignatureVerificationError, match="identity"):
        strict_verify_ed25519(identity, signature, b"message")
    with pytest.raises(SignatureVerificationError, match="identity"):
        strict_verify_ed25519(key.public_key_bytes(), identity + signature[32:], b"message")


@pytest.mark.parametrize("value", ["Zg", "Zg===", "Z g==", "Zh==", "-_=="])
def test_noncanonical_base64_is_rejected(value: str) -> None:
    with pytest.raises(DsseError):
        canonical_b64decode(value)
