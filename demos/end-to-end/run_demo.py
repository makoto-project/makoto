"""Build and verify the canonical Makoto v0.2 September 16 demonstration."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from makoto.bundle import load_attestation, write_handoff_bundle
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.dsse import SigningKey, canonical_b64decode, canonical_b64encode
from makoto.model import Artifact, Attestation, TransformationInput, create_transform
from makoto.schema import strict_json_loads, validate_core

ROOT = Path(__file__).resolve().parents[2]
DEMO = Path(__file__).resolve().parent
WORK = DEMO / ".work"
TIME = "2026-09-16T16:00:00Z"
NEGATIVE_EXPECTATIONS = ROOT / "testdata" / "v0.2" / "negative"


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


def _run(*arguments: str, capture: bool = False, expect: int = 0) -> str:
    print("$ makoto " + " ".join(arguments))
    completed = subprocess.run(
        [sys.executable, "-m", "makoto.cli", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=capture,
        text=True,
    )
    if completed.returncode != expect:
        raise RuntimeError(
            f"command exited {completed.returncode}, expected {expect}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    if not capture and completed.stdout:
        print(completed.stdout, end="")
    return completed.stdout


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value) + b"\n")


def _fixed_keys() -> dict[str, SigningKey]:
    names = ("origin", "normalize", "public", "handoff", "attacker")
    keys = {
        name: SigningKey.from_seed(bytes([index]) * 32) for index, name in enumerate(names, start=1)
    }
    for name, key in keys.items():
        (WORK / "keys").mkdir(parents=True, exist_ok=True)
        (WORK / "keys" / f"{name}.private.pem").write_bytes(key.private_pkcs8_pem())
        (WORK / "keys" / f"{name}.public.pem").write_bytes(key.public_spki_pem())
    return keys


def _build_receiver_catalog() -> Path:
    resources_dir = WORK / "receiver" / "resources"
    entries: list[dict[str, Any]] = []
    for source in sorted((DEMO / "private-schemas" / "example.internal").glob("*.json")):
        raw = source.read_bytes()
        value = strict_json_loads(raw)
        assert isinstance(value, dict)
        digest = sha256_bytes(raw)
        destination = resources_dir / f"{digest}.schema.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        entries.append(
            {
                "id": value["$id"],
                "digest": {"sha256": digest},
                "path": f"resources/{digest}.schema.json",
            }
        )
    entries.sort(key=lambda item: (item["id"].encode(), item["digest"]["sha256"]))
    catalog = {"version": "0.2", "resources": entries}
    path = WORK / "receiver" / "catalog.json"
    _write_json(path, catalog)
    validate_core("catalog", catalog, repository_root=ROOT)
    return path


def _create_profiles(catalog: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    predicate_path = WORK / "receiver" / "public-transform-metadata.profile.json"
    artifact_path = WORK / "receiver" / "customer-public.profile.json"
    _run(
        "profile",
        "create",
        "--schema-root",
        str(DEMO / "private-schemas/example.internal/public-transform-metadata-v1.schema.json"),
        "--target",
        "predicate",
        "--critical",
        "true",
        "--schema-catalog",
        str(catalog),
        "--out",
        str(predicate_path),
    )
    _run(
        "profile",
        "create",
        "--schema-root",
        str(DEMO / "private-schemas/example.internal/customer-public-v1.schema.json"),
        "--target",
        "artifact",
        "--subject-name",
        "customers.public.json",
        "--media-type",
        "application/json",
        "--critical",
        "true",
        "--schema-catalog",
        str(catalog),
        "--out",
        str(artifact_path),
    )
    return _object(predicate_path), _object(artifact_path)


def _build_policy(
    keys: dict[str, SigningKey],
    predicate_profile: dict[str, Any],
    artifact_profile: dict[str, Any],
    *,
    include_attacker: bool = False,
) -> dict[str, Any]:
    configured = ("origin", "normalize", "public", "handoff")
    if include_attacker:
        configured += ("attacker",)
    return {
        "version": "0.2",
        "keys": {
            keys[name].keyid(): {
                "type": "ed25519",
                "publicKey": canonical_b64encode(keys[name].public_spki()),
                "label": f"insecure demo-only {name} key",
            }
            for name in configured
        },
        "rules": [
            {
                "id": "urn:makoto:demo:rule:normalize",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
                "authorizedKeyIds": [keys["normalize"].keyid()],
                "minimumSignatures": 1,
                "operationTypes": ["urn:makoto:demo:operation:normalize"],
            },
            {
                "id": "urn:makoto:demo:rule:origin",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/origin"],
                "authorizedKeyIds": [keys["origin"].keyid()],
                "minimumSignatures": 1,
                "sourceKinds": ["urn:makoto:demo:source:synthetic-file"],
                "sourceUris": ["urn:makoto:demo:v0.2:source:customers-raw"],
            },
            {
                "id": "urn:makoto:demo:rule:public-safe",
                "predicateTypes": ["https://usemakoto.dev/predicate/v0.2/transform"],
                "authorizedKeyIds": [keys["public"].keyid()],
                "minimumSignatures": 1,
                "operationTypes": ["urn:makoto:demo:operation:public-safe"],
                "profileConstraints": [
                    {
                        "id": predicate_profile["id"],
                        "digest": predicate_profile["digest"],
                        "closureDigest": predicate_profile["closureDigest"],
                        "target": "predicate",
                    }
                ],
            },
        ],
        "handoff": {
            "authorizedKeyIds": [keys["handoff"].keyid()],
            "minimumSignatures": 1,
            "requireExpectedManifest": True,
            "requireExpectedHead": True,
            "requireExpectedArtifacts": True,
            "requireRecipient": False,
            "requireNonce": False,
            "allowReplayableHandoff": False,
        },
        "requiredProfiles": [
            {
                "id": artifact_profile["id"],
                "digest": artifact_profile["digest"],
                "closureDigest": artifact_profile["closureDigest"],
                "target": "artifact",
                "subjectName": artifact_profile["subjectName"],
                "mediaType": artifact_profile["mediaType"],
                "scope": "eachMatchingFinalArtifact",
            }
        ],
        "limits": _limits(),
    }


def _positive_flow(
    keys: dict[str, SigningKey],
    catalog: Path,
    predicate_profile: dict[str, Any],
    artifact_profile: dict[str, Any],
) -> tuple[dict[str, Attestation], Artifact, dict[str, Any], Path]:
    data = WORK / "data"
    attestations_dir = WORK / "attestations"
    bindings = WORK / "bindings"
    data.mkdir(parents=True, exist_ok=True)
    attestations_dir.mkdir(parents=True, exist_ok=True)
    bindings.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DEMO / "fixtures/customers.raw.json", data / "customers.raw.json")
    subprocess.run(
        [
            sys.executable,
            str(DEMO / "transform.py"),
            "normalize",
            str(data / "customers.raw.json"),
            str(data / "customers.normalized.json"),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(DEMO / "transform.py"),
            "public-safe",
            str(data / "customers.normalized.json"),
            str(data / "customers.public.json"),
        ],
        check=True,
    )
    origin_path = attestations_dir / "01-origin.dsse.json"
    normalize_path = attestations_dir / "02-normalize.dsse.json"
    public_path = attestations_dir / "03-public-safe.dsse.json"
    _run(
        "attest",
        "origin",
        "--subject",
        f"customers.raw.json={data / 'customers.raw.json'}",
        "--source-kind",
        "urn:makoto:demo:source:synthetic-file",
        "--source-uri",
        "urn:makoto:demo:v0.2:source:customers-raw",
        "--event-id",
        "urn:uuid:11111111-1111-4111-8111-111111111111",
        "--occurred-at",
        TIME,
        "--key",
        str(WORK / "keys/origin.private.pem"),
        "--out",
        str(origin_path),
    )
    normalize_binding = bindings / "normalize-input.json"
    _write_json(
        normalize_binding,
        {
            "name": "raw",
            "path": "../data/customers.raw.json",
            "predecessor": "../attestations/01-origin.dsse.json",
            "subjectName": "customers.raw.json",
        },
    )
    _run(
        "attest",
        "transform",
        "--subject",
        f"customers.normalized.json={data / 'customers.normalized.json'}",
        "--input-binding",
        str(normalize_binding),
        "--operation-type",
        "urn:makoto:demo:operation:normalize",
        "--operation-name",
        "Normalize customer records",
        "--event-id",
        "urn:uuid:22222222-2222-4222-8222-222222222222",
        "--occurred-at",
        TIME,
        "--key",
        str(WORK / "keys/normalize.private.pem"),
        "--out",
        str(normalize_path),
    )
    public_binding = bindings / "public-input.json"
    _write_json(
        public_binding,
        {
            "name": "normalized",
            "path": "../data/customers.normalized.json",
            "predecessor": "../attestations/02-normalize.dsse.json",
            "subjectName": "customers.normalized.json",
        },
    )
    _run(
        "attest",
        "transform",
        "--subject",
        f"customers.public.json={data / 'customers.public.json'}",
        "--input-binding",
        str(public_binding),
        "--operation-type",
        "urn:makoto:demo:operation:public-safe",
        "--operation-name",
        "Remove direct identifiers and bucket ages",
        "--extensions",
        str(DEMO / "fixtures/final-extensions.json"),
        "--profile",
        str(WORK / "receiver/public-transform-metadata.profile.json"),
        "--profile",
        str(WORK / "receiver/customer-public.profile.json"),
        "--schema-catalog",
        str(catalog),
        "--event-id",
        "urn:uuid:33333333-3333-4333-8333-333333333333",
        "--occurred-at",
        TIME,
        "--key",
        str(WORK / "keys/public.private.pem"),
        "--out",
        str(public_path),
    )
    loaded = {
        "origin": load_attestation(origin_path, repository_root=ROOT),
        "normalize": load_attestation(normalize_path, repository_root=ROOT),
        "public": load_attestation(public_path, repository_root=ROOT),
    }
    public_artifact = Artifact.from_path(
        data / "customers.public.json",
        name="customers.public.json",
        media_type="application/json",
    )
    artifact_binding = bindings / "final-artifact.json"
    _write_json(
        artifact_binding,
        {
            "head": "../attestations/03-public-safe.dsse.json",
            "subjectName": public_artifact.name,
            "path": "../data/customers.public.json",
            "mediaType": "application/json",
        },
    )
    required_profile = _required_profile_binding(loaded["public"], artifact_profile)
    required_profile_path = bindings / "required-profile.json"
    _write_json(required_profile_path, required_profile)
    bundle = WORK / "positive-bundle"
    _run(
        "handoff",
        "create",
        "--head",
        str(public_path),
        "--attestations",
        str(attestations_dir),
        "--artifact-binding",
        str(artifact_binding),
        "--required-profile-binding",
        str(required_profile_path),
        "--schema-catalog",
        str(catalog),
        "--bundle-id",
        "urn:uuid:55555555-5555-4555-8555-555555555555",
        "--issued-at",
        TIME,
        "--recipient",
        "example:downstream-team",
        "--key",
        str(WORK / "keys/handoff.private.pem"),
        "--out",
        str(bundle),
        capture=True,
    )
    bundle_index = strict_json_loads((bundle / "bundle.json").read_bytes())
    manifest_envelope = strict_json_loads((bundle / bundle_index["manifest"]).read_bytes())
    manifest_payload = canonical_b64decode(manifest_envelope["payload"])
    created = {
        "handoff": strict_json_loads(manifest_payload),
        "manifestDigest": {"sha256": sha256_bytes(manifest_payload)},
    }
    return loaded, public_artifact, created, bundle


def _required_profile_binding(
    head: Attestation, artifact_profile: dict[str, Any]
) -> dict[str, Any]:
    return {
        "head": head.digest(),
        "id": artifact_profile["id"],
        "digest": artifact_profile["digest"],
        "closureDigest": artifact_profile["closureDigest"],
        "target": "artifact",
        "subjectName": artifact_profile["subjectName"],
        "mediaType": artifact_profile["mediaType"],
        "scope": "eachMatchingFinalArtifact",
    }


def _expectations(created: dict[str, Any], artifact: Artifact) -> dict[str, Any]:
    handoff = created["handoff"]
    return {
        "manifest": created["manifestDigest"],
        "head": handoff["heads"][0],
        "artifact": {
            "head": handoff["artifacts"][0]["head"],
            "subjectName": handoff["artifacts"][0]["name"],
            "digest": artifact.digest(),
        },
    }


def _verify_case(
    name: str,
    bundle: Path,
    policy: Path,
    catalog: Path,
    expected: dict[str, Any],
    primary_error: str | None,
) -> dict[str, Any]:
    expected_artifact = WORK / "expected" / f"{name}.artifact.json"
    _write_json(expected_artifact, expected["artifact"])
    arguments = [
        "verify",
        "bundle",
        str(bundle),
        "--policy",
        str(policy),
        "--schema-catalog",
        str(catalog),
        "--expected-manifest",
        f"sha256:{expected['manifest']['sha256']}",
        "--expected-head",
        f"sha256:{expected['head']['sha256']}",
        "--expected-artifact",
        str(expected_artifact),
        "--evaluation-time",
        TIME,
        "--json",
    ]
    output = _run(*arguments, capture=True, expect=0 if primary_error is None else 1)
    report = json.loads(output)
    validate_core("verification-report", report, repository_root=ROOT)
    if report["primaryError"] != primary_error:
        raise RuntimeError(
            f"{name}: primaryError {report['primaryError']!r}, expected {primary_error!r}"
        )
    if primary_error is not None:
        _compare_expected_report(name, report)
    destination = WORK / "reports" / f"{name}.json"
    _write_json(destination, report)
    print(f"{name}: {report['decision'].upper()} ({report['primaryError'] or 'all checks pass'})")
    return report


def _compare_expected_report(name: str, report: dict[str, Any]) -> None:
    expected = _object(NEGATIVE_EXPECTATIONS / name / "expected-report.json")
    for field in (
        "requiredErrorCodes",
        "allowedAdditionalErrorCodes",
        "requiredWarningCodes",
        "allowedAdditionalWarningCodes",
    ):
        values = expected[field]
        if len(values) != len(set(values)):
            raise RuntimeError(f"{name}: expected {field} contains duplicates")
    if report["decision"] != expected["decision"]:
        raise RuntimeError(f"{name}: decision differs from expected-report.json")
    if report["primaryError"] != expected["primaryError"]:
        raise RuntimeError(f"{name}: primaryError differs from expected-report.json")
    actual_errors = {item["code"] for item in report["errors"]}
    required_errors = set(expected["requiredErrorCodes"])
    allowed_errors = required_errors | set(expected["allowedAdditionalErrorCodes"])
    if not required_errors <= actual_errors or not actual_errors <= allowed_errors:
        raise RuntimeError(f"{name}: error-code set differs from expected-report.json")
    actual_warnings = {item["code"] for item in report["warnings"]}
    required_warnings = set(expected["requiredWarningCodes"])
    allowed_warnings = required_warnings | set(expected["allowedAdditionalWarningCodes"])
    if not required_warnings <= actual_warnings or not actual_warnings <= allowed_warnings:
        raise RuntimeError(f"{name}: warning-code set differs from expected-report.json")
    actual_checks = {item["id"]: item["status"] for item in report["checks"]}
    expected_checks = expected["checks"]
    if set(actual_checks) != set(expected_checks):
        raise RuntimeError(f"{name}: check-ID set differs from expected-report.json")
    for check_id, status in actual_checks.items():
        allowed_statuses = expected_checks[check_id]
        if len(allowed_statuses) != len(set(allowed_statuses)) or status not in allowed_statuses:
            raise RuntimeError(f"{name}: unexpected status {status!r} for {check_id}")


def _replacement_bundle(
    name: str,
    attestations: list[Attestation],
    head: Attestation,
    artifact: Artifact,
    keys: dict[str, SigningKey],
    artifact_profile: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    output = WORK / "negative" / name / "bundle"
    created = write_handoff_bundle(
        attestations=attestations,
        heads=[head],
        final_artifacts=[(artifact, head)],
        bundle_id=f"urn:makoto:demo:negative:{name}",
        issued_at=TIME,
        signing_key=keys["handoff"],
        output=output,
        repository_root=ROOT,
        recipient="example:downstream-team",
        required_profiles=[_required_profile_binding(head, artifact_profile)],
    )
    return output, _expectations(created, artifact)


def _stale_modified(attestation: Attestation, mutate: Any) -> Attestation:
    statement = copy.deepcopy(attestation.statement)
    mutate(statement)
    payload = canonical_json(statement)
    envelope = copy.deepcopy(attestation.envelope)
    envelope["payload"] = canonical_b64encode(payload)
    return Attestation(statement, payload, envelope)


def _negative_cases(
    loaded: dict[str, Attestation],
    public_artifact: Artifact,
    positive_bundle: Path,
    positive_expected: dict[str, Any],
    keys: dict[str, SigningKey],
    predicate_profile: dict[str, Any],
    artifact_profile: dict[str, Any],
    policy_path: Path,
    catalog: Path,
) -> None:
    mutated = WORK / "negative/mutated-final-data/bundle"
    shutil.copytree(positive_bundle, mutated)
    target = next((mutated / "artifacts/final").iterdir())
    target.write_bytes(target.read_bytes() + b"x")
    _verify_case(
        "mutated-final-data", mutated, policy_path, catalog, positive_expected, "E_ARTIFACT_DIGEST"
    )

    digest_mismatch = WORK / "negative/statement-digest-mismatch/bundle"
    shutil.copytree(positive_bundle, digest_mismatch)
    final_path = digest_mismatch / (
        "attestations/" + loaded["public"].digest()["sha256"] + ".dsse.json"
    )
    envelope = _object(final_path)
    statement = strict_json_loads(canonical_b64decode(envelope["payload"]))
    assert isinstance(statement, dict)
    statement["predicate"]["operation"]["name"] = "Attacker-edited metadata"
    envelope["payload"] = canonical_b64encode(canonical_json(statement))
    _write_json(final_path, envelope)
    _verify_case(
        "statement-digest-mismatch",
        digest_mismatch,
        policy_path,
        catalog,
        positive_expected,
        "E_STATEMENT_DIGEST",
    )

    edited = _stale_modified(
        loaded["public"],
        lambda statement: statement["predicate"]["operation"].update(
            name="Attacker-edited metadata"
        ),
    )
    edited_bundle, edited_expected = _replacement_bundle(
        "edited-signed-metadata",
        [loaded["origin"], loaded["normalize"], edited],
        edited,
        public_artifact,
        keys,
        artifact_profile,
    )
    _verify_case(
        "edited-signed-metadata",
        edited_bundle,
        policy_path,
        catalog,
        edited_expected,
        "E_SIGNATURE_INVALID",
    )

    removed = WORK / "negative/removed-predecessor/bundle"
    shutil.copytree(positive_bundle, removed)
    index = _object(removed / "bundle.json")
    origin_digest = loaded["origin"].digest()["sha256"]
    origin_item = next(
        item for item in index["attestations"] if item["statementDigest"]["sha256"] == origin_digest
    )
    (removed / origin_item["path"]).unlink()
    index["attestations"] = [
        item for item in index["attestations"] if item["statementDigest"]["sha256"] != origin_digest
    ]
    _write_json(removed / "bundle.json", index)
    _verify_case(
        "removed-predecessor",
        removed,
        policy_path,
        catalog,
        positive_expected,
        "E_PREDECESSOR_MISSING",
    )

    def rewire(statement: dict[str, Any]) -> None:
        item = statement["predicate"]["inputs"][0]
        item["digest"] = loaded["origin"].statement["subject"][0]["digest"]
        item["provenance"]["statementDigest"] = loaded["origin"].digest()
        item["provenance"]["subjectName"] = "customers.raw.json"

    rewired = _stale_modified(loaded["public"], rewire)
    rewired_bundle, rewired_expected = _replacement_bundle(
        "rewired-step",
        [loaded["origin"], rewired],
        rewired,
        public_artifact,
        keys,
        artifact_profile,
    )
    _verify_case(
        "rewired-step",
        rewired_bundle,
        policy_path,
        catalog,
        rewired_expected,
        "E_SIGNATURE_INVALID",
    )

    bad_data_path = WORK / "negative/private-schema-violation/customers.public.json"
    subprocess.run(
        [
            sys.executable,
            str(DEMO / "transform.py"),
            "public-safe",
            str(WORK / "data/customers.normalized.json"),
            str(bad_data_path),
            "--reintroduce-email",
        ],
        check=True,
    )
    bad_artifact = Artifact.from_path(
        bad_data_path, name="customers.public.json", media_type="application/json"
    )
    bad_statement = create_transform(
        artifacts=[bad_artifact],
        inputs=[
            TransformationInput(
                "normalized",
                Artifact.from_path(
                    WORK / "data/customers.normalized.json", name="customers.normalized.json"
                ),
                loaded["normalize"],
                "customers.normalized.json",
            )
        ],
        event_id="urn:uuid:33333333-3333-4333-8333-333333333333",
        occurred_at=TIME,
        operation_type="urn:makoto:demo:operation:public-safe",
        operation_name="Remove direct identifiers and bucket ages",
        signing_key=keys["public"],
        repository_root=ROOT,
        profiles=[predicate_profile, artifact_profile],
        extensions={"urn:makoto:demo:privacy-reviewed": True},
    )
    bad_bundle, bad_expected = _replacement_bundle(
        "private-schema-violation",
        [loaded["origin"], loaded["normalize"], bad_statement],
        bad_statement,
        bad_artifact,
        keys,
        artifact_profile,
    )
    _verify_case(
        "private-schema-violation",
        bad_bundle,
        policy_path,
        catalog,
        bad_expected,
        "E_PROFILE_INVALID",
    )

    attacker_statement = create_transform(
        artifacts=[public_artifact],
        inputs=[
            TransformationInput(
                "normalized",
                Artifact.from_path(
                    WORK / "data/customers.normalized.json", name="customers.normalized.json"
                ),
                loaded["normalize"],
                "customers.normalized.json",
            )
        ],
        event_id="urn:uuid:33333333-3333-4333-8333-333333333333",
        occurred_at=TIME,
        operation_type="urn:makoto:demo:operation:public-safe",
        operation_name="Remove direct identifiers and bucket ages",
        signing_key=keys["attacker"],
        repository_root=ROOT,
        profiles=[predicate_profile, artifact_profile],
        extensions={"urn:makoto:demo:privacy-reviewed": True},
    )
    attacker_bundle, attacker_expected = _replacement_bundle(
        "unauthorized-signer",
        [loaded["origin"], loaded["normalize"], attacker_statement],
        attacker_statement,
        public_artifact,
        keys,
        artifact_profile,
    )
    attacker_policy = WORK / "receiver/attacker-known-policy.json"
    _write_json(
        attacker_policy,
        _build_policy(
            keys,
            predicate_profile,
            artifact_profile,
            include_attacker=True,
        ),
    )
    _verify_case(
        "unauthorized-signer",
        attacker_bundle,
        attacker_policy,
        catalog,
        attacker_expected,
        "E_SIGNER_UNAUTHORIZED",
    )


def _object(path: Path) -> dict[str, Any]:
    value = strict_json_loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _export_demo(destination: Path) -> None:
    resolved = destination.resolve()
    if ROOT.resolve() not in resolved.parents:
        raise ValueError("demo export must remain inside the repository")
    if resolved in {ROOT.resolve(), DEMO.resolve(), WORK.resolve()}:
        raise ValueError("demo export target is too broad")
    shutil.rmtree(resolved, ignore_errors=True)
    resolved.mkdir(parents=True)
    for directory in ("data", "positive-bundle", "receiver", "reports"):
        shutil.copytree(WORK / directory, resolved / directory)
    files = []
    for path in sorted(resolved.rglob("*"), key=lambda item: item.relative_to(resolved).as_posix()):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(resolved).as_posix(),
                    "digest": {"sha256": sha256_bytes(path.read_bytes())},
                }
            )
    _write_json(
        resolved / "manifest.json",
        {"version": "0.2", "generatedAt": TIME, "files": files},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance", action="store_true")
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    if not args.acceptance:
        parser.error("the supported deterministic mode is --acceptance")
    start = time.monotonic()
    print("ACCEPTANCE_START cleanup-and-generation")
    shutil.rmtree(WORK, ignore_errors=True)
    try:
        keys = _fixed_keys()
        catalog = _build_receiver_catalog()
        predicate_profile, artifact_profile = _create_profiles(catalog)
        policy_path = WORK / "receiver/policy.json"
        _write_json(
            policy_path,
            _build_policy(keys, predicate_profile, artifact_profile),
        )
        _run("policy", "check", "--policy", str(policy_path))
        loaded, public_artifact, created, positive_bundle = _positive_flow(
            keys, catalog, predicate_profile, artifact_profile
        )
        positive_expected = _expectations(created, public_artifact)
        _write_json(
            WORK / "receiver/expected-artifact.json",
            positive_expected["artifact"],
        )
        _verify_case(
            "positive",
            positive_bundle,
            policy_path,
            catalog,
            positive_expected,
            None,
        )
        _negative_cases(
            loaded,
            public_artifact,
            positive_bundle,
            positive_expected,
            keys,
            predicate_profile,
            artifact_profile,
            policy_path,
            catalog,
        )
        if args.export is not None:
            _export_demo(args.export)
    except Exception:
        print(f"ACCEPTANCE_FAILURE retained={WORK}", file=sys.stderr)
        raise
    elapsed = time.monotonic() - start
    print("ACCEPTANCE_END reports-compared-and-cleanup")
    print(f"ACCEPTANCE_ELAPSED_SECONDS {elapsed:.3f}")
    if elapsed >= 60:
        raise RuntimeError("acceptance exceeded the 60-second limit")
    shutil.rmtree(WORK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
