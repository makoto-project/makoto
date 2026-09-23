from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from makoto.bundle import VerificationRequest, verify_bundle, write_handoff_bundle
from makoto.canonical import canonical_json
from makoto.cli import main
from makoto.dsse import SigningKey, canonical_b64encode
from makoto.licence import SpdxExpressionError, validate_spdx_expression
from makoto.model import Artifact, TransformationInput, create_origin, create_transform
from makoto.records import (
    RecordProofError,
    create_record_inclusion_proof,
    merkle_root,
    record_commitment,
    record_digests_from_declaration,
    verify_record_inclusion_proof,
)
from makoto.schema import (
    CoreValidationError,
    core_dataset_manifest_profile_reference,
    create_profile_reference,
    standard_license_profile_reference,
    validate_core,
    validate_with_catalog,
)
from makoto.schema_catalog import SCHEMA_NAMES_BY_VERSION, build_catalog, schema_directory

ROOT = Path(__file__).resolve().parents[1]
TIME = "2026-09-23T16:00:00Z"
ENTRY_NAME = "part-00000.bin"


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


def _policy(keys: dict[str, SigningKey], license_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "0.3",
        "keys": {
            key.keyid(): {
                "type": "ed25519",
                "publicKey": canonical_b64encode(key.public_spki()),
            }
            for key in keys.values()
        },
        "rules": [
            {
                "id": "urn:makoto:test:rule:dataset-origin-v03",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.3/origin"],
                "authorizedKeyIds": [keys["origin"].keyid()],
                "minimumSignatures": 1,
                "sourceKinds": ["urn:makoto:test:dataset-source"],
                "profileConstraints": [
                    {
                        "id": license_profile["id"],
                        "digest": license_profile["digest"],
                        "closureDigest": license_profile["closureDigest"],
                        "target": "statement",
                    }
                ],
            },
            {
                "id": "urn:makoto:test:rule:transform-v03",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.3/transform"],
                "authorizedKeyIds": [keys["transform"].keyid()],
                "minimumSignatures": 1,
                "operationTypes": ["urn:makoto:test:operation:select"],
            },
        ],
        "handoff": {
            "authorizedKeyIds": [keys["handoff"].keyid()],
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


def _build_bundle(
    tmp_path: Path, *, spdx_expression: str = "CC-BY-4.0", include_claim: bool = True
) -> tuple[Path, Path, dict[str, Any]]:
    keys = {
        "origin": SigningKey.from_seed(bytes([31]) * 32),
        "transform": SigningKey.from_seed(bytes([32]) * 32),
        "handoff": SigningKey.from_seed(bytes([33]) * 32),
    }
    partition = Artifact(ENTRY_NAME, b"alpha\nbeta\n", "application/octet-stream")
    declaration = {
        "version": "0.3",
        "kind": "byteRanges",
        "ranges": [{"offset": 0, "length": 6}, {"offset": 6, "length": 5}],
    }
    record_digests = record_digests_from_declaration(
        declaration, entry_bytes=partition.data, repository_root=ROOT
    )
    manifest_value = {
        "version": "0.3",
        "entries": [
            {
                "name": ENTRY_NAME,
                "digest": partition.digest(),
                "size": len(partition.data),
                "mediaType": partition.media_type,
                "recordMerkle": record_commitment(record_digests),
            }
        ],
    }
    manifest = Artifact(
        "dataset-manifest.json",
        canonical_json(manifest_value) + b"\n",
        "application/vnd.makoto.dataset-manifest.v0.3+json",
    )
    dataset_profile = core_dataset_manifest_profile_reference(
        manifest.name, repository_root=ROOT, protocol_version="0.3"
    )
    license_profile = standard_license_profile_reference(repository_root=ROOT)
    extensions = None
    if include_claim:
        extensions = {
            "https://usemakoto.dev/claim/v0.3/license": {
                "claims": [
                    {
                        "subjectName": manifest.name,
                        "spdxExpression": spdx_expression,
                        "evidenceUrl": "https://example.test/licence-evidence.json",
                    }
                ]
            }
        }
    origin = create_origin(
        artifacts=[manifest],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111103",
        occurred_at=TIME,
        source_kind="urn:makoto:test:dataset-source",
        signing_key=keys["origin"],
        repository_root=ROOT,
        profiles=[dataset_profile, license_profile],
        extensions=extensions,
        protocol_version="0.3",
    )
    output = Artifact("selected.bin", partition.data)
    transform = create_transform(
        artifacts=[output],
        inputs=[TransformationInput("selected", partition, origin, manifest.name, ENTRY_NAME)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222203",
        occurred_at=TIME,
        operation_type="urn:makoto:test:operation:select",
        signing_key=keys["transform"],
        repository_root=ROOT,
        protocol_version="0.3",
    )
    bundle_path = tmp_path / "bundle"
    write_handoff_bundle(
        attestations=[origin, transform],
        heads=[transform],
        final_artifacts=[(output, transform)],
        dataset_manifests=[(manifest, origin)],
        dataset_entries=[(partition, origin, manifest.name, ENTRY_NAME)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555503",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=bundle_path,
        repository_root=ROOT,
        protocol_version="0.3",
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_bytes(canonical_json(_policy(keys, license_profile)) + b"\n")
    return (
        bundle_path,
        policy_path,
        {
            "declaration": declaration,
            "entry": partition,
            "manifest": manifest,
            "origin": origin,
            "recordDigests": record_digests,
        },
    )


def test_v03_schema_family_and_catalog_are_complete() -> None:
    directory = schema_directory(ROOT, version="0.3")
    schemas = {path.stem.removesuffix(".schema"): path for path in directory.glob("*.schema.json")}
    assert set(schemas) == set(SCHEMA_NAMES_BY_VERSION["0.3"])
    for name, path in schemas.items():
        schema = __import__("json").loads(path.read_bytes())
        assert schema["$id"] == f"https://usemakoto.dev/schema/v0.3/{name}.schema.json"
        Draft202012Validator.check_schema(schema)
    assert build_catalog(ROOT, version="0.3")["version"] == "0.3"


def test_v03_statement_rejects_v02_predicate_identifier() -> None:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "data.bin", "digest": {"sha256": "a" * 64}}],
        "predicateType": "https://usemakoto.dev/predicate/v0.2/origin",
        "predicate": {
            "schemaVersion": "0.3",
            "event": {
                "id": "urn:uuid:11111111-1111-4111-8111-111111111103",
                "occurredAt": TIME,
            },
            "source": {"kind": "urn:makoto:test:source"},
        },
    }
    with pytest.raises(CoreValidationError, match="mixes Makoto protocol"):
        validate_core("statement", statement, repository_root=ROOT)


def test_external_profile_uses_explicit_v03_family(tmp_path: Path) -> None:
    identifier = "https://schemas.example.test/public-record.json"
    schema_path = tmp_path / "public-record.schema.json"
    schema_bytes = canonical_json(
        {
            "$schema": "https://usemakoto.dev/schema/v0.3/profile-dialect.schema.json",
            "$id": identifier,
            "type": "object",
            "required": ["classification"],
            "properties": {"classification": {"const": "public"}},
            "additionalProperties": False,
        }
    )
    schema_path.write_bytes(schema_bytes)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(
        canonical_json(
            {
                "version": "0.3",
                "resources": [
                    {
                        "id": identifier,
                        "digest": {"sha256": hashlib.sha256(schema_bytes).hexdigest()},
                        "path": schema_path.name,
                    }
                ],
            }
        )
    )
    reference = create_profile_reference(
        schema_path,
        target="statement",
        critical=True,
        catalog_paths=[catalog_path],
        repository_root=ROOT,
        protocol_version="0.3",
    )
    result = validate_with_catalog(
        {"classification": "public"},
        reference,
        catalog_paths=[catalog_path],
        repository_root=ROOT,
        protocol_version="0.3",
    )
    assert result.valid, result.errors


def test_standard_license_profile_accepts_complete_claim() -> None:
    bundle_path = ROOT / "testdata/v0.3/license/positive-statement.json"
    statement = __import__("json").loads(bundle_path.read_bytes())
    result = validate_with_catalog(
        statement,
        standard_license_profile_reference(repository_root=ROOT),
        catalog_paths=[],
        repository_root=ROOT,
    )
    assert result.valid, result.errors


@pytest.mark.parametrize(
    "expression",
    [
        "(MIT OR Apache-2.0) WITH Classpath-exception-2.0",
        "MIT WITH DocumentRef-local:LicenseRef-exception",
    ],
)
def test_spdx_expression_rejects_invalid_exception_forms(expression: str) -> None:
    with pytest.raises(SpdxExpressionError):
        validate_spdx_expression(expression)


@pytest.mark.parametrize(
    "fixture",
    ["missing-claim-statement.json", "malformed-spdx-statement.json"],
)
def test_standard_license_profile_rejects_negative_fixtures(fixture: str) -> None:
    statement = __import__("json").loads((ROOT / "testdata/v0.3/license" / fixture).read_bytes())
    result = validate_with_catalog(
        statement,
        standard_license_profile_reference(repository_root=ROOT),
        catalog_paths=[],
        repository_root=ROOT,
    )
    assert not result.valid


def test_v03_bundle_with_required_license_profile_allows(tmp_path: Path) -> None:
    bundle_path, policy_path, _evidence = _build_bundle(tmp_path)
    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
        )
    )
    assert report["decision"] == "allow", report["errors"]
    assert report["reportVersion"] == "0.3"


@pytest.mark.parametrize(
    ("spdx_expression", "include_claim"),
    [("MIT AND", True), ("MIT", False)],
)
def test_v03_policy_denies_false_required_license_claim(
    tmp_path: Path, spdx_expression: str, include_claim: bool
) -> None:
    bundle_path, policy_path, _evidence = _build_bundle(
        tmp_path,
        spdx_expression=spdx_expression,
        include_claim=include_claim,
    )
    report = verify_bundle(
        VerificationRequest(
            bundle_root=bundle_path,
            policy_path=policy_path,
            repository_root=ROOT,
        )
    )
    assert report["decision"] == "deny"
    assert any(item["code"] == "E_PROFILE_INVALID" for item in report["errors"])


def test_record_proof_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    _bundle, _policy_path, evidence = _build_bundle(tmp_path)
    digests = evidence["recordDigests"]
    proof = create_record_inclusion_proof(
        record_digests=digests,
        record_index=1,
        manifest_statement_digest=evidence["origin"].digest()["sha256"],
        manifest_subject_name=evidence["manifest"].name,
        entry_name=ENTRY_NAME,
        entry_digest=evidence["entry"].digest()["sha256"],
        byte_range={"offset": 6, "length": 5},
        repository_root=ROOT,
    )
    expected_root = merkle_root(digests).hex()
    verify_record_inclusion_proof(
        proof,
        expected_root=expected_root,
        record_bytes=b"beta\n",
        repository_root=ROOT,
    )
    with pytest.raises(RecordProofError, match="record bytes"):
        verify_record_inclusion_proof(
            proof,
            expected_root=expected_root,
            record_bytes=b"gamma\n",
            repository_root=ROOT,
        )


def test_record_hash_declaration_round_trip() -> None:
    expected = tuple(hashlib.sha256(value).digest() for value in (b"alpha", b"beta"))
    declaration = {
        "version": "0.3",
        "kind": "recordHashes",
        "hashes": [{"sha256": digest.hex()} for digest in expected],
    }
    actual = record_digests_from_declaration(
        declaration,
        entry_bytes=None,
        repository_root=ROOT,
    )
    assert actual == expected
    assert record_commitment(actual)["recordCount"] == 2


def test_record_proof_rejects_out_of_range_index(tmp_path: Path) -> None:
    _bundle, _policy_path, evidence = _build_bundle(tmp_path)
    with pytest.raises(RecordProofError, match="record index"):
        create_record_inclusion_proof(
            record_digests=evidence["recordDigests"],
            record_index=2,
            manifest_statement_digest=evidence["origin"].digest()["sha256"],
            manifest_subject_name=evidence["manifest"].name,
            entry_name=ENTRY_NAME,
            entry_digest=evidence["entry"].digest()["sha256"],
            repository_root=ROOT,
        )


def test_record_cli_produces_and_verifies_against_allowed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_path, policy_path, evidence = _build_bundle(tmp_path)
    declaration_path = tmp_path / "records.json"
    declaration_path.write_bytes(canonical_json(evidence["declaration"]) + b"\n")
    entry_path = tmp_path / ENTRY_NAME
    entry_path.write_bytes(evidence["entry"].data)
    proof_path = tmp_path / "proof.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "makoto",
            "record",
            "prove",
            "--bundle",
            str(bundle_path),
            "--policy",
            str(policy_path),
            "--manifest-statement-digest",
            "sha256:" + evidence["origin"].digest()["sha256"],
            "--manifest-subject-name",
            evidence["manifest"].name,
            "--entry-name",
            ENTRY_NAME,
            "--declaration",
            str(declaration_path),
            "--entry",
            str(entry_path),
            "--record-index",
            "1",
            "--out",
            str(proof_path),
        ],
    )
    assert main() == 0
    assert proof_path.is_file()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "makoto",
            "record",
            "verify",
            "--bundle",
            str(bundle_path),
            "--policy",
            str(policy_path),
            "--proof",
            str(proof_path),
            "--entry",
            str(entry_path),
            "--json",
        ],
    )
    assert main() == 0


def test_record_proof_cost_at_one_million_records() -> None:
    record_count = 1_000_000
    digests = [hashlib.sha256(b"record").digest()] * record_count
    started = time.monotonic()
    root = merkle_root(digests)
    proof = create_record_inclusion_proof(
        record_digests=digests,
        record_index=654321,
        manifest_statement_digest="a" * 64,
        manifest_subject_name="manifest.json",
        entry_name=ENTRY_NAME,
        entry_digest="b" * 64,
        repository_root=ROOT,
    )
    verify_record_inclusion_proof(
        proof,
        expected_root=root.hex(),
        repository_root=ROOT,
    )
    elapsed = time.monotonic() - started
    assert len(proof["auditPath"]) <= 20
    assert elapsed < 15
