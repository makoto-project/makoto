from __future__ import annotations

import base64
import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sigstore.models import Bundle

from makoto.canonical import canonical_json
from makoto.digest import digest_object, sha256_bytes
from makoto.dsse import SigningKey, canonical_b64encode, sign_envelope
from makoto.policy import TrustPolicy
from makoto.schema import CoreValidationError, validate_core
from makoto.sigstore import (
    SigstoreError,
    identity_id,
    load_trusted_root,
    verify_keyless_signature,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "testdata" / "v0.3" / "sigstore"
SUBJECT = (
    "https://github.com/sigstore-conformance/"
    "extremely-dangerous-public-oidc-beacon/.github/workflows/"
    "extremely-dangerous-oidc-beacon.yml@refs/heads/main"
)
IDENTITY: dict[str, Any] = {
    "type": "sigstore",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": SUBJECT,
    "githubActions": {
        "repository": "sigstore-conformance/extremely-dangerous-public-oidc-beacon",
        "workflowRef": "refs/heads/main",
        "event": "workflow_dispatch",
    },
}


def _limits() -> dict[str, int]:
    return {
        "maxBundleFiles": 10000,
        "maxMetadataBytes": 104857600,
        "maxArtifactBytesPerFile": 10737418240,
        "maxAggregateArtifactBytes": 53687091200,
        "maxSnapshotBytes": 53687091200,
        "maxArtifactValidationBytes": 104857600,
        "maxJsonDepth": 128,
        "maxJsonNumberChars": 1024,
        "maxJsonExponentMagnitude": 10000,
        "maxSchemaBytes": 2097152,
        "maxSchemaResources": 256,
        "maxSchemaEvaluationDepth": 256,
        "maxSchemaOperations": 10000000,
        "maxRegexLength": 4096,
        "profileEvaluationTimeoutSeconds": 5,
        "profileWorkerMemoryBytes": 536870912,
        "maxNdjsonLineBytes": 1048576,
        "maxSignaturesTotal": 10000,
        "maxProfileEvaluations": 10000,
        "maxDiagnostics": 10000,
        "maxReportRecords": 20000,
        "maxReportBytes": 67108864,
    }


def _bundle_value() -> dict[str, Any]:
    value = json.loads((FIXTURES / "dsse-bundle.json").read_bytes())
    assert isinstance(value, dict)
    return value


def _envelope(bundle_value: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle_value = bundle_value or _bundle_value()
    inner = bundle_value["dsseEnvelope"]
    return {
        "payloadType": inner["payloadType"],
        "payload": inner["payload"],
        "signatures": [
            {
                "keyid": identity_id(IDENTITY),
                "sig": inner["signatures"][0]["sig"],
                "sigstoreBundle": bundle_value,
            }
        ],
    }


def _policy() -> dict[str, Any]:
    signer_id = identity_id(IDENTITY)
    root_bytes = (FIXTURES / "trusted-root.json").read_bytes()
    return {
        "version": "0.3",
        "keys": {},
        "keylessIdentities": {signer_id: IDENTITY},
        "sigstoreTrustRoot": {
            "uri": "urn:makoto:test:sigstore-root",
            "digest": digest_object(sha256_bytes(root_bytes)),
        },
        "rules": [
            {
                "id": "urn:makoto:test:keyless",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.3/origin"],
                "authorizedIdentityIds": [signer_id],
                "minimumSignatures": 1,
            }
        ],
        "handoff": {
            "authorizedIdentityIds": [signer_id],
            "minimumSignatures": 1,
            "requireExpectedManifest": False,
            "requireExpectedHead": False,
            "requireExpectedArtifacts": False,
            "requireRecipient": False,
            "requireNonce": False,
            "allowReplayableHandoff": True,
        },
        "requiredProfiles": [],
        "limits": _limits(),
    }


def test_keyless_envelope_and_policy_validate() -> None:
    validate_core("envelope", _envelope(), repository_root=ROOT, protocol_version="0.3")
    validate_core("trust-policy", _policy(), repository_root=ROOT, protocol_version="0.3")
    with pytest.raises(CoreValidationError):
        validate_core("envelope", _envelope(), repository_root=ROOT, protocol_version="0.2")


def test_exact_identity_issuer_and_github_constraints() -> None:
    envelope = _envelope()
    root = load_trusted_root(
        FIXTURES / "trusted-root.json",
        expected_sha256=sha256_bytes((FIXTURES / "trusted-root.json").read_bytes()),
    )
    for field, value in (("issuer", "https://wrong.example"), ("subject", "https://wrong.example")):
        wrong = copy.deepcopy(IDENTITY)
        wrong[field] = value
        wrong_envelope = copy.deepcopy(envelope)
        wrong_envelope["signatures"][0]["keyid"] = identity_id(wrong)
        with pytest.raises(SigstoreError, match="verification failed"):
            verify_keyless_signature(
                wrong_envelope,
                wrong_envelope["signatures"][0],
                identity=wrong,
                trusted_root=root,
            )
    wrong_event = copy.deepcopy(IDENTITY)
    wrong_event["githubActions"]["event"] = "pull_request"
    wrong_envelope = copy.deepcopy(envelope)
    wrong_envelope["signatures"][0]["keyid"] = identity_id(wrong_event)
    with pytest.raises(SigstoreError, match="verification failed"):
        verify_keyless_signature(
            wrong_envelope,
            wrong_envelope["signatures"][0],
            identity=wrong_event,
            trusted_root=root,
        )


def test_recorded_bundle_verifies_offline() -> None:
    envelope = _envelope()
    root = load_trusted_root(
        FIXTURES / "trusted-root.json",
        expected_sha256=sha256_bytes((FIXTURES / "trusted-root.json").read_bytes()),
    )
    verify_keyless_signature(
        envelope,
        envelope["signatures"][0],
        identity=IDENTITY,
        trusted_root=root,
    )


def test_offline_wrapper_requires_exact_payload_and_bundle_signature(monkeypatch: Any) -> None:
    envelope = _envelope()
    payload = Bundle.from_json(
        (FIXTURES / "dsse-bundle.json").read_bytes()
    )._dsse_envelope._inner.payload

    def verified(_self: Any, _bundle: Any, _policy: Any) -> tuple[str, bytes]:
        return envelope["payloadType"], payload

    monkeypatch.setattr("makoto.sigstore.Verifier.verify_dsse", verified)
    root = load_trusted_root(
        FIXTURES / "trusted-root.json",
        expected_sha256=sha256_bytes((FIXTURES / "trusted-root.json").read_bytes()),
    )
    verify_keyless_signature(
        envelope,
        envelope["signatures"][0],
        identity=IDENTITY,
        trusted_root=root,
    )
    envelope["payload"] = canonical_b64encode(b"tampered")
    with pytest.raises(SigstoreError, match="payload"):
        verify_keyless_signature(
            envelope,
            envelope["signatures"][0],
            identity=IDENTITY,
            trusted_root=root,
        )


def test_tampered_log_entry_is_rejected() -> None:
    value = _bundle_value()
    body = value["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"]
    value["verificationMaterial"]["tlogEntries"][0]["canonicalizedBody"] = (
        "A" if body[0] != "A" else "B"
    ) + body[1:]
    envelope = _envelope(value)
    root = load_trusted_root(
        FIXTURES / "trusted-root.json",
        expected_sha256=sha256_bytes((FIXTURES / "trusted-root.json").read_bytes()),
    )
    with pytest.raises(SigstoreError, match="verification failed"):
        verify_keyless_signature(
            envelope,
            envelope["signatures"][0],
            identity=IDENTITY,
            trusted_root=root,
        )


def test_expired_certificate_without_valid_log_time_is_rejected() -> None:
    value = _bundle_value()
    value["verificationMaterial"]["tlogEntries"][0]["integratedTime"] = "0"
    envelope = _envelope(value)
    root = load_trusted_root(
        FIXTURES / "trusted-root.json",
        expected_sha256=sha256_bytes((FIXTURES / "trusted-root.json").read_bytes()),
    )
    with pytest.raises(SigstoreError, match="verification failed"):
        verify_keyless_signature(
            envelope,
            envelope["signatures"][0],
            identity=IDENTITY,
            trusted_root=root,
        )


def test_trust_root_must_be_receiver_supplied(monkeypatch: Any) -> None:
    policy = TrustPolicy.from_bytes(canonical_json(_policy()), repository_root=ROOT)
    result = policy.verify_signatures(_envelope(), evaluation_time=datetime.now(UTC))
    assert result[0].key_known is True
    assert result[0].cryptographic == "fail"


def test_ed25519_and_keyless_signers_can_share_a_threshold(monkeypatch: Any) -> None:
    key = SigningKey.from_seed(bytes(range(32)))
    bundle = _bundle_value()
    inner = bundle["dsseEnvelope"]
    envelope = sign_envelope(inner["payloadType"], base64.b64decode(inner["payload"]), key)
    signer_id = identity_id(IDENTITY)
    envelope["signatures"].append(
        {
            "keyid": signer_id,
            "sig": inner["signatures"][0]["sig"],
            "sigstoreBundle": bundle,
        }
    )
    envelope["signatures"].sort(key=lambda item: item["keyid"].encode())
    value = _policy()
    value["keys"] = {
        key.keyid(): {"type": "ed25519", "publicKey": canonical_b64encode(key.public_spki())}
    }
    value["rules"][0]["authorizedKeyIds"] = [key.keyid()]
    value["rules"][0]["minimumSignatures"] = 2
    monkeypatch.setattr("makoto.policy.verify_keyless_signature", lambda *args, **kwargs: None)
    policy = TrustPolicy.from_bytes(
        canonical_json(value),
        repository_root=ROOT,
        sigstore_trust_root_path=FIXTURES / "trusted-root.json",
    )
    statement = {"predicateType": "https://usemakoto.dev/predicate/v0.3/origin", "predicate": {}}
    result = policy.authorize_statement(
        statement,
        envelope,
        evaluation_time=datetime.now(UTC),
    )
    assert result.candidate_rule_ids == ("urn:makoto:test:keyless",)
