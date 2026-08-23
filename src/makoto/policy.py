"""Consumer-owned trust-policy parsing and authorization decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from makoto.digest import digest_object, sha256_bytes
from makoto.dsse import (
    DsseError,
    SignatureVerificationError,
    canonical_b64decode,
    spki_from_pem,
    strict_verify_ed25519,
)
from makoto.schema import strict_json_loads, validate_core


class PolicyError(ValueError):
    """Raised when policy configuration or authorization fails."""


@dataclass(frozen=True)
class SignatureResult:
    keyid: str
    key_known: bool
    cryptographic: str


@dataclass(frozen=True)
class AuthorizationResult:
    signatures: tuple[SignatureResult, ...]
    candidate_rule_ids: tuple[str, ...]
    authorizing_rule_ids: tuple[str, ...]

    @property
    def authorized(self) -> bool:
        return bool(self.authorizing_rule_ids)


@dataclass(frozen=True)
class TrustPolicy:
    value: dict[str, Any]
    exact_bytes: bytes
    public_keys: Mapping[str, bytes]

    @classmethod
    def from_bytes(cls, data: bytes, *, repository_root: Path) -> TrustPolicy:
        parsed = strict_json_loads(data)
        if not isinstance(parsed, dict):
            raise PolicyError("trust policy must be a JSON object")
        validate_core("trust-policy", parsed, repository_root=repository_root)
        policy = cast(dict[str, Any], parsed)
        public_keys: dict[str, bytes] = {}
        for keyid, key in policy["keys"].items():
            try:
                public_keys[keyid] = canonical_b64decode(key["publicKey"], expected_length=44)
            except DsseError as error:
                raise PolicyError(f"invalid configured key {keyid!r}") from error
        return cls(value=policy, exact_bytes=data, public_keys=public_keys)

    @classmethod
    def from_path(cls, path: Path, *, repository_root: Path) -> TrustPolicy:
        return cls.from_bytes(path.read_bytes(), repository_root=repository_root)

    def digest(self) -> dict[str, str]:
        return digest_object(sha256_bytes(self.exact_bytes))

    def _key_valid_at(self, keyid: str, evaluation_time: datetime) -> bool:
        key = self.value["keys"][keyid]
        valid_from = key.get("validFrom")
        valid_until = key.get("validUntil")
        if valid_from is not None and evaluation_time < _parse_timestamp(valid_from):
            return False
        return not (valid_until is not None and evaluation_time >= _parse_timestamp(valid_until))

    def verify_signatures(
        self,
        envelope: Mapping[str, Any],
        *,
        evaluation_time: datetime,
    ) -> tuple[SignatureResult, ...]:
        payload_type = envelope["payloadType"]
        payload = canonical_b64decode(envelope["payload"])
        from makoto.dsse import pae, public_key_from_spki

        message = pae(payload_type, payload)
        results: list[SignatureResult] = []
        for signature in envelope["signatures"]:
            keyid = signature["keyid"]
            if keyid not in self.public_keys:
                results.append(SignatureResult(keyid, False, "not_checked"))
                continue
            signature_bytes = canonical_b64decode(signature["sig"], expected_length=64)
            try:
                strict_verify_ed25519(
                    public_key_from_spki(self.public_keys[keyid]), signature_bytes, message
                )
            except SignatureVerificationError:
                results.append(SignatureResult(keyid, True, "fail"))
            else:
                results.append(SignatureResult(keyid, True, "pass"))
        return tuple(results)

    def authorize_statement(
        self,
        statement: Mapping[str, Any],
        envelope: Mapping[str, Any],
        *,
        evaluation_time: datetime,
    ) -> AuthorizationResult:
        signatures = self.verify_signatures(envelope, evaluation_time=evaluation_time)
        passing_keyids = {
            result.keyid
            for result in signatures
            if result.cryptographic == "pass" and self._key_valid_at(result.keyid, evaluation_time)
        }
        selected = [rule for rule in self.value["rules"] if _rule_matches(rule, statement)]
        candidates: list[str] = []
        for rule in selected:
            counted = passing_keyids.intersection(rule["authorizedKeyIds"])
            if len(counted) < rule["minimumSignatures"]:
                continue
            candidates.append(rule["id"])
        return AuthorizationResult(
            signatures=signatures,
            candidate_rule_ids=tuple(sorted(candidates, key=str.encode)),
            authorizing_rule_ids=(),
        )

    def authorization_profile_requirements(
        self,
        statement: Mapping[str, Any],
        result: AuthorizationResult,
    ) -> dict[tuple[str, str, str, str], tuple[str, ...]]:
        """Return exact digest-pinned profile requirements for candidate rules."""

        profiles = statement["predicate"].get("profiles", [])
        rules_by_id = {rule["id"]: rule for rule in self.value["rules"]}
        required: dict[tuple[str, str, str, str], set[str]] = {}
        for rule_id in result.candidate_rule_ids:
            for constraint in rules_by_id[rule_id].get("profileConstraints", []):
                if "digest" not in constraint:
                    continue
                for profile in profiles:
                    if _profile_constraint_matches(constraint, [profile]):
                        identity = (
                            profile["id"],
                            profile["digest"]["sha256"],
                            profile["closureDigest"]["sha256"],
                            profile["target"],
                        )
                        required.setdefault(identity, set()).add(rule_id)
        return {
            identity: tuple(sorted(rule_ids, key=str.encode))
            for identity, rule_ids in required.items()
        }

    def finalize_statement_authorization(
        self,
        statement: Mapping[str, Any],
        result: AuthorizationResult,
        profile_states: Mapping[tuple[str, str, str, str], str],
    ) -> AuthorizationResult:
        """Apply Step 7 digest-pinned profile outcomes to Step 6 candidates."""

        profiles = statement["predicate"].get("profiles", [])
        rules_by_id = {rule["id"]: rule for rule in self.value["rules"]}
        authorized: list[str] = []
        for rule_id in result.candidate_rule_ids:
            passed = True
            for constraint in rules_by_id[rule_id].get("profileConstraints", []):
                if "digest" not in constraint:
                    continue
                matching = [
                    profile
                    for profile in profiles
                    if _profile_constraint_matches(constraint, [profile])
                ]
                if not matching:
                    passed = False
                    break
                profile = matching[0]
                identity = (
                    profile["id"],
                    profile["digest"]["sha256"],
                    profile["closureDigest"]["sha256"],
                    profile["target"],
                )
                if profile_states.get(identity) != "pass":
                    passed = False
                    break
            if passed:
                authorized.append(rule_id)
        return AuthorizationResult(
            signatures=result.signatures,
            candidate_rule_ids=result.candidate_rule_ids,
            authorizing_rule_ids=tuple(sorted(authorized, key=str.encode)),
        )

    def authorize_handoff(
        self,
        envelope: Mapping[str, Any],
        *,
        evaluation_time: datetime,
    ) -> tuple[tuple[SignatureResult, ...], bool]:
        signatures = self.verify_signatures(envelope, evaluation_time=evaluation_time)
        passing = {
            result.keyid
            for result in signatures
            if result.cryptographic == "pass" and self._key_valid_at(result.keyid, evaluation_time)
        }
        rule = self.value["handoff"]
        authorized = (
            len(passing.intersection(rule["authorizedKeyIds"])) >= rule["minimumSignatures"]
        )
        return signatures, authorized


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _rule_matches(rule: Mapping[str, Any], statement: Mapping[str, Any]) -> bool:
    predicate_type = statement["predicateType"]
    if predicate_type not in rule["predicateTypes"]:
        return False
    predicate = statement["predicate"]
    if "sourceKinds" in rule:
        source = predicate.get("source", {})
        if source.get("kind") not in rule["sourceKinds"]:
            return False
    if "sourceUris" in rule:
        source = predicate.get("source", {})
        if source.get("uri") not in rule["sourceUris"]:
            return False
    if "operationTypes" in rule:
        operation = predicate.get("operation", {})
        if operation.get("type") not in rule["operationTypes"]:
            return False
    profiles = predicate.get("profiles", [])
    return all(
        _profile_constraint_matches(constraint, profiles)
        for constraint in rule.get("profileConstraints", [])
    )


def _profile_constraint_matches(
    constraint: Mapping[str, Any], profiles: list[Mapping[str, Any]]
) -> bool:
    for profile in profiles:
        if profile["id"] != constraint["id"] or profile["target"] != constraint["target"]:
            continue
        if "digest" in constraint and profile["digest"] != constraint["digest"]:
            continue
        if (
            "closureDigest" in constraint
            and profile["closureDigest"] != constraint["closureDigest"]
        ):
            continue
        return True
    return False


def public_spki_der_from_pem(path: Path) -> bytes:
    """Load and strictly inspect one public key for CLI use."""

    return spki_from_pem(path.read_bytes())
