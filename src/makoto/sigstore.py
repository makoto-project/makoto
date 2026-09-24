"""Sigstore keyless signing and offline verification for Makoto v0.3."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from sigstore import dsse as sigstore_dsse
from sigstore.errors import Error as SigstoreLibraryError
from sigstore.errors import VerificationError
from sigstore.models import Bundle, ClientTrustConfig, TrustedRoot
from sigstore.oidc import IdentityToken, detect_credential
from sigstore.sign import SigningContext
from sigstore.verify import Verifier
from sigstore.verify.policy import (
    AllOf,
    GitHubWorkflowRef,
    GitHubWorkflowRepository,
    GitHubWorkflowTrigger,
    Identity,
    VerificationPolicy,
)

from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.dsse import canonical_b64decode


class SigstoreError(ValueError):
    """Raised when Sigstore material or verification is invalid."""


def validate_identity(identity: Mapping[str, Any]) -> None:
    """Validate the closed keyless identity shape used by policy and signing."""

    required = {"type", "issuer", "subject"}
    if set(identity) not in (required, required | {"githubActions"}):
        raise SigstoreError("keyless identity has unknown or missing fields")
    if identity.get("type") != "sigstore":
        raise SigstoreError("keyless identity type must be sigstore")
    for field in ("issuer", "subject"):
        value = identity.get(field)
        if not isinstance(value, str) or not value:
            raise SigstoreError(f"keyless identity {field} must be a nonempty string")
    github = identity.get("githubActions")
    if github is not None:
        if not isinstance(github, Mapping) or set(github) != {
            "repository",
            "workflowRef",
            "event",
        }:
            raise SigstoreError("GitHub Actions identity constraint is malformed")
        if any(not isinstance(value, str) or not value for value in github.values()):
            raise SigstoreError("GitHub Actions identity values must be nonempty strings")


def identity_id(identity: Mapping[str, Any]) -> str:
    """Return the stable ID for an exact receiver identity constraint."""

    validate_identity(identity)
    return f"sha256:{sha256_bytes(canonical_json(dict(identity)))}"


def load_trusted_root(path: Path, *, expected_sha256: str) -> TrustedRoot:
    """Load receiver-supplied trust-root bytes after checking their policy pin."""

    try:
        exact_bytes = path.read_bytes()
    except OSError as error:
        raise SigstoreError(f"cannot read Sigstore trust root: {error}") from error
    if sha256_bytes(exact_bytes) != expected_sha256:
        raise SigstoreError("Sigstore trust-root digest does not match policy")
    try:
        return TrustedRoot.from_file(str(path))
    except SigstoreLibraryError as error:
        raise SigstoreError(f"invalid Sigstore trust root: {error}") from error


def verification_policy(identity: Mapping[str, Any]) -> VerificationPolicy:
    """Build exact issuer, subject, and optional GitHub Actions constraints."""

    validate_identity(identity)
    children: list[VerificationPolicy] = [
        Identity(identity=str(identity["subject"]), issuer=str(identity["issuer"]))
    ]
    github = identity.get("githubActions")
    if isinstance(github, Mapping):
        children.extend(
            (
                GitHubWorkflowRepository(str(github["repository"])),
                GitHubWorkflowRef(str(github["workflowRef"])),
                GitHubWorkflowTrigger(str(github["event"])),
            )
        )
    return children[0] if len(children) == 1 else AllOf(children=children)


def verify_keyless_signature(
    envelope: Mapping[str, Any],
    signature: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    trusted_root: TrustedRoot,
) -> None:
    """Verify one embedded bundle without network access."""

    if signature.get("keyid") != identity_id(identity):
        raise SigstoreError("keyless signature identity ID does not match policy")
    bundle_value = signature.get("sigstoreBundle")
    if not isinstance(bundle_value, Mapping):
        raise SigstoreError("keyless signature has no Sigstore bundle")
    try:
        bundle = Bundle.from_json(canonical_json(dict(bundle_value)))
        payload_type, payload = Verifier(trusted_root=trusted_root).verify_dsse(
            bundle, verification_policy(identity)
        )
    except (SigstoreLibraryError, ValueError) as error:
        raise SigstoreError(f"Sigstore verification failed: {error}") from error
    if payload_type != envelope.get("payloadType"):
        raise SigstoreError("Sigstore bundle payload type does not match envelope")
    outer_payload = envelope.get("payload")
    if not isinstance(outer_payload, str) or canonical_b64decode(outer_payload) != payload:
        raise SigstoreError("Sigstore bundle payload does not match envelope")
    bundle_json = cast(dict[str, Any], json.loads(bundle.to_json()))
    inner_signatures = bundle_json["dsseEnvelope"]["signatures"]
    if len(inner_signatures) != 1 or inner_signatures[0]["sig"] != signature.get("sig"):
        raise SigstoreError("Sigstore bundle signature does not match envelope")


def keyless_cosign_envelope(
    envelope: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    identity_token: str | None = None,
    staging: bool = False,
) -> dict[str, Any]:
    """Sign an in-toto DSSE envelope through Fulcio and Rekor."""

    validate_identity(identity)
    if envelope.get("payloadType") != "application/vnd.in-toto+json":
        raise SigstoreError("Sigstore keyless signing requires an in-toto statement envelope")
    payload_text = envelope.get("payload")
    if not isinstance(payload_text, str):
        raise SigstoreError("envelope payload is malformed")
    token = identity_token or detect_credential()
    if not token:
        raise SigstoreError("no ambient Sigstore OIDC identity token is available")
    trust_config = ClientTrustConfig.staging() if staging else ClientTrustConfig.production()
    context = SigningContext.from_trust_config(trust_config)
    try:
        with context.signer(IdentityToken(token), cache=False) as signer:
            bundle = signer.sign_dsse(sigstore_dsse.Statement(canonical_b64decode(payload_text)))
        verification_policy(identity).verify(bundle.signing_certificate)
    except (SigstoreLibraryError, VerificationError) as error:
        raise SigstoreError(f"Sigstore signing failed: {error}") from error
    bundle_json = cast(dict[str, Any], json.loads(bundle.to_json()))
    inner = bundle_json["dsseEnvelope"]
    if inner["payloadType"] != envelope["payloadType"] or inner["payload"] != payload_text:
        raise SigstoreError("Sigstore changed the envelope payload")
    signatures = inner["signatures"]
    if len(signatures) != 1:
        raise SigstoreError("Sigstore returned an unexpected signature count")
    result = dict(envelope)
    result_signatures = [dict(item) for item in cast(list[dict[str, Any]], envelope["signatures"])]
    signer_id = identity_id(identity)
    if any(item["keyid"] == signer_id for item in result_signatures):
        raise SigstoreError("envelope already contains this keyless identity")
    result_signatures.append(
        {
            "keyid": signer_id,
            "sig": signatures[0]["sig"],
            "sigstoreBundle": bundle_json,
        }
    )
    result["signatures"] = sorted(result_signatures, key=lambda item: item["keyid"].encode())
    return result
