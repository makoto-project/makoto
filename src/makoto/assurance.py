"""SLSA-shaped Makoto track and verified-property evaluation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from makoto.bundle import load_attestation
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.dsse import SigningKey, sign_envelope
from makoto.model import STATEMENT_PAYLOAD_TYPE, Attestation
from makoto.policy import TrustPolicy
from makoto.protocol import predicate_type
from makoto.schema import strict_json_loads, validate_core

VSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"
VSA_VERSION = "1.2"
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?Z$"
)

ORIGIN_LEVELS = (
    "MAKOTO_ORIGIN_LEVEL_1",
    "MAKOTO_ORIGIN_LEVEL_2",
    "MAKOTO_ORIGIN_LEVEL_3",
)
TRANSFORM_LEVELS = (
    "MAKOTO_TRANSFORM_LEVEL_1",
    "MAKOTO_TRANSFORM_LEVEL_2",
    "MAKOTO_TRANSFORM_LEVEL_3",
)
PROPERTIES = (
    "MAKOTO_AUTHORIZED",
    "MAKOTO_GRAPH_COMPLETE",
    "MAKOTO_FRESHNESS_ANCHORED",
    "MAKOTO_SCHEMA_CONFORMANT",
    "MAKOTO_REPRODUCED",
)


class AssuranceError(ValueError):
    """Raised when assurance evidence or configuration is malformed."""


@dataclass(frozen=True)
class EnvelopeEvidence:
    attestation: Attestation
    envelope_digest: str


@dataclass(frozen=True)
class RunEvidence:
    report: dict[str, Any]
    report_digest: str
    attestations: tuple[EnvelopeEvidence, ...]


@dataclass(frozen=True)
class VsaEvidence:
    statement: dict[str, Any]
    envelope: dict[str, Any]
    envelope_digest: str


@dataclass(frozen=True)
class ReproductionEvidence:
    run: RunEvidence
    assessments: tuple[VsaEvidence, ...]


@dataclass(frozen=True)
class SummaryEvaluation:
    subjects: tuple[dict[str, Any], ...]
    verified_levels: tuple[str, ...]
    diagnostics: tuple[str, ...]
    passed: bool


def resource_descriptor(uri: str, digest: str) -> dict[str, Any]:
    """Return the exact ResourceDescriptor subset used by Makoto v0.2."""

    _require_uri(uri, "resource URI")
    _require_digest(digest, "resource digest")
    return {"uri": uri, "digest": {"sha256": digest}}


def descriptor_for_bytes(uri: str, data: bytes) -> dict[str, Any]:
    return resource_descriptor(uri, sha256_bytes(data))


def create_assessment_vsa(
    *,
    track: str,
    level: int,
    subjects: Sequence[Mapping[str, Any]],
    input_attestations: Sequence[Mapping[str, Any]],
    verifier_id: str,
    resource_uri: str,
    policy: Mapping[str, Any],
    time_verified: str,
    signing_keys: SigningKey | Sequence[SigningKey],
    repository_root: Path,
    hardware_evidence: Sequence[Mapping[str, Any]] = (),
) -> dict[str, object]:
    """Create a signed assessment VSA without defining an attestation quote format."""

    if track not in {"origin", "transform"}:
        raise AssuranceError("assessment track must be origin or transform")
    if level not in {2, 3}:
        raise AssuranceError("assessment level must be 2 or 3")
    if track != "transform" and hardware_evidence:
        raise AssuranceError("hardware evidence is only valid for the Transform track")
    if track == "transform" and level == 3 and not hardware_evidence:
        raise AssuranceError("Transform L3 requires at least one hardware-evidence digest")
    verified_level = ORIGIN_LEVELS[level - 1] if track == "origin" else TRANSFORM_LEVELS[level - 1]
    statement = _vsa_statement(
        subjects=subjects,
        verifier_id=verifier_id,
        time_verified=time_verified,
        resource_uri=resource_uri,
        policy=policy,
        input_attestations=(*input_attestations, *hardware_evidence),
        verification_result="PASSED",
        verified_levels=(verified_level,),
    )
    validate_core("statement", statement, repository_root=repository_root)
    payload = canonical_json(statement)
    envelope = sign_envelope(STATEMENT_PAYLOAD_TYPE, payload, signing_keys)
    validate_core("envelope", envelope, repository_root=repository_root)
    return envelope


def create_summary_vsa(
    *,
    evaluation: SummaryEvaluation,
    run: RunEvidence,
    assessments: Sequence[VsaEvidence],
    reproductions: Sequence[ReproductionEvidence],
    verifier_id: str,
    resource_uri: str,
    policy: Mapping[str, Any],
    time_verified: str,
    signing_keys: SigningKey | Sequence[SigningKey],
    repository_root: Path,
) -> dict[str, object]:
    """Create the signed SLSA VSA that communicates one Makoto evaluation."""

    descriptors = [
        resource_descriptor(
            f"urn:makoto:verification-report:sha256:{run.report_digest}",
            run.report_digest,
        )
    ]
    descriptors.extend(
        resource_descriptor(f"urn:makoto:vsa:sha256:{item.envelope_digest}", item.envelope_digest)
        for item in assessments
    )
    for reproduction in reproductions:
        descriptors.append(
            resource_descriptor(
                f"urn:makoto:verification-report:sha256:{reproduction.run.report_digest}",
                reproduction.run.report_digest,
            )
        )
        descriptors.extend(
            resource_descriptor(
                f"urn:makoto:vsa:sha256:{item.envelope_digest}",
                item.envelope_digest,
            )
            for item in reproduction.assessments
        )
    descriptors = _sorted_descriptors(descriptors)
    statement = _vsa_statement(
        subjects=evaluation.subjects,
        verifier_id=verifier_id,
        time_verified=time_verified,
        resource_uri=resource_uri,
        policy=policy,
        input_attestations=descriptors,
        verification_result="PASSED" if evaluation.passed else "FAILED",
        verified_levels=evaluation.verified_levels if evaluation.passed else ("FAILED",),
    )
    validate_core("statement", statement, repository_root=repository_root)
    payload = canonical_json(statement)
    envelope = sign_envelope(STATEMENT_PAYLOAD_TYPE, payload, signing_keys)
    validate_core("envelope", envelope, repository_root=repository_root)
    return envelope


def load_run_evidence(
    report_path: Path, attestation_directory: Path, *, repository_root: Path
) -> RunEvidence:
    """Load an exact report and the statement envelopes it summarizes."""

    report_bytes = report_path.read_bytes()
    parsed = strict_json_loads(report_bytes)
    if not isinstance(parsed, dict):
        raise AssuranceError("verification report must be a JSON object")
    validate_core("verification-report", parsed, repository_root=repository_root)
    if attestation_directory.is_symlink() or not attestation_directory.is_dir():
        raise AssuranceError("attestation directory must be a real directory")
    evidence: list[EnvelopeEvidence] = []
    for path in sorted(attestation_directory.iterdir(), key=lambda item: item.name.encode()):
        if not path.name.endswith(".dsse.json"):
            continue
        raw = path.read_bytes()
        attestation = load_attestation(path, repository_root=repository_root)
        if attestation.statement["predicateType"] == VSA_PREDICATE_TYPE:
            continue
        evidence.append(EnvelopeEvidence(attestation, sha256_bytes(raw)))
    digests = [item.attestation.digest()["sha256"] for item in evidence]
    if len(digests) != len(set(digests)):
        raise AssuranceError("attestation directory contains duplicate payloads")
    report_digests = {
        item["digest"]["sha256"]
        for item in cast(list[dict[str, Any]], parsed["statements"])
        if item["predicateType"]
        in {
            predicate_type(parsed["reportVersion"], "origin"),
            predicate_type(parsed["reportVersion"], "transform"),
        }
    }
    if set(digests) != report_digests:
        raise AssuranceError("report statements do not exactly match supplied attestations")
    return RunEvidence(
        report=cast(dict[str, Any], parsed),
        report_digest=sha256_bytes(report_bytes),
        attestations=tuple(evidence),
    )


def load_vsa_evidence(path: Path, *, repository_root: Path) -> VsaEvidence:
    raw = path.read_bytes()
    attestation = load_attestation(path, repository_root=repository_root)
    if attestation.statement["predicateType"] != VSA_PREDICATE_TYPE:
        raise AssuranceError(f"assessment is not a SLSA v1 VSA: {path}")
    _validate_vsa_statement(attestation.statement)
    return VsaEvidence(
        statement=attestation.statement,
        envelope=cast(dict[str, Any], attestation.envelope),
        envelope_digest=sha256_bytes(raw),
    )


def evaluate_summary(
    *,
    run: RunEvidence,
    policy: TrustPolicy,
    assessments: Sequence[VsaEvidence] = (),
    reproductions: Sequence[ReproductionEvidence] = (),
) -> SummaryEvaluation:
    """Evaluate track levels and properties with closed, boolean rules."""

    configuration = policy.value.get("verificationSummary")
    if not isinstance(configuration, dict):
        raise AssuranceError("trust policy has no verificationSummary configuration")
    if run.report["policyDigest"] != policy.digest():
        raise AssuranceError("verification report policy digest does not match the policy")
    diagnostics: set[str] = set()
    check_status = {
        item["id"]: item["status"] for item in cast(list[dict[str, str]], run.report["checks"])
    }
    origin_level = _base_origin_level(run, check_status, diagnostics)
    transform_level = _base_transform_level(run, check_status, diagnostics)
    accepted = _accepted_assessments(run, assessments, policy, diagnostics)
    if origin_level >= 1:
        origin_level = max(origin_level, accepted["origin"][0])
    if transform_level >= 1:
        transform_level = max(transform_level, accepted["transform"][0])

    levels: list[str] = []
    if origin_level:
        levels.append(ORIGIN_LEVELS[origin_level - 1])
    if transform_level:
        levels.append(TRANSFORM_LEVELS[transform_level - 1])

    properties: list[str] = []
    if _authorized(run.report, check_status):
        properties.append("MAKOTO_AUTHORIZED")
    else:
        diagnostics.add("E_PROPERTY_AUTHORIZED")
    if _graph_complete(check_status):
        properties.append("MAKOTO_GRAPH_COMPLETE")
    else:
        diagnostics.add("E_PROPERTY_GRAPH_COMPLETE")
    if _freshness_anchored(run.report, check_status):
        properties.append("MAKOTO_FRESHNESS_ANCHORED")
    else:
        diagnostics.add("E_PROPERTY_FRESHNESS_ANCHORED")
    if _schema_conformant(run.report, policy, check_status):
        properties.append("MAKOTO_SCHEMA_CONFORMANT")
    else:
        diagnostics.add("E_PROPERTY_SCHEMA_CONFORMANT")
    if _reproduced(run, accepted["transform"][1], reproductions, policy):
        properties.append("MAKOTO_REPRODUCED")
    else:
        diagnostics.add("E_PROPERTY_REPRODUCED")

    verified = tuple(levels + properties)
    required = set(configuration.get("requiredVerifiedLevels", [])) | set(
        configuration.get("requiredProperties", [])
    )
    missing = sorted(
        (item for item in required if not _requirement_satisfied(item, verified)),
        key=str.encode,
    )
    if missing:
        diagnostics.add("E_REQUIRED_VERIFICATION_RESULT")
    passed = run.report["decision"] == "allow" and not missing
    if run.report["decision"] != "allow":
        diagnostics.add("E_REPORT_DENIED")
    return SummaryEvaluation(
        subjects=_final_subjects(run.report),
        verified_levels=verified,
        diagnostics=tuple(sorted(diagnostics, key=str.encode)),
        passed=passed,
    )


def _vsa_statement(
    *,
    subjects: Sequence[Mapping[str, Any]],
    verifier_id: str,
    time_verified: str,
    resource_uri: str,
    policy: Mapping[str, Any],
    input_attestations: Sequence[Mapping[str, Any]],
    verification_result: str,
    verified_levels: Sequence[str],
) -> dict[str, Any]:
    _require_uri(verifier_id, "verifier ID")
    _require_uri(resource_uri, "resource URI")
    _parse_timestamp(time_verified)
    _validate_policy_descriptor(policy)
    normalized_subjects = _sorted_subjects(subjects)
    normalized_inputs = _sorted_descriptors(input_attestations)
    predicate: dict[str, Any] = {
        "verifier": {"id": verifier_id},
        "timeVerified": time_verified,
        "resourceUri": resource_uri,
        "policy": dict(policy),
        "inputAttestations": normalized_inputs,
        "verificationResult": verification_result,
        "verifiedLevels": list(verified_levels),
        "dependencyLevels": {},
        "slsaVersion": VSA_VERSION,
    }
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": list(normalized_subjects),
        "predicateType": VSA_PREDICATE_TYPE,
        "predicate": predicate,
    }
    _validate_vsa_statement(statement)
    return statement


def _validate_vsa_statement(statement: Mapping[str, Any]) -> None:
    if statement.get("predicateType") != VSA_PREDICATE_TYPE:
        raise AssuranceError("VSA predicate type is invalid")
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        raise AssuranceError("VSA predicate must be an object")
    required = {
        "verifier",
        "timeVerified",
        "resourceUri",
        "policy",
        "inputAttestations",
        "verificationResult",
        "verifiedLevels",
        "dependencyLevels",
        "slsaVersion",
    }
    if not required.issubset(predicate):
        raise AssuranceError("VSA predicate is missing required SLSA fields")
    verifier = predicate["verifier"]
    if (
        not isinstance(verifier, dict)
        or "id" not in verifier
        or not set(verifier).issubset({"id", "version"})
        or (
            "version" in verifier
            and (
                not isinstance(verifier["version"], dict)
                or any(
                    not isinstance(key, str) or not isinstance(value, str)
                    for key, value in verifier["version"].items()
                )
            )
        )
    ):
        raise AssuranceError("VSA verifier identity is malformed")
    _require_uri(verifier["id"], "VSA verifier ID")
    _require_uri(predicate["resourceUri"], "VSA resource URI")
    _parse_timestamp(predicate["timeVerified"])
    _validate_policy_descriptor(predicate["policy"])
    if predicate["verificationResult"] not in {"PASSED", "FAILED"}:
        raise AssuranceError("VSA verificationResult is invalid")
    if predicate["slsaVersion"] != VSA_VERSION:
        raise AssuranceError("VSA slsaVersion must be 1.2")
    levels = predicate["verifiedLevels"]
    if not isinstance(levels, list) or any(not isinstance(item, str) for item in levels):
        raise AssuranceError("VSA verifiedLevels must be a string array")
    if levels != sorted(set(levels), key=_verified_level_sort_key):
        raise AssuranceError("VSA verifiedLevels must be sorted and unique")
    if (
        sum(item in ORIGIN_LEVELS for item in levels) > 1
        or sum(item in TRANSFORM_LEVELS for item in levels) > 1
    ):
        raise AssuranceError("VSA must contain at most one level per Makoto track")
    if predicate["verificationResult"] == "FAILED" and levels != ["FAILED"]:
        raise AssuranceError("a failed VSA must contain only FAILED in verifiedLevels")
    if predicate["verificationResult"] == "PASSED" and "FAILED" in levels:
        raise AssuranceError("a passed VSA cannot contain FAILED in verifiedLevels")
    dependency_levels = predicate["dependencyLevels"]
    if not isinstance(dependency_levels, dict) or any(
        not isinstance(key, str)
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for key, value in dependency_levels.items()
    ):
        raise AssuranceError("VSA dependencyLevels must contain nonnegative integer counts")
    _sorted_subjects(cast(Sequence[Mapping[str, Any]], statement["subject"]))
    _sorted_descriptors(cast(Sequence[Mapping[str, Any]], predicate["inputAttestations"]))


def _base_origin_level(run: RunEvidence, checks: Mapping[str, str], diagnostics: set[str]) -> int:
    required = ("parse-strictly", "core-schemas", "index-payloads", "signatures")
    origin_type = _run_predicate_type(run, "origin")
    origins = _track_evidence(run, origin_type)
    if not origins or any(checks.get(item) != "pass" for item in required):
        diagnostics.add("E_ORIGIN_LEVEL_1")
        return 0
    records = _report_records(run.report, origin_type)
    if any(item["coreSchema"] != "pass" for item in records):
        diagnostics.add("E_ORIGIN_LEVEL_1")
        return 0
    root_digests = {item["sha256"] for item in run.report["roots"]}
    origin_digests = {item.attestation.digest()["sha256"] for item in origins}
    if root_digests != origin_digests:
        diagnostics.add("E_ORIGIN_LEVEL_1")
        return 0
    return 1


def _base_transform_level(
    run: RunEvidence, checks: Mapping[str, str], diagnostics: set[str]
) -> int:
    transforms = _track_evidence(run, _run_predicate_type(run, "transform"))
    if not transforms:
        return 0
    required = (
        "core-schemas",
        "graph",
        "graph-dependency-artifacts",
        "roots-and-heads",
        "completeness-anchor",
    )
    if any(checks.get(item) != "pass" for item in required):
        diagnostics.add("E_TRANSFORM_LEVEL_1")
        return 0
    return 1


def _accepted_assessments(
    run: RunEvidence,
    assessments: Sequence[VsaEvidence],
    policy: TrustPolicy,
    diagnostics: set[str],
) -> dict[str, tuple[int, frozenset[str]]]:
    configuration = cast(dict[str, Any], policy.value["verificationSummary"])
    rules = cast(list[dict[str, Any]], configuration.get("verifiers", []))
    evaluation_time = _parse_timestamp(run.report["evaluationTime"])
    best = {"origin": 0, "transform": 0}
    groups: dict[str, set[str]] = {"origin": set(), "transform": set()}
    for evidence in assessments:
        predicate = evidence.statement["predicate"]
        matching = [
            rule
            for rule in rules
            if rule["verifierId"] == predicate["verifier"]["id"]
            and rule["resourceUri"] == predicate["resourceUri"]
            and rule["policy"] == predicate["policy"]
        ]
        if len(matching) != 1 or predicate["verificationResult"] != "PASSED":
            diagnostics.add("E_ASSESSMENT_TRUST")
            continue
        rule = matching[0]
        signatures = policy.verify_signatures(evidence.envelope, evaluation_time=evaluation_time)
        passing = {
            item.keyid
            for item in signatures
            if item.cryptographic == "pass"
            and item.keyid in rule["authorizedKeyIds"]
            and policy._key_valid_at(item.keyid, evaluation_time)
        }
        if len(passing) < rule["minimumSignatures"]:
            diagnostics.add("E_ASSESSMENT_SIGNATURE")
            continue
        claims = set(predicate["verifiedLevels"]).intersection(rule["allowedVerifiedLevels"])
        for track, levels, track_predicate_type in (
            ("origin", ORIGIN_LEVELS, _run_predicate_type(run, "origin")),
            ("transform", TRANSFORM_LEVELS, _run_predicate_type(run, "transform")),
        ):
            claimed = max((levels.index(item) + 1 for item in claims if item in levels), default=0)
            if claimed < 2:
                continue
            expected_subjects = _track_subjects(run, track_predicate_type)
            if tuple(evidence.statement["subject"]) != expected_subjects:
                diagnostics.add(f"E_{track.upper()}_ASSESSMENT_SUBJECTS")
                continue
            expected_inputs = {
                item.envelope_digest for item in _track_evidence(run, track_predicate_type)
            }
            if track == "origin" and claimed >= 3:
                expected_inputs.update(
                    item["digest"]["sha256"] for item in rule.get("requiredControlEvidence", [])
                )
            actual_inputs = {item["digest"]["sha256"] for item in predicate["inputAttestations"]}
            hardware_inputs: set[str] = set()
            if track == "transform" and claimed >= 3:
                hardware_inputs = actual_inputs - expected_inputs
                inputs_match = expected_inputs.issubset(actual_inputs)
            else:
                inputs_match = actual_inputs == expected_inputs
            if not inputs_match:
                diagnostics.add(f"E_{track.upper()}_ASSESSMENT_INPUTS")
                continue
            accepted_level = claimed
            if (
                track == "origin"
                and claimed >= 3
                and not _required_profiles_pass(run.report, rule.get("requiredProfiles", []))
            ):
                diagnostics.add("E_ORIGIN_LEVEL_3")
                accepted_level = 2
            if track == "transform" and claimed >= 3 and not hardware_inputs:
                diagnostics.add("E_TRANSFORM_LEVEL_3")
                accepted_level = 2
            best[track] = max(best[track], accepted_level)
            if accepted_level >= 2:
                groups[track].add(rule["independenceGroup"])
    for track in ("origin", "transform"):
        if best[track] < 2 and _track_evidence(run, _run_predicate_type(run, track)):
            diagnostics.add(f"E_{track.upper()}_LEVEL_2")
    return {track: (best[track], frozenset(groups[track])) for track in ("origin", "transform")}


def _authorized(report: Mapping[str, Any], checks: Mapping[str, str]) -> bool:
    return (
        all(
            checks.get(item) == "pass"
            for item in ("signatures", "authorization-thresholds", "authorization")
        )
        and report["handoff"]["authorization"] == "pass"
    )


def _graph_complete(checks: Mapping[str, str]) -> bool:
    return all(
        checks.get(item) == "pass"
        for item in (
            "index-payloads",
            "graph-dependency-artifacts",
            "graph",
            "roots-and-heads",
            "completeness-anchor",
        )
    )


def _freshness_anchored(report: Mapping[str, Any], checks: Mapping[str, str]) -> bool:
    freshness = report["handoff"]["freshnessChecks"]
    return checks.get("freshness-anchors") == "pass" and any(
        value == "pass" for value in freshness.values()
    )


def _schema_conformant(
    report: Mapping[str, Any], policy: TrustPolicy, checks: Mapping[str, str]
) -> bool:
    if any(
        checks.get(item) != "pass"
        for item in ("core-schemas", "metadata-profiles", "artifact-profiles")
    ):
        return False
    required: set[tuple[str, str, str, str]] = set()
    for item in policy.value["requiredProfiles"]:
        required.add(
            (item["id"], item["digest"]["sha256"], item["closureDigest"]["sha256"], item["target"])
        )
    for rule in policy.value["rules"]:
        for item in rule.get("profileConstraints", []):
            if "digest" in item:
                required.add(
                    (
                        item["id"],
                        item["digest"]["sha256"],
                        item["closureDigest"]["sha256"],
                        item["target"],
                    )
                )
    return bool(required) and _required_profiles_pass(report, required)


def _required_profiles_pass(
    report: Mapping[str, Any],
    required_profiles: Sequence[Mapping[str, Any]] | set[tuple[str, str, str, str]],
) -> bool:
    if isinstance(required_profiles, set):
        required = required_profiles
    else:
        required = {
            (
                item["id"],
                item["digest"]["sha256"],
                item["closureDigest"]["sha256"],
                item["target"],
            )
            for item in required_profiles
        }
    passing = {
        (
            item["id"],
            item["digest"]["sha256"],
            item["closureDigest"]["sha256"],
            item["target"],
        )
        for item in report["profiles"]
        if item["resolution"] == "pass" and item["validation"] == "pass"
    }
    return bool(required) and required.issubset(passing)


def _reproduced(
    primary: RunEvidence,
    primary_groups: frozenset[str],
    reproductions: Sequence[ReproductionEvidence],
    policy: TrustPolicy,
) -> bool:
    if primary.report["decision"] != "allow" or not primary_groups:
        return False
    primary_fingerprint = _run_fingerprint(primary)
    if primary_fingerprint is None:
        return False
    for candidate in reproductions:
        if candidate.run.report["policyDigest"] != policy.digest():
            continue
        diagnostics: set[str] = set()
        accepted = _accepted_assessments(candidate.run, candidate.assessments, policy, diagnostics)
        groups = accepted["transform"][1]
        if candidate.run.report["decision"] != "allow" or not groups:
            continue
        if not primary_groups.isdisjoint(groups):
            continue
        if _run_fingerprint(candidate.run) == primary_fingerprint:
            return True
    return False


def _run_fingerprint(run: RunEvidence) -> tuple[Any, ...] | None:
    roots: list[str] = []
    nodes: list[tuple[Any, ...]] = []
    for item in run.attestations:
        statement = item.attestation.statement
        if statement["predicateType"] == _run_predicate_type(run, "origin"):
            roots.extend(subject["digest"]["sha256"] for subject in statement["subject"])
            continue
        if statement["predicateType"] != _run_predicate_type(run, "transform"):
            continue
        predicate = statement["predicate"]
        operation = predicate["operation"]
        tool = operation.get("tool")
        parameters = operation.get("parametersDigest")
        if not isinstance(tool, dict) or "digest" not in tool or parameters is None:
            return None
        inputs = tuple(sorted(input_item["digest"]["sha256"] for input_item in predicate["inputs"]))
        outputs = tuple(_subject_pairs(statement["subject"]))
        nodes.append(
            (
                inputs,
                operation["type"],
                tool["digest"]["sha256"],
                parameters["sha256"],
                outputs,
            )
        )
    return (
        tuple(sorted(roots)),
        tuple(sorted(nodes)),
        tuple((item["name"], item["digest"]["sha256"]) for item in _final_subjects(run.report)),
    )


def _track_evidence(run: RunEvidence, predicate_type: str) -> tuple[EnvelopeEvidence, ...]:
    return tuple(
        item
        for item in run.attestations
        if item.attestation.statement["predicateType"] == predicate_type
    )


def _run_predicate_type(run: RunEvidence, track: str) -> str:
    return predicate_type(str(run.report["reportVersion"]), track)


def _track_subjects(run: RunEvidence, predicate_type: str) -> tuple[dict[str, Any], ...]:
    subjects: list[Mapping[str, Any]] = []
    for item in _track_evidence(run, predicate_type):
        subjects.extend(item.attestation.statement["subject"])
    return _sorted_subjects(subjects)


def _report_records(report: Mapping[str, Any], predicate_type: str) -> list[dict[str, Any]]:
    return [item for item in report["statements"] if item["predicateType"] == predicate_type]


def _final_subjects(report: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    subjects = [
        {"name": item["subjectName"], "digest": item["digest"]}
        for item in report["artifacts"]
        if item["lifecycleRole"] == "final" and item["digestStatus"] == "pass"
    ]
    if not subjects:
        subjects = [
            {"name": item["subjectName"], "digest": item["digest"]}
            for item in report["expectedArtifacts"]
        ]
    if not subjects:
        raise AssuranceError("report has no final subjects to summarize")
    return _sorted_subjects(subjects)


def _subject_pairs(subjects: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    return sorted((item["name"], item["digest"]["sha256"]) for item in subjects)


def _sorted_subjects(subjects: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for item in subjects:
        if set(item) != {"name", "digest"} or not isinstance(item["name"], str):
            raise AssuranceError("VSA subject is malformed")
        digest = item["digest"]
        if not isinstance(digest, dict) or set(digest) != {"sha256"}:
            raise AssuranceError("VSA subject digest is malformed")
        _require_digest(digest["sha256"], "VSA subject digest")
        normalized.append({"name": item["name"], "digest": {"sha256": digest["sha256"]}})
    normalized.sort(key=lambda item: (item["name"].encode(), item["digest"]["sha256"]))
    if not normalized:
        raise AssuranceError("VSA subjects must be nonempty")
    unique = {(item["name"], item["digest"]["sha256"]): item for item in normalized}
    return tuple(
        unique[key] for key in sorted(unique, key=lambda item: (item[0].encode(), item[1]))
    )


def _sorted_descriptors(
    descriptors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in descriptors:
        if set(item) != {"uri", "digest"}:
            raise AssuranceError("resource descriptor must contain exactly uri and digest")
        _require_uri(item["uri"], "resource descriptor URI")
        digest = item["digest"]
        if not isinstance(digest, dict) or set(digest) != {"sha256"}:
            raise AssuranceError("resource descriptor digest is malformed")
        _require_digest(digest["sha256"], "resource descriptor digest")
        normalized.append({"uri": item["uri"], "digest": {"sha256": digest["sha256"]}})
    normalized.sort(key=lambda item: (item["uri"].encode(), item["digest"]["sha256"]))
    identities = [(item["uri"], item["digest"]["sha256"]) for item in normalized]
    if len(identities) != len(set(identities)):
        raise AssuranceError("resource descriptors must be unique")
    return normalized


def _validate_policy_descriptor(policy: Any) -> None:
    if not isinstance(policy, dict) or set(policy) != {"uri", "digest"}:
        raise AssuranceError("VSA policy must contain exactly uri and digest")
    _require_uri(policy["uri"], "VSA policy URI")
    digest = policy["digest"]
    if not isinstance(digest, dict) or set(digest) != {"sha256"}:
        raise AssuranceError("VSA policy digest is malformed")
    _require_digest(digest["sha256"], "VSA policy digest")


def _verified_level_sort_key(value: str) -> tuple[int, int, bytes]:
    if value in ORIGIN_LEVELS:
        return (0, ORIGIN_LEVELS.index(value), b"")
    if value in TRANSFORM_LEVELS:
        return (1, TRANSFORM_LEVELS.index(value), b"")
    if value in PROPERTIES:
        return (2, PROPERTIES.index(value), b"")
    return (3, 0, value.encode())


def _requirement_satisfied(required: str, verified: Sequence[str]) -> bool:
    if required in ORIGIN_LEVELS:
        required_rank = ORIGIN_LEVELS.index(required)
        return any(
            item in ORIGIN_LEVELS and ORIGIN_LEVELS.index(item) >= required_rank
            for item in verified
        )
    if required in TRANSFORM_LEVELS:
        required_rank = TRANSFORM_LEVELS.index(required)
        return any(
            item in TRANSFORM_LEVELS and TRANSFORM_LEVELS.index(item) >= required_rank
            for item in verified
        )
    return required in verified


def _require_uri(value: Any, label: str) -> None:
    if not isinstance(value, str) or any(character.isspace() for character in value):
        raise AssuranceError(f"{label} must be an absolute URI")
    parsed = urlsplit(value)
    if not parsed.scheme or _URI_SCHEME.fullmatch(parsed.scheme) is None:
        raise AssuranceError(f"{label} must be an absolute URI")


def _require_digest(value: Any, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AssuranceError(f"{label} must be 64 lowercase hexadecimal characters")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise AssuranceError("VSA timestamp must be an RFC 3339 UTC timestamp")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(UTC)
    except ValueError as error:
        raise AssuranceError("VSA timestamp is invalid") from error
