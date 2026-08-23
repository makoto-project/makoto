from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from makoto import cli
from makoto.canonical import canonical_json
from makoto.dsse import SigningKey, canonical_b64encode
from makoto.model import Artifact, TransformationInput, create_origin, create_transform
from makoto.schema import DATASET_MANIFEST_MEDIA_TYPE, core_dataset_manifest_profile_reference


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value) + b"\n")


def _verification_policy(keys: dict[str, SigningKey]) -> dict[str, object]:
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
        "limits": {
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
        },
    }


def test_subject_binding_resolves_relative_path_and_preserves_mixed_order(
    tmp_path: Path,
) -> None:
    compact = tmp_path / "compact.bin"
    bound = tmp_path / "data" / "bound.bin"
    compact.write_bytes(b"compact")
    bound.parent.mkdir()
    bound.write_bytes(b"bound")
    binding = tmp_path / "data" / "subject.json"
    write_json(binding, {"name": "name=with-equals", "path": "bound.bin"})
    parser = cli._parser()

    args = parser.parse_args(
        [
            "attest",
            "origin",
            "--subject",
            f"compact={compact}",
            "--subject-binding",
            str(binding),
            "--source-kind",
            "urn:makoto:test:source",
            "--key",
            str(tmp_path / "key.pem"),
            "--out",
            str(tmp_path / "out.json"),
        ]
    )
    artifacts = cli._subjects(args.subject_inputs)

    assert [(item.name, item.data) for item in artifacts] == [
        ("compact", b"compact"),
        ("name=with-equals", b"bound"),
    ]


def test_subject_binding_rejects_unknown_fields(tmp_path: Path) -> None:
    binding = tmp_path / "subject.json"
    write_json(binding, {"name": "subject", "path": "value.bin", "unexpected": True})

    with pytest.raises(cli.CliInputError, match=r"extra=\['unexpected'\]"):
        cli._subjects([("--subject-binding", binding)])


def test_handoff_cli_maps_dataset_material_and_partition_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attestations = tmp_path / "attestations"
    attestations.mkdir()
    origin_path = attestations / "01-origin.dsse.json"
    head_path = attestations / "02-head.dsse.json"
    origin_path.write_bytes(b"origin")
    head_path.write_bytes(b"head")
    final_path = tmp_path / "final.json"
    manifest_path = tmp_path / "dataset-manifest.json"
    partition_path = tmp_path / "part-000.json"
    final_path.write_bytes(b"final")
    manifest_path.write_bytes(b"manifest")
    partition_path.write_bytes(b"partition")
    final_binding = tmp_path / "final-binding.json"
    material_binding = tmp_path / "material-binding.json"
    partition_binding = tmp_path / "partition-binding.json"
    write_json(
        final_binding,
        {
            "head": "attestations/02-head.dsse.json",
            "subjectName": "final.json",
            "path": "final.json",
            "mediaType": "application/json",
        },
    )
    write_json(
        material_binding,
        {
            "statement": "attestations/01-origin.dsse.json",
            "subjectName": "dataset-manifest.json",
            "path": "dataset-manifest.json",
        },
    )
    write_json(
        partition_binding,
        {
            "manifestStatement": "attestations/01-origin.dsse.json",
            "manifestSubjectName": "dataset-manifest.json",
            "entryName": "year=2026/part-000.json",
            "path": "part-000.json",
        },
    )
    profile = core_dataset_manifest_profile_reference(
        "dataset-manifest.json", repository_root=cli.REPOSITORY_ROOT
    )
    origin = SimpleNamespace(statement={"predicate": {"profiles": [profile]}})
    head = object()
    loaded = {origin_path.resolve(): origin, head_path.resolve(): head}
    monkeypatch.setattr(
        cli,
        "load_attestation",
        lambda path, repository_root: loaded[path.resolve()],
    )
    monkeypatch.setattr(cli, "_signing_keys", lambda paths: [object()])
    captured: dict[str, Any] = {}

    def fake_write_handoff_bundle(**kwargs: Any) -> dict[str, object]:
        captured.update(kwargs)
        return {"created": True}

    monkeypatch.setattr(cli, "write_handoff_bundle", fake_write_handoff_bundle)
    args = cli._parser().parse_args(
        [
            "handoff",
            "create",
            "--head",
            str(head_path),
            "--attestations",
            str(attestations),
            "--artifact-binding",
            str(final_binding),
            "--artifact-material",
            str(material_binding),
            "--dataset-entry-binding",
            str(partition_binding),
            "--key",
            str(tmp_path / "key.pem"),
            "--out",
            str(tmp_path / "bundle"),
        ]
    )

    assert cli._cmd_handoff_create(args) == 0

    assert captured["heads"] == [head]
    assert captured["historical_artifacts"] == []
    assert captured["dataset_manifests"][0][0].name == "dataset-manifest.json"
    assert captured["dataset_manifests"][0][1] is origin
    assert captured["dataset_entries"][0][0].data == b"partition"
    assert captured["dataset_entries"][0][1:] == (
        origin,
        "dataset-manifest.json",
        "year=2026/part-000.json",
    )
    captured_output = capsys.readouterr()
    assert captured_output.out == ""
    assert captured_output.err == ""


def test_handoff_cli_bundles_ordinary_historical_artifact_material(tmp_path: Path) -> None:
    origin_key = SigningKey.from_seed(bytes([31]) * 32)
    transform_key = SigningKey.from_seed(bytes([32]) * 32)
    handoff_key = SigningKey.from_seed(bytes([33]) * 32)
    raw = Artifact("raw.json", b'{"value":1}\n')
    final = Artifact("final.json", b'{"value":2}\n', "application/json")
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111131",
        occurred_at="2026-09-16T16:00:00Z",
        source_kind="urn:makoto:test:source",
        signing_key=origin_key,
        repository_root=cli.REPOSITORY_ROOT,
    )
    transform = create_transform(
        artifacts=[final],
        inputs=[TransformationInput("raw", raw, origin, raw.name)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222232",
        occurred_at="2026-09-16T16:01:00Z",
        operation_type="urn:makoto:test:operation:transform",
        signing_key=transform_key,
        repository_root=cli.REPOSITORY_ROOT,
    )
    attestations = tmp_path / "attestations"
    write_json(attestations / "01-origin.dsse.json", origin.envelope)
    write_json(attestations / "02-transform.dsse.json", transform.envelope)
    (tmp_path / "raw.json").write_bytes(raw.data)
    (tmp_path / "final.json").write_bytes(final.data)
    (tmp_path / "handoff.private.pem").write_bytes(handoff_key.private_pkcs8_pem())
    final_binding = tmp_path / "final-binding.json"
    material_binding = tmp_path / "material-binding.json"
    write_json(
        final_binding,
        {
            "head": "attestations/02-transform.dsse.json",
            "subjectName": final.name,
            "path": "final.json",
            "mediaType": "application/json",
        },
    )
    write_json(
        material_binding,
        {
            "statement": "attestations/01-origin.dsse.json",
            "subjectName": raw.name,
            "path": "raw.json",
        },
    )
    bundle_path = tmp_path / "bundle"
    args = cli._parser().parse_args(
        [
            "handoff",
            "create",
            "--head",
            str(attestations / "02-transform.dsse.json"),
            "--attestations",
            str(attestations),
            "--artifact-binding",
            str(final_binding),
            "--artifact-material",
            str(material_binding),
            "--bundle-id",
            "urn:uuid:55555555-5555-4555-8555-555555555533",
            "--issued-at",
            "2026-09-16T16:02:00Z",
            "--key",
            str(tmp_path / "handoff.private.pem"),
            "--out",
            str(bundle_path),
        ]
    )

    assert cli._cmd_handoff_create(args) == 0

    bundle = cli._strict_object(bundle_path / "bundle.json")
    historical = [
        item for item in bundle["artifacts"] if item["statementDigest"] == origin.digest()
    ]
    assert len(historical) == 1
    assert historical[0]["subjectName"] == raw.name
    assert (bundle_path / historical[0]["path"]).read_bytes() == raw.data


def test_origin_cli_attests_dataset_manifest_with_exact_core_profile(tmp_path: Path) -> None:
    partition = Artifact("part-000.json", b'{"customer_id":"abc"}\n')
    manifest = Artifact(
        "customers.dataset-manifest.json",
        canonical_json(
            {
                "version": "0.2",
                "entries": [
                    {
                        "name": "year=2026/part-000.json",
                        "digest": partition.digest(),
                        "size": len(partition.data),
                    }
                ],
            }
        )
        + b"\n",
        DATASET_MANIFEST_MEDIA_TYPE,
    )
    manifest_path = tmp_path / manifest.name
    manifest_path.write_bytes(manifest.data)
    profile = core_dataset_manifest_profile_reference(
        manifest.name, repository_root=cli.REPOSITORY_ROOT
    )
    profile_path = tmp_path / "dataset-profile.json"
    write_json(profile_path, profile)
    key = SigningKey.from_seed(bytes([51]) * 32)
    key_path = tmp_path / "origin.private.pem"
    key_path.write_bytes(key.private_pkcs8_pem())
    output = tmp_path / "origin.dsse.json"
    args = cli._parser().parse_args(
        [
            "attest",
            "origin",
            "--subject",
            f"{manifest.name}={manifest_path}",
            "--source-kind",
            "urn:makoto:test:dataset-source",
            "--profile",
            str(profile_path),
            "--event-id",
            "urn:uuid:11111111-1111-4111-8111-111111111151",
            "--occurred-at",
            "2026-09-16T16:00:00Z",
            "--key",
            str(key_path),
            "--out",
            str(output),
        ]
    )

    assert cli._cmd_attest_origin(args) == 0

    attestation = cli.load_attestation(output, repository_root=cli.REPOSITORY_ROOT)
    assert attestation.subject(manifest.name)["digest"] == manifest.digest()
    assert attestation.statement["predicate"]["profiles"] == [profile]


def _partition_transform_fixture(
    tmp_path: Path,
    *,
    entry_name: str = "year=2026/part-000.json",
    declared_size: int | None = None,
) -> tuple[Path, Path, Path, Path, Path]:
    partition = Artifact("part-000.json", b'{"customer_id":"abc"}\n')
    entry: dict[str, object] = {"name": entry_name, "digest": partition.digest()}
    if declared_size is not None:
        entry["size"] = declared_size
    manifest = Artifact(
        "customers.dataset-manifest.json",
        canonical_json({"version": "0.2", "entries": [entry]}) + b"\n",
        DATASET_MANIFEST_MEDIA_TYPE,
    )
    profile = core_dataset_manifest_profile_reference(
        manifest.name, repository_root=cli.REPOSITORY_ROOT
    )
    origin = create_origin(
        artifacts=[manifest],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111161",
        occurred_at="2026-09-16T16:00:00Z",
        source_kind="urn:makoto:test:dataset-source",
        signing_key=SigningKey.from_seed(bytes([61]) * 32),
        repository_root=cli.REPOSITORY_ROOT,
        profiles=[profile],
    )
    predecessor_path = tmp_path / "origin.dsse.json"
    manifest_path = tmp_path / manifest.name
    partition_path = tmp_path / partition.name
    output_path = tmp_path / "output.json"
    key_path = tmp_path / "transform.private.pem"
    write_json(predecessor_path, origin.envelope)
    manifest_path.write_bytes(manifest.data)
    partition_path.write_bytes(partition.data)
    output_path.write_bytes(b'{"customer_id":"abc","safe":true}\n')
    key_path.write_bytes(SigningKey.from_seed(bytes([62]) * 32).private_pkcs8_pem())
    return predecessor_path, manifest_path, partition_path, output_path, key_path


def test_transform_cli_verifies_partition_membership_before_signing(tmp_path: Path) -> None:
    predecessor, manifest, partition, output, key = _partition_transform_fixture(
        tmp_path, declared_size=len(b'{"customer_id":"abc"}\n')
    )
    binding = tmp_path / "input-binding.json"
    write_json(
        binding,
        {
            "name": "selected-partition",
            "path": partition.name,
            "predecessor": predecessor.name,
            "subjectName": manifest.name,
            "entryName": "year=2026/part-000.json",
            "predecessorMaterial": manifest.name,
        },
    )
    envelope_path = tmp_path / "transform.dsse.json"
    args = cli._parser().parse_args(
        [
            "attest",
            "transform",
            "--subject",
            f"output.json={output}",
            "--input-binding",
            str(binding),
            "--operation-type",
            "urn:makoto:test:operation:partition-transform",
            "--event-id",
            "urn:uuid:22222222-2222-4222-8222-222222222262",
            "--occurred-at",
            "2026-09-16T16:01:00Z",
            "--key",
            str(key),
            "--out",
            str(envelope_path),
        ]
    )

    assert cli._cmd_attest_transform(args) == 0

    attestation = cli.load_attestation(envelope_path, repository_root=cli.REPOSITORY_ROOT)
    signed_input = attestation.statement["predicate"]["inputs"][0]
    assert signed_input["provenance"]["entryName"] == "year=2026/part-000.json"
    assert signed_input["digest"] == Artifact.from_path(partition).digest()


def test_real_cli_dataset_round_trip_allows_at_receiver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_cli(*arguments: str) -> int:
        monkeypatch.setattr(cli.sys, "argv", ["makoto", *arguments])
        return cli.main()

    keys = {
        "origin": SigningKey.from_seed(bytes([71]) * 32),
        "transform": SigningKey.from_seed(bytes([72]) * 32),
        "handoff": SigningKey.from_seed(bytes([73]) * 32),
    }
    key_paths: dict[str, Path] = {}
    for name, key in keys.items():
        path = tmp_path / f"{name}.private.pem"
        path.write_bytes(key.private_pkcs8_pem())
        key_paths[name] = path

    partition = Artifact("part-000.json", b'{"customer_id":"abc"}\n')
    partition_path = tmp_path / partition.name
    partition_path.write_bytes(partition.data)
    manifest = Artifact(
        "customers.dataset-manifest.json",
        canonical_json(
            {
                "version": "0.2",
                "entries": [
                    {
                        "name": "year=2026/part-000.json",
                        "digest": partition.digest(),
                        "size": len(partition.data),
                    }
                ],
            }
        )
        + b"\n",
        DATASET_MANIFEST_MEDIA_TYPE,
    )
    manifest_path = tmp_path / manifest.name
    manifest_path.write_bytes(manifest.data)
    profile_path = tmp_path / "dataset-profile.json"
    write_json(
        profile_path,
        core_dataset_manifest_profile_reference(manifest.name, repository_root=cli.REPOSITORY_ROOT),
    )

    attestations = tmp_path / "attestations"
    origin_path = attestations / "01-origin.dsse.json"
    assert (
        run_cli(
            "attest",
            "origin",
            "--subject",
            f"{manifest.name}={manifest_path}",
            "--source-kind",
            "urn:makoto:test:dataset-source",
            "--profile",
            str(profile_path),
            "--event-id",
            "urn:uuid:11111111-1111-4111-8111-111111111171",
            "--occurred-at",
            "2026-09-16T16:00:00Z",
            "--key",
            str(key_paths["origin"]),
            "--out",
            str(origin_path),
        )
        == 0
    )

    transformed_path = tmp_path / "customers.safe.json"
    transformed_path.write_bytes(b'{"customer_id":"abc","safe":true}\n')
    input_binding = tmp_path / "partition-input.json"
    write_json(
        input_binding,
        {
            "name": "selected-partition",
            "path": partition.name,
            "predecessor": "attestations/01-origin.dsse.json",
            "subjectName": manifest.name,
            "entryName": "year=2026/part-000.json",
            "predecessorMaterial": manifest.name,
        },
    )
    transform_path = attestations / "02-transform.dsse.json"
    assert (
        run_cli(
            "attest",
            "transform",
            "--subject",
            f"{transformed_path.name}={transformed_path}",
            "--input-binding",
            str(input_binding),
            "--operation-type",
            "urn:makoto:test:operation:partition-transform",
            "--event-id",
            "urn:uuid:22222222-2222-4222-8222-222222222272",
            "--occurred-at",
            "2026-09-16T16:01:00Z",
            "--key",
            str(key_paths["transform"]),
            "--out",
            str(transform_path),
        )
        == 0
    )
    transform = cli.load_attestation(transform_path, repository_root=cli.REPOSITORY_ROOT)

    artifact_binding = tmp_path / "final-artifact.json"
    write_json(
        artifact_binding,
        {
            "head": "attestations/02-transform.dsse.json",
            "subjectName": transformed_path.name,
            "path": transformed_path.name,
            "mediaType": "application/json",
        },
    )
    manifest_binding = tmp_path / "dataset-material.json"
    write_json(
        manifest_binding,
        {
            "statement": "attestations/01-origin.dsse.json",
            "subjectName": manifest.name,
            "path": manifest.name,
        },
    )
    entry_binding = tmp_path / "dataset-entry.json"
    write_json(
        entry_binding,
        {
            "manifestStatement": "attestations/01-origin.dsse.json",
            "manifestSubjectName": manifest.name,
            "entryName": "year=2026/part-000.json",
            "path": partition.name,
        },
    )
    bundle_path = tmp_path / "bundle"
    assert (
        run_cli(
            "handoff",
            "create",
            "--head",
            str(transform_path),
            "--attestations",
            str(attestations),
            "--artifact-binding",
            str(artifact_binding),
            "--artifact-material",
            str(manifest_binding),
            "--dataset-entry-binding",
            str(entry_binding),
            "--bundle-id",
            "urn:uuid:55555555-5555-4555-8555-555555555573",
            "--issued-at",
            "2026-09-16T16:02:00Z",
            "--key",
            str(key_paths["handoff"]),
            "--out",
            str(bundle_path),
        )
        == 0
    )
    capsys.readouterr()

    policy_path = tmp_path / "receiver-policy.json"
    write_json(policy_path, _verification_policy(keys))
    assert (
        run_cli(
            "verify",
            "bundle",
            str(bundle_path),
            "--policy",
            str(policy_path),
            "--expected-head",
            f"sha256:{transform.digest()['sha256']}",
            "--evaluation-time",
            "2026-09-16T16:03:00Z",
            "--json",
        )
        == 0
    )
    report = cli.strict_json_loads(capsys.readouterr().out.encode())

    assert report["decision"] == "allow", report["errors"]
    assert report["summary"]["statementsReachable"] == 2
    assert report["summary"]["historicalMaterialsChecked"] == 1
    assert len(report["datasetEntries"]) == 1
    assert report["datasetEntries"][0]["digestStatus"] == "pass"
    assert {item["digestStatus"] for item in report["artifacts"]} == {"pass"}
    cli.validate_core("verification-report", report, repository_root=cli.REPOSITORY_ROOT)


@pytest.mark.parametrize(
    ("entry_name", "include_material", "error"),
    [
        ("year=2026/part-000.json", False, "entryName and predecessorMaterial together"),
        (None, True, "entryName and predecessorMaterial together"),
        ("year=2026/missing.json", True, "not a member"),
    ],
)
def test_transform_cli_rejects_unprovable_partition_binding(
    tmp_path: Path,
    entry_name: str | None,
    include_material: bool,
    error: str,
) -> None:
    predecessor, manifest, partition, output, key = _partition_transform_fixture(tmp_path)
    value = {
        "name": "selected-partition",
        "path": partition.name,
        "predecessor": predecessor.name,
        "subjectName": manifest.name,
    }
    if entry_name is not None:
        value["entryName"] = entry_name
    if include_material:
        value["predecessorMaterial"] = manifest.name
    binding = tmp_path / "input-binding.json"
    write_json(binding, value)
    envelope_path = tmp_path / "transform.dsse.json"
    args = cli._parser().parse_args(
        [
            "attest",
            "transform",
            "--subject",
            f"output.json={output}",
            "--input-binding",
            str(binding),
            "--operation-type",
            "urn:makoto:test:operation:partition-transform",
            "--key",
            str(key),
            "--out",
            str(envelope_path),
        ]
    )

    with pytest.raises(cli.CliInputError, match=error):
        cli._cmd_attest_transform(args)
    assert not envelope_path.exists()


def test_transform_cli_rejects_partition_size_mismatch(tmp_path: Path) -> None:
    predecessor, manifest, partition, output, key = _partition_transform_fixture(
        tmp_path, declared_size=1
    )
    binding = tmp_path / "input-binding.json"
    write_json(
        binding,
        {
            "name": "selected-partition",
            "path": partition.name,
            "predecessor": predecessor.name,
            "subjectName": manifest.name,
            "entryName": "year=2026/part-000.json",
            "predecessorMaterial": manifest.name,
        },
    )
    args = cli._parser().parse_args(
        [
            "attest",
            "transform",
            "--subject",
            f"output.json={output}",
            "--input-binding",
            str(binding),
            "--operation-type",
            "urn:makoto:test:operation:partition-transform",
            "--key",
            str(key),
            "--out",
            str(tmp_path / "transform.dsse.json"),
        ]
    )

    with pytest.raises(cli.CliInputError, match="byte count"):
        cli._cmd_attest_transform(args)
