from __future__ import annotations

import base64
import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from makoto.canonical import canonical_json
from makoto.dsse import SigningKey, canonical_b64encode
from makoto.schema import (
    DATASET_MANIFEST_MEDIA_TYPE,
    CoreValidationError,
    ProfileResolutionError,
    StrictJsonError,
    core_dataset_manifest_profile_reference,
    create_profile_reference,
    strict_json_loads,
    validate_core,
    validate_with_catalog,
)
from makoto.schema_catalog import SCHEMA_NAMES, build_catalog, serialize
from makoto.standard_registry import STANDARD_RESOURCES, verify_standard_registry
from makoto.unicode15 import UNICODE_VERSION, casefold, normalize_nfc, verify_unicode_data

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "v0.2"
HEX = "a" * 64
DIGEST = {"sha256": HEX}
TEST_KEY = SigningKey.from_seed(bytes(range(32)))
KEY_ID = TEST_KEY.keyid()
TIMESTAMP = "2026-09-16T16:00:00Z"


def load_schemas() -> dict[str, dict[str, Any]]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    }


SCHEMAS = load_schemas()
REGISTRY = Registry()
for schema in SCHEMAS.values():
    REGISTRY = REGISTRY.with_resource(schema["$id"], Resource.from_contents(schema))


def validate(name: str, instance: object) -> None:
    Draft202012Validator(SCHEMAS[f"{name}.schema.json"], registry=REGISTRY).validate(instance)


def profile(target: str = "predicate") -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "https://schemas.example.test/makoto/profile-v1.json",
        "digest": DIGEST,
        "closureDigest": {"sha256": "0" * 64},
        "target": target,
        "critical": True,
        "resources": [],
    }
    if target == "artifact":
        value.update(subjectName="output.json", mediaType="application/json")
    closure_descriptor = {
        "resources": value["resources"],
        "root": {"digest": value["digest"], "id": value["id"]},
    }
    value["closureDigest"] = {
        "sha256": hashlib.sha256(canonical_json(closure_descriptor)).hexdigest()
    }
    return value


def origin() -> dict[str, Any]:
    return {
        "schemaVersion": "0.2",
        "event": {"id": "urn:uuid:11111111-1111-4111-8111-111111111111", "occurredAt": TIMESTAMP},
        "source": {
            "kind": "urn:makoto:test:source:file",
            "uri": "urn:makoto:test:input",
            "mediaType": "application/json",
        },
        "profiles": [],
        "extensions": {"urn:example:test": {"classification": "synthetic"}},
    }


def transform() -> dict[str, Any]:
    return {
        "schemaVersion": "0.2",
        "event": {"id": "urn:uuid:22222222-2222-4222-8222-222222222222", "occurredAt": TIMESTAMP},
        "operation": {"type": "urn:makoto:test:operation:normalize"},
        "inputs": [
            {
                "name": "input.json",
                "digest": DIGEST,
                "provenance": {"statementDigest": DIGEST, "subjectName": "input.json"},
            }
        ],
        "profiles": [],
        "extensions": {},
    }


def statement(predicate_type: str, predicate: dict[str, Any]) -> dict[str, Any]:
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "output.json", "digest": DIGEST}],
        "predicateType": predicate_type,
        "predicate": predicate,
    }


def limits() -> dict[str, int]:
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


def checks() -> list[dict[str, object]]:
    ids = (
        "load-safely",
        "parse-strictly",
        "index-payloads",
        "core-schemas",
        "signatures",
        "authorization-thresholds",
        "metadata-profiles",
        "authorization",
        "graph-dependency-artifacts",
        "graph",
        "roots-and-heads",
        "completeness-anchor",
        "freshness-anchors",
        "artifact-bytes",
        "artifact-profiles",
        "decision",
    )
    return [{"id": check_id, "status": "pass", "prerequisiteChecks": []} for check_id in ids]


def empty_report() -> dict[str, Any]:
    zero_summary = {
        "statementsTotal": 0,
        "quarantinedStatementsTotal": 0,
        "statementsReachable": 0,
        "statementsValid": 0,
        "statementsAuthorized": 0,
        "signaturesTotal": 0,
        "signaturesChecked": 0,
        "signaturesValid": 0,
        "manifestSignaturesRequired": 0,
        "manifestSignaturesValid": 0,
        "manifestSignaturesAuthorized": 0,
        "roots": 0,
        "heads": 0,
        "artifactsDeclared": 0,
        "artifactsChecked": 0,
        "historicalMaterialsDeclared": 0,
        "historicalMaterialsChecked": 0,
        "profilesDeclared": 0,
        "profilesValidated": 0,
    }
    return {
        "reportVersion": "0.2",
        "decision": "allow",
        "reportTruncated": False,
        "primaryError": None,
        "bundleId": None,
        "evaluationTime": TIMESTAMP,
        "policyDigest": DIGEST,
        "policyDigestEncoding": "exact-input-bytes",
        "coreCatalogDigest": DIGEST,
        "manifestDigest": None,
        "expectedManifestDigest": None,
        "handoff": {
            "signatures": [],
            "authorization": "pass",
            "completeness": "pass",
            "freshnessMethod": "none",
            "freshnessChecks": {
                "expected-manifest": "not_checked",
                "expected-heads": "not_checked",
                "expected-artifacts": "not_checked",
                "nonce": "not_checked",
                "max-age": "not_checked",
            },
            "freshnessStatus": "not_checked",
        },
        "expectedHeads": [],
        "actualHeads": [],
        "expectedArtifacts": [],
        "expectedRecipient": None,
        "actualRecipient": None,
        "recipientStatus": "not_checked",
        "expectedNonce": None,
        "actualNonce": None,
        "nonceStatus": "not_checked",
        "roots": [],
        "summary": zero_summary,
        "statements": [],
        "profiles": [],
        "artifacts": [],
        "unindexedEnvelopes": [],
        "quarantinedStatements": [],
        "datasetEntries": [],
        "unreferencedFiles": [],
        "checks": checks(),
        "warnings": [],
        "errors": [],
        "tool": {"name": "makoto", "version": "0.2.0"},
    }


def valid_instances() -> dict[str, object]:
    envelope = {
        "payloadType": "application/vnd.in-toto+json",
        "payload": base64.b64encode(b"{}").decode(),
        "signatures": [{"keyid": KEY_ID, "sig": base64.b64encode(bytes(64)).decode()}],
    }
    handoff = {
        "version": "0.2",
        "bundleId": "urn:uuid:55555555-5555-4555-8555-555555555555",
        "issuedAt": TIMESTAMP,
        "roots": [DIGEST],
        "heads": [DIGEST],
        "statements": [DIGEST],
        "artifacts": [{"name": "output.json", "digest": DIGEST, "head": DIGEST}],
        "requiredProfiles": [],
    }
    policy = {
        "version": "0.2",
        "keys": {
            KEY_ID: {
                "type": "ed25519",
                "publicKey": canonical_b64encode(TEST_KEY.public_spki()),
            }
        },
        "rules": [
            {
                "id": "urn:makoto:test:rule:origin",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/origin"],
                "authorizedKeyIds": [KEY_ID],
                "minimumSignatures": 1,
            }
        ],
        "handoff": {
            "authorizedKeyIds": [KEY_ID],
            "minimumSignatures": 1,
            "requireExpectedManifest": False,
            "requireExpectedHead": True,
            "requireExpectedArtifacts": False,
            "requireRecipient": False,
            "requireNonce": False,
            "allowReplayableHandoff": False,
        },
        "requiredProfiles": [],
        "limits": limits(),
    }
    return {
        "envelope": envelope,
        "statement": statement("https://usemakoto.dev/predicate/v0.2/origin", origin()),
        "origin": origin(),
        "transform": transform(),
        "profile-reference": profile(),
        "profile-dialect": {
            "$schema": "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json",
            "$id": "https://schemas.example.test/profile.json",
            "type": "object",
            "required": ["classification"],
            "properties": {"classification": {"type": "string"}},
        },
        "catalog": {"version": "0.2", "resources": []},
        "dataset-manifest": {
            "version": "0.2",
            "entries": [{"name": "part-000.json", "digest": DIGEST}],
        },
        "handoff": handoff,
        "bundle": {
            "version": "0.2",
            "manifest": "manifest.dsse.json",
            "attestations": [],
            "artifacts": [],
            "datasetEntries": [],
        },
        "trust-policy": policy,
        "verification-report": empty_report(),
    }


def test_schema_set_and_ids_are_exact() -> None:
    assert set(SCHEMAS) == {f"{name}.schema.json" for name in SCHEMA_NAMES}
    for name in SCHEMA_NAMES:
        assert SCHEMAS[f"{name}.schema.json"]["$id"] == (
            f"https://usemakoto.dev/schema/v0.2/{name}.schema.json"
        )


def test_every_schema_is_draft_2020_12_valid() -> None:
    for schema in SCHEMAS.values():
        Draft202012Validator.check_schema(schema)


def test_standard_registry_matches_normative_v02_byte_identities() -> None:
    resources = verify_standard_registry()
    assert tuple(resources) == tuple(item.identifier for item in STANDARD_RESOURCES)
    assert len(resources) == 8


def test_unicode_15_inputs_and_full_case_folding_are_pinned() -> None:
    verify_unicode_data()
    assert UNICODE_VERSION == "15.0.0"
    assert casefold("Straße Σίσυφος") == "strasse σίσυφοσ"
    assert normalize_nfc("e\u0301") == "é"


@pytest.mark.parametrize(("name", "instance"), valid_instances().items())
def test_positive_schema_vectors(name: str, instance: object) -> None:
    validate(name, instance)


@pytest.mark.parametrize(("name", "instance"), valid_instances().items())
def test_positive_core_validation_vectors(name: str, instance: object) -> None:
    validate_core(name, instance, repository_root=ROOT)


@pytest.mark.parametrize(("name", "instance"), valid_instances().items())
def test_closed_roots_reject_unknown_members(name: str, instance: object) -> None:
    invalid = dict(instance)  # type: ignore[arg-type]
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        validate(name, invalid)


def test_statement_dispatches_core_predicate_schema() -> None:
    invalid = statement("https://usemakoto.dev/predicate/v0.2/origin", transform())
    with pytest.raises(ValidationError):
        validate("statement", invalid)


def test_statement_structurally_allows_extension_predicate() -> None:
    validate(
        "statement",
        statement("urn:example:predicate:v1", {"vendorSpecific": True}),
    )


@pytest.mark.parametrize(
    "predicate_type",
    ["x:%zz", "https://example.test/é", "https://[not-ipv6]/predicate"],
)
def test_statement_rejects_non_rfc3986_predicate_uri(predicate_type: str) -> None:
    with pytest.raises(CoreValidationError, match="absolute URI"):
        validate_core(
            "statement",
            statement(predicate_type, {"vendorSpecific": True}),
            repository_root=ROOT,
        )


def test_statement_accepts_valid_opaque_predicate_uri() -> None:
    validate_core(
        "statement",
        statement("x:opaque/value?query=yes", {"vendorSpecific": True}),
        repository_root=ROOT,
    )


def test_subject_name_limit_is_measured_in_utf8_bytes() -> None:
    accepted = statement("urn:example:predicate:v1", {"vendorSpecific": True})
    accepted["subject"][0]["name"] = "😀" * 1024
    validate_core("statement", accepted, repository_root=ROOT)

    rejected = statement("urn:example:predicate:v1", {"vendorSpecific": True})
    rejected["subject"][0]["name"] = "😀" * 1025
    with pytest.raises(CoreValidationError, match="4096 UTF-8 bytes"):
        validate_core("statement", rejected, repository_root=ROOT)


def test_dataset_manifest_rejects_unicode_15_casefold_collisions() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {"name": "part/STRASSE.json", "digest": {"sha256": "a" * 64}},
            {"name": "part/Straße.json", "digest": {"sha256": "b" * 64}},
        ],
    }

    with pytest.raises(CoreValidationError, match="Unicode 15.0 full case folding"):
        validate_core("dataset-manifest", value, repository_root=ROOT)


def test_dataset_manifest_rejects_non_nfc_entry_name() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {"name": "part/cafe\u0301.json", "digest": DIGEST},
        ],
    }

    with pytest.raises(CoreValidationError, match="not NFC-normalized"):
        validate_core("dataset-manifest", value, repository_root=ROOT)


def test_dataset_manifest_rejects_ascii_del_in_entry_name() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {"name": "part/\u007f.json", "digest": DIGEST},
        ],
    }

    with pytest.raises(CoreValidationError, match="forbidden character"):
        validate_core("dataset-manifest", value, repository_root=ROOT)


def test_dataset_manifest_reserved_basename_uses_ascii_case_only() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {"name": "part/CoN.json", "digest": DIGEST},
        ],
    }

    with pytest.raises(CoreValidationError, match="reserved basename"):
        validate_core("dataset-manifest", value, repository_root=ROOT)


def test_dataset_manifest_accepts_distinct_portable_partition_names() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {"name": "year=2026/month=08/part-00000.parquet", "digest": DIGEST},
            {"name": "year=2026/month=09/part-00000.parquet", "digest": {"sha256": "b" * 64}},
        ],
    }

    validate_core("dataset-manifest", value, repository_root=ROOT)


@pytest.mark.parametrize(
    "entry_name",
    [
        "../part.json",
        "/absolute/part.json",
        "directory\\part.json",
        "part/CoN.json",
        "part/cafe\u0301.json",
        "part/\u007f.json",
        "😀" * 257,
    ],
)
def test_transform_entry_name_uses_dataset_logical_path_contract(entry_name: str) -> None:
    value = transform()
    value["inputs"][0]["provenance"]["entryName"] = entry_name

    with pytest.raises(CoreValidationError):
        validate_core("transform", value, repository_root=ROOT)


def test_core_dataset_manifest_profile_is_exact_and_validates_without_catalog() -> None:
    subject_name = "dataset.manifest.json"
    reference = create_profile_reference(
        SCHEMA_DIR / "dataset-manifest.schema.json",
        target="artifact",
        critical=True,
        catalog_paths=[],
        subject_name=subject_name,
        media_type=DATASET_MANIFEST_MEDIA_TYPE,
        repository_root=ROOT,
    )

    assert reference == core_dataset_manifest_profile_reference(subject_name, repository_root=ROOT)
    result = validate_with_catalog(
        valid_instances()["dataset-manifest"],
        reference,
        catalog_paths=[],
        repository_root=ROOT,
    )
    assert result.valid


def test_core_dataset_manifest_profile_rejects_non_core_media_type() -> None:
    with pytest.raises(ProfileResolutionError, match="core media type"):
        create_profile_reference(
            SCHEMA_DIR / "dataset-manifest.schema.json",
            target="artifact",
            critical=True,
            catalog_paths=[],
            subject_name="dataset.manifest.json",
            media_type="application/json",
            repository_root=ROOT,
        )


def test_core_dataset_manifest_profile_rejects_catalog_schema_mismatch(tmp_path: Path) -> None:
    schema_target = tmp_path / "schemas/v0.2"
    shutil.copytree(SCHEMA_DIR, schema_target)
    catalog_path = schema_target / "catalog.json"
    catalog = strict_json_loads(catalog_path.read_bytes())
    assert isinstance(catalog, dict)
    dataset_entry = next(
        item
        for item in catalog["resources"]
        if item["id"] == "https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json"
    )
    dataset_entry["digest"] = {"sha256": "f" * 64}
    catalog_path.write_bytes(canonical_json(catalog) + b"\n")

    with pytest.raises(ProfileResolutionError, match="immutable core catalog"):
        core_dataset_manifest_profile_reference("dataset.manifest.json", repository_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("digest", {"sha256": "f" * 64}),
        ("closureDigest", {"sha256": "f" * 64}),
        ("target", "predicate"),
        ("mediaType", "application/json"),
        ("critical", False),
        ("resources", [{"id": "https://example.test/x", "digest": {"sha256": "f" * 64}}]),
    ],
)
def test_core_dataset_manifest_profile_rejects_direct_identity_mutation(
    field: str, replacement: object
) -> None:
    reference = core_dataset_manifest_profile_reference(
        "dataset.manifest.json", repository_root=ROOT
    )
    reference[field] = replacement

    with pytest.raises((CoreValidationError, ProfileResolutionError)):
        validate_with_catalog(
            valid_instances()["dataset-manifest"],
            reference,
            catalog_paths=[],
            repository_root=ROOT,
        )


def test_artifact_profile_requires_target_fields() -> None:
    invalid = profile("artifact")
    invalid.pop("subjectName")
    with pytest.raises(ValidationError):
        validate("profile-reference", invalid)


def test_non_artifact_profile_forbids_target_fields() -> None:
    invalid = profile("predicate")
    invalid["subjectName"] = "output.json"
    with pytest.raises(ValidationError):
        validate("profile-reference", invalid)


def test_catalog_is_exactly_reproducible_and_digest_pinned() -> None:
    catalog_path = SCHEMA_DIR / "catalog.json"
    assert catalog_path.read_bytes() == serialize(build_catalog())
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    validate("catalog", catalog)
    for resource in catalog["resources"]:
        raw = (SCHEMA_DIR / resource["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == resource["digest"]["sha256"]


def test_v01_schema_is_not_modified_or_accepted_as_v02() -> None:
    legacy = {
        "schema_version": "0.1",
        "id": "dbom-legacy",
        "created_at": TIMESTAMP,
        "source": {},
        "signature": {},
        "lineage": [],
    }
    with pytest.raises(ValidationError):
        validate("statement", legacy)


@pytest.mark.parametrize(
    "raw",
    [
        b'\xef\xbb\xbf{"version":"0.2"}',
        b'{"version":"0.2","version":"0.2"}',
        b'{"value":"\\ud800"}',
        b'{"value":NaN}',
    ],
)
def test_strict_json_rejects_noncanonical_inputs(raw: bytes) -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads(raw)


def test_semantic_validation_rejects_duplicate_subject_names() -> None:
    value = statement("https://usemakoto.dev/predicate/v0.2/origin", origin())
    value["subject"].append({"name": "output.json", "digest": {"sha256": "b" * 64}})
    with pytest.raises(CoreValidationError, match="subject names must be unique"):
        validate_core("statement", value, repository_root=ROOT)


def test_semantic_validation_rejects_invalid_calendar_date() -> None:
    value = origin()
    value["event"]["occurredAt"] = "2026-02-31T16:00:00Z"
    with pytest.raises(CoreValidationError, match="valid UTC RFC 3339"):
        validate_core("origin", value, repository_root=ROOT)


def test_semantic_validation_rejects_unsorted_handoff_sets() -> None:
    value = valid_instances()["handoff"]
    assert isinstance(value, dict)
    value["statements"] = [{"sha256": "b" * 64}, {"sha256": "a" * 64}]
    with pytest.raises(CoreValidationError, match="canonical order"):
        validate_core("handoff", value, repository_root=ROOT)


def test_profile_semantics_reject_nested_standard_pattern() -> None:
    value = valid_instances()["profile-dialect"]
    assert isinstance(value, dict)
    value["properties"] = {"classification": {"type": "string", "pattern": "^public$"}}
    with pytest.raises(CoreValidationError):
        validate_core("profile-dialect", value, repository_root=ROOT)


def test_profile_semantics_reject_unknown_nested_keyword() -> None:
    value = valid_instances()["profile-dialect"]
    assert isinstance(value, dict)
    value["properties"] = {"classification": {"type": "string", "vendorKeyword": True}}
    with pytest.raises(CoreValidationError):
        validate_core("profile-dialect", value, repository_root=ROOT)


def test_statement_recursively_applies_origin_semantics() -> None:
    predicate = origin()
    predicate["event"]["id"] = "not a uri"
    predicate["event"]["occurredAt"] = "2026-02-31T16:00:00Z"
    predicate["source"]["kind"] = "not a uri"
    value = statement("https://usemakoto.dev/predicate/v0.2/origin", predicate)
    with pytest.raises(CoreValidationError, match="event ID"):
        validate_core("statement", value, repository_root=ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(properties={"name": {"type": 42}}),
        lambda value: value.update(
            properties={"name": {"type": "string", "$id": "https://example.test/nested"}}
        ),
    ],
)
def test_profile_dialect_recursively_rejects_invalid_nested_schema(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    value = valid_instances()["profile-dialect"]
    assert isinstance(value, dict)
    mutation(value)
    with pytest.raises(CoreValidationError):
        validate_core("profile-dialect", value, repository_root=ROOT)


def test_profile_dialect_rejects_boolean_resource_root() -> None:
    with pytest.raises(CoreValidationError):
        validate_core("profile-dialect", True, repository_root=ROOT)


def test_profile_dialect_schema_itself_recursively_closes_nested_keywords() -> None:
    validator = Draft202012Validator(SCHEMAS["profile-dialect.schema.json"], registry=REGISTRY)
    base = valid_instances()["profile-dialect"]
    assert isinstance(base, dict)
    for nested in (
        {"type": 7},
        {"totallyUnknown": True},
        {"$id": "https://schemas.example.test/nested", "type": "string"},
    ):
        candidate = dict(base)
        candidate["properties"] = {"value": nested}
        assert list(validator.iter_errors(candidate))
    assert list(validator.iter_errors(True))


def test_profile_dialect_rejects_invalid_and_duplicate_anchors() -> None:
    value = valid_instances()["profile-dialect"]
    assert isinstance(value, dict)
    value["properties"] = {
        "first": {"$anchor": "bad space", "type": "string"},
        "second": {"$anchor": "duplicate", "type": "string"},
        "third": {"$anchor": "duplicate", "type": "string"},
    }

    with pytest.raises(CoreValidationError):
        validate_core("profile-dialect", value, repository_root=ROOT)


def test_profile_reference_recomputes_closure_and_validates_resource_ids() -> None:
    value = profile()
    value["resources"] = [{"id": "not a uri", "digest": DIGEST}]
    with pytest.raises(CoreValidationError, match="resource ID"):
        validate_core("profile-reference", value, repository_root=ROOT)


def test_statement_rejects_duplicate_signed_profile_reference() -> None:
    predicate = origin()
    reference = profile()
    predicate["profiles"] = [reference, dict(reference)]
    value = statement("https://usemakoto.dev/predicate/v0.2/origin", predicate)
    with pytest.raises(CoreValidationError, match="profile references must be unique"):
        validate_core("statement", value, repository_root=ROOT)


def test_policy_recomputes_key_id_and_validates_windows_and_array_order() -> None:
    value = valid_instances()["trust-policy"]
    assert isinstance(value, dict)
    key = value["keys"].pop(KEY_ID)
    value["keys"][f"sha256:{'b' * 64}"] = key
    with pytest.raises(CoreValidationError, match="key ID does not match"):
        validate_core("trust-policy", value, repository_root=ROOT)

    value = valid_instances()["trust-policy"]
    assert isinstance(value, dict)
    value["keys"][KEY_ID]["validFrom"] = "2026-09-17T00:00:00Z"
    value["keys"][KEY_ID]["validUntil"] = "2026-09-16T00:00:00Z"
    value["rules"][0]["predicateTypes"] = [
        "https://usemakoto.dev/predicate/v0.2/transform",
        "https://usemakoto.dev/predicate/v0.2/origin",
    ]
    with pytest.raises(CoreValidationError, match="validFrom must be earlier"):
        validate_core("trust-policy", value, repository_root=ROOT)


def test_policy_rejects_conflicting_required_profile_media_types() -> None:
    value = valid_instances()["trust-policy"]
    assert isinstance(value, dict)
    base = {
        "id": "https://schemas.example.test/makoto/customer-v1.json",
        "digest": DIGEST,
        "closureDigest": DIGEST,
        "target": "artifact",
        "subjectName": "customers.json",
        "scope": "eachMatchingFinalArtifact",
    }
    value["requiredProfiles"] = [
        {**base, "mediaType": "application/json"},
        {**base, "mediaType": "application/x-ndjson"},
    ]

    with pytest.raises(CoreValidationError, match="disagree on media type"):
        validate_core("trust-policy", value, repository_root=ROOT)


def test_envelope_rejects_duplicate_key_ids_and_noncanonical_base64() -> None:
    value = valid_instances()["envelope"]
    assert isinstance(value, dict)
    value["payload"] = "AB=="
    value["signatures"].append(dict(value["signatures"][0]))
    with pytest.raises(CoreValidationError, match="canonical|unique"):
        validate_core("envelope", value, repository_root=ROOT)


def test_bundle_rejects_empty_path_segment() -> None:
    value = valid_instances()["bundle"]
    assert isinstance(value, dict)
    value["manifest"] = "a//manifest.dsse.json"
    with pytest.raises(CoreValidationError, match="empty or dot segment"):
        validate_core("bundle", value, repository_root=ROOT)


def test_extension_https_key_requires_authority() -> None:
    value = origin()
    value["extensions"] = {"https:///no-authority": True}
    with pytest.raises(CoreValidationError, match="extension key"):
        validate_core("origin", value, repository_root=ROOT)


def test_report_accepts_nullable_summary_counters() -> None:
    value = empty_report()
    value["summary"] = {name: None for name in value["summary"]}
    validate_core("verification-report", value, repository_root=ROOT)


def test_report_rejects_unknown_diagnostic_context_and_owner() -> None:
    value = empty_report()
    value["errors"] = [
        {
            "code": "E_JSON_INVALID",
            "step": 2,
            "message": "bad JSON",
            "context": {"inventedSecret": "must not leak"},
            "causedByCheck": "made-up",
        }
    ]
    with pytest.raises(CoreValidationError, match="not valid|owner is invalid|unknown members"):
        validate_core("verification-report", value, repository_root=ROOT)


def test_report_skipped_profile_requires_prerequisite() -> None:
    value = empty_report()
    value["profiles"] = [
        {
            "statementDigest": DIGEST,
            "id": "https://schemas.example.test/profile.json",
            "digest": DIGEST,
            "closureDigest": DIGEST,
            "target": "predicate",
            "subjectName": None,
            "mediaType": None,
            "critical": True,
            "requiredByManifest": False,
            "requiredByPolicy": False,
            "requiredByAuthorizationRuleIds": [],
            "resolution": "skipped",
            "validation": "skipped",
            "prerequisiteChecks": [],
        }
    ]
    with pytest.raises(CoreValidationError, match="requires a prerequisite|non-empty"):
        validate_core("verification-report", value, repository_root=ROOT)


def test_report_diagnostic_code_fixes_step_owner_and_context() -> None:
    value = empty_report()
    value["errors"] = [
        {
            "code": "E_CORE_SCHEMA",
            "step": 2,
            "message": "bundle index is invalid",
            "context": {"path": "bundle.json"},
            "causedByCheck": "parse-strictly",
        }
    ]
    with pytest.raises(CoreValidationError, match="not valid"):
        validate_core("verification-report", value, repository_root=ROOT)

    value["errors"][0] = {
        "code": "E_JSON_INVALID",
        "step": 2,
        "message": "invalid JSON",
        "context": {},
        "causedByCheck": "parse-strictly",
    }
    with pytest.raises(CoreValidationError, match="not valid"):
        validate_core("verification-report", value, repository_root=ROOT)


def test_report_uses_field_specific_prerequisite_languages() -> None:
    value = empty_report()
    value["artifacts"] = [
        {
            "lifecycleRole": "historical",
            "artifactKind": "ordinary",
            "statementDigest": DIGEST,
            "head": None,
            "subjectName": "raw.json",
            "digest": DIGEST,
            "digestStatus": "skipped",
            "digestPrerequisiteChecks": ["resolution"],
            "profileStatus": "not_checked",
            "profilePrerequisiteChecks": [],
            "applicableProfileCount": 0,
        }
    ]
    with pytest.raises(CoreValidationError):
        validate_core("verification-report", value, repository_root=ROOT)

    value = empty_report()
    value["checks"][1] = {
        "id": "parse-strictly",
        "status": "skipped",
        "prerequisiteChecks": ["decision"],
    }
    with pytest.raises(CoreValidationError, match="prerequisite check is invalid"):
        validate_core("verification-report", value, repository_root=ROOT)


def test_profile_prerequisites_explain_validation_not_resolution() -> None:
    value = empty_report()
    value["profiles"] = [
        {
            "statementDigest": DIGEST,
            "id": "https://schemas.example.test/profile.json",
            "digest": DIGEST,
            "closureDigest": DIGEST,
            "target": "predicate",
            "subjectName": None,
            "mediaType": None,
            "critical": False,
            "requiredByManifest": False,
            "requiredByPolicy": False,
            "requiredByAuthorizationRuleIds": [],
            "resolution": "skipped",
            "validation": "not_checked",
            "prerequisiteChecks": [],
        }
    ]
    validate_core("verification-report", value, repository_root=ROOT)


def test_ordinary_core_schemas_never_use_standard_pattern_keywords() -> None:
    for name, schema in SCHEMAS.items():
        if name == "profile-dialect.schema.json":
            continue
        encoded = json.dumps(schema, ensure_ascii=False)
        assert '"pattern"' not in encoded, name
        assert '"patternProperties"' not in encoded, name
