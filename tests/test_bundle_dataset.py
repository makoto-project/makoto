from __future__ import annotations

from pathlib import Path

import pytest

from makoto.bundle import (
    ArtifactMaterialSource,
    DatasetEntrySource,
    VerificationRequest,
    verify_bundle,
    write_handoff_bundle,
)
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.dsse import SigningKey, canonical_b64encode
from makoto.model import Artifact, TransformationInput, create_origin, create_transform
from makoto.schema import (
    DATASET_MANIFEST_MEDIA_TYPE,
    core_dataset_manifest_profile_reference,
    strict_json_loads,
    validate_core,
)

ROOT = Path(__file__).resolve().parents[1]
TIME = "2026-09-16T16:00:00Z"
ENTRY_NAME = "year=2026/month=09/part-00000.json"


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
    return {
        "version": "0.2",
        "keys": {
            key.keyid(): {
                "type": "ed25519",
                "publicKey": canonical_b64encode(key.public_spki()),
            }
            for key in keys.values()
        },
        "rules": [
            {
                "id": "urn:makoto:test:rule:dataset-origin",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/origin"],
                "authorizedKeyIds": [keys["origin"].keyid()],
                "minimumSignatures": 1,
                "sourceKinds": ["urn:makoto:test:dataset-source"],
            },
            {
                "id": "urn:makoto:test:rule:partition-transform",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
                "authorizedKeyIds": [keys["transform"].keyid()],
                "minimumSignatures": 1,
                "operationTypes": ["urn:makoto:test:operation:partition-transform"],
            },
        ],
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


def _build_dataset_bundle(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    keys = {
        "origin": SigningKey.from_seed(bytes([11]) * 32),
        "transform": SigningKey.from_seed(bytes([12]) * 32),
        "handoff": SigningKey.from_seed(bytes([13]) * 32),
    }
    partition = Artifact("part-00000.json", b'{"customer_id":"abc"}\n', "application/json")
    manifest_value = {
        "version": "0.2",
        "entries": [
            {
                "name": ENTRY_NAME,
                "digest": partition.digest(),
                "size": len(partition.data),
                "mediaType": "application/json",
            }
        ],
    }
    manifest = Artifact(
        "customers.dataset-manifest.json",
        canonical_json(manifest_value) + b"\n",
        DATASET_MANIFEST_MEDIA_TYPE,
    )
    profile = core_dataset_manifest_profile_reference(manifest.name, repository_root=ROOT)
    origin = create_origin(
        artifacts=[manifest],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111119",
        occurred_at=TIME,
        source_kind="urn:makoto:test:dataset-source",
        signing_key=keys["origin"],
        repository_root=ROOT,
        profiles=[profile],
    )
    output = Artifact("customers.public.json", b'[{"customer_id":"abc"}]\n', "application/json")
    transform = create_transform(
        artifacts=[output],
        inputs=[
            TransformationInput(
                "selected-partition",
                partition,
                origin,
                manifest.name,
                entry_name=ENTRY_NAME,
            )
        ],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222229",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:partition-transform",
        signing_key=keys["transform"],
        repository_root=ROOT,
    )
    bundle_path = tmp_path / "bundle"
    created = write_handoff_bundle(
        attestations=[origin, transform],
        heads=[transform],
        final_artifacts=[(output, transform)],
        dataset_manifests=[(manifest, origin)],
        dataset_entries=[(partition, origin, manifest.name, ENTRY_NAME)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555559",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")
    return (
        bundle_path,
        policy_path,
        {
            "manifestDigest": created["manifestDigest"]["sha256"],
            "headDigest": transform.digest()["sha256"],
            "datasetStatementDigest": origin.digest()["sha256"],
            "datasetSubjectName": manifest.name,
        },
    )


def _verify(bundle_path: Path, policy_path: Path, expected: dict[str, str]) -> dict[str, object]:
    return verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest={"sha256": expected["manifestDigest"]},
            expected_heads=({"sha256": expected["headDigest"]},),
            evaluation_time=TIME,
        )
    )


def test_verified_dataset_manifest_membership_allows_partition_pruned_edge(
    tmp_path: Path,
) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)

    report = _verify(bundle_path, policy_path, expected)

    assert report["decision"] == "allow", report["errors"]
    assert any(
        record["id"] == "https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json"
        and record["validation"] == "pass"
        for record in report["profiles"]
    )
    assert report["datasetEntries"] == [
        {
            "manifestStatementDigest": {"sha256": expected["datasetStatementDigest"]},
            "manifestSubjectName": expected["datasetSubjectName"],
            "entryName": ENTRY_NAME,
            "digest": report["datasetEntries"][0]["digest"],
            "declaredSize": str(len(b'{"customer_id":"abc"}\n')),
            "digestStatus": "pass",
            "digestPrerequisiteChecks": [],
            "sizeStatus": "pass",
            "sizePrerequisiteChecks": [],
        }
    ]
    validate_core("verification-report", report, repository_root=ROOT)


def test_dataset_entry_path_hashes_only_the_logical_entry_identity(tmp_path: Path) -> None:
    bundle_path, _policy_path, expected = _build_dataset_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    mapping = bundle["datasetEntries"][0]
    identity = {
        "entryName": mapping["entryName"],
        "manifestStatementDigest": mapping["manifestStatementDigest"],
        "manifestSubjectName": mapping["manifestSubjectName"],
    }

    assert mapping["manifestStatementDigest"]["sha256"] == expected["datasetStatementDigest"]
    assert mapping["path"] == (
        f"artifacts/dataset-entries/{sha256_bytes(canonical_json(identity))}.bin"
    )


def test_required_dataset_manifest_digest_mismatch_fails_at_step_8(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    dataset_path = next((bundle_path / "artifacts" / "historical").iterdir())
    dataset_path.write_bytes(dataset_path.read_bytes() + b"x")

    report = _verify(bundle_path, policy_path, expected)

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_ARTIFACT_DIGEST"
    assert report["errors"][0]["step"] == 8
    assert report["errors"][0]["causedByCheck"] == "graph-dependency-artifacts"
    validate_core("verification-report", report, repository_root=ROOT)


def test_required_dataset_manifest_missing_bytes_fails_closed(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    dataset_path = next((bundle_path / "artifacts" / "historical").iterdir())
    dataset_path.unlink()

    report = _verify(bundle_path, policy_path, expected)

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_DATASET_MANIFEST_REQUIRED"
    validate_core("verification-report", report, repository_root=ROOT)


def test_dataset_entry_partition_digest_fails_but_size_still_passes(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    partition_path = next((bundle_path / "artifacts" / "dataset-entries").iterdir())
    partition_path.write_bytes(partition_path.read_bytes().replace(b"abc", b"xyz"))

    report = _verify(bundle_path, policy_path, expected)

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_ARTIFACT_DIGEST"
    assert report["datasetEntries"][0]["digestStatus"] == "fail"
    assert report["datasetEntries"][0]["sizeStatus"] == "pass"
    validate_core("verification-report", report, repository_root=ROOT)


def test_dataset_entry_mapping_digest_must_equal_manifest_member(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)

    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    assert isinstance(bundle, dict)
    bundle["datasetEntries"][0]["digest"] = {"sha256": "f" * 64}
    (bundle_path / "bundle.json").write_bytes(canonical_json(bundle) + b"\n")

    report = _verify(bundle_path, policy_path, expected)

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_DATASET_MANIFEST_INVALID"
    assert report["datasetEntries"][0]["digestStatus"] == "fail"
    assert report["datasetEntries"][0]["sizeStatus"] == "skipped"
    validate_core("verification-report", report, repository_root=ROOT)


def test_dataset_entry_mapping_target_must_exist(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    next((bundle_path / "artifacts" / "dataset-entries").iterdir()).unlink()

    report = _verify(bundle_path, policy_path, expected)

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_ARTIFACT_MISSING"
    assert report["datasetEntries"][0]["digestStatus"] == "fail"
    assert report["datasetEntries"][0]["sizeStatus"] == "skipped"
    validate_core("verification-report", report, repository_root=ROOT)


@pytest.mark.parametrize("mutated", [False, True])
def test_consumer_dataset_entry_supplies_partition_bytes(tmp_path: Path, mutated: bool) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    mapping = bundle["datasetEntries"].pop()
    bundled_path = bundle_path / mapping["path"]
    consumer_path = tmp_path / "consumer" / "partition.json"
    consumer_path.parent.mkdir()
    consumer_path.write_bytes(bundled_path.read_bytes() + (b"x" if mutated else b""))
    bundled_path.unlink()
    (bundle_path / "bundle.json").write_bytes(canonical_json(bundle) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest={"sha256": expected["manifestDigest"]},
            expected_heads=({"sha256": expected["headDigest"]},),
            evaluation_time=TIME,
            dataset_entry_bindings=(
                DatasetEntrySource(
                    manifest_statement_digest=mapping["manifestStatementDigest"]["sha256"],
                    manifest_subject_name=mapping["manifestSubjectName"],
                    entry_name=mapping["entryName"],
                    digest=mapping["digest"]["sha256"],
                    path=consumer_path,
                ),
            ),
        )
    )

    if mutated:
        assert report["decision"] == "deny"
        assert report["datasetEntries"][0]["digestStatus"] == "fail"
        assert "E_ARTIFACT_DIGEST" in {error["code"] for error in report["errors"]}
    else:
        assert report["decision"] == "allow", report["errors"]
        assert report["datasetEntries"][0]["digestStatus"] == "pass"
        assert report["datasetEntries"][0]["sizeStatus"] == "pass"
    validate_core("verification-report", report, repository_root=ROOT)


def test_consumer_dataset_manifest_supplies_step_8_material(tmp_path: Path) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    mapping = next(
        item
        for item in bundle["artifacts"]
        if item["subjectName"] == expected["datasetSubjectName"]
    )
    bundle["artifacts"].remove(mapping)
    bundled_path = bundle_path / mapping["path"]
    consumer_path = tmp_path / "consumer" / "dataset-manifest.json"
    consumer_path.parent.mkdir()
    consumer_path.write_bytes(bundled_path.read_bytes())
    bundled_path.unlink()
    (bundle_path / "bundle.json").write_bytes(canonical_json(bundle) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest={"sha256": expected["manifestDigest"]},
            expected_heads=({"sha256": expected["headDigest"]},),
            evaluation_time=TIME,
            artifact_materials=(
                ArtifactMaterialSource(
                    statement_digest=mapping["statementDigest"]["sha256"],
                    subject_name=mapping["subjectName"],
                    digest=mapping["digest"]["sha256"],
                    path=consumer_path,
                ),
            ),
        )
    )

    assert report["decision"] == "allow", report["errors"]
    historical = next(
        item for item in report["artifacts"] if item["artifactKind"] == "dataset-manifest"
    )
    assert historical["digestStatus"] == "pass"
    validate_core("verification-report", report, repository_root=ROOT)


def test_consumer_material_cannot_replace_missing_final_dataset_manifest_mapping(
    tmp_path: Path,
) -> None:
    keys = {
        "origin": SigningKey.from_seed(bytes([61]) * 32),
        "transform": SigningKey.from_seed(bytes([62]) * 32),
        "handoff": SigningKey.from_seed(bytes([63]) * 32),
    }
    partition = Artifact("part.json", b'{"customer_id":"abc"}\n', "application/json")
    manifest = Artifact(
        "customers.dataset-manifest.json",
        canonical_json(
            {
                "version": "0.2",
                "entries": [
                    {
                        "name": "part.json",
                        "digest": partition.digest(),
                        "size": len(partition.data),
                        "mediaType": "application/json",
                    }
                ],
            }
        )
        + b"\n",
        DATASET_MANIFEST_MEDIA_TYPE,
    )
    origin = create_origin(
        artifacts=[manifest],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111161",
        occurred_at=TIME,
        source_kind="urn:makoto:test:dataset-source",
        signing_key=keys["origin"],
        repository_root=ROOT,
        profiles=[core_dataset_manifest_profile_reference(manifest.name, repository_root=ROOT)],
    )
    bundle_path = tmp_path / "bundle"
    created = write_handoff_bundle(
        attestations=[origin],
        heads=[origin],
        final_artifacts=[(manifest, origin)],
        dataset_manifests=[(manifest, origin)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555561",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys)) + b"\n")
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    mapping = bundle["artifacts"].pop()
    bundled_path = bundle_path / mapping["path"]
    consumer_path = tmp_path / "consumer-manifest.json"
    consumer_path.write_bytes(bundled_path.read_bytes())
    bundled_path.unlink()
    (bundle_path / "bundle.json").write_bytes(canonical_json(bundle) + b"\n")

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_manifest=created["manifestDigest"],
            expected_heads=(origin.digest(),),
            artifact_materials=(
                ArtifactMaterialSource(
                    origin.digest()["sha256"],
                    manifest.name,
                    manifest.digest()["sha256"],
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


@pytest.mark.parametrize("collection", ["artifact", "dataset-entry"])
def test_bundle_and_consumer_identity_collision_is_step_2_core_error(
    tmp_path: Path, collection: str
) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    consumer_path = tmp_path / "consumer.bin"
    if collection == "artifact":
        mapping = next(
            item
            for item in bundle["artifacts"]
            if item["subjectName"] == expected["datasetSubjectName"]
        )
        consumer_path.write_bytes((bundle_path / mapping["path"]).read_bytes())
        request = VerificationRequest(
            bundle_path,
            policy_path,
            ROOT,
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
    else:
        mapping = bundle["datasetEntries"][0]
        consumer_path.write_bytes((bundle_path / mapping["path"]).read_bytes())
        request = VerificationRequest(
            bundle_path,
            policy_path,
            ROOT,
            dataset_entry_bindings=(
                DatasetEntrySource(
                    mapping["manifestStatementDigest"]["sha256"],
                    mapping["manifestSubjectName"],
                    mapping["entryName"],
                    mapping["digest"]["sha256"],
                    consumer_path,
                ),
            ),
            evaluation_time=TIME,
        )

    report = verify_bundle(request)

    assert report["decision"] == "deny"
    assert report["primaryError"] == "E_CORE_SCHEMA"
    assert report["errors"][0]["step"] == 2
    assert report["manifestDigest"] is None
    assert report["statements"] == []
    assert report["profiles"] == []
    assert report["artifacts"] == []
    assert report["datasetEntries"] == []
    validate_core("verification-report", report, repository_root=ROOT)


@pytest.mark.parametrize("unknown", ["statement", "member"])
def test_consumer_dataset_binding_must_target_a_verified_manifest_member(
    tmp_path: Path, unknown: str
) -> None:
    bundle_path, policy_path, expected = _build_dataset_bundle(tmp_path)
    bundle = strict_json_loads((bundle_path / "bundle.json").read_bytes())
    mapping = bundle["datasetEntries"][0]
    consumer_path = tmp_path / "consumer-partition.json"
    consumer_path.write_bytes((bundle_path / mapping["path"]).read_bytes())
    statement_digest = (
        "0" * 64 if unknown == "statement" else mapping["manifestStatementDigest"]["sha256"]
    )
    entry_name = "missing/partition.json" if unknown == "member" else mapping["entryName"]

    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
            expected_heads=({"sha256": expected["headDigest"]},),
            dataset_entry_bindings=(
                DatasetEntrySource(
                    statement_digest,
                    mapping["manifestSubjectName"],
                    entry_name,
                    mapping["digest"]["sha256"],
                    consumer_path,
                ),
            ),
            evaluation_time=TIME,
        )
    )

    assert report["decision"] == "deny"
    expected_code = (
        "E_DATASET_MANIFEST_REQUIRED" if unknown == "statement" else "E_DATASET_MANIFEST_INVALID"
    )
    assert expected_code in {error["code"] for error in report["errors"]}
    validate_core("verification-report", report, repository_root=ROOT)
