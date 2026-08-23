from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import makoto.bundle as bundle_module
from makoto.bundle import (
    ArtifactMaterialSource,
    BundleError,
    VerificationConfigurationError,
    VerificationRequest,
    VerificationTiming,
    verify_bundle,
    write_handoff_bundle,
)
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.dsse import SigningKey, canonical_b64decode, canonical_b64encode
from makoto.model import (
    Artifact,
    Attestation,
    TransformationInput,
    create_handoff,
    create_origin,
    create_transform,
)
from makoto.policy import TrustPolicy
from makoto.schema import create_profile_reference, strict_json_loads, validate_core

ROOT = Path(__file__).resolve().parents[1]
TIME = "2026-09-16T16:00:00Z"


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


def _policy(keys: dict[str, SigningKey]) -> dict[str, object]:
    rules = [
        {
            "id": "urn:makoto:test:rule:normalize",
            "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
            "authorizedKeyIds": [keys["normalize"].keyid()],
            "minimumSignatures": 1,
            "operationTypes": ["urn:makoto:test:operation:normalize"],
        },
        {
            "id": "urn:makoto:test:rule:origin",
            "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/origin"],
            "authorizedKeyIds": [keys["origin"].keyid()],
            "minimumSignatures": 1,
            "sourceKinds": ["urn:makoto:test:source"],
        },
        {
            "id": "urn:makoto:test:rule:public-safe",
            "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
            "authorizedKeyIds": [keys["public"].keyid()],
            "minimumSignatures": 1,
            "operationTypes": ["urn:makoto:test:operation:public-safe"],
        },
    ]
    return {
        "version": "0.2",
        "keys": {
            key.keyid(): {
                "type": "ed25519",
                "publicKey": canonical_b64encode(key.public_spki()),
            }
            for key in keys.values()
        },
        "rules": rules,
        "handoff": {
            "authorizedKeyIds": [keys["handoff"].keyid()],
            "minimumSignatures": 1,
            "requireExpectedManifest": False,
            "requireExpectedHead": True,
            "requireExpectedArtifacts": False,
            "requireRecipient": False,
            "requireNonce": False,
            "allowReplayableHandoff": False,
        },
        "requiredProfiles": [],
        "limits": _limits(),
    }


def _build_bundle(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    raw = Artifact("customers.raw.json", b'[{"email":" A@EXAMPLE.TEST "}]\n')
    normalized = Artifact("customers.normalized.json", b'[{"email":"a@example.test"}]\n')
    public = Artifact("customers.public.json", b'[{"customer_id":"abc"}]\n', "application/json")
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
    )
    normalize = create_transform(
        artifacts=[normalized],
        inputs=[TransformationInput("raw", raw, origin, raw.name)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222222",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:normalize",
        signing_key=keys["normalize"],
        repository_root=ROOT,
    )
    public_safe = create_transform(
        artifacts=[public],
        inputs=[TransformationInput("normalized", normalized, normalize, normalized.name)],
        event_id="urn:uuid:33333333-3333-4333-8333-333333333333",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:public-safe",
        signing_key=keys["public"],
        repository_root=ROOT,
    )
    bundle_path = tmp_path / "bundle"
    created = write_handoff_bundle(
        attestations=[origin, normalize, public_safe],
        heads=[public_safe],
        final_artifacts=[(public, public_safe)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555555",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")
    expected = {
        "manifest": created["manifestDigest"],
        "head": public_safe.digest(),
        "artifact": {
            "head": public_safe.digest(),
            "subjectName": public.name,
            "digest": public.digest(),
        },
    }
    return bundle_path, policy_path, expected


def test_complete_bundle_allows_and_report_validates(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            expected_artifacts=(expected["artifact"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )
    assert report["decision"] == "allow", report["errors"]
    assert report["primaryError"] is None
    assert report["manifestDigest"] == expected["manifest"]
    validate_core("verification-report", report, repository_root=ROOT)


def test_complete_bundle_records_each_normative_step_duration(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    timing = VerificationTiming()

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            expected_artifacts=(expected["artifact"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
            timing=timing,
        )
    )

    assert report["decision"] == "allow", report["errors"]
    values = timing.as_dict()
    assert values["totalNanoseconds"] >= sum(values["steps"].values())  # type: ignore[union-attr]
    assert all(value > 0 for value in values["steps"].values())  # type: ignore[union-attr]


def test_early_deny_records_only_reached_step_and_decision(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir()
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")
    timing = VerificationTiming()

    report = verify_bundle(
        VerificationRequest(
            bundle_path,
            policy_path,
            ROOT,
            evaluation_time=TIME,
            timing=timing,
        )
    )

    assert report["decision"] == "deny"
    steps = timing.as_dict()["steps"]
    assert steps["1"] > 0  # type: ignore[index]
    assert steps["14"] > 0  # type: ignore[index]
    assert all(steps[str(step)] == 0 for step in range(2, 14))  # type: ignore[index]


def test_temp_parent_owns_private_snapshot_directory_and_cleans_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(b"{}\n")
    temp_parent = tmp_path / "private-temp"
    temp_parent.mkdir(mode=0o700)
    observed: dict[str, object] = {}

    def inspect(request: VerificationRequest) -> dict[str, object]:
        assert request.snapshot_root is not None
        observed["path"] = request.snapshot_root
        observed["mode"] = request.snapshot_root.stat().st_mode & 0o777
        return {"decision": "deny"}

    monkeypatch.setattr(bundle_module, "_verify_bundle", inspect)

    report = verify_bundle(
        VerificationRequest(
            bundle_root=tmp_path / "unused-bundle",
            policy_path=policy_path,
            repository_root=ROOT,
            temp_parent=temp_parent,
        )
    )

    assert report == {"decision": "deny"}
    assert observed["mode"] == 0o700
    assert isinstance(observed["path"], Path)
    assert not observed["path"].exists()
    assert list(temp_parent.iterdir()) == []


def test_policy_inside_bundle_is_step_one_evidence_denial(tmp_path: Path) -> None:
    bundle_path, policy_path, _expected = _build_bundle(tmp_path)
    in_bundle_policy = bundle_path / "consumer-policy.json"
    in_bundle_policy.write_bytes(policy_path.read_bytes())

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=in_bundle_policy,
            repository_root=ROOT,
            evaluation_time=TIME,
        )
    )

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_BUNDLE_UNSAFE_PATH"
    assert (
        next(check for check in report["checks"] if check["id"] == "load-safely")["status"]
        == "fail"
    )


def test_missing_bundle_index_returns_total_deny_report(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle"
    bundle_path.mkdir()
    policy_path = tmp_path / "policy.json"
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")

    report = verify_bundle(
        VerificationRequest(bundle_path, policy_path, ROOT, evaluation_time=TIME)
    )

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_HANDOFF_REQUIRED"
    assert statuses["load-safely"] == "fail"
    assert statuses["parse-strictly"] == "skipped"
    assert statuses["artifact-bytes"] == "skipped"
    validate_core("verification-report", report, repository_root=ROOT)


def test_missing_manifest_returns_total_deny_report(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    (bundle_path / bundle["manifest"]).unlink()

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_HANDOFF_REQUIRED"
    assert statuses["load-safely"] == "pass"
    assert statuses["parse-strictly"] == "fail"
    assert statuses["signatures"] == "skipped"
    validate_core("verification-report", report, repository_root=ROOT)


def test_malformed_manifest_returns_json_deny_report(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    (bundle_path / bundle["manifest"]).write_bytes(b"{\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_JSON_INVALID"
    validate_core("verification-report", report, repository_root=ROOT)


@pytest.mark.parametrize(
    ("mutation", "expected_code", "payload_type_status"),
    [
        ("json", "E_JSON_INVALID", "not_checked"),
        ("base64", "E_ENVELOPE_MALFORMED", "pass"),
        ("payload-type", "E_PAYLOAD_TYPE", "fail"),
    ],
)
def test_malformed_statement_envelope_returns_total_deny_report(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    payload_type_status: str,
) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    statement_path = bundle_path / bundle["attestations"][0]["path"]
    if mutation == "json":
        statement_path.write_bytes(b"{\n")
    elif mutation == "base64":
        envelope = strict_json_loads(statement_path.read_bytes())
        envelope["payload"] = "!!!"
        statement_path.write_bytes(canonical_json(envelope) + b"\n")
    else:
        envelope = strict_json_loads(statement_path.read_bytes())
        envelope["payloadType"] = "application/vnd.makoto.handoff.v0.2+json"
        statement_path.write_bytes(canonical_json(envelope) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )

    assert report["decision"] == "deny"
    assert expected_code in {error["code"] for error in report["errors"]}
    assert report["unindexedEnvelopes"] == [
        {
            "path": bundle["attestations"][0]["path"],
            "payloadTypeStatus": payload_type_status,
            "diagnosticCode": expected_code,
        }
    ]
    validate_core("verification-report", report, repository_root=ROOT)


def test_statement_consuming_open_oserror_returns_total_deny_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    target = bundle["attestations"][0]["path"]
    real_safe_read = bundle_module._safe_read

    def fail_target(
        root: Path, logical_path: str, inventory: dict[str, tuple[str, tuple[int, int]]]
    ) -> bytes:
        if logical_path == target:
            raise PermissionError("simulated consuming-open denial")
        return real_safe_read(root, logical_path, inventory)

    monkeypatch.setattr(bundle_module, "_safe_read", fail_target)

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )

    assert report["decision"] == "deny"
    assert "E_BUNDLE_UNSAFE_PATH" in {error["code"] for error in report["errors"]}
    validate_core("verification-report", report, repository_root=ROOT)


def test_final_rescan_failure_is_reported_without_erasing_completed_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    real_scan = bundle_module._scan_bundle
    calls = 0

    def changed_on_rescan(root: Path) -> dict[str, tuple[str, tuple[int, int]]]:
        nonlocal calls
        calls += 1
        inventory = real_scan(root)
        if calls > 1:
            inventory = {**inventory, "changed.bin": ("file", (0, 0))}
        return inventory

    monkeypatch.setattr(bundle_module, "_scan_bundle", changed_on_rescan)

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            expected_artifacts=(expected["artifact"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )

    artifact = next(item for item in report["artifacts"] if item["lifecycleRole"] == "final")
    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_BUNDLE_UNSAFE_PATH"
    assert artifact["digestStatus"] == "pass"
    assert (
        next(check for check in report["checks"] if check["id"] == "artifact-bytes")["status"]
        == "fail"
    )
    validate_core("verification-report", report, repository_root=ROOT)


@pytest.mark.parametrize("mutated", [False, True])
def test_consumer_artifact_material_supplies_historical_bytes(
    tmp_path: Path, mutated: bool
) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    origin_entry = next(
        item
        for item in bundle["attestations"]
        if strict_json_loads(
            canonical_b64decode(
                strict_json_loads((bundle_path / item["path"]).read_bytes())["payload"]
            )
        )["predicateType"]
        == "https://usemakoto.dev/predicate/v0.2/origin"
    )
    origin = strict_json_loads(
        canonical_b64decode(
            strict_json_loads((bundle_path / origin_entry["path"]).read_bytes())["payload"]
        )
    )
    subject = origin["subject"][0]
    material_path = tmp_path / "consumer" / "customers.raw.json"
    material_path.parent.mkdir()
    raw_bytes = b'[{"email":" A@EXAMPLE.TEST "}]\n'
    material_path.write_bytes(raw_bytes + (b"x" if mutated else b""))
    source = ArtifactMaterialSource(
        statement_digest=origin_entry["statementDigest"]["sha256"],
        subject_name=subject["name"],
        digest=subject["digest"]["sha256"],
        path=material_path,
    )

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            artifact_materials=(source,),
            evaluation_time=TIME,
        )
    )

    historical = next(item for item in report["artifacts"] if item["lifecycleRole"] == "historical")
    if mutated:
        assert report["decision"] == "deny"
        assert historical["digestStatus"] == "fail"
        assert "E_ARTIFACT_DIGEST" in {error["code"] for error in report["errors"]}
    else:
        assert report["decision"] == "allow", report["errors"]
        assert historical["digestStatus"] == "pass"
    validate_core("verification-report", report, repository_root=ROOT)


def test_unauthorized_handoff_still_hashes_consumer_historical_material(
    tmp_path: Path,
) -> None:
    bundle_path, policy_path, _expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    origin_entry = next(
        item
        for item in bundle["attestations"]
        if strict_json_loads(
            canonical_b64decode(
                strict_json_loads((bundle_path / item["path"]).read_bytes())["payload"]
            )
        )["predicateType"]
        == "https://usemakoto.dev/predicate/v0.2/origin"
    )
    origin = strict_json_loads(
        canonical_b64decode(
            strict_json_loads((bundle_path / origin_entry["path"]).read_bytes())["payload"]
        )
    )
    subject = origin["subject"][0]
    material_path = tmp_path / "consumer" / "customers.raw.json"
    material_path.parent.mkdir()
    material_path.write_bytes(b'[{"email":" A@EXAMPLE.TEST "}]\n')
    policy = strict_json_loads(policy_path.read_bytes())
    policy["handoff"]["authorizedKeyIds"] = policy["rules"][0]["authorizedKeyIds"]
    policy_path.write_bytes(canonical_json(policy) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            artifact_materials=(
                ArtifactMaterialSource(
                    origin_entry["statementDigest"]["sha256"],
                    subject["name"],
                    subject["digest"]["sha256"],
                    material_path,
                ),
            ),
            evaluation_time=TIME,
        )
    )

    historical = next(item for item in report["artifacts"] if item["lifecycleRole"] == "historical")
    assert report["decision"] == "deny"
    assert "E_SIGNER_UNAUTHORIZED" in {error["code"] for error in report["errors"]}
    assert historical["digestStatus"] == "pass"
    validate_core("verification-report", report, repository_root=ROOT)


def test_duplicate_consumer_artifact_identity_is_configuration_error(tmp_path: Path) -> None:
    material = tmp_path / "material.bin"
    material.write_bytes(b"material")
    source = ArtifactMaterialSource("0" * 64, "subject", "1" * 64, material)

    with pytest.raises(VerificationConfigurationError, match="identities must be unique"):
        verify_bundle(
            VerificationRequest(
                bundle_root=tmp_path / "does-not-exist",
                policy_path=tmp_path / "does-not-matter",
                repository_root=ROOT,
                artifact_materials=(source, source),
            )
        )


def test_distinct_consumer_identities_cannot_alias_one_physical_file(tmp_path: Path) -> None:
    material = tmp_path / "material.bin"
    material.write_bytes(b"material")

    with pytest.raises(VerificationConfigurationError, match="distinct physical files"):
        verify_bundle(
            VerificationRequest(
                bundle_root=tmp_path / "does-not-exist",
                policy_path=tmp_path / "does-not-matter",
                repository_root=ROOT,
                artifact_materials=(
                    ArtifactMaterialSource("0" * 64, "first", "1" * 64, material),
                    ArtifactMaterialSource("2" * 64, "second", "3" * 64, material),
                ),
            )
        )


def test_consumer_material_cannot_replace_a_missing_final_bundle_mapping(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    mapping = next(
        item for item in bundle["artifacts"] if item["statementDigest"] == expected["head"]
    )
    bundle["artifacts"].remove(mapping)
    bundled_path = bundle_path / mapping["path"]
    consumer_path = tmp_path / "consumer" / "final.json"
    consumer_path.parent.mkdir()
    consumer_path.write_bytes(bundled_path.read_bytes())
    bundled_path.unlink()
    (bundle_path / "bundle.json").write_bytes(canonical_json(bundle) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            artifact_materials=(
                ArtifactMaterialSource(
                    mapping["statementDigest"]["sha256"],
                    mapping["subjectName"],
                    mapping["digest"]["sha256"],
                    consumer_path,
                ),
            ),
            evaluation_time=TIME,
        )
    )

    final = next(item for item in report["artifacts"] if item["lifecycleRole"] == "final")
    assert report["decision"] == "deny"
    assert "E_MANIFEST_SET" in {error["code"] for error in report["errors"]}
    assert final["digestStatus"] == "fail"
    validate_core("verification-report", report, repository_root=ROOT)


def test_consumer_material_inside_bundle_returns_total_unsafe_path_report(
    tmp_path: Path,
) -> None:
    bundle_path, policy_path, _expected = _build_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    material_path = bundle_path / bundle["artifacts"][0]["path"]

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            artifact_materials=(
                ArtifactMaterialSource("0" * 64, "subject", "1" * 64, material_path),
            ),
            evaluation_time=TIME,
        )
    )

    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_BUNDLE_UNSAFE_PATH"
    assert statuses["load-safely"] == "fail"
    assert statuses["parse-strictly"] == "skipped"
    validate_core("verification-report", report, repository_root=ROOT)


def test_handoff_bundles_generic_historical_artifact_bytes(tmp_path: Path) -> None:
    keys = {
        "origin": SigningKey.from_seed(bytes([41]) * 32),
        "normalize": SigningKey.from_seed(bytes([42]) * 32),
        "public": SigningKey.from_seed(bytes([43]) * 32),
        "handoff": SigningKey.from_seed(bytes([44]) * 32),
    }
    raw = Artifact("raw.bin", b"raw historical bytes")
    final = Artifact("final.bin", b"final bytes")
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111141",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
    )
    transform = create_transform(
        artifacts=[final],
        inputs=[TransformationInput("raw", raw, origin, raw.name)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222242",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:normalize",
        signing_key=keys["normalize"],
        repository_root=ROOT,
    )

    bundle_path = tmp_path / "bundle"
    created = write_handoff_bundle(
        attestations=[origin, transform],
        heads=[transform],
        final_artifacts=[(final, transform)],
        historical_artifacts=[(raw, origin)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555543",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
    )

    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    historical = [
        item for item in bundle["artifacts"] if item["statementDigest"] == origin.digest()
    ]
    assert len(historical) == 1
    assert historical[0]["subjectName"] == raw.name
    assert (bundle_path / historical[0]["path"]).read_bytes() == raw.data

    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")
    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=created["manifestDigest"],
            expected_heads=(transform.digest(),),
            evaluation_time=TIME,
        )
    )
    historical_records = [
        item for item in report["artifacts"] if item["lifecycleRole"] == "historical"
    ]
    assert report["decision"] == "allow", report["errors"]
    assert len(historical_records) == 1
    assert historical_records[0]["digestStatus"] == "pass"
    assert report["summary"]["historicalMaterialsChecked"] == 1
    validate_core("verification-report", report, repository_root=ROOT)


def test_unreachable_listed_historical_artifact_is_still_hashed_and_reported(
    tmp_path: Path,
) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    orphan_artifact = Artifact("orphan.bin", b"authorized but unreachable historical bytes")
    orphan = create_origin(
        artifacts=[orphan_artifact],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111199",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
    )

    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    manifest_envelope = strict_json_loads((bundle_path / bundle["manifest"]).read_bytes())
    original_payload = strict_json_loads(canonical_b64decode(manifest_envelope["payload"]))
    attestations = []
    for entry in bundle["attestations"]:
        envelope = strict_json_loads((bundle_path / entry["path"]).read_bytes())
        payload = canonical_b64decode(envelope["payload"])
        statement = strict_json_loads(payload)
        attestations.append(Attestation(statement, payload, envelope))
    head = next(item for item in attestations if item.digest() == expected["head"])
    original_root = next(
        item for item in attestations if item.digest() in original_payload["roots"]
    )
    final_path = next((bundle_path / "artifacts" / "final").iterdir())
    final_artifact = Artifact(
        original_payload["artifacts"][0]["name"],
        final_path.read_bytes(),
        original_payload["artifacts"][0].get("mediaType"),
    )
    replacement = create_handoff(
        statements=[*attestations, orphan],
        roots=[original_root, orphan],
        final_artifacts=[(final_artifact, head)],
        bundle_id=original_payload["bundleId"],
        issued_at=original_payload["issuedAt"],
        signing_key=keys["handoff"],
        repository_root=ROOT,
    )
    (bundle_path / bundle["manifest"]).write_bytes(canonical_json(replacement.envelope) + b"\n")

    orphan_statement_digest = orphan.digest()["sha256"]
    orphan_attestation_path = f"attestations/{orphan_statement_digest}.dsse.json"
    (bundle_path / orphan_attestation_path).write_bytes(canonical_json(orphan.envelope) + b"\n")
    bundle["attestations"].append(
        {"statementDigest": orphan.digest(), "path": orphan_attestation_path}
    )
    bundle["attestations"].sort(key=lambda item: item["statementDigest"]["sha256"])
    orphan_material_path = "artifacts/historical/orphan.bin"
    (bundle_path / "artifacts" / "historical").mkdir()
    (bundle_path / orphan_material_path).write_bytes(orphan_artifact.data)
    bundle["artifacts"].append(
        {
            "digest": orphan_artifact.digest(),
            "path": orphan_material_path,
            "statementDigest": orphan.digest(),
            "subjectName": orphan_artifact.name,
        }
    )
    bundle["artifacts"].sort(
        key=lambda item: (
            item["statementDigest"]["sha256"],
            item["subjectName"].encode(),
            item["digest"]["sha256"],
        )
    )
    (bundle_path / "bundle.json").write_bytes(canonical_json(bundle) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=replacement.digest(),
            expected_heads=(head.digest(),),
            evaluation_time=TIME,
        )
    )

    orphan_record = next(
        item for item in report["artifacts"] if item["statementDigest"] == orphan.digest()
    )
    assert report["decision"] == "deny"
    assert "E_MANIFEST_SET" in {error["code"] for error in report["errors"]}
    assert orphan_record["lifecycleRole"] == "historical"
    assert orphan_record["digestStatus"] == "pass"
    assert report["summary"]["historicalMaterialsChecked"] == 1
    validate_core("verification-report", report, repository_root=ROOT)


@pytest.mark.parametrize("include_material", [True, False])
def test_critical_historical_profile_requires_and_validates_artifact_bytes(
    tmp_path: Path,
    include_material: bool,
) -> None:
    keys = {
        "origin": SigningKey.from_seed(bytes([45]) * 32),
        "normalize": SigningKey.from_seed(bytes([46]) * 32),
        "public": SigningKey.from_seed(bytes([47]) * 32),
        "handoff": SigningKey.from_seed(bytes([48]) * 32),
    }
    schema_path = tmp_path / "safe-historical.schema.json"
    schema_value = {
        "$schema": "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json",
        "$id": "https://schemas.example.test/makoto/safe-historical-v1.json",
        "type": "object",
        "required": ["safe"],
        "properties": {"safe": {"const": True}},
        "additionalProperties": False,
    }
    schema_path.write_bytes(canonical_json(schema_value) + b"\n")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(
        canonical_json(
            {
                "version": "0.2",
                "resources": [
                    {
                        "id": schema_value["$id"],
                        "digest": {"sha256": sha256_bytes(schema_path.read_bytes())},
                        "path": schema_path.name,
                    }
                ],
            }
        )
        + b"\n"
    )
    raw = Artifact("historical.json", b'{"safe":true}\n', "application/json")
    profile = create_profile_reference(
        schema_path,
        target="artifact",
        critical=True,
        catalog_paths=[catalog_path],
        subject_name=raw.name,
        media_type="application/json",
        repository_root=ROOT,
    )
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111145",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
        profiles=[profile],
    )
    final = Artifact("final.json", b'{"safe":true,"normalized":true}\n', "application/json")
    transform = create_transform(
        artifacts=[final],
        inputs=[TransformationInput("raw", raw, origin, raw.name)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222246",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:normalize",
        signing_key=keys["normalize"],
        repository_root=ROOT,
    )
    bundle_path = tmp_path / "bundle"
    created = write_handoff_bundle(
        attestations=[origin, transform],
        heads=[transform],
        final_artifacts=[(final, transform)],
        historical_artifacts=[(raw, origin)] if include_material else [],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555548",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            schema_catalogs=(catalog_path,),
            expected_manifest=created["manifestDigest"],
            expected_heads=(transform.digest(),),
            evaluation_time=TIME,
        )
    )

    historical = next(item for item in report["artifacts"] if item["lifecycleRole"] == "historical")
    if include_material:
        assert report["decision"] == "allow", report["errors"]
        assert historical["digestStatus"] == "pass"
        assert historical["profileStatus"] == "pass"
        assert any(
            record["id"] == schema_value["$id"] and record["validation"] == "pass"
            for record in report["profiles"]
        )
    else:
        assert report["decision"] == "deny"
        assert "E_ARTIFACT_MISSING" in {error["code"] for error in report["errors"]}
        assert historical["digestStatus"] == "fail"
        assert historical["profileStatus"] == "skipped"
        assert historical["profilePrerequisiteChecks"] == ["artifact-bytes"]
    validate_core("verification-report", report, repository_root=ROOT)


def test_handoff_rejects_conflicting_signed_artifact_media_types(tmp_path: Path) -> None:
    key = SigningKey.from_seed(bytes([49]) * 32)
    schema_path = tmp_path / "artifact.schema.json"
    schema = {
        "$schema": "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json",
        "$id": "https://schemas.example.test/makoto/artifact-v1.json",
        "type": "object",
    }
    schema_path.write_bytes(canonical_json(schema) + b"\n")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(
        canonical_json(
            {
                "version": "0.2",
                "resources": [
                    {
                        "id": schema["$id"],
                        "digest": {"sha256": sha256_bytes(schema_path.read_bytes())},
                        "path": schema_path.name,
                    }
                ],
            }
        )
        + b"\n"
    )
    artifact = Artifact("final.json", b"{}\n", "application/json")
    json_profile = create_profile_reference(
        schema_path,
        target="artifact",
        critical=True,
        catalog_paths=[catalog_path],
        subject_name=artifact.name,
        media_type="application/json",
        repository_root=ROOT,
    )
    ndjson_profile = {**json_profile, "mediaType": "application/x-ndjson"}
    validate_core("profile-reference", ndjson_profile, repository_root=ROOT)
    origin = create_origin(
        artifacts=[artifact],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111149",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=key,
        repository_root=ROOT,
        profiles=[json_profile, ndjson_profile],
    )

    with pytest.raises(BundleError, match="media type conflicts"):
        write_handoff_bundle(
            attestations=[origin],
            heads=[origin],
            final_artifacts=[(artifact, origin)],
            bundle_id="urn:uuid:55555555-5555-4555-8555-555555555549",
            issued_at=TIME,
            signing_key=key,
            output=tmp_path / "bundle",
            repository_root=ROOT,
            schema_catalog_paths=[catalog_path],
        )
    assert not (tmp_path / "bundle").exists()


def test_one_byte_final_artifact_mutation_is_denied(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    artifact_path = next((bundle_path / "artifacts" / "final").iterdir())
    artifact_path.write_bytes(artifact_path.read_bytes() + b"x")
    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            expected_artifacts=(expected["artifact"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )
    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_ARTIFACT_DIGEST"
    validate_core("verification-report", report, repository_root=ROOT)


def test_handoff_creation_rejects_consumed_nonterminal_artifact(tmp_path: Path) -> None:
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    raw = Artifact("raw.json", b"raw")
    middle = Artifact("middle.json", b"middle")
    final = Artifact("final.json", b"final")
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
    )
    normalize = create_transform(
        artifacts=[middle],
        inputs=[TransformationInput("raw", raw, origin, raw.name)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222222",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:normalize",
        signing_key=keys["normalize"],
        repository_root=ROOT,
    )
    public = create_transform(
        artifacts=[final],
        inputs=[TransformationInput("middle", middle, normalize, middle.name)],
        event_id="urn:uuid:33333333-3333-4333-8333-333333333333",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:public-safe",
        signing_key=keys["public"],
        repository_root=ROOT,
    )

    with pytest.raises(BundleError, match="not terminal"):
        write_handoff_bundle(
            attestations=[origin, normalize, public],
            heads=[normalize, public],
            final_artifacts=[(middle, normalize), (final, public)],
            bundle_id="urn:uuid:55555555-5555-4555-8555-555555555555",
            issued_at=TIME,
            signing_key=keys["handoff"],
            output=tmp_path / "bundle",
            repository_root=ROOT,
        )


def test_expected_head_mismatch_returns_deny_report(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=({"sha256": "0" * 64},),
            evaluation_time=TIME,
        )
    )
    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_EXPECTED_HEAD"
    validate_core("verification-report", report, repository_root=ROOT)


def test_expired_key_remains_cryptographically_valid_but_is_not_authorized() -> None:
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    policy_value = _policy(keys)
    policy_value["keys"][keys["origin"].keyid()]["validUntil"] = TIME  # type: ignore[index]
    policy = TrustPolicy.from_bytes(canonical_json(policy_value), repository_root=ROOT)
    origin = create_origin(
        artifacts=[Artifact("raw.json", b"raw")],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
    )

    result = policy.authorize_statement(
        origin.statement,
        origin.envelope,
        evaluation_time=datetime.fromisoformat(TIME.replace("Z", "+00:00")).astimezone(UTC),
    )

    assert result.signatures[0].cryptographic == "pass"
    assert not result.authorized


def test_digest_pinned_profile_must_resolve_before_authorization(tmp_path: Path) -> None:
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    schema_path = tmp_path / "private-origin.schema.json"
    schema_path.write_bytes(
        canonical_json(
            {
                "$schema": "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json",
                "$id": "https://schemas.example.test/makoto/private-origin-v1.json",
                "type": "object",
            }
        )
        + b"\n"
    )
    profile = create_profile_reference(
        schema_path,
        target="predicate",
        critical=False,
        catalog_paths=[],
        repository_root=ROOT,
    )
    raw = Artifact("raw.json", b"raw")
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        occurred_at=TIME,
        source_kind="urn:makoto:test:source",
        signing_key=keys["origin"],
        repository_root=ROOT,
        profiles=[profile],
    )
    bundle_path = tmp_path / "bundle"
    created = write_handoff_bundle(
        attestations=[origin],
        heads=[origin],
        final_artifacts=[(raw, origin)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555555",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
    )
    policy_value = _policy(keys)
    origin_rule = next(
        rule
        for rule in policy_value["rules"]
        if rule["id"] == "urn:makoto:test:rule:origin"  # type: ignore[index]
    )
    origin_rule["profileConstraints"] = [
        {
            "id": profile["id"],
            "target": "predicate",
            "digest": profile["digest"],
            "closureDigest": profile["closureDigest"],
        }
    ]
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(policy_value) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=created["manifestDigest"],
            expected_heads=(origin.digest(),),
            evaluation_time=TIME,
        )
    )

    statement = next(item for item in report["statements"] if item["digest"] == origin.digest())
    profile_record = next(item for item in report["profiles"] if item["id"] == profile["id"])
    assert statement["candidateRuleIds"] == ["urn:makoto:test:rule:origin"]
    assert statement["authorizingRuleIds"] == []
    assert profile_record["requiredByAuthorizationRuleIds"] == ["urn:makoto:test:rule:origin"]
    assert report["decision"] == "deny"
    assert "E_PROFILE_UNRESOLVED" in {error["code"] for error in report["errors"]}
    validate_core("verification-report", report, repository_root=ROOT)


def test_unauthorized_handoff_does_not_admit_or_read_final_artifacts(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_bundle(tmp_path)
    keys = {
        "origin": SigningKey.from_seed(bytes([1]) * 32),
        "normalize": SigningKey.from_seed(bytes([2]) * 32),
        "public": SigningKey.from_seed(bytes([3]) * 32),
        "handoff": SigningKey.from_seed(bytes([4]) * 32),
    }
    policy_value = _policy(keys)
    policy_value["handoff"]["authorizedKeyIds"] = [keys["origin"].keyid()]  # type: ignore[index]
    policy_path.write_bytes(canonical_json(policy_value) + b"\n")
    next((bundle_path / "artifacts" / "final").iterdir()).unlink()

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=expected["manifest"],  # type: ignore[arg-type]
            expected_heads=(expected["head"],),  # type: ignore[arg-type]
            expected_artifacts=(expected["artifact"],),  # type: ignore[arg-type]
            evaluation_time=TIME,
        )
    )

    assert report["decision"] == "deny"
    assert report["artifacts"] == []
    assert report["handoff"]["completeness"] == "skipped"
    assert report["handoff"]["freshnessStatus"] == "skipped"
    assert {error["code"] for error in report["errors"]} == {"E_SIGNER_UNAUTHORIZED"}
    validate_core("verification-report", report, repository_root=ROOT)
