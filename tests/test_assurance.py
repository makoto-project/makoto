from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from makoto import cli
from makoto.assurance import (
    ORIGIN_LEVELS,
    TRANSFORM_LEVELS,
    EnvelopeEvidence,
    ReproductionEvidence,
    RunEvidence,
    SummaryEvaluation,
    VsaEvidence,
    create_assessment_vsa,
    create_summary_vsa,
    descriptor_for_bytes,
    evaluate_summary,
    resource_descriptor,
)
from makoto.bundle import load_attestation
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.dsse import (
    SigningKey,
    canonical_b64decode,
    canonical_b64encode,
    sign_envelope,
    verify_envelope_signature,
)
from makoto.model import Attestation
from makoto.policy import TrustPolicy
from makoto.schema import strict_json_loads, validate_core

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demos" / "v0.2-end-to-end" / "generated"
NEGATIVE = ROOT / "testdata" / "v0.2" / "assurance" / "negative"
ASSESSOR_A = SigningKey.from_seed(bytes([21]) * 32)
ASSESSOR_B = SigningKey.from_seed(bytes([22]) * 32)
SUMMARY_KEY = SigningKey.from_seed(bytes([23]) * 32)
TIME = "2026-09-16T20:00:00Z"
PROFILE_REFERENCE = strict_json_loads(
    (ROOT / "docs" / "profiles" / "origin-l3-reference-v1.profile.json").read_bytes()
)
assert isinstance(PROFILE_REFERENCE, dict)


def _descriptor(uri: str, character: str) -> dict[str, Any]:
    return resource_descriptor(uri, character * 64)


def _policy(*, required_levels: list[str] | None = None) -> TrustPolicy:
    value = strict_json_loads((DEMO / "receiver" / "policy.json").read_bytes())
    assert isinstance(value, dict)
    for key, label in ((ASSESSOR_A, "assessor a"), (ASSESSOR_B, "assessor b")):
        value["keys"][key.keyid()] = {
            "type": "ed25519",
            "publicKey": canonical_b64encode(key.public_spki()),
            "label": label,
        }
    value["keys"] = dict(sorted(value["keys"].items(), key=lambda item: item[0].encode()))
    profile_pin = {
        field: PROFILE_REFERENCE[field] for field in ("id", "digest", "closureDigest", "target")
    }
    value["verificationSummary"] = {
        "resourceUri": "urn:makoto:test:handoff",
        "summaryPolicy": _descriptor("urn:makoto:test:summary-policy", "a"),
        "requiredVerifiedLevels": sorted(required_levels or [], key=str.encode),
        "requiredProperties": [
            "MAKOTO_AUTHORIZED",
            "MAKOTO_FRESHNESS_ANCHORED",
            "MAKOTO_GRAPH_COMPLETE",
            "MAKOTO_SCHEMA_CONFORMANT",
        ],
        "verifiers": [
            {
                "id": "urn:makoto:test:verifier:origin-a",
                "verifierId": "urn:makoto:test:platform:capture-a",
                "authorizedKeyIds": [ASSESSOR_A.keyid()],
                "minimumSignatures": 1,
                "policy": _descriptor("urn:makoto:test:origin-policy", "b"),
                "resourceUri": "urn:makoto:test:origin-resource",
                "allowedVerifiedLevels": [ORIGIN_LEVELS[1], ORIGIN_LEVELS[2]],
                "independenceGroup": "capture-a",
                "requiredProfiles": [profile_pin],
            },
            {
                "id": "urn:makoto:test:verifier:transform-a",
                "verifierId": "urn:makoto:test:platform:transform-a",
                "authorizedKeyIds": [ASSESSOR_A.keyid()],
                "minimumSignatures": 1,
                "policy": _descriptor("urn:makoto:test:transform-policy-a", "c"),
                "resourceUri": "urn:makoto:test:transform-resource",
                "allowedVerifiedLevels": [TRANSFORM_LEVELS[1], TRANSFORM_LEVELS[2]],
                "independenceGroup": "transform-a",
            },
            {
                "id": "urn:makoto:test:verifier:transform-b",
                "verifierId": "urn:makoto:test:platform:transform-b",
                "authorizedKeyIds": [ASSESSOR_B.keyid()],
                "minimumSignatures": 1,
                "policy": _descriptor("urn:makoto:test:transform-policy-b", "d"),
                "resourceUri": "urn:makoto:test:transform-resource",
                "allowedVerifiedLevels": [TRANSFORM_LEVELS[1], TRANSFORM_LEVELS[2]],
                "independenceGroup": "transform-b",
            },
        ],
    }
    raw = canonical_json(value) + b"\n"
    return TrustPolicy.from_bytes(raw, repository_root=ROOT)


def _run(policy: TrustPolicy, mutation: str | None = None) -> RunEvidence:
    report = strict_json_loads((DEMO / "reports" / "positive.json").read_bytes())
    assert isinstance(report, dict)
    report = copy.deepcopy(report)
    report["policyDigest"] = policy.digest()
    if mutation == "origin-core-schema-fail":
        next(item for item in report["statements"] if item["predicateType"].endswith("/origin"))[
            "coreSchema"
        ] = "fail"
    elif mutation == "graph-check-fail":
        _check(report, "graph")["status"] = "fail"
    elif mutation == "authorization-check-fail":
        _check(report, "authorization")["status"] = "fail"
    elif mutation == "completeness-anchor-fail":
        _check(report, "completeness-anchor")["status"] = "fail"
    elif mutation == "freshness-unanchored":
        _check(report, "freshness-anchors")["status"] = "fail"
        report["handoff"]["freshnessChecks"] = {
            key: "not_checked" for key in report["handoff"]["freshnessChecks"]
        }
    elif mutation == "required-profile-fail":
        report["profiles"][0]["validation"] = "fail"
    raw_report = canonical_json(report) + b"\n"
    attestation_directory = DEMO / "positive-bundle" / "attestations"
    evidence: list[EnvelopeEvidence] = []
    for path in sorted(attestation_directory.iterdir(), key=lambda item: item.name.encode()):
        raw = path.read_bytes()
        evidence.append(
            EnvelopeEvidence(load_attestation(path, repository_root=ROOT), sha256_bytes(raw))
        )
    return RunEvidence(
        report=report,
        report_digest=sha256_bytes(raw_report),
        attestations=tuple(evidence),
    )


def _check(report: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(item for item in report["checks"] if item["id"] == check_id)


def _reproducible_run(run: RunEvidence, *, tool_digest: str = "7") -> RunEvidence:
    evidence: list[EnvelopeEvidence] = []
    for item in run.attestations:
        statement = copy.deepcopy(item.attestation.statement)
        if statement["predicateType"].endswith("/transform"):
            statement["predicate"]["operation"]["tool"] = {"digest": {"sha256": tool_digest * 64}}
            statement["predicate"]["operation"]["parametersDigest"] = {"sha256": "8" * 64}
        evidence.append(
            EnvelopeEvidence(
                Attestation(
                    statement=statement,
                    payload=item.attestation.payload,
                    envelope=item.attestation.envelope,
                ),
                item.envelope_digest,
            )
        )
    return RunEvidence(run.report, run.report_digest, tuple(evidence))


def _assessment(
    run: RunEvidence,
    *,
    track: str,
    level: int,
    platform: str = "a",
    hardware: bool = True,
) -> VsaEvidence:
    predicate_type = (
        "https://usemakoto.dev/predicate/v0.2/origin"
        if track == "origin"
        else "https://usemakoto.dev/predicate/v0.2/transform"
    )
    selected = [
        item
        for item in run.attestations
        if item.attestation.statement["predicateType"] == predicate_type
    ]
    subjects = [subject for item in selected for subject in item.attestation.statement["subject"]]
    inputs = [
        resource_descriptor(
            f"urn:makoto:attestation:sha256:{item.envelope_digest}",
            item.envelope_digest,
        )
        for item in selected
    ]
    if track == "origin":
        verifier_id = "urn:makoto:test:platform:capture-a"
        resource_uri = "urn:makoto:test:origin-resource"
        policy = _descriptor("urn:makoto:test:origin-policy", "b")
        key = ASSESSOR_A
    else:
        verifier_id = f"urn:makoto:test:platform:transform-{platform}"
        resource_uri = "urn:makoto:test:transform-resource"
        policy = _descriptor(
            f"urn:makoto:test:transform-policy-{platform}",
            "c" if platform == "a" else "d",
        )
        key = ASSESSOR_A if platform == "a" else ASSESSOR_B
    hardware_evidence = (
        [_descriptor("urn:makoto:test:hardware-quote", "e")]
        if track == "transform" and level == 3 and hardware
        else []
    )
    actual_level = 2 if track == "transform" and level == 3 and not hardware else level
    envelope = create_assessment_vsa(
        track=track,
        level=actual_level,
        subjects=subjects,
        input_attestations=inputs,
        verifier_id=verifier_id,
        resource_uri=resource_uri,
        policy=policy,
        time_verified=TIME,
        signing_keys=key,
        repository_root=ROOT,
        hardware_evidence=hardware_evidence,
    )
    if track == "transform" and level == 3 and not hardware:
        payload = strict_json_loads(canonical_b64decode(envelope["payload"]))
        assert isinstance(payload, dict)
        payload["predicate"]["verifiedLevels"] = [TRANSFORM_LEVELS[2]]
        payload["predicate"].pop("extensions", None)
        envelope = sign_envelope("application/vnd.in-toto+json", canonical_json(payload), key)
    raw = canonical_json(envelope) + b"\n"
    statement = strict_json_loads(canonical_b64decode(envelope["payload"]))
    assert isinstance(statement, dict)
    return VsaEvidence(statement, envelope, sha256_bytes(raw))


def test_assurance_policy_and_signed_summary_are_interoperable() -> None:
    policy = _policy(required_levels=[ORIGIN_LEVELS[1], TRANSFORM_LEVELS[2]])
    run = _run(policy)
    assessments = (
        _assessment(run, track="origin", level=2),
        _assessment(run, track="transform", level=3),
    )

    evaluation = evaluate_summary(run=run, policy=policy, assessments=assessments)

    assert evaluation.passed
    assert evaluation.verified_levels == (
        ORIGIN_LEVELS[1],
        TRANSFORM_LEVELS[2],
        "MAKOTO_AUTHORIZED",
        "MAKOTO_GRAPH_COMPLETE",
        "MAKOTO_FRESHNESS_ANCHORED",
        "MAKOTO_SCHEMA_CONFORMANT",
    )
    envelope = create_summary_vsa(
        evaluation=evaluation,
        run=run,
        assessments=assessments,
        reproductions=(),
        verifier_id="urn:makoto:test:summary-verifier",
        resource_uri=policy.value["verificationSummary"]["resourceUri"],
        policy=policy.value["verificationSummary"]["summaryPolicy"],
        time_verified=TIME,
        signing_keys=SUMMARY_KEY,
        repository_root=ROOT,
    )
    verify_envelope_signature(envelope, public_spki=SUMMARY_KEY.public_spki())
    statement = strict_json_loads(canonical_b64decode(envelope["payload"]))
    assert isinstance(statement, dict)
    assert statement["predicateType"] == "https://slsa.dev/verification_summary/v1"
    assert statement["predicate"]["verificationResult"] == "PASSED"
    assert statement["predicate"]["slsaVersion"] == "1.2"


def test_transform_l3_assessment_carries_raw_hardware_evidence_digest() -> None:
    policy = _policy()
    assessment = _assessment(_run(policy), track="transform", level=3)
    assert (
        _descriptor("urn:makoto:test:hardware-quote", "e")
        in assessment.statement["predicate"]["inputAttestations"]
    )


def test_strict_reproduction_rejects_reused_independence_group() -> None:
    policy = _policy()
    run = _run(policy)
    transform = _assessment(run, track="transform", level=2)
    reproduction = ReproductionEvidence(run=run, assessments=(transform,))

    evaluation = evaluate_summary(
        run=run,
        policy=policy,
        assessments=(transform,),
        reproductions=(reproduction,),
    )

    assert "MAKOTO_REPRODUCED" not in evaluation.verified_levels
    assert "E_PROPERTY_REPRODUCED" in evaluation.diagnostics


def test_strict_reproduction_requires_identical_complete_node_multiset() -> None:
    policy = _policy()
    primary = _reproducible_run(_run(policy))
    secondary = _reproducible_run(_run(policy))
    primary_assessment = _assessment(primary, track="transform", level=2, platform="a")
    secondary_assessment = _assessment(secondary, track="transform", level=2, platform="b")

    matched = evaluate_summary(
        run=primary,
        policy=policy,
        assessments=(primary_assessment,),
        reproductions=(ReproductionEvidence(secondary, (secondary_assessment,)),),
    )
    assert "MAKOTO_REPRODUCED" in matched.verified_levels

    changed = _reproducible_run(_run(policy), tool_digest="9")
    changed_assessment = _assessment(changed, track="transform", level=2, platform="b")
    mismatched = evaluate_summary(
        run=primary,
        policy=policy,
        assessments=(primary_assessment,),
        reproductions=(ReproductionEvidence(changed, (changed_assessment,)),),
    )
    assert "MAKOTO_REPRODUCED" not in mismatched.verified_levels


@pytest.mark.parametrize(
    "fixture_path", sorted(NEGATIVE.glob("*.json"), key=lambda path: path.name.encode())
)
def test_negative_assurance_fixture(fixture_path: Path) -> None:
    fixture = strict_json_loads(fixture_path.read_bytes())
    assert isinstance(fixture, dict)
    policy = _policy()
    mutation = fixture["mutation"]
    report_mutation = (
        mutation
        if mutation
        in {
            "origin-core-schema-fail",
            "graph-check-fail",
            "authorization-check-fail",
            "completeness-anchor-fail",
            "freshness-unanchored",
            "required-profile-fail",
        }
        else None
    )
    run = _run(policy, report_mutation)
    assessments: tuple[VsaEvidence, ...] = ()
    reproductions: tuple[ReproductionEvidence, ...] = ()
    if mutation == "required-profile-missing":
        assessments = (_assessment(run, track="origin", level=3),)
    elif mutation == "hardware-evidence-missing":
        assessments = (_assessment(run, track="transform", level=3, hardware=False),)
    elif mutation == "independence-group-reused":
        assessment = _assessment(run, track="transform", level=2)
        assessments = (assessment,)
        reproductions = (ReproductionEvidence(run=run, assessments=(assessment,)),)

    evaluation = evaluate_summary(
        run=run,
        policy=policy,
        assessments=assessments,
        reproductions=reproductions,
    )

    assert fixture["expectedDiagnostic"] in evaluation.diagnostics
    assert fixture["target"] not in evaluation.verified_levels


def test_all_levels_and_properties_have_one_negative_fixture() -> None:
    targets = {strict_json_loads(path.read_bytes())["target"] for path in NEGATIVE.glob("*.json")}
    assert targets == {
        *ORIGIN_LEVELS,
        *TRANSFORM_LEVELS,
        "MAKOTO_AUTHORIZED",
        "MAKOTO_GRAPH_COMPLETE",
        "MAKOTO_FRESHNESS_ANCHORED",
        "MAKOTO_SCHEMA_CONFORMANT",
        "MAKOTO_REPRODUCED",
    }


def test_descriptor_for_bytes_binds_exact_evidence() -> None:
    assert descriptor_for_bytes("urn:makoto:test:evidence", b"quote") == {
        "uri": "urn:makoto:test:evidence",
        "digest": {"sha256": sha256_bytes(b"quote")},
    }


def test_failed_summary_is_signed_but_never_claims_passed() -> None:
    policy = _policy(required_levels=[TRANSFORM_LEVELS[2]])
    run = _run(policy)
    evaluation = SummaryEvaluation(
        subjects=({"name": "output", "digest": {"sha256": "f" * 64}},),
        verified_levels=(),
        diagnostics=("E_REQUIRED_VERIFICATION_RESULT",),
        passed=False,
    )
    envelope = create_summary_vsa(
        evaluation=evaluation,
        run=run,
        assessments=(),
        reproductions=(),
        verifier_id="urn:makoto:test:summary-verifier",
        resource_uri="urn:makoto:test:handoff",
        policy=_descriptor("urn:makoto:test:summary-policy", "a"),
        time_verified=TIME,
        signing_keys=SUMMARY_KEY,
        repository_root=ROOT,
    )
    payload = strict_json_loads(canonical_b64decode(envelope["payload"]))
    assert isinstance(payload, dict)
    assert payload["predicate"]["verificationResult"] == "FAILED"
    assert payload["predicate"]["verifiedLevels"] == ["FAILED"]
    validate_core("statement", payload, repository_root=ROOT)


def test_vsa_assess_cli_emits_signed_transform_l3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform_paths = []
    for path in sorted(
        (DEMO / "positive-bundle" / "attestations").iterdir(),
        key=lambda item: item.name.encode(),
    ):
        attestation = load_attestation(path, repository_root=ROOT)
        if attestation.statement["predicateType"].endswith("/transform"):
            transform_paths.append(path)
    quote = tmp_path / "quote.bin"
    quote.write_bytes(b"vendor-specific-quote")
    binding = tmp_path / "quote.json"
    binding.write_bytes(
        canonical_json({"uri": "urn:makoto:test:quote", "path": "quote.bin"}) + b"\n"
    )
    key = tmp_path / "assessor.pem"
    key.write_bytes(ASSESSOR_A.private_pkcs8_pem())
    output = tmp_path / "assessment.dsse.json"
    arguments = [
        "makoto",
        "vsa",
        "assess",
        "--track",
        "transform",
        "--level",
        "3",
    ]
    for path in transform_paths:
        arguments.extend(("--input-attestation", str(path)))
    arguments.extend(
        (
            "--hardware-evidence",
            str(binding),
            "--verifier-id",
            "urn:makoto:test:platform:transform-a",
            "--resource-uri",
            "urn:makoto:test:transform-resource",
            "--policy-uri",
            "urn:makoto:test:transform-policy-a",
            "--policy-digest",
            f"sha256:{'c' * 64}",
            "--time-verified",
            TIME,
            "--key",
            str(key),
            "--out",
            str(output),
        )
    )
    monkeypatch.setattr(cli.sys, "argv", arguments)

    assert cli.main() == 0
    assessment = strict_json_loads(output.read_bytes())
    assert isinstance(assessment, dict)
    verify_envelope_signature(assessment, public_spki=ASSESSOR_A.public_spki())


def test_vsa_summarize_cli_uses_existing_trust_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy(required_levels=[ORIGIN_LEVELS[1], TRANSFORM_LEVELS[2]])
    run = _run(policy)
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(policy.exact_bytes)
    report_path = tmp_path / "report.json"
    report_path.write_bytes(canonical_json(run.report) + b"\n")
    assessment_paths = []
    for index, assessment in enumerate(
        (
            _assessment(run, track="origin", level=2),
            _assessment(run, track="transform", level=3),
        )
    ):
        path = tmp_path / f"assessment-{index}.dsse.json"
        path.write_bytes(canonical_json(assessment.envelope) + b"\n")
        assessment_paths.append(path)
    key = tmp_path / "summary.pem"
    key.write_bytes(SUMMARY_KEY.private_pkcs8_pem())
    output = tmp_path / "summary.dsse.json"
    evaluation_output = tmp_path / "evaluation.json"
    arguments = [
        "makoto",
        "vsa",
        "summarize",
        "--report",
        str(report_path),
        "--attestations",
        str(DEMO / "positive-bundle" / "attestations"),
        "--policy",
        str(policy_path),
    ]
    for path in assessment_paths:
        arguments.extend(("--assessment", str(path)))
    arguments.extend(
        (
            "--verifier-id",
            "urn:makoto:test:summary-verifier",
            "--time-verified",
            TIME,
            "--key",
            str(key),
            "--evaluation-out",
            str(evaluation_output),
            "--out",
            str(output),
        )
    )
    monkeypatch.setattr(cli.sys, "argv", arguments)

    assert cli.main() == 0
    summary = strict_json_loads(output.read_bytes())
    assert isinstance(summary, dict)
    verify_envelope_signature(summary, public_spki=SUMMARY_KEY.public_spki())
    evaluation = strict_json_loads(evaluation_output.read_bytes())
    assert isinstance(evaluation, dict)
    assert evaluation["passed"] is True
