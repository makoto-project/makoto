"""Safe local bundle loading, graph verification, and recipient decisions."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
from collections.abc import Sequence, Set
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from makoto.canonical import canonical_json
from makoto.dataset import DatasetManifestError, DatasetManifestIndex, parse_dataset_manifest
from makoto.digest import digest_object, sha256_bytes
from makoto.dsse import DsseError, SigningKey, canonical_b64decode
from makoto.graph import GraphProblem, build_graph, reachable_from_heads
from makoto.model import (
    HANDOFF_PAYLOAD_TYPE,
    STATEMENT_PAYLOAD_TYPE,
    Artifact,
    Attestation,
    create_handoff,
)
from makoto.policy import AuthorizationResult, SignatureResult, TrustPolicy
from makoto.report import Diagnostic, add_error, add_warning, finalize_report, new_report, set_check
from makoto.schema import (
    DATASET_MANIFEST_MEDIA_TYPE,
    DATASET_MANIFEST_SCHEMA_ID,
    CoreValidationError,
    ProfileResolutionError,
    StrictJsonError,
    core_dataset_manifest_profile_reference,
    load_catalog_resources,
    strict_json_loads,
    validate_core,
    validate_with_catalog,
)
from makoto.schema_catalog import schema_directory
from makoto.unicode15 import casefold, normalize_nfc


class BundleError(ValueError):
    """Raised for invalid invocation or an unrecoverable bundle operation."""


class VerificationConfigurationError(BundleError):
    """Raised before bundle evidence is opened for invalid consumer configuration."""


@dataclass
class VerificationTiming:
    """Observational monotonic accounting for the fourteen verifier steps."""

    steps: dict[int, int] | None = None
    total_nanoseconds: int = 0
    _total_started: int | None = None
    _active_step: int | None = None
    _active_started: int | None = None

    def __post_init__(self) -> None:
        if self.steps is None:
            self.steps = {step: 0 for step in range(1, 15)}

    def begin(self, step: int) -> None:
        now = time.monotonic_ns()
        if self._total_started is None:
            self._total_started = now
        if self._active_step is not None and self._active_started is not None:
            assert self.steps is not None
            self.steps[self._active_step] += now - self._active_started
        self._active_step = step
        self._active_started = now

    def finish(self) -> None:
        now = time.monotonic_ns()
        if self._active_step is not None and self._active_started is not None:
            assert self.steps is not None
            self.steps[self._active_step] += now - self._active_started
        if self._total_started is not None:
            self.total_nanoseconds = now - self._total_started
        self._active_step = None
        self._active_started = None

    def as_dict(self) -> dict[str, object]:
        values = self.steps or {step: 0 for step in range(1, 15)}
        return {
            "steps": {str(step): values[step] for step in range(1, 15)},
            "totalNanoseconds": self.total_nanoseconds,
        }


class EnvelopeLoadFailure(BundleError):
    """A classified bundle-envelope evidence failure owned by one verifier step."""

    def __init__(
        self,
        code: str,
        step: int,
        check: str,
        message: str,
        *,
        payload_type_status: str = "not_checked",
    ) -> None:
        self.code = code
        self.step = step
        self.check = check
        self.payload_type_status = payload_type_status
        super().__init__(message)


@dataclass(frozen=True)
class ArtifactMaterialSource:
    statement_digest: str
    subject_name: str
    digest: str
    path: Path

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.statement_digest, self.subject_name, self.digest)


@dataclass(frozen=True)
class DatasetEntrySource:
    manifest_statement_digest: str
    manifest_subject_name: str
    entry_name: str
    digest: str
    path: Path

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.manifest_statement_digest, self.manifest_subject_name, self.entry_name)


@dataclass(frozen=True)
class VerificationRequest:
    bundle_root: Path
    policy_path: Path
    repository_root: Path
    schema_catalogs: tuple[Path, ...] = ()
    expected_manifest: dict[str, str] | None = None
    expected_heads: tuple[dict[str, str], ...] = ()
    expected_artifacts: tuple[dict[str, Any], ...] = ()
    expected_recipient: str | None = None
    expected_nonce: str | None = None
    evaluation_time: str | None = None
    artifact_materials: tuple[ArtifactMaterialSource, ...] = ()
    dataset_entry_bindings: tuple[DatasetEntrySource, ...] = ()
    consumer_metadata_paths: tuple[Path, ...] = ()
    temp_parent: Path | None = None
    snapshot_root: Path | None = None
    timing: VerificationTiming | None = None


@dataclass(frozen=True)
class EnvelopeRecord:
    envelope: dict[str, Any]
    payload: bytes
    value: dict[str, Any]
    digest: str


@dataclass(frozen=True)
class DatasetVerification:
    """Step 8 results cached for graph and later artifact-profile reuse."""

    indexes: dict[tuple[str, str, str], DatasetManifestIndex]
    memberships: dict[tuple[str, str, str], str]
    snapshots: dict[tuple[str, str, str], bytes]
    profile_states: dict[tuple[str, str, str, str, str], str]
    verified_subjects: frozenset[tuple[str, str]]
    failed_subjects: frozenset[tuple[str, str]]
    edge_entries: dict[tuple[str, str, str], str]


def load_attestation(path: Path, *, repository_root: Path) -> Attestation:
    """Load one strict statement envelope for producer-side graph assembly."""

    parsed = strict_json_loads(path.read_bytes())
    if not isinstance(parsed, dict):
        raise BundleError(f"attestation {path} is not an object")
    validate_core("envelope", parsed, repository_root=repository_root)
    envelope = cast(dict[str, Any], parsed)
    if envelope["payloadType"] != STATEMENT_PAYLOAD_TYPE:
        raise BundleError(f"attestation {path} has the wrong payload type")
    payload = canonical_b64decode(envelope["payload"])
    statement = strict_json_loads(payload)
    if not isinstance(statement, dict):
        raise BundleError(f"attestation payload {path} is not an object")
    validate_core("statement", statement, repository_root=repository_root)
    return Attestation(cast(dict[str, Any], statement), payload, envelope)


def write_handoff_bundle(
    *,
    attestations: list[Attestation],
    heads: list[Attestation],
    final_artifacts: list[tuple[Artifact, Attestation]],
    bundle_id: str,
    issued_at: str,
    signing_key: SigningKey | Sequence[SigningKey],
    output: Path,
    repository_root: Path,
    recipient: str | None = None,
    nonce: str | None = None,
    required_profiles: list[dict[str, object]] | None = None,
    historical_artifacts: list[tuple[Artifact, Attestation]] | None = None,
    dataset_manifests: list[tuple[Artifact, Attestation]] | None = None,
    dataset_entries: list[tuple[Artifact, Attestation, str, str]] | None = None,
    schema_catalog_paths: Sequence[Path] = (),
    external_profiles: Sequence[dict[str, Any]] = (),
    force: bool = False,
) -> dict[str, Any]:
    """Create one deterministic local bundle using identity-hashed artifact paths."""

    statement_map = {attestation.digest()["sha256"]: attestation for attestation in attestations}
    if len(statement_map) != len(attestations):
        raise BundleError("attestations contain duplicate statement payloads")
    historical_materials: dict[tuple[str, str, str], Artifact] = {}
    for artifact, attestation in historical_artifacts or []:
        statement_digest = attestation.digest()["sha256"]
        if statement_digest not in statement_map:
            raise BundleError("historical artifact statement is absent from attestations")
        try:
            subject = attestation.subject(artifact.name)
        except ValueError as error:
            raise BundleError(str(error)) from error
        if subject["digest"] != artifact.digest():
            raise BundleError("historical artifact bytes do not match the selected subject")
        identity = (statement_digest, artifact.name, artifact.digest()["sha256"])
        if identity in historical_materials:
            raise BundleError("historical artifacts contain a duplicate subject identity")
        historical_materials[identity] = artifact
    dataset_memberships: dict[tuple[str, str, str], str] = {}
    dataset_indexes: dict[tuple[str, str, str], DatasetManifestIndex] = {}
    for artifact, attestation in dataset_manifests or []:
        statement_digest = attestation.digest()["sha256"]
        if statement_digest not in statement_map:
            raise BundleError("dataset manifest statement is absent from attestations")
        subject = attestation.subject(artifact.name)
        if subject["digest"] != artifact.digest():
            raise BundleError("dataset manifest bytes do not match the selected subject")
        expected_profile = core_dataset_manifest_profile_reference(
            artifact.name, repository_root=repository_root
        )
        if expected_profile not in attestation.statement["predicate"].get("profiles", []):
            raise BundleError("dataset manifest subject lacks the exact mandatory core profile")
        try:
            manifest_index = parse_dataset_manifest(artifact.data, repository_root=repository_root)
        except DatasetManifestError as error:
            raise BundleError(f"dataset manifest is invalid: {error}") from error
        dataset_identity = (statement_digest, artifact.name, artifact.digest()["sha256"])
        if dataset_identity in historical_materials:
            raise BundleError("historical artifacts contain a duplicate subject identity")
        historical_materials[dataset_identity] = artifact
        dataset_indexes[dataset_identity] = manifest_index
        for entry in manifest_index.entries:
            dataset_memberships[(statement_digest, artifact.name, entry.name)] = entry.digest
    dataset_entry_materials: dict[tuple[str, str, str], Artifact] = {}
    for artifact, attestation, manifest_subject_name, entry_name in dataset_entries or []:
        statement_digest = attestation.digest()["sha256"]
        matching_indexes = [
            index
            for (
                candidate_digest,
                candidate_name,
                _subject_digest,
            ), index in dataset_indexes.items()
            if candidate_digest == statement_digest and candidate_name == manifest_subject_name
        ]
        if len(matching_indexes) != 1:
            raise BundleError("dataset entry does not name one supplied dataset manifest")
        member = matching_indexes[0].member(entry_name)
        if member is None or member.digest != artifact.digest()["sha256"]:
            raise BundleError("dataset entry bytes do not match the selected manifest member")
        if member.size is not None and member.size != len(artifact.data):
            raise BundleError("dataset entry byte count does not match the manifest member")
        logical_identity = (statement_digest, manifest_subject_name, entry_name)
        if logical_identity in dataset_entry_materials:
            raise BundleError("dataset entries contain a duplicate logical identity")
        dataset_entry_materials[logical_identity] = artifact
    graph = build_graph(
        {digest: item.statement for digest, item in statement_map.items()},
        dataset_memberships=dataset_memberships,
    )
    supplied_head_digests = [head.digest()["sha256"] for head in heads]
    if len(supplied_head_digests) != len(set(supplied_head_digests)):
        raise BundleError("heads contain a duplicate statement identity")
    head_digests = set(supplied_head_digests)
    reachable = set(reachable_from_heads(sorted(head_digests), graph.predecessors))
    final_head_digests = {head.digest()["sha256"] for _artifact, head in final_artifacts}
    if head_digests != final_head_digests:
        raise BundleError("heads must equal the statement set referenced by final artifacts")
    for artifact, head in final_artifacts:
        final_identity = (head.digest()["sha256"], artifact.name, artifact.digest()["sha256"])
        if final_identity in graph.consumed_subjects:
            raise BundleError("final artifact is consumed by a descendant and is not terminal")
        profile_media_types = {
            profile["mediaType"]
            for profile in head.statement["predicate"].get("profiles", [])
            if profile["target"] == "artifact" and profile["subjectName"] == artifact.name
        }
        media_types = profile_media_types | (
            {artifact.media_type} if artifact.media_type is not None else set()
        )
        if len(media_types) > 1:
            raise BundleError(
                f"final artifact media type conflicts with signed profiles: {artifact.name}"
            )
    if graph.problems or reachable != set(statement_map):
        raise BundleError("attestation directory is not exactly the reachable valid graph")
    handoff = create_handoff(
        statements=attestations,
        roots=[statement_map[digest] for digest in graph.roots],
        final_artifacts=final_artifacts,
        bundle_id=bundle_id,
        issued_at=issued_at,
        signing_key=signing_key,
        repository_root=repository_root,
        required_profiles=required_profiles,
        recipient=recipient,
        nonce=nonce,
    )
    exported_schema_resources = _select_exported_schema_resources(
        attestations=attestations,
        catalog_paths=schema_catalog_paths,
        external_profiles=external_profiles,
        repository_root=repository_root,
    )
    if output.exists() and not force:
        raise BundleError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        manifest_path = "manifest.dsse.json"
        (staged / manifest_path).write_bytes(canonical_json(handoff.envelope) + b"\n")
        attestation_entries: list[dict[str, Any]] = []
        for digest, attestation in sorted(statement_map.items()):
            logical_path = f"attestations/{digest}.dsse.json"
            target = staged / logical_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(canonical_json(attestation.envelope) + b"\n")
            attestation_entries.append(
                {"statementDigest": digest_object(digest), "path": logical_path}
            )
        artifact_entries: list[dict[str, Any]] = []
        for artifact, head in final_artifacts:
            final_identity_record = {
                "digest": artifact.digest(),
                "statementDigest": head.digest(),
                "subjectName": artifact.name,
            }
            identity_digest = sha256_bytes(canonical_json(final_identity_record))
            logical_path = f"artifacts/final/{identity_digest}.bin"
            target = staged / logical_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact.data)
            artifact_entries.append({**final_identity_record, "path": logical_path})
        for identity_tuple, artifact in sorted(historical_materials.items()):
            statement_digest, subject_name, digest = identity_tuple
            historical_identity_record = {
                "digest": digest_object(digest),
                "statementDigest": digest_object(statement_digest),
                "subjectName": subject_name,
            }
            if any(
                item["statementDigest"] == historical_identity_record["statementDigest"]
                and item["subjectName"] == historical_identity_record["subjectName"]
                and item["digest"] == historical_identity_record["digest"]
                for item in artifact_entries
            ):
                continue
            identity_digest = sha256_bytes(canonical_json(historical_identity_record))
            logical_path = f"artifacts/historical/{identity_digest}.bin"
            target = staged / logical_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact.data)
            artifact_entries.append({**historical_identity_record, "path": logical_path})
        artifact_entries.sort(
            key=lambda item: (
                item["statementDigest"]["sha256"],
                item["subjectName"].encode(),
                item["digest"]["sha256"],
            )
        )
        dataset_entry_records: list[dict[str, Any]] = []
        for logical_identity, artifact in sorted(dataset_entry_materials.items()):
            statement_digest, manifest_subject_name, entry_name = logical_identity
            identity_record = {
                "entryName": entry_name,
                "manifestStatementDigest": digest_object(statement_digest),
                "manifestSubjectName": manifest_subject_name,
            }
            identity_digest = sha256_bytes(canonical_json(identity_record))
            logical_path = f"artifacts/dataset-entries/{identity_digest}.bin"
            target = staged / logical_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact.data)
            dataset_entry_records.append(
                {**identity_record, "digest": artifact.digest(), "path": logical_path}
            )
        bundle_index = {
            "version": "0.2",
            "manifest": manifest_path,
            "attestations": attestation_entries,
            "artifacts": artifact_entries,
            "datasetEntries": dataset_entry_records,
        }
        if exported_schema_resources:
            catalog_entries: list[dict[str, Any]] = []
            written_digests: set[str] = set()
            for (identifier, digest), exact_bytes in sorted(exported_schema_resources.items()):
                relative_resource_path = f"resources/{digest}.schema.json"
                if digest not in written_digests:
                    target = staged / "schemas" / relative_resource_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(exact_bytes)
                    written_digests.add(digest)
                catalog_entries.append(
                    {
                        "id": identifier,
                        "digest": digest_object(digest),
                        "path": relative_resource_path,
                    }
                )
            exported_catalog = {"version": "0.2", "resources": catalog_entries}
            validate_core("catalog", exported_catalog, repository_root=repository_root)
            catalog_path = staged / "schemas" / "catalog.json"
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            catalog_path.write_bytes(canonical_json(exported_catalog) + b"\n")
            bundle_index["schemaCatalog"] = "schemas/catalog.json"
        validate_core("bundle", bundle_index, repository_root=repository_root)
        (staged / "bundle.json").write_bytes(canonical_json(bundle_index) + b"\n")
        if output.exists():
            shutil.rmtree(output)
        os.replace(staged, output)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return {
        "bundle": bundle_index,
        "handoff": handoff.manifest,
        "manifestDigest": handoff.digest(),
    }


def _select_exported_schema_resources(
    *,
    attestations: Sequence[Attestation],
    catalog_paths: Sequence[Path],
    external_profiles: Sequence[dict[str, Any]],
    repository_root: Path,
) -> dict[tuple[str, str], bytes]:
    """Select the exact non-core closures needed by embedded signed profiles."""

    # Preserve the library's historical external-resolution mode when callers
    # do not opt into either closure embedding or explicit externalization.
    if not catalog_paths and not external_profiles:
        return {}
    resources = load_catalog_resources(catalog_paths, repository_root=repository_root)
    core_catalog_value = strict_json_loads(
        (schema_directory(repository_root) / "catalog.json").read_bytes()
    )
    assert isinstance(core_catalog_value, dict)
    core_resources = {
        item["id"]: item["digest"]["sha256"] for item in core_catalog_value["resources"]
    }
    for identifier, digest in resources:
        if identifier in core_resources and digest != core_resources[identifier]:
            raise BundleError(f"catalog attempts to shadow immutable core schema: {identifier}")

    selected_profiles: dict[bytes, dict[str, Any]] = {}
    for attestation in attestations:
        for profile in attestation.statement["predicate"].get("profiles", []):
            identity = canonical_json(profile)
            selected_profiles[identity] = profile

    external_identities: set[bytes] = set()
    for profile in external_profiles:
        validate_core("profile-reference", profile, repository_root=repository_root)
        identity = canonical_json(profile)
        if identity in external_identities:
            raise BundleError("external profile identities must be unique")
        if identity not in selected_profiles:
            raise BundleError("external profile does not match a selected signed profile")
        external_identities.add(identity)

    exported: dict[tuple[str, str], bytes] = {}
    for identity, profile in sorted(selected_profiles.items()):
        if identity in external_identities:
            continue
        keys = [
            (profile["id"], profile["digest"]["sha256"]),
            *[(item["id"], item["digest"]["sha256"]) for item in profile.get("resources", [])],
        ]
        for key in keys:
            identifier, digest = key
            if identifier in core_resources:
                if digest != core_resources[identifier]:
                    raise BundleError(
                        f"profile attempts to shadow immutable core schema: {identifier}"
                    )
                continue
            resource = resources.get(key)
            if resource is None:
                raise BundleError(f"selected profile resource is unavailable: {identifier}")
            exported[key] = resource.exact_bytes
    return exported


def verify_bundle(request: VerificationRequest) -> dict[str, Any]:
    _validate_consumer_configuration(request)
    if request.temp_parent is not None:
        metadata = request.temp_parent.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise VerificationConfigurationError("temp parent must be a real directory")
    with tempfile.TemporaryDirectory(
        prefix="makoto-verify-", dir=request.temp_parent
    ) as raw_snapshot_root:
        snapshot_root = Path(raw_snapshot_root)
        snapshot_root.chmod(0o700)
        return _verify_bundle(replace(request, snapshot_root=snapshot_root))


def _verify_bundle(request: VerificationRequest) -> dict[str, Any]:
    policy = TrustPolicy.from_path(request.policy_path, repository_root=request.repository_root)
    evaluation_time = request.evaluation_time or _now_timestamp()
    core_catalog_bytes = (schema_directory(request.repository_root) / "catalog.json").read_bytes()
    report = new_report(
        evaluation_time=evaluation_time,
        policy_digest=policy.digest(),
        core_catalog_digest=digest_object(sha256_bytes(core_catalog_bytes)),
    )
    for check_id in (
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
    ):
        set_check(report, check_id, "pass")

    _begin_timing(request, 1)
    try:
        inventory = _scan_bundle(request.bundle_root)
    except (BundleError, OSError) as error:
        add_error(
            report,
            Diagnostic(
                "E_BUNDLE_UNSAFE_PATH", 1, str(error), "load-safely", {"path": "bundle.json"}
            ),
        )
        set_check(report, "load-safely", "fail")
        _block_unreached_checks(report, {"load-safely"}, "load-safely")
        return _complete_report(report, request)
    try:
        consumer_artifact_bytes, consumer_dataset_entry_bytes = _snapshot_consumer_materials(
            request, inventory
        )
    except (BundleError, OSError) as error:
        add_error(
            report,
            Diagnostic(
                "E_BUNDLE_UNSAFE_PATH",
                1,
                str(error),
                "load-safely",
                {"path": "consumer-material"},
            ),
        )
        set_check(report, "load-safely", "fail")
        _block_unreached_checks(report, {"load-safely"}, "load-safely")
        return _complete_report(report, request)
    if inventory.get("bundle.json", (None,))[0] != "file":
        add_error(
            report,
            Diagnostic(
                "E_HANDOFF_REQUIRED",
                1,
                "bundle.json is absent from the completed bundle inventory",
                "load-safely",
                {"path": "bundle.json"},
            ),
        )
        set_check(report, "load-safely", "fail")
        _block_unreached_checks(report, {"load-safely"}, "load-safely")
        return _complete_report(report, request)
    try:
        bundle_bytes = _safe_read(request.bundle_root, "bundle.json", inventory)
    except (BundleError, OSError) as error:
        add_error(
            report,
            Diagnostic(
                "E_BUNDLE_UNSAFE_PATH",
                1,
                str(error),
                "load-safely",
                {"path": "bundle.json"},
            ),
        )
        set_check(report, "load-safely", "fail")
        _block_unreached_checks(report, {"load-safely"}, "load-safely")
        return _complete_report(report, request)

    _begin_timing(request, 2)
    try:
        bundle_value = strict_json_loads(bundle_bytes)
        if not isinstance(bundle_value, dict):
            raise CoreValidationError(())
        validate_core("bundle", bundle_value, repository_root=request.repository_root)
        bundle = cast(dict[str, Any], bundle_value)
    except CoreValidationError as error:
        add_error(
            report,
            Diagnostic("E_CORE_SCHEMA", 2, str(error), "core-schemas", {"path": "bundle.json"}),
        )
        set_check(report, "core-schemas", "fail")
        _block_unreached_checks(
            report,
            {"load-safely", "parse-strictly", "core-schemas"},
            "core-schemas",
            not_checked={"index-payloads"},
        )
        return _complete_report(report, request)
    except Exception as error:
        add_error(
            report,
            Diagnostic("E_JSON_INVALID", 2, str(error), "parse-strictly", {"path": "bundle.json"}),
        )
        set_check(report, "parse-strictly", "fail")
        _block_unreached_checks(report, {"load-safely", "parse-strictly"}, "parse-strictly")
        return _complete_report(report, request)

    referenced_paths = {"bundle.json", bundle["manifest"]}
    referenced_paths.update(item["path"] for item in bundle["attestations"])
    referenced_paths.update(item["path"] for item in bundle["artifacts"])
    referenced_paths.update(item["path"] for item in bundle.get("datasetEntries", []))
    if "schemaCatalog" in bundle:
        referenced_paths.add(bundle["schemaCatalog"])
    bundle_artifact_identities = {
        (item["statementDigest"]["sha256"], item["subjectName"], item["digest"]["sha256"])
        for item in bundle["artifacts"]
    }
    bundle_dataset_identities = {
        (
            item["manifestStatementDigest"]["sha256"],
            item["manifestSubjectName"],
            item["entryName"],
        )
        for item in bundle.get("datasetEntries", [])
    }
    artifact_collisions = bundle_artifact_identities & set(consumer_artifact_bytes)
    dataset_collisions = bundle_dataset_identities & set(consumer_dataset_entry_bytes)
    for statement_digest, _subject_name, _digest in sorted(artifact_collisions):
        add_error(
            report,
            Diagnostic(
                "E_CORE_SCHEMA",
                2,
                "artifact material identity is supplied by both bundle and consumer",
                "core-schemas",
                {"statementDigest": digest_object(statement_digest)},
            ),
        )
        set_check(report, "core-schemas", "fail")
    for statement_digest, _subject_name, _entry_name in sorted(dataset_collisions):
        add_error(
            report,
            Diagnostic(
                "E_CORE_SCHEMA",
                2,
                "dataset-entry identity is supplied by both bundle and consumer",
                "core-schemas",
                {"statementDigest": digest_object(statement_digest)},
            ),
        )
        set_check(report, "core-schemas", "fail")
    if artifact_collisions or dataset_collisions:
        _block_unreached_checks(
            report,
            {"load-safely", "parse-strictly", "core-schemas"},
            "core-schemas",
            not_checked={"index-payloads"},
        )
        return _complete_report(report, request)

    report["unreferencedFiles"] = [
        {"path": path, "status": "not_checked", "reason": "unreferenced"}
        for path in sorted(inventory)
        if path not in referenced_paths and inventory[path][0] == "file"
    ]

    manifest_path = bundle["manifest"]
    if inventory.get(manifest_path, (None,))[0] != "file":
        add_error(
            report,
            Diagnostic(
                "E_HANDOFF_REQUIRED",
                2,
                "the indexed handoff manifest is absent",
                "parse-strictly",
                {"path": manifest_path},
            ),
        )
        set_check(report, "parse-strictly", "fail")
        _block_unreached_checks(report, {"load-safely", "parse-strictly"}, "parse-strictly")
        return _complete_report(report, request)
    try:
        manifest_record = _load_envelope(
            request.bundle_root,
            manifest_path,
            inventory,
            expected_payload_type=HANDOFF_PAYLOAD_TYPE,
            payload_schema="handoff",
            repository_root=request.repository_root,
            timing=request.timing,
        )
    except EnvelopeLoadFailure as error:
        add_error(
            report,
            Diagnostic(error.code, error.step, str(error), error.check, {"path": manifest_path}),
        )
        set_check(report, error.check, "fail")
        retained = {"load-safely", "parse-strictly"}
        if error.step >= 3:
            retained.add("index-payloads")
        if error.step >= 4:
            retained.add("core-schemas")
        _block_unreached_checks(report, retained, error.check)
        return _complete_report(report, request)
    report["manifestDigest"] = digest_object(manifest_record.digest)
    report["bundleId"] = manifest_record.value["bundleId"]
    report["actualRecipient"] = manifest_record.value.get("recipient")
    report["actualNonce"] = manifest_record.value.get("nonce")
    report["actualHeads"] = manifest_record.value["heads"]
    report["summary"]["manifestSignaturesRequired"] = policy.value["handoff"]["minimumSignatures"]

    evaluation_datetime = _parse_timestamp(evaluation_time)
    _begin_timing(request, 5)
    handoff_signatures, handoff_authorized = policy.authorize_handoff(
        manifest_record.envelope, evaluation_time=evaluation_datetime
    )
    _begin_timing(request, 6)
    report["handoff"]["signatures"] = [_signature_dict(item) for item in handoff_signatures]
    report["summary"]["signaturesTotal"] += len(handoff_signatures)
    report["summary"]["signaturesChecked"] += sum(item.key_known for item in handoff_signatures)
    report["summary"]["signaturesValid"] += sum(
        item.cryptographic == "pass" for item in handoff_signatures
    )
    report["summary"]["manifestSignaturesValid"] = sum(
        item.cryptographic == "pass" for item in handoff_signatures
    )
    report["summary"]["manifestSignaturesAuthorized"] = int(handoff_authorized)
    _record_signature_diagnostics(report, handoff_signatures, manifest_record.digest)
    report["handoff"]["authorization"] = "pass" if handoff_authorized else "fail"
    if not handoff_authorized:
        add_error(
            report,
            Diagnostic(
                "E_SIGNER_UNAUTHORIZED",
                6,
                "handoff signature threshold was not met",
                "authorization-thresholds",
                {"statementDigest": digest_object(manifest_record.digest)},
            ),
        )
        set_check(report, "authorization-thresholds", "fail")

    statement_records: dict[str, EnvelopeRecord] = {}
    declared_attestations = {
        item["statementDigest"]["sha256"]: item for item in bundle["attestations"]
    }
    for declared_digest, item in sorted(declared_attestations.items()):
        try:
            record = _load_envelope(
                request.bundle_root,
                item["path"],
                inventory,
                expected_payload_type=STATEMENT_PAYLOAD_TYPE,
                payload_schema="statement",
                repository_root=request.repository_root,
                timing=request.timing,
            )
        except EnvelopeLoadFailure as error:
            if error.step == 2:
                report["unindexedEnvelopes"].append(
                    {
                        "path": item["path"],
                        "payloadTypeStatus": error.payload_type_status,
                        "diagnosticCode": error.code,
                    }
                )
            add_error(
                report,
                Diagnostic(
                    error.code,
                    error.step,
                    str(error),
                    error.check,
                    {"path": item["path"]},
                ),
            )
            set_check(report, error.check, "fail")
            continue
        if record.digest != declared_digest:
            add_error(
                report,
                Diagnostic(
                    "E_STATEMENT_DIGEST",
                    3,
                    "indexed statement digest differs from decoded payload bytes",
                    "index-payloads",
                    {
                        "statementDigest": digest_object(record.digest),
                        "declared": digest_object(declared_digest),
                    },
                ),
            )
            set_check(report, "index-payloads", "fail")
            continue
        statement_records[record.digest] = record

    statements = {digest: record.value for digest, record in statement_records.items()}
    manifest_statement_set = {item["sha256"] for item in manifest_record.value["statements"]}
    authorization: dict[str, AuthorizationResult] = {}
    for digest, record in sorted(statement_records.items()):
        _begin_timing(request, 5)
        result = policy.authorize_statement(
            record.value, record.envelope, evaluation_time=evaluation_datetime
        )
        _begin_timing(request, 6)
        authorization[digest] = result
        report["summary"]["signaturesTotal"] += len(result.signatures)
        report["summary"]["signaturesChecked"] += sum(item.key_known for item in result.signatures)
        report["summary"]["signaturesValid"] += sum(
            item.cryptographic == "pass" for item in result.signatures
        )
        _record_signature_diagnostics(report, result.signatures, digest)
        if not result.candidate_rule_ids:
            add_error(
                report,
                Diagnostic(
                    "E_SIGNER_UNAUTHORIZED",
                    6,
                    "no matching policy rule met its signature threshold",
                    "authorization-thresholds",
                    {"statementDigest": digest_object(digest)},
                ),
            )
            set_check(report, "authorization-thresholds", "fail")
            set_check(report, "authorization", "fail")

    _begin_timing(request, 7)
    catalogs = list(request.schema_catalogs)
    if "schemaCatalog" in bundle:
        catalogs.append(request.bundle_root / bundle["schemaCatalog"])
    profile_states = _validate_metadata_profiles(
        report,
        statements,
        manifest_statement_set,
        catalogs,
        request.repository_root,
        policy,
        authorization,
    )
    for digest, result in sorted(authorization.items()):
        statement = statements[digest]
        statement_states = {
            (profile_id, profile_digest, closure_digest, target): state
            for (
                statement_digest,
                profile_id,
                profile_digest,
                closure_digest,
                target,
            ), state in profile_states.items()
            if statement_digest == digest
        }
        finalized = policy.finalize_statement_authorization(statement, result, statement_states)
        authorization[digest] = finalized
        if not finalized.authorized and finalized.candidate_rule_ids:
            add_error(
                report,
                Diagnostic(
                    "E_PROFILE_UNRESOLVED",
                    7,
                    "no candidate rule satisfied every digest-pinned profile constraint",
                    "authorization",
                    {"statementDigest": digest_object(digest)},
                ),
            )
            set_check(report, "authorization", "fail")

    _begin_timing(request, 8)
    dataset_verification = _prevalidate_dataset_manifests(
        report,
        bundle=bundle,
        manifest=manifest_record.value,
        statements=statements,
        authorization=authorization,
        handoff_authorized=handoff_authorized,
        root=request.bundle_root,
        inventory=inventory,
        repository_root=request.repository_root,
        consumer_materials=consumer_artifact_bytes,
        consumer_dataset_identities=set(consumer_dataset_entry_bytes),
        catalogs=catalogs,
    )
    profile_states.update(dataset_verification.profile_states)
    _begin_timing(request, 9)
    usable_statements = {
        digest: statement
        for digest, statement in statements.items()
        if digest in manifest_statement_set and authorization[digest].authorized
    }
    graph = build_graph(
        usable_statements,
        dataset_memberships=dataset_verification.memberships,
        verified_dataset_subjects=dataset_verification.verified_subjects,
    )
    _begin_timing(request, 10)
    requested_heads = [item["sha256"] for item in manifest_record.value["heads"]]
    unavailable_heads = [digest for digest in requested_heads if digest not in usable_statements]
    unavailable_head_prerequisites = sorted(
        {
            "index-payloads" if digest not in statements else "authorization"
            for digest in unavailable_heads
        },
        key=("index-payloads", "core-schemas", "authorization").index,
    )
    reachable = reachable_from_heads(
        [digest for digest in requested_heads if digest in usable_statements], graph.predecessors
    )
    effective_graph_problems = tuple(
        problem for problem in graph.problems if problem.code != "E_DATASET_MANIFEST_REQUIRED"
    )
    for problem in effective_graph_problems:
        _record_graph_problem(report, problem)
    if effective_graph_problems:
        set_check(report, "graph", "fail")
    elif unavailable_heads:
        set_check(report, "graph", "skipped", unavailable_head_prerequisites)
        set_check(report, "roots-and-heads", "skipped", ["graph"])
    report["roots"] = [digest_object(value) for value in graph.roots]
    report["summary"]["roots"] = len(graph.roots)
    report["summary"]["heads"] = len(graph.heads)
    report["summary"]["statementsReachable"] = len(reachable)

    _begin_timing(request, 11)
    manifest_roots = {item["sha256"] for item in manifest_record.value["roots"]}
    manifest_heads = {item["sha256"] for item in manifest_record.value["heads"]}
    artifact_heads = {item["head"]["sha256"] for item in manifest_record.value["artifacts"]}
    final_subjects_ok = True
    eligible_final_subjects: set[tuple[str, str, str]] = set()
    if handoff_authorized:
        for artifact in manifest_record.value["artifacts"]:
            head_digest = artifact["head"]["sha256"]
            head_statement = usable_statements.get(head_digest)
            subject_identity = (
                head_digest,
                artifact["name"],
                artifact["digest"]["sha256"],
            )
            exact_subject = head_statement is not None and any(
                subject["name"] == artifact["name"] and subject["digest"] == artifact["digest"]
                for subject in head_statement["subject"]
            )
            terminal = subject_identity not in graph.consumed_subjects
            if exact_subject and terminal:
                eligible_final_subjects.add(subject_identity)
            else:
                final_subjects_ok = False
                add_error(
                    report,
                    Diagnostic(
                        "E_MANIFEST_SET",
                        11,
                        "final artifact is not an exact terminal subject of its declared head",
                        "completeness-anchor",
                        {
                            "bundleId": report["bundleId"],
                            "head": artifact["head"],
                            "subjectName": artifact["name"],
                            "artifactDigest": artifact["digest"],
                        },
                    ),
                )
    if handoff_authorized:
        completeness_ok = (
            set(statement_records) == manifest_statement_set
            and set(reachable) == manifest_statement_set
            and set(graph.roots) == manifest_roots
            and manifest_heads == artifact_heads
            and final_subjects_ok
        )
        if not completeness_ok:
            add_error(
                report,
                Diagnostic(
                    "E_MANIFEST_SET",
                    11,
                    "signed manifest sets do not equal the verified graph and bundle index",
                    "completeness-anchor",
                    {"bundleId": manifest_record.value["bundleId"]},
                ),
            )
            set_check(report, "completeness-anchor", "fail")
        report["handoff"]["completeness"] = "pass" if completeness_ok else "fail"
    else:
        set_check(report, "completeness-anchor", "skipped", ["authorization-thresholds"])
        set_check(report, "freshness-anchors", "skipped", ["authorization-thresholds"])
        report["handoff"]["completeness"] = "skipped"

    if not handoff_authorized:
        _begin_timing(request, 12)
        historical_checked = _verify_unauthorized_consumer_historical(
            report,
            manifest=manifest_record.value,
            statements=statements,
            consumer_materials=consumer_artifact_bytes,
        )
        if not historical_checked:
            set_check(report, "artifact-bytes", "not_checked")
        set_check(report, "artifact-profiles", "not_checked")
        _populate_statement_records(report, statements, authorization, effective_graph_problems)
        report["summary"]["statementsTotal"] = len(manifest_statement_set)
        report["summary"]["statementsValid"] = len(statement_records)
        report["summary"]["statementsAuthorized"] = sum(
            result.authorized for result in authorization.values()
        )
        report["summary"]["profilesDeclared"] = len(report["profiles"])
        report["summary"]["profilesValidated"] = sum(
            profile["validation"] == "pass" for profile in report["profiles"]
        )
        report["summary"]["historicalMaterialsDeclared"] = len(report["artifacts"])
        report["summary"]["historicalMaterialsChecked"] = sum(
            artifact["digestStatus"] == "pass" for artifact in report["artifacts"]
        )
        _record_final_rescan(report, request.bundle_root, inventory)
        return _complete_report(report, request)

    _begin_timing(request, 12)
    artifact_mappings = {
        (item["statementDigest"]["sha256"], item["subjectName"], item["digest"]["sha256"]): item
        for item in bundle["artifacts"]
    }
    artifact_bytes = dict(dataset_verification.snapshots)
    final_artifact_identities = {
        (artifact["head"]["sha256"], artifact["name"], artifact["digest"]["sha256"])
        for artifact in manifest_record.value["artifacts"]
    }
    for artifact in manifest_record.value["artifacts"]:
        key = (artifact["head"]["sha256"], artifact["name"], artifact["digest"]["sha256"])
        if key not in eligible_final_subjects:
            report["artifacts"].append(
                {
                    "lifecycleRole": "final",
                    "artifactKind": "ordinary",
                    "statementDigest": artifact["head"],
                    "head": artifact["head"],
                    "subjectName": artifact["name"],
                    "digest": artifact["digest"],
                    "digestStatus": "skipped",
                    "digestPrerequisiteChecks": ["completeness-anchor"],
                    "profileStatus": "skipped",
                    "profilePrerequisiteChecks": ["completeness-anchor"],
                    "applicableProfileCount": 0,
                }
            )
            set_check(report, "artifact-bytes", "skipped", ["completeness-anchor"])
            set_check(report, "artifact-profiles", "skipped", ["completeness-anchor"])
            continue
        mapping = artifact_mappings.get(key)
        digest_status = "fail"
        if mapping is None:
            add_error(
                report,
                Diagnostic(
                    "E_MANIFEST_SET",
                    11,
                    "final artifact lacks its exact bundle mapping",
                    "completeness-anchor",
                    {
                        "bundleId": report["bundleId"],
                        "head": artifact["head"],
                        "subjectName": artifact["name"],
                        "artifactDigest": artifact["digest"],
                    },
                ),
            )
            set_check(report, "completeness-anchor", "fail")
        elif key in artifact_bytes:
            digest_status = "pass"
        else:
            try:
                material = _safe_read(request.bundle_root, mapping["path"], inventory)
            except (BundleError, OSError) as error:
                code = (
                    "E_ARTIFACT_MISSING"
                    if str(error).startswith("bundle file is absent:")
                    else "E_BUNDLE_UNSAFE_PATH"
                )
                add_error(
                    report,
                    Diagnostic(
                        code,
                        12,
                        str(error),
                        "artifact-bytes",
                        {
                            "head": artifact["head"],
                            "subjectName": artifact["name"],
                            "artifactDigest": artifact["digest"],
                            "path": mapping["path"],
                        },
                    ),
                )
            else:
                actual_digest = sha256_bytes(material)
                if actual_digest != artifact["digest"]["sha256"]:
                    add_error(
                        report,
                        Diagnostic(
                            "E_ARTIFACT_DIGEST",
                            12,
                            "final artifact bytes differ from the signed digest",
                            "artifact-bytes",
                            {
                                "head": artifact["head"],
                                "subjectName": artifact["name"],
                                "artifactDigest": artifact["digest"],
                            },
                        ),
                    )
                else:
                    digest_status = "pass"
                    artifact_bytes[key] = material
        if digest_status == "fail":
            set_check(report, "artifact-bytes", "fail")
        report["artifacts"].append(
            {
                "lifecycleRole": "final",
                "artifactKind": "ordinary",
                "statementDigest": artifact["head"],
                "head": artifact["head"],
                "subjectName": artifact["name"],
                "digest": artifact["digest"],
                "digestStatus": digest_status,
                "digestPrerequisiteChecks": [],
                "profileStatus": "not_checked",
                "profilePrerequisiteChecks": [],
                "applicableProfileCount": 0,
            }
        )

    _verify_historical_artifacts(
        report,
        mappings=artifact_mappings,
        final_identities=final_artifact_identities,
        statements=usable_statements,
        reachable=frozenset(reachable),
        artifact_bytes=artifact_bytes,
        root=request.bundle_root,
        inventory=inventory,
        repository_root=request.repository_root,
        consumer_materials=consumer_artifact_bytes,
    )
    _verify_dataset_entries(
        report,
        bundle=bundle,
        verification=dataset_verification,
        root=request.bundle_root,
        inventory=inventory,
        consumer_bindings=consumer_dataset_entry_bytes,
    )
    _begin_timing(request, 13)
    _validate_artifact_profiles(
        report,
        statements,
        artifact_bytes,
        catalogs,
        request.repository_root,
        profile_states,
        final_media_hints={
            (
                artifact["head"]["sha256"],
                artifact["name"],
                artifact["digest"]["sha256"],
            ): artifact.get("mediaType")
            for artifact in manifest_record.value["artifacts"]
        },
    )
    _enforce_required_profiles(report, manifest_record.value, statements, policy)
    _begin_timing(request, 11)
    _evaluate_freshness(report, request, policy, manifest_record)
    _begin_timing(request, 14)
    _populate_statement_records(report, statements, authorization, effective_graph_problems)
    report["summary"]["statementsTotal"] = len(manifest_statement_set)
    report["summary"]["statementsValid"] = len(statement_records)
    report["summary"]["statementsAuthorized"] = sum(
        result.authorized for result in authorization.values()
    )
    report["summary"]["artifactsDeclared"] = len(manifest_record.value["artifacts"])
    report["summary"]["artifactsChecked"] = sum(
        artifact["lifecycleRole"] == "final" and artifact["digestStatus"] == "pass"
        for artifact in report["artifacts"]
    )
    report["summary"]["historicalMaterialsDeclared"] = sum(
        artifact["lifecycleRole"] == "historical" for artifact in report["artifacts"]
    )
    report["summary"]["historicalMaterialsChecked"] = sum(
        artifact["lifecycleRole"] == "historical" and artifact["digestStatus"] == "pass"
        for artifact in report["artifacts"]
    )
    report["summary"]["profilesDeclared"] = len(report["profiles"])
    report["summary"]["profilesValidated"] = sum(
        profile["validation"] == "pass" for profile in report["profiles"]
    )
    _record_final_rescan(report, request.bundle_root, inventory)
    return _complete_report(report, request, begin_step=False)


def _begin_timing(request: VerificationRequest, step: int) -> None:
    if request.timing is not None:
        request.timing.begin(step)


def _complete_report(
    report: dict[str, Any],
    request: VerificationRequest,
    *,
    begin_step: bool = True,
) -> dict[str, Any]:
    if begin_step:
        _begin_timing(request, 14)
    report["unindexedEnvelopes"].sort(key=lambda item: item["path"].encode())
    completed = finalize_report(report)
    if request.timing is not None:
        request.timing.finish()
    return completed


def _block_unreached_checks(
    report: dict[str, Any],
    retained: set[str],
    prerequisite: str,
    *,
    not_checked: Set[str] = frozenset(),
) -> None:
    """Fold optimistic defaults after an early terminal evidence failure."""

    for check in report["checks"]:
        if check["id"] == "decision" or check["id"] in retained:
            continue
        if check["id"] in not_checked:
            check["status"] = "not_checked"
            check["prerequisiteChecks"] = []
        else:
            check["status"] = "skipped"
            check["prerequisiteChecks"] = [prerequisite]


def _record_final_rescan(
    report: dict[str, Any],
    root: Path,
    first: dict[str, tuple[str, tuple[int, int]]],
) -> None:
    try:
        _final_rescan(root, first)
    except (BundleError, OSError) as error:
        add_error(
            report,
            Diagnostic(
                "E_BUNDLE_UNSAFE_PATH",
                12,
                str(error),
                "artifact-bytes",
                {"path": "."},
            ),
        )
        set_check(report, "artifact-bytes", "fail")


def _load_envelope(
    root: Path,
    logical_path: str,
    inventory: dict[str, tuple[str, tuple[int, int]]],
    *,
    expected_payload_type: str,
    payload_schema: str,
    repository_root: Path,
    timing: VerificationTiming | None = None,
) -> EnvelopeRecord:
    if timing is not None:
        timing.begin(2)
    try:
        raw = _safe_read(root, logical_path, inventory)
    except (BundleError, OSError) as error:
        raise EnvelopeLoadFailure(
            "E_BUNDLE_UNSAFE_PATH", 2, "parse-strictly", str(error)
        ) from error
    try:
        parsed = strict_json_loads(raw)
    except StrictJsonError as error:
        code = (
            "E_JSON_DUPLICATE_KEY"
            if str(error).startswith("duplicate JSON member ")
            else "E_JSON_INVALID"
        )
        raise EnvelopeLoadFailure(code, 2, "parse-strictly", str(error)) from error
    if not isinstance(parsed, dict):
        raise EnvelopeLoadFailure(
            "E_ENVELOPE_MALFORMED",
            2,
            "parse-strictly",
            f"envelope {logical_path!r} is not an object",
        )
    try:
        validate_core("envelope", parsed, repository_root=repository_root)
    except CoreValidationError as error:
        raw_payload_type = parsed.get("payloadType")
        payload_type_status = (
            "pass"
            if raw_payload_type == expected_payload_type
            else "fail"
            if isinstance(raw_payload_type, str)
            else "not_checked"
        )
        raise EnvelopeLoadFailure(
            "E_ENVELOPE_MALFORMED",
            2,
            "parse-strictly",
            str(error),
            payload_type_status=payload_type_status,
        ) from error
    envelope = cast(dict[str, Any], parsed)
    if envelope["payloadType"] != expected_payload_type:
        raise EnvelopeLoadFailure(
            "E_PAYLOAD_TYPE",
            2,
            "parse-strictly",
            f"envelope {logical_path!r} has the wrong payload type",
            payload_type_status="fail",
        )
    try:
        payload = canonical_b64decode(envelope["payload"])
    except DsseError as error:
        raise EnvelopeLoadFailure(
            "E_ENVELOPE_MALFORMED",
            2,
            "parse-strictly",
            str(error),
            payload_type_status="pass",
        ) from error
    if timing is not None:
        timing.begin(3)
    try:
        payload_value = strict_json_loads(payload)
    except StrictJsonError as error:
        code = (
            "E_JSON_DUPLICATE_KEY"
            if str(error).startswith("duplicate JSON member ")
            else "E_JSON_INVALID"
        )
        raise EnvelopeLoadFailure(
            code, 3, "index-payloads", str(error), payload_type_status="pass"
        ) from error
    if not isinstance(payload_value, dict):
        raise EnvelopeLoadFailure(
            "E_CORE_SCHEMA",
            4,
            "core-schemas",
            f"payload in {logical_path!r} is not an object",
            payload_type_status="pass",
        )
    if timing is not None:
        timing.begin(4)
    try:
        validate_core(payload_schema, payload_value, repository_root=repository_root)
    except CoreValidationError as error:
        raise EnvelopeLoadFailure(
            "E_CORE_SCHEMA",
            4,
            "core-schemas",
            str(error),
            payload_type_status="pass",
        ) from error
    return EnvelopeRecord(
        envelope, payload, cast(dict[str, Any], payload_value), sha256_bytes(payload)
    )


def _scan_bundle(root: Path) -> dict[str, tuple[str, tuple[int, int]]]:
    if root.is_symlink() or not root.is_dir():
        raise BundleError("bundle root must be a real directory")
    inventory: dict[str, tuple[str, tuple[int, int]]] = {}
    folded: dict[str, str] = {}
    identities: dict[tuple[int, int], str] = {}
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix().encode()
    ):
        relative = path.relative_to(root).as_posix()
        if relative != normalize_nfc(relative):
            raise BundleError(f"bundle path is not NFC: {relative}")
        folded_name = casefold(relative)
        if folded_name in folded and folded[folded_name] != relative:
            raise BundleError(f"bundle paths collide after case folding: {relative}")
        folded[folded_name] = relative
        metadata = path.lstat()
        identity = (metadata.st_dev, metadata.st_ino)
        if stat.S_ISLNK(metadata.st_mode) or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
        ):
            raise BundleError(f"bundle entry has an unsafe type: {relative}")
        if identity in identities:
            raise BundleError(f"bundle entries alias one physical object: {relative}")
        identities[identity] = relative
        inventory[relative] = ("file" if stat.S_ISREG(metadata.st_mode) else "directory", identity)
    return inventory


def _validate_consumer_configuration(request: VerificationRequest) -> None:
    try:
        expected_head_identities = [item["sha256"] for item in request.expected_heads]
        expected_artifact_identities = [
            (item["head"]["sha256"], item["subjectName"], item["digest"]["sha256"])
            for item in request.expected_artifacts
        ]
    except (KeyError, TypeError) as error:
        raise VerificationConfigurationError(
            "consumer expected values have the wrong shape"
        ) from error
    if len(expected_head_identities) != len(set(expected_head_identities)):
        raise VerificationConfigurationError("expected-head identities must be unique")
    if len(expected_artifact_identities) != len(set(expected_artifact_identities)):
        raise VerificationConfigurationError("expected-artifact identities must be unique")
    artifact_identities = [source.identity for source in request.artifact_materials]
    dataset_identities = [source.identity for source in request.dataset_entry_bindings]
    if len(artifact_identities) != len(set(artifact_identities)):
        raise VerificationConfigurationError("consumer artifact-material identities must be unique")
    if len(dataset_identities) != len(set(dataset_identities)):
        raise VerificationConfigurationError(
            "consumer dataset-entry-binding identities must be unique"
        )
    physical_identities: set[tuple[int, int]] = set()
    metadata_paths = [
        request.policy_path,
        *request.schema_catalogs,
        *request.consumer_metadata_paths,
    ]
    consumer_paths = [source.path for source in request.artifact_materials]
    consumer_paths.extend(source.path for source in request.dataset_entry_bindings)
    consumer_paths.extend(metadata_paths)
    for path in consumer_paths:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise VerificationConfigurationError(
                f"consumer input cannot be inspected: {path}"
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise VerificationConfigurationError(
                f"consumer input must be a real regular file: {path}"
            )
        physical_identity = (metadata.st_dev, metadata.st_ino)
        if physical_identity in physical_identities:
            raise VerificationConfigurationError(
                "consumer input paths must identify distinct physical files"
            )
        physical_identities.add(physical_identity)


def _snapshot_consumer_materials(
    request: VerificationRequest,
    inventory: dict[str, tuple[str, tuple[int, int]]],
) -> tuple[
    dict[tuple[str, str, str], bytes],
    dict[tuple[str, str, str], tuple[str, bytes]],
]:
    bundle_root = request.bundle_root.resolve()
    bundle_identities = {identity for _kind, identity in inventory.values()}
    consumer_identities: set[tuple[int, int]] = set()
    if request.snapshot_root is None:
        raise BundleError("verifier snapshot directory is unavailable")

    def open_consumer(path: Path) -> tuple[int, os.stat_result]:
        if path.is_symlink():
            raise BundleError(f"consumer input must not be a symbolic link: {path}")
        resolved = path.resolve()
        try:
            resolved.relative_to(bundle_root)
        except ValueError:
            pass
        else:
            raise BundleError(f"consumer input is contained by the bundle: {path}")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise BundleError(f"consumer input is not a regular file: {path}")
        identity = (metadata.st_dev, metadata.st_ino)
        if identity in bundle_identities:
            os.close(descriptor)
            raise BundleError(f"consumer input aliases a bundle entry: {path}")
        if identity in consumer_identities:
            os.close(descriptor)
            raise BundleError(f"consumer inputs alias one physical object: {path}")
        consumer_identities.add(identity)
        return descriptor, metadata

    for metadata_path in (
        request.policy_path,
        *request.schema_catalogs,
        *request.consumer_metadata_paths,
    ):
        descriptor, _metadata = open_consumer(metadata_path)
        os.close(descriptor)

    def snapshot(path: Path) -> bytes:
        descriptor, before = open_consumer(path)
        snapshot_descriptor, raw_snapshot_path = tempfile.mkstemp(
            prefix="material-", dir=request.snapshot_root
        )
        snapshot_path = Path(raw_snapshot_path)
        try:
            os.fchmod(snapshot_descriptor, 0o600)
            with (
                os.fdopen(os.dup(descriptor), "rb") as source,
                os.fdopen(snapshot_descriptor, "wb") as target,
            ):
                snapshot_descriptor = -1
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            after = os.fstat(descriptor)
            stable_fields = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            if stable_fields != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise BundleError(f"consumer input changed while snapshotting: {path}")
            return snapshot_path.read_bytes()
        finally:
            os.close(descriptor)
            if snapshot_descriptor >= 0:
                os.close(snapshot_descriptor)

    artifact_materials = {
        source.identity: snapshot(source.path) for source in request.artifact_materials
    }
    dataset_entries = {
        source.identity: (source.digest, snapshot(source.path))
        for source in request.dataset_entry_bindings
    }
    return artifact_materials, dataset_entries


def _safe_read(
    root: Path, logical_path: str, inventory: dict[str, tuple[str, tuple[int, int]]]
) -> bytes:
    expected = inventory.get(logical_path)
    if expected is None or expected[0] != "file":
        raise BundleError(f"bundle file is absent: {logical_path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(root / logical_path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != expected[1]:
            raise BundleError(f"bundle file changed identity: {logical_path}")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def _prevalidate_dataset_manifests(
    report: dict[str, Any],
    *,
    bundle: dict[str, Any],
    manifest: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    authorization: dict[str, AuthorizationResult],
    handoff_authorized: bool,
    root: Path,
    inventory: dict[str, tuple[str, tuple[int, int]]],
    repository_root: Path,
    consumer_materials: dict[tuple[str, str, str], bytes],
    consumer_dataset_identities: set[tuple[str, str, str]],
    catalogs: Sequence[Path],
) -> DatasetVerification:
    """Perform the bounded-by-current-runtime subset of normative Step 8 once."""

    authorized = {
        digest
        for digest, result in authorization.items()
        if result.authorized and digest in statements
    }
    subjects: dict[tuple[str, str], tuple[str, str, str]] = {}
    for statement_digest in sorted(authorized):
        for subject in statements[statement_digest]["subject"]:
            subjects[(statement_digest, subject["name"])] = (
                statement_digest,
                subject["name"],
                subject["digest"]["sha256"],
            )

    candidates: dict[tuple[str, str, str], bool] = {}
    edge_entries: dict[tuple[str, str, str], str] = {}

    def add_candidate(identity: tuple[str, str, str] | None, *, required: bool) -> None:
        if identity is not None:
            candidates[identity] = candidates.get(identity, False) or required

    for consumer_digest in sorted(authorized):
        statement = statements[consumer_digest]
        for item in statement["predicate"].get("inputs", []):
            provenance = item["provenance"]
            if "entryName" not in provenance:
                continue
            predecessor_digest = provenance["statementDigest"]["sha256"]
            if predecessor_digest not in authorized:
                continue
            logical_identity = (
                predecessor_digest,
                provenance["subjectName"],
                provenance["entryName"],
            )
            edge_digest = item["digest"]["sha256"]
            previous_edge_digest = edge_entries.get(logical_identity)
            if previous_edge_digest is None or edge_digest < previous_edge_digest:
                edge_entries[logical_identity] = edge_digest
            add_candidate(
                subjects.get((predecessor_digest, provenance["subjectName"])), required=True
            )

    for statement_digest in sorted(authorized):
        statement = statements[statement_digest]
        for profile in statement["predicate"].get("profiles", []):
            if profile["target"] == "artifact" and profile["id"] == DATASET_MANIFEST_SCHEMA_ID:
                add_candidate(
                    subjects.get((statement_digest, profile["subjectName"])), required=False
                )

    if handoff_authorized:
        for statement_digest, subject_name, _entry_name in sorted(consumer_dataset_identities):
            add_candidate(
                subjects.get((statement_digest, subject_name)),
                required=True,
            )
        for mapping in bundle.get("datasetEntries", []):
            add_candidate(
                subjects.get(
                    (
                        mapping["manifestStatementDigest"]["sha256"],
                        mapping["manifestSubjectName"],
                    )
                ),
                required=True,
            )
        for artifact in manifest["artifacts"]:
            if artifact.get("mediaType") == DATASET_MANIFEST_MEDIA_TYPE:
                add_candidate(
                    subjects.get((artifact["head"]["sha256"], artifact["name"])),
                    required=False,
                )

    mappings = {
        (
            item["statementDigest"]["sha256"],
            item["subjectName"],
            item["digest"]["sha256"],
        ): item
        for item in bundle["artifacts"]
    }
    indexes: dict[tuple[str, str, str], DatasetManifestIndex] = {}
    memberships: dict[tuple[str, str, str], str] = {}
    snapshots: dict[tuple[str, str, str], bytes] = {}
    profile_states: dict[tuple[str, str, str, str, str], str] = {}
    verified_subjects: set[tuple[str, str]] = set()
    failed_subjects: set[tuple[str, str]] = set()

    def fail(code: str, message: str, identity: tuple[str, str, str]) -> None:
        statement_digest, subject_name, subject_digest = identity
        add_error(
            report,
            Diagnostic(
                code,
                8,
                message,
                "graph-dependency-artifacts",
                {
                    "manifestStatementDigest": digest_object(statement_digest),
                    "manifestSubjectName": subject_name,
                    "artifactDigest": digest_object(subject_digest),
                },
            ),
        )
        set_check(report, "graph-dependency-artifacts", "fail")
        failed_subjects.add((statement_digest, subject_name))

    for identity, required in sorted(candidates.items()):
        statement_digest, subject_name, subject_digest = identity
        statement = statements[statement_digest]
        profiles = [
            profile
            for profile in statement["predicate"].get("profiles", [])
            if profile["target"] == "artifact" and profile["subjectName"] == subject_name
        ]
        expected_profile = core_dataset_manifest_profile_reference(
            subject_name, repository_root=repository_root
        )
        if expected_profile not in profiles:
            fail(
                "E_DATASET_MANIFEST_INVALID",
                "dataset-manifest subject lacks the exact mandatory core profile identity",
                identity,
            )
            continue
        mapping = mappings.get(identity) if handoff_authorized else None
        material = consumer_materials.get(identity) if handoff_authorized else None
        if mapping is None and material is None:
            if required:
                fail(
                    "E_DATASET_MANIFEST_REQUIRED",
                    "dataset-manifest bytes required by an entry edge or mapping are absent",
                    identity,
                )
            continue
        if material is None:
            assert mapping is not None
            try:
                material = _safe_read(root, mapping["path"], inventory)
            except OSError as error:
                fail(
                    "E_BUNDLE_UNSAFE_PATH",
                    f"dataset-manifest material became unsafe: {error}",
                    identity,
                )
                continue
            except BundleError as error:
                if required:
                    fail(
                        "E_DATASET_MANIFEST_REQUIRED"
                        if str(error).startswith("bundle file is absent:")
                        else "E_BUNDLE_UNSAFE_PATH",
                        "dataset-manifest bytes required by an entry edge or mapping are absent"
                        if str(error).startswith("bundle file is absent:")
                        else f"dataset-manifest material became unsafe: {error}",
                        identity,
                    )
                continue

        profile_identity = (
            statement_digest,
            expected_profile["id"],
            expected_profile["digest"]["sha256"],
            expected_profile["closureDigest"]["sha256"],
            "artifact",
        )
        if sha256_bytes(material) != subject_digest:
            fail(
                "E_ARTIFACT_DIGEST",
                "dataset-manifest bytes differ from the signed subject digest",
                identity,
            )
            profile_states[profile_identity] = "skipped"
            record = _profile_record(statement_digest, expected_profile, "skipped", "skipped")
            record["prerequisiteChecks"] = ["graph-dependency-artifacts"]
            report["profiles"].append(record)
            continue

        manifest_hint = next(
            (
                artifact.get("mediaType")
                for artifact in manifest["artifacts"]
                if artifact["head"]["sha256"] == statement_digest
                and artifact["name"] == subject_name
                and artifact["digest"]["sha256"] == subject_digest
            ),
            None,
        )
        media_types = {profile["mediaType"] for profile in profiles}
        if manifest_hint is not None:
            media_types.add(manifest_hint)
        if len(media_types) > 1:
            fail(
                "E_PROFILE_INVALID",
                "dataset-manifest media types conflict across signed profiles and handoff",
                identity,
            )
            for profile in profiles:
                profile_identity = (
                    statement_digest,
                    profile["id"],
                    profile["digest"]["sha256"],
                    profile["closureDigest"]["sha256"],
                    profile["target"],
                )
                try:
                    validate_with_catalog(
                        {},
                        profile,
                        catalog_paths=catalogs,
                        repository_root=repository_root,
                    )
                except (ProfileResolutionError, ValueError):
                    resolution = "fail"
                else:
                    resolution = "pass"
                profile_states[profile_identity] = "fail"
                report["profiles"].append(
                    _profile_record(statement_digest, profile, resolution, "fail")
                )
            continue

        snapshots[identity] = material
        try:
            index = parse_dataset_manifest(material, repository_root=repository_root)
        except DatasetManifestError as error:
            fail("E_DATASET_MANIFEST_INVALID", str(error), identity)
            resolution = "pass"
            validation = (
                "skipped"
                if error.phase == "parse"
                else ("fail" if error.phase == "schema" else "pass")
            )
            profile_states[profile_identity] = validation
            record = _profile_record(statement_digest, expected_profile, resolution, validation)
            record["prerequisiteChecks"] = (
                ["graph-dependency-artifacts"] if error.phase == "parse" else []
            )
            report["profiles"].append(record)
            continue

        indexes[identity] = index
        verified_subjects.add((statement_digest, subject_name))
        for entry in index.entries:
            memberships[(statement_digest, subject_name, entry.name)] = entry.digest
        profile_states[profile_identity] = "pass"
        report["profiles"].append(
            _profile_record(statement_digest, expected_profile, "pass", "pass")
        )

    return DatasetVerification(
        indexes=indexes,
        memberships=memberships,
        snapshots=snapshots,
        profile_states=profile_states,
        verified_subjects=frozenset(verified_subjects),
        failed_subjects=frozenset(failed_subjects),
        edge_entries=edge_entries,
    )


def _verify_dataset_entries(
    report: dict[str, Any],
    *,
    bundle: dict[str, Any],
    verification: DatasetVerification,
    root: Path,
    inventory: dict[str, tuple[str, tuple[int, int]]],
    consumer_bindings: dict[tuple[str, str, str], tuple[str, bytes]],
) -> None:
    """Verify the Step 12 partition population against cached Step 8 indexes."""

    mappings = {
        (
            item["manifestStatementDigest"]["sha256"],
            item["manifestSubjectName"],
            item["entryName"],
        ): item
        for item in bundle.get("datasetEntries", [])
    }
    logical_identities = sorted(
        set(verification.edge_entries) | set(mappings) | set(consumer_bindings)
    )
    for logical_identity in logical_identities:
        statement_digest, subject_name, entry_name = logical_identity
        mapping = mappings.get(logical_identity)
        consumer_binding = consumer_bindings.get(logical_identity)
        matching_indexes = [
            index
            for (candidate_digest, candidate_name, _subject_digest), index in (
                verification.indexes.items()
            )
            if candidate_digest == statement_digest and candidate_name == subject_name
        ]
        member = matching_indexes[0].member(entry_name) if len(matching_indexes) == 1 else None
        fallback_digest = (
            mapping["digest"]["sha256"]
            if mapping is not None
            else (
                consumer_binding[0]
                if consumer_binding is not None
                else verification.edge_entries[logical_identity]
            )
        )
        record: dict[str, Any] = {
            "manifestStatementDigest": digest_object(statement_digest),
            "manifestSubjectName": subject_name,
            "entryName": entry_name,
            "digest": digest_object(member.digest if member is not None else fallback_digest),
            "declaredSize": str(member.size)
            if member is not None and member.size is not None
            else None,
            "digestStatus": "not_checked",
            "digestPrerequisiteChecks": [],
            "sizeStatus": "not_checked",
            "sizePrerequisiteChecks": [],
        }
        report["datasetEntries"].append(record)

        context = {
            "manifestStatementDigest": digest_object(statement_digest),
            "manifestSubjectName": subject_name,
            "entryName": entry_name,
            "artifactDigest": record["digest"],
        }
        if len(matching_indexes) != 1:
            if consumer_binding is not None:
                add_error(
                    report,
                    Diagnostic(
                        "E_DATASET_MANIFEST_REQUIRED",
                        8,
                        "consumer dataset-entry binding has no verified dataset manifest",
                        "graph-dependency-artifacts",
                        context,
                    ),
                )
                set_check(report, "graph-dependency-artifacts", "fail")
                record["digestStatus"] = "skipped"
                record["digestPrerequisiteChecks"] = ["graph-dependency-artifacts"]
                record["sizeStatus"] = "skipped"
                record["sizePrerequisiteChecks"] = ["graph-dependency-artifacts"]
            else:
                record["digestStatus"] = "skipped"
                record["digestPrerequisiteChecks"] = ["graph-dependency-artifacts"]
                record["sizeStatus"] = "skipped"
                record["sizePrerequisiteChecks"] = ["graph-dependency-artifacts"]
            continue
        if member is None:
            if mapping is not None or consumer_binding is not None:
                add_error(
                    report,
                    Diagnostic(
                        "E_DATASET_MANIFEST_INVALID",
                        12,
                        "dataset-entry mapping names an unknown manifest member",
                        "artifact-bytes",
                        context,
                    ),
                )
                set_check(report, "artifact-bytes", "fail")
                record["digestStatus"] = "fail"
                record["sizeStatus"] = "skipped"
                record["sizePrerequisiteChecks"] = ["artifact-bytes"]
            continue
        if mapping is None and consumer_binding is None:
            continue
        if mapping is not None:
            supplied_digest = mapping["digest"]["sha256"]
        else:
            assert consumer_binding is not None
            supplied_digest = consumer_binding[0]
        if supplied_digest != member.digest:
            add_error(
                report,
                Diagnostic(
                    "E_DATASET_MANIFEST_INVALID",
                    12,
                    "dataset-entry mapping digest differs from the manifest member",
                    "artifact-bytes",
                    context,
                ),
            )
            set_check(report, "artifact-bytes", "fail")
            record["digestStatus"] = "fail"
            record["sizeStatus"] = "skipped"
            record["sizePrerequisiteChecks"] = ["artifact-bytes"]
            continue
        if mapping is not None and mapping["path"] not in inventory:
            add_error(
                report,
                Diagnostic(
                    "E_ARTIFACT_MISSING",
                    12,
                    "dataset-entry mapping target is absent",
                    "artifact-bytes",
                    {**context, "path": mapping["path"]},
                ),
            )
            set_check(report, "artifact-bytes", "fail")
            record["digestStatus"] = "fail"
            record["sizeStatus"] = "skipped"
            record["sizePrerequisiteChecks"] = ["artifact-bytes"]
            continue
        try:
            if mapping is not None:
                material = _safe_read(root, mapping["path"], inventory)
            else:
                assert consumer_binding is not None
                material = consumer_binding[1]
        except (BundleError, OSError) as error:
            add_error(
                report,
                Diagnostic(
                    "E_BUNDLE_UNSAFE_PATH",
                    12,
                    str(error),
                    "artifact-bytes",
                    {
                        **context,
                        "path": mapping["path"] if mapping is not None else "consumer-material",
                    },
                ),
            )
            set_check(report, "artifact-bytes", "fail")
            record["digestStatus"] = "fail"
            record["sizeStatus"] = "skipped"
            record["sizePrerequisiteChecks"] = ["artifact-bytes"]
            continue

        if sha256_bytes(material) == member.digest:
            record["digestStatus"] = "pass"
        else:
            record["digestStatus"] = "fail"
            add_error(
                report,
                Diagnostic(
                    "E_ARTIFACT_DIGEST",
                    12,
                    "dataset-entry bytes differ from the manifest member digest",
                    "artifact-bytes",
                    context,
                ),
            )
            set_check(report, "artifact-bytes", "fail")
        if member.size is not None:
            if len(material) == member.size:
                record["sizeStatus"] = "pass"
            else:
                record["sizeStatus"] = "fail"
                add_error(
                    report,
                    Diagnostic(
                        "E_ARTIFACT_SIZE",
                        12,
                        "dataset-entry byte count differs from the manifest member size",
                        "artifact-bytes",
                        {
                            **context,
                            "declaredSize": str(member.size),
                            "actualSize": str(len(material)),
                        },
                    ),
                )
                set_check(report, "artifact-bytes", "fail")


def _final_rescan(root: Path, first: dict[str, tuple[str, tuple[int, int]]]) -> None:
    if _scan_bundle(root) != first:
        raise BundleError("bundle tree changed during verification")


def _record_signature_diagnostics(
    report: dict[str, Any], signatures: tuple[SignatureResult, ...], statement_digest: str
) -> None:
    for signature in signatures:
        if not signature.key_known:
            add_warning(
                report,
                Diagnostic(
                    "W_SIGNATURE_UNKNOWN",
                    5,
                    "signature key is not configured",
                    "signatures",
                    {"statementDigest": digest_object(statement_digest), "keyid": signature.keyid},
                ),
            )
        elif signature.cryptographic == "fail":
            add_error(
                report,
                Diagnostic(
                    "E_SIGNATURE_INVALID",
                    5,
                    "signature verification failed",
                    "signatures",
                    {"statementDigest": digest_object(statement_digest), "keyid": signature.keyid},
                ),
            )
            set_check(report, "signatures", "fail")


def _signature_dict(result: SignatureResult) -> dict[str, Any]:
    return {
        "keyid": result.keyid,
        "keyKnown": result.key_known,
        "cryptographic": result.cryptographic,
    }


def _record_graph_problem(report: dict[str, Any], problem: GraphProblem) -> None:
    steps = {
        "E_PREDICATE_SEMANTICS_UNSUPPORTED": (4, "core-schemas"),
        "E_DATASET_MANIFEST_REQUIRED": (8, "graph-dependency-artifacts"),
        "E_EVENT_ID_DUPLICATE": (9, "graph"),
        "E_PREDECESSOR_MISSING": (9, "graph"),
        "E_PREDECESSOR_SUBJECT": (9, "graph"),
        "E_INPUT_DIGEST": (9, "graph"),
        "E_GRAPH_CYCLE": (9, "graph"),
        "E_ROOT_INVALID": (10, "roots-and-heads"),
    }
    step, owner = steps[problem.code]
    add_error(
        report,
        Diagnostic(
            problem.code,
            step,
            problem.message,
            owner,
            {"statementDigest": digest_object(problem.statement_digest)},
        ),
    )
    set_check(report, owner, "fail")


def _validate_metadata_profiles(
    report: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    manifest_statement_set: set[str],
    catalogs: list[Path],
    repository_root: Path,
    policy: TrustPolicy,
    authorization: dict[str, AuthorizationResult],
) -> dict[tuple[str, str, str, str, str], str]:
    states: dict[tuple[str, str, str, str, str], str] = {}
    for statement_digest in sorted(manifest_statement_set):
        statement = statements.get(statement_digest)
        if statement is None:
            continue
        requirements = policy.authorization_profile_requirements(
            statement, authorization[statement_digest]
        )
        for profile in statement["predicate"].get("profiles", []):
            target = profile["target"]
            if target == "artifact":
                continue
            identity = (
                statement_digest,
                profile["id"],
                profile["digest"]["sha256"],
                profile["closureDigest"]["sha256"],
                target,
            )
            requirement_identity = identity[1:]
            required_by_rules = requirements.get(requirement_identity, ())
            instance = statement if target == "statement" else statement["predicate"]
            resolution = "pass"
            validation = "pass"
            try:
                result = validate_with_catalog(
                    instance,
                    profile,
                    catalog_paths=catalogs,
                    repository_root=repository_root,
                )
            except ProfileResolutionError as error:
                resolution = "fail" if profile["critical"] else "indeterminate"
                validation = "skipped"
                diagnostic = Diagnostic(
                    "E_PROFILE_UNRESOLVED" if profile["critical"] else "W_PROFILE_INDETERMINATE",
                    7,
                    str(error),
                    "metadata-profiles",
                    {
                        "statementDigest": digest_object(statement_digest),
                        "profileId": profile["id"],
                        "profileDigest": profile["digest"],
                    },
                )
                (add_error if profile["critical"] else add_warning)(report, diagnostic)
            else:
                if not result.valid:
                    validation = "fail"
                    add_error(
                        report,
                        Diagnostic(
                            "E_PROFILE_INVALID",
                            7,
                            "; ".join(result.errors),
                            "metadata-profiles",
                            {
                                "statementDigest": digest_object(statement_digest),
                                "profileId": profile["id"],
                                "profileDigest": profile["digest"],
                            },
                        ),
                    )
            if resolution == "fail" or validation == "fail":
                set_check(report, "metadata-profiles", "fail")
            states[identity] = validation
            record = _profile_record(statement_digest, profile, resolution, validation)
            record["requiredByAuthorizationRuleIds"] = list(required_by_rules)
            report["profiles"].append(record)
    return states


def _verify_unauthorized_consumer_historical(
    report: dict[str, Any],
    *,
    manifest: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    consumer_materials: dict[tuple[str, str, str], bytes],
) -> bool:
    """Hash only independently supplied historical bytes without trusting bundle mappings."""

    manifest_statement_set = {item["sha256"] for item in manifest["statements"]}
    final_identities = {
        (artifact["head"]["sha256"], artifact["name"], artifact["digest"]["sha256"])
        for artifact in manifest["artifacts"]
    }
    checked = False
    for identity, material in sorted(consumer_materials.items()):
        statement_digest, subject_name, subject_digest = identity
        statement = statements.get(statement_digest)
        exact_subject = (
            statement_digest in manifest_statement_set
            and statement is not None
            and any(
                subject["name"] == subject_name and subject["digest"]["sha256"] == subject_digest
                for subject in statement["subject"]
            )
        )
        if not exact_subject or identity in final_identities:
            add_error(
                report,
                Diagnostic(
                    "E_MANIFEST_SET",
                    11,
                    "consumer historical material is not an exact listed historical subject",
                    "completeness-anchor",
                    {
                        "bundleId": manifest["bundleId"],
                        "statementDigest": digest_object(statement_digest),
                        "subjectName": subject_name,
                        "artifactDigest": digest_object(subject_digest),
                    },
                ),
            )
            set_check(report, "completeness-anchor", "fail")
            continue
        checked = True
        digest_status = "pass" if sha256_bytes(material) == subject_digest else "fail"
        if digest_status == "fail":
            add_error(
                report,
                Diagnostic(
                    "E_ARTIFACT_DIGEST",
                    12,
                    "consumer historical bytes differ from the signed subject digest",
                    "artifact-bytes",
                    {
                        "statementDigest": digest_object(statement_digest),
                        "subjectName": subject_name,
                        "artifactDigest": digest_object(subject_digest),
                    },
                ),
            )
            set_check(report, "artifact-bytes", "fail")
        report["artifacts"].append(
            {
                "lifecycleRole": "historical",
                "artifactKind": "ordinary",
                "statementDigest": digest_object(statement_digest),
                "head": None,
                "subjectName": subject_name,
                "digest": digest_object(subject_digest),
                "digestStatus": digest_status,
                "digestPrerequisiteChecks": [],
                "profileStatus": "not_checked",
                "profilePrerequisiteChecks": [],
                "applicableProfileCount": 0,
            }
        )
    return checked


def _verify_historical_artifacts(
    report: dict[str, Any],
    *,
    mappings: dict[tuple[str, str, str], dict[str, Any]],
    final_identities: set[tuple[str, str, str]],
    statements: dict[str, dict[str, Any]],
    reachable: frozenset[str],
    artifact_bytes: dict[tuple[str, str, str], bytes],
    root: Path,
    inventory: dict[str, tuple[str, tuple[int, int]]],
    repository_root: Path,
    consumer_materials: dict[tuple[str, str, str], bytes],
) -> None:
    """Verify supplied or profile-required historical subjects as ordinary evidence."""

    profile_targets: set[tuple[str, str, str]] = set()
    for statement_digest in sorted(reachable):
        statement = statements.get(statement_digest)
        if statement is None:
            continue
        subjects = {subject["name"]: subject for subject in statement["subject"]}
        for profile in statement["predicate"].get("profiles", []):
            if profile["target"] != "artifact":
                continue
            subject = subjects.get(profile["subjectName"])
            if subject is not None:
                profile_targets.add(
                    (statement_digest, profile["subjectName"], subject["digest"]["sha256"])
                )

    candidates = (set(mappings) | set(consumer_materials) | profile_targets) - final_identities
    for identity in sorted(candidates):
        statement_digest, subject_name, subject_digest = identity
        statement = statements.get(statement_digest)
        exact_subject = statement is not None and any(
            subject["name"] == subject_name and subject["digest"]["sha256"] == subject_digest
            for subject in statement["subject"]
        )
        profiles: list[dict[str, Any]] = []
        if exact_subject and statement is not None:
            profiles = [
                profile
                for profile in statement["predicate"].get("profiles", [])
                if profile["target"] == "artifact" and profile["subjectName"] == subject_name
            ]
        dataset_profile = (
            core_dataset_manifest_profile_reference(subject_name, repository_root=repository_root)
            if exact_subject
            else None
        )
        record: dict[str, Any] = {
            "lifecycleRole": "historical",
            "artifactKind": "dataset-manifest"
            if dataset_profile is not None and dataset_profile in profiles
            else "ordinary",
            "statementDigest": digest_object(statement_digest),
            "head": None,
            "subjectName": subject_name,
            "digest": digest_object(subject_digest),
            "digestStatus": "not_checked",
            "digestPrerequisiteChecks": [],
            "profileStatus": "not_checked",
            "profilePrerequisiteChecks": [],
            "applicableProfileCount": 0,
        }
        report["artifacts"].append(record)

        if not exact_subject:
            add_error(
                report,
                Diagnostic(
                    "E_MANIFEST_SET",
                    11,
                    "historical artifact mapping is not an exact manifest-listed signed subject",
                    "completeness-anchor",
                    {
                        "bundleId": report["bundleId"],
                        "statementDigest": digest_object(statement_digest),
                        "subjectName": subject_name,
                        "artifactDigest": digest_object(subject_digest),
                    },
                ),
            )
            set_check(report, "completeness-anchor", "fail")
            record["digestStatus"] = "skipped"
            record["digestPrerequisiteChecks"] = ["completeness-anchor"]
            record["profileStatus"] = "skipped"
            record["profilePrerequisiteChecks"] = ["completeness-anchor"]
            continue

        mapping = mappings.get(identity)
        consumer_material = consumer_materials.get(identity)
        required = any(profile["critical"] for profile in profiles)
        if mapping is None and consumer_material is None:
            if required:
                add_error(
                    report,
                    Diagnostic(
                        "E_ARTIFACT_MISSING",
                        12,
                        "critical historical artifact bytes are absent",
                        "artifact-bytes",
                        {
                            "statementDigest": digest_object(statement_digest),
                            "subjectName": subject_name,
                            "artifactDigest": digest_object(subject_digest),
                        },
                    ),
                )
                set_check(report, "artifact-bytes", "fail")
                record["digestStatus"] = "fail"
            else:
                add_warning(
                    report,
                    Diagnostic(
                        "W_HISTORICAL_ARTIFACT_NOT_CHECKED",
                        12,
                        "optional historical artifact bytes were not supplied",
                        "artifact-bytes",
                        {
                            "statementDigest": digest_object(statement_digest),
                            "subjectName": subject_name,
                            "artifactDigest": digest_object(subject_digest),
                        },
                    ),
                )
            continue

        if identity in artifact_bytes:
            record["digestStatus"] = "pass"
            continue
        try:
            material = (
                _safe_read(root, mapping["path"], inventory)
                if mapping is not None
                else consumer_material
            )
            assert material is not None
        except (BundleError, OSError) as error:
            code = (
                "E_ARTIFACT_MISSING"
                if str(error).startswith("bundle file is absent:")
                else "E_BUNDLE_UNSAFE_PATH"
            )
            add_error(
                report,
                Diagnostic(
                    code,
                    12,
                    str(error),
                    "artifact-bytes",
                    {
                        "statementDigest": digest_object(statement_digest),
                        "subjectName": subject_name,
                        "artifactDigest": digest_object(subject_digest),
                        "path": mapping["path"] if mapping is not None else "consumer-material",
                    },
                ),
            )
            set_check(report, "artifact-bytes", "fail")
            record["digestStatus"] = "fail"
            continue
        if sha256_bytes(material) != subject_digest:
            add_error(
                report,
                Diagnostic(
                    "E_ARTIFACT_DIGEST",
                    12,
                    "historical artifact bytes differ from the signed subject digest",
                    "artifact-bytes",
                    {
                        "statementDigest": digest_object(statement_digest),
                        "subjectName": subject_name,
                        "artifactDigest": digest_object(subject_digest),
                    },
                ),
            )
            set_check(report, "artifact-bytes", "fail")
            record["digestStatus"] = "fail"
            continue
        artifact_bytes[identity] = material
        record["digestStatus"] = "pass"


def _validate_artifact_profiles(
    report: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    artifact_bytes: dict[tuple[str, str, str], bytes],
    catalogs: list[Path],
    repository_root: Path,
    profile_states: dict[tuple[str, str, str, str, str], str],
    final_media_hints: dict[tuple[str, str, str], str | None],
) -> None:
    for artifact in report["artifacts"]:
        statement_digest = artifact["statementDigest"]["sha256"]
        key = (statement_digest, artifact["subjectName"], artifact["digest"]["sha256"])
        statement = statements.get(statement_digest)
        if statement is None:
            continue
        if artifact["digestPrerequisiteChecks"] == ["completeness-anchor"]:
            continue
        profiles = [
            profile
            for profile in statement["predicate"].get("profiles", [])
            if profile["target"] == "artifact" and profile["subjectName"] == artifact["subjectName"]
        ]
        artifact["applicableProfileCount"] = len(profiles)
        if not profiles:
            if artifact["lifecycleRole"] == "final":
                add_warning(
                    report,
                    Diagnostic(
                        "W_ARTIFACT_UNPROFILED",
                        13,
                        "final artifact has no applicable content profile",
                        "artifact-profiles",
                        {
                            "head": artifact["head"],
                            "subjectName": artifact["subjectName"],
                            "artifactDigest": artifact["digest"],
                        },
                    ),
                )
            continue
        material = artifact_bytes.get(key)
        if material is None:
            artifact["profileStatus"] = "skipped"
            artifact["profilePrerequisiteChecks"] = ["artifact-bytes"]
            continue
        media_types = {profile["mediaType"] for profile in profiles}
        manifest_hint = final_media_hints.get(key)
        if manifest_hint is not None:
            media_types.add(manifest_hint)
        if len(media_types) > 1:
            artifact["profileStatus"] = "fail"
            set_check(report, "artifact-profiles", "fail")
            for profile in profiles:
                try:
                    validate_with_catalog(
                        {},
                        profile,
                        catalog_paths=catalogs,
                        repository_root=repository_root,
                    )
                except (ProfileResolutionError, ValueError):
                    resolution = "fail"
                else:
                    resolution = "pass"
                add_error(
                    report,
                    Diagnostic(
                        "E_PROFILE_INVALID",
                        13,
                        "artifact media types conflict across signed profiles and handoff",
                        "artifact-profiles",
                        {
                            "statementDigest": artifact["statementDigest"],
                            "subjectName": artifact["subjectName"],
                            "profileId": profile["id"],
                            "profileDigest": profile["digest"],
                        },
                    ),
                )
                report["profiles"].append(
                    _profile_record(statement_digest, profile, resolution, "fail")
                )
            continue
        status = "pass"
        for profile in profiles:
            profile_identity = (
                statement_digest,
                profile["id"],
                profile["digest"]["sha256"],
                profile["closureDigest"]["sha256"],
                profile["target"],
            )
            cached_state = profile_states.get(profile_identity)
            if cached_state is not None:
                if cached_state != "pass":
                    status = "fail"
                continue
            try:
                instance = _parse_artifact(material, profile["mediaType"])
                result = validate_with_catalog(
                    instance,
                    profile,
                    catalog_paths=catalogs,
                    repository_root=repository_root,
                )
            except (ProfileResolutionError, ValueError) as error:
                code = (
                    "E_PROFILE_UNRESOLVED"
                    if isinstance(error, ProfileResolutionError)
                    else "E_ARTIFACT_FORMAT"
                )
                add_error(
                    report,
                    Diagnostic(
                        code,
                        13,
                        str(error),
                        "artifact-profiles",
                        {
                            "statementDigest": artifact["statementDigest"],
                            "subjectName": artifact["subjectName"],
                            "profileId": profile["id"],
                            "profileDigest": profile["digest"],
                        },
                    ),
                )
                status = "fail"
                resolution = "fail"
                validation = "skipped"
            else:
                resolution = "pass"
                validation = "pass" if result.valid else "fail"
                if not result.valid:
                    status = "fail"
                    add_error(
                        report,
                        Diagnostic(
                            "E_PROFILE_INVALID",
                            13,
                            "; ".join(result.errors),
                            "artifact-profiles",
                            {
                                "statementDigest": artifact["statementDigest"],
                                "subjectName": artifact["subjectName"],
                                "profileId": profile["id"],
                                "profileDigest": profile["digest"],
                            },
                        ),
                    )
            report["profiles"].append(
                _profile_record(statement_digest, profile, resolution, validation)
            )
        artifact["profileStatus"] = status
        if status == "fail":
            set_check(report, "artifact-profiles", "fail")


def _profile_record(
    statement_digest: str,
    profile: dict[str, Any],
    resolution: str,
    validation: str,
) -> dict[str, Any]:
    prerequisites = []
    if validation == "skipped":
        prerequisites = [
            "artifact-profiles" if profile["target"] == "artifact" else "metadata-profiles"
        ]
    return {
        "statementDigest": digest_object(statement_digest),
        "id": profile["id"],
        "digest": profile["digest"],
        "closureDigest": profile["closureDigest"],
        "target": profile["target"],
        "subjectName": profile.get("subjectName"),
        "mediaType": profile.get("mediaType"),
        "critical": profile["critical"],
        "requiredByManifest": False,
        "requiredByPolicy": False,
        "requiredByAuthorizationRuleIds": [],
        "resolution": resolution,
        "validation": validation,
        "prerequisiteChecks": prerequisites,
    }


def _parse_artifact(data: bytes, media_type: str) -> object:
    if media_type == "application/json" or (
        media_type.startswith("application/") and media_type.endswith("+json")
    ):
        return strict_json_loads(data)
    if media_type == "application/x-ndjson":
        values = []
        for line in data.splitlines():
            if line.strip():
                values.append(strict_json_loads(line))
        return values
    raise ValueError(f"unsupported artifact media type {media_type!r}")


def _enforce_required_profiles(
    report: dict[str, Any],
    manifest: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    policy: TrustPolicy,
) -> None:
    requirements: list[tuple[dict[str, Any], bool, bool]] = []
    requirements.extend((value, True, False) for value in manifest["requiredProfiles"])
    requirements.extend((value, False, True) for value in policy.value["requiredProfiles"])
    for requirement, by_manifest, by_policy in requirements:
        matching_artifacts = [
            artifact
            for artifact in manifest["artifacts"]
            if artifact["name"] == requirement["subjectName"]
            and ("head" not in requirement or artifact["head"] == requirement["head"])
        ]
        satisfied = bool(matching_artifacts)
        for artifact in matching_artifacts:
            statement = statements.get(artifact["head"]["sha256"])
            if statement is None:
                satisfied = False
                continue
            matching_profiles = [
                profile
                for profile in statement["predicate"].get("profiles", [])
                if profile["id"] == requirement["id"]
                and profile["digest"] == requirement["digest"]
                and profile["closureDigest"] == requirement["closureDigest"]
                and profile["target"] == "artifact"
                and profile["subjectName"] == requirement["subjectName"]
                and profile["mediaType"] == requirement["mediaType"]
            ]
            if not matching_profiles:
                satisfied = False
        if not satisfied:
            add_error(
                report,
                Diagnostic(
                    "E_REQUIRED_PROFILE_MISSING",
                    11 if by_manifest else 13,
                    "required final-artifact profile is absent from its signed head",
                    "completeness-anchor" if by_manifest else "artifact-profiles",
                    {
                        "profileId": requirement["id"],
                        "profileDigest": requirement["digest"],
                        "subjectName": requirement["subjectName"],
                    },
                ),
            )
            set_check(
                report,
                "completeness-anchor" if by_manifest else "artifact-profiles",
                "fail",
            )
        for record in report["profiles"]:
            if (
                record["id"] == requirement["id"]
                and record["digest"] == requirement["digest"]
                and record["closureDigest"] == requirement["closureDigest"]
                and record["target"] == "artifact"
                and record["subjectName"] == requirement["subjectName"]
            ):
                record["requiredByManifest"] = record["requiredByManifest"] or by_manifest
                record["requiredByPolicy"] = record["requiredByPolicy"] or by_policy


def _evaluate_freshness(
    report: dict[str, Any],
    request: VerificationRequest,
    policy: TrustPolicy,
    manifest_record: EnvelopeRecord,
) -> None:
    methods: list[str] = []
    failures = False
    if request.expected_manifest is not None or policy.value["handoff"]["requireExpectedManifest"]:
        methods.append("expected-manifest")
        report["expectedManifestDigest"] = request.expected_manifest
        passed = request.expected_manifest == digest_object(manifest_record.digest)
        report["handoff"]["freshnessChecks"]["expected-manifest"] = "pass" if passed else "fail"
        if not passed:
            failures = True
            add_error(
                report,
                Diagnostic(
                    "E_EXPECTED_MANIFEST",
                    11,
                    "expected manifest digest does not match",
                    "freshness-anchors",
                    {
                        "expected": request.expected_manifest,
                        "actual": digest_object(manifest_record.digest),
                    },
                ),
            )
    if request.expected_heads or policy.value["handoff"]["requireExpectedHead"]:
        methods.append("expected-heads")
        report["expectedHeads"] = list(request.expected_heads)
        passed = {item["sha256"] for item in request.expected_heads} == {
            item["sha256"] for item in manifest_record.value["heads"]
        }
        report["handoff"]["freshnessChecks"]["expected-heads"] = "pass" if passed else "fail"
        if not passed:
            failures = True
            add_error(
                report,
                Diagnostic(
                    "E_EXPECTED_HEAD",
                    11,
                    "expected head set does not match",
                    "freshness-anchors",
                    {"bundleId": manifest_record.value["bundleId"]},
                ),
            )
    if request.expected_artifacts or policy.value["handoff"]["requireExpectedArtifacts"]:
        methods.append("expected-artifacts")
        report["expectedArtifacts"] = list(request.expected_artifacts)
        expected = {
            (item["head"]["sha256"], item["subjectName"], item["digest"]["sha256"])
            for item in request.expected_artifacts
        }
        actual = {
            (item["head"]["sha256"], item["name"], item["digest"]["sha256"])
            for item in manifest_record.value["artifacts"]
        }
        passed = expected == actual
        report["handoff"]["freshnessChecks"]["expected-artifacts"] = "pass" if passed else "fail"
        if not passed:
            failures = True
            add_error(
                report,
                Diagnostic(
                    "E_EXPECTED_ARTIFACT",
                    11,
                    "expected artifact set does not match",
                    "freshness-anchors",
                    {"bundleId": manifest_record.value["bundleId"]},
                ),
            )
    if request.expected_recipient is not None or policy.value["handoff"]["requireRecipient"]:
        report["expectedRecipient"] = request.expected_recipient
        passed = (
            request.expected_recipient is not None
            and request.expected_recipient == report["actualRecipient"]
        )
        report["recipientStatus"] = "pass" if passed else "fail"
        if not passed:
            failures = True
            add_error(
                report,
                Diagnostic(
                    "E_HANDOFF_RECIPIENT",
                    11,
                    "handoff recipient does not match",
                    "freshness-anchors",
                    {"expected": request.expected_recipient, "actual": report["actualRecipient"]},
                ),
            )
    if request.expected_nonce is not None or policy.value["handoff"]["requireNonce"]:
        methods.append("nonce")
        report["expectedNonce"] = request.expected_nonce
        passed = (
            request.expected_nonce is not None and request.expected_nonce == report["actualNonce"]
        )
        report["nonceStatus"] = "pass" if passed else "fail"
        report["handoff"]["freshnessChecks"]["nonce"] = report["nonceStatus"]
        if not passed:
            failures = True
            add_error(
                report,
                Diagnostic(
                    "E_HANDOFF_NONCE",
                    11,
                    "handoff nonce does not match",
                    "freshness-anchors",
                    {"expected": request.expected_nonce, "actual": report["actualNonce"]},
                ),
            )
    if "maxAgeSeconds" in policy.value["handoff"]:
        methods.append("max-age")
        issued = _parse_timestamp(manifest_record.value["issuedAt"])
        evaluated = _parse_timestamp(report["evaluationTime"])
        delta = (evaluated - issued).total_seconds()
        passed = (
            -policy.value["handoff"]["maxFutureSkewSeconds"]
            <= delta
            <= policy.value["handoff"]["maxAgeSeconds"]
        )
        report["handoff"]["freshnessChecks"]["max-age"] = "pass" if passed else "fail"
        if not passed:
            failures = True
            add_error(
                report,
                Diagnostic(
                    "E_HANDOFF_STALE",
                    11,
                    "handoff is outside the allowed time window",
                    "freshness-anchors",
                    {"bundleId": manifest_record.value["bundleId"]},
                ),
            )
    if not methods and not policy.value["handoff"]["allowReplayableHandoff"]:
        failures = True
        add_error(
            report,
            Diagnostic(
                "E_FRESHNESS_REQUIRED",
                11,
                "policy requires an approved freshness method",
                "freshness-anchors",
                {"bundleId": manifest_record.value["bundleId"]},
            ),
        )
    elif not methods:
        add_warning(
            report,
            Diagnostic(
                "W_FRESHNESS_NOT_CHECKED",
                11,
                "policy explicitly permits replayable handoffs",
                "freshness-anchors",
                {"bundleId": manifest_record.value["bundleId"]},
            ),
        )
    report["handoff"]["freshnessMethod"] = (
        "none" if not methods else methods[0] if len(methods) == 1 else "multiple"
    )
    report["handoff"]["freshnessStatus"] = (
        "fail" if failures else "pass" if methods else "not_checked"
    )
    if failures:
        set_check(report, "freshness-anchors", "fail")


def _populate_statement_records(
    report: dict[str, Any],
    statements: dict[str, dict[str, Any]],
    authorization: dict[str, AuthorizationResult],
    problems: tuple[GraphProblem, ...],
) -> None:
    failed_graph = {problem.statement_digest for problem in problems}
    for digest, statement in sorted(statements.items()):
        auth = authorization[digest]
        if not auth.authorized:
            graph_status = "skipped"
            graph_prerequisites = ["authorization"]
        else:
            graph_status = "fail" if digest in failed_graph else "pass"
            graph_prerequisites = []
        report["statements"].append(
            {
                "digest": digest_object(digest),
                "predicateType": statement["predicateType"],
                "eventId": statement["predicate"]["event"]["id"],
                "coreSchema": "pass",
                "coreSchemaPrerequisiteChecks": [],
                "signatures": [_signature_dict(item) for item in auth.signatures],
                "candidateRuleIds": list(auth.candidate_rule_ids),
                "authorizingRuleIds": list(auth.authorizing_rule_ids),
                "authorization": "pass" if auth.authorized else "fail",
                "authorizationPrerequisiteChecks": [],
                "graph": graph_status,
                "graphPrerequisiteChecks": graph_prerequisites,
            }
        )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _now_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
