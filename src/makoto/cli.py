"""Normative Makoto v0.2 command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never, cast
from urllib.parse import urlsplit

from makoto import __version__
from makoto.bundle import (
    ArtifactMaterialSource,
    BundleError,
    DatasetEntrySource,
    VerificationRequest,
    VerificationTiming,
    load_attestation,
    verify_bundle,
    write_handoff_bundle,
)
from makoto.canonical import canonical_json
from makoto.dataset import DatasetManifestError, parse_dataset_manifest
from makoto.digest import digest_object, sha256_bytes, sha256_stream
from makoto.dsse import (
    DsseError,
    SigningKey,
    canonical_b64decode,
    canonical_b64encode,
    keyid_from_spki,
    pae,
    spki_from_pem,
)
from makoto.model import Artifact, Attestation, TransformationInput, create_origin, create_transform
from makoto.policy import TrustPolicy
from makoto.report import report_bytes
from makoto.schema import (
    CoreValidationError,
    ProfileResolutionError,
    StrictJsonError,
    core_dataset_manifest_profile_reference,
    create_profile_reference,
    load_catalog_resources,
    strict_json_loads,
    validate_core,
    validate_with_catalog,
    validate_with_schema_bytes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class CliInputError(ValueError):
    """Raised for stable exit-2 invocation and configuration failures."""


_REPEATABLE_OPTIONS = frozenset(
    {
        "--artifact-binding",
        "--artifact-material",
        "--dataset-entry-binding",
        "--expected-artifact",
        "--expected-head",
        "--external-profile",
        "--head",
        "--input-binding",
        "--key",
        "--profile",
        "--required-profile-binding",
        "--schema-catalog",
        "--subject",
        "--subject-binding",
    }
)


class _MakotoArgumentParser(argparse.ArgumentParser):
    """Reject repeated singleton options before any handler can open input files."""

    def parse_args(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        values = list(sys.argv[1:] if args is None else args)
        counts: dict[str, int] = {}
        for value in values:
            option = value.split("=", 1)[0]
            if not option.startswith("--") or option in _REPEATABLE_OPTIONS:
                continue
            counts[option] = counts.get(option, 0) + 1
            if counts[option] > 1:
                self.error(f"singleton option may be supplied only once: {option}")
        return super().parse_args(values, namespace)

    def error(self, message: str) -> Never:
        raise CliInputError(message)


class _SubjectArgument(argparse.Action):
    """Preserve occurrence order across compact and binding-file subjects."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        del parser
        subjects = list(getattr(namespace, self.dest, None) or [])
        subjects.append((option_string or "", cast(str | Path, values)))
        setattr(namespace, self.dest, subjects)


def _parser() -> argparse.ArgumentParser:
    parser = _MakotoArgumentParser(prog="makoto")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    digest = commands.add_parser("digest")
    digest.add_argument("artifact", type=Path)
    digest.add_argument("--json", action="store_true")
    digest.set_defaults(handler=_cmd_digest)

    key = commands.add_parser("key")
    key_commands = key.add_subparsers(dest="key_command", required=True)
    key_generate = key_commands.add_parser("generate")
    key_generate.add_argument("--private-out", type=Path, required=True)
    key_generate.add_argument("--public-out", type=Path, required=True)
    key_generate.set_defaults(handler=_cmd_key_generate)
    key_inspect = key_commands.add_parser("inspect")
    key_inspect.add_argument("--public", type=Path, required=True)
    key_inspect.add_argument("--json", action="store_true")
    key_inspect.set_defaults(handler=_cmd_key_inspect)

    envelope = commands.add_parser("envelope")
    envelope_commands = envelope.add_subparsers(dest="envelope_command", required=True)
    envelope_inspect = envelope_commands.add_parser("inspect")
    envelope_inspect.add_argument("--envelope", type=Path, required=True)
    envelope_inspect.add_argument("--json", action="store_true")
    envelope_inspect.set_defaults(handler=_cmd_envelope_inspect)
    envelope_cosign = envelope_commands.add_parser("cosign")
    envelope_cosign.add_argument("--envelope", type=Path, required=True)
    envelope_cosign.add_argument("--key", type=Path, required=True)
    envelope_cosign.add_argument("--out", type=Path, required=True)
    envelope_cosign.add_argument("--force", action="store_true")
    envelope_cosign.set_defaults(handler=_cmd_envelope_cosign)

    attest = commands.add_parser("attest")
    attest_commands = attest.add_subparsers(dest="attest_command", required=True)
    origin = attest_commands.add_parser("origin")
    _add_common_attestation_arguments(origin)
    origin.add_argument("--source-kind", required=True)
    origin.add_argument("--source-uri")
    origin.add_argument("--source-metadata", type=Path)
    origin.set_defaults(handler=_cmd_attest_origin)
    transform = attest_commands.add_parser("transform")
    _add_common_attestation_arguments(transform)
    transform.add_argument("--input-binding", type=Path, action="append", required=True)
    transform.add_argument("--operation-type", required=True)
    transform.add_argument("--operation-name")
    transform.add_argument("--operation-metadata", type=Path)
    transform.set_defaults(handler=_cmd_attest_transform)

    handoff = commands.add_parser("handoff")
    handoff_commands = handoff.add_subparsers(dest="handoff_command", required=True)
    handoff_create = handoff_commands.add_parser("create")
    handoff_create.add_argument("--head", type=Path, action="append", required=True)
    handoff_create.add_argument("--attestations", type=Path, required=True)
    handoff_create.add_argument("--artifact-binding", type=Path, action="append", required=True)
    handoff_create.add_argument("--artifact-material", type=Path, action="append", default=[])
    handoff_create.add_argument("--dataset-entry-binding", type=Path, action="append", default=[])
    handoff_create.add_argument(
        "--required-profile-binding", type=Path, action="append", default=[]
    )
    handoff_create.add_argument("--schema-catalog", type=Path, action="append", default=[])
    handoff_create.add_argument("--external-profile", type=Path, action="append", default=[])
    handoff_create.add_argument("--bundle-id")
    handoff_create.add_argument("--recipient")
    handoff_create.add_argument("--nonce")
    handoff_create.add_argument("--issued-at")
    handoff_create.add_argument("--key", type=Path, action="append", required=True)
    handoff_create.add_argument("--out", type=Path, required=True)
    handoff_create.add_argument("--force", action="store_true")
    handoff_create.set_defaults(handler=_cmd_handoff_create)

    verify = commands.add_parser("verify")
    verify_commands = verify.add_subparsers(dest="verify_command", required=True)
    verify_parser = verify_commands.add_parser("bundle")
    verify_parser.add_argument("bundle_directory", type=Path)
    verify_parser.add_argument("--policy", type=Path, required=True)
    verify_parser.add_argument("--schema-catalog", type=Path, action="append", default=[])
    verify_parser.add_argument("--expected-manifest", type=_digest_flag)
    verify_parser.add_argument("--expected-head", type=_digest_flag, action="append", default=[])
    verify_parser.add_argument("--expected-artifact", type=Path, action="append", default=[])
    verify_parser.add_argument("--artifact-material", type=Path, action="append", default=[])
    verify_parser.add_argument("--dataset-entry-binding", type=Path, action="append", default=[])
    verify_parser.add_argument("--expected-recipient")
    verify_parser.add_argument("--expected-nonce")
    verify_parser.add_argument("--evaluation-time")
    verify_parser.add_argument("--temp-parent", type=Path)
    verify_parser.add_argument("--timing", action="store_true")
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(handler=_cmd_verify_bundle)

    schema = commands.add_parser("schema")
    schema_commands = schema.add_subparsers(dest="schema_command", required=True)
    schema_validate = schema_commands.add_parser("validate")
    schema_validate.add_argument("instance", type=Path)
    selection = schema_validate.add_mutually_exclusive_group(required=True)
    selection.add_argument("--profile-reference", type=Path)
    selection.add_argument("--schema")
    schema_validate.add_argument("--schema-digest", type=_digest_flag)
    schema_validate.add_argument("--schema-catalog", type=Path, action="append", default=[])
    schema_validate.add_argument("--verbose", action="store_true")
    schema_validate.set_defaults(handler=_cmd_schema_validate)

    profile = commands.add_parser("profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_create = profile_commands.add_parser("create")
    profile_create.add_argument("--schema-root", type=Path, required=True)
    profile_create.add_argument(
        "--target", choices=("statement", "predicate", "artifact"), required=True
    )
    profile_create.add_argument("--subject-name")
    profile_create.add_argument("--media-type")
    profile_create.add_argument("--critical", type=_boolean, required=True)
    profile_create.add_argument("--schema-catalog", type=Path, action="append", default=[])
    profile_create.add_argument("--out", type=Path, required=True)
    profile_create.add_argument("--force", action="store_true")
    profile_create.set_defaults(handler=_cmd_profile_create)

    policy = commands.add_parser("policy")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    policy_check = policy_commands.add_parser("check")
    policy_check.add_argument("--policy", type=Path, required=True)
    policy_check.add_argument("--json", action="store_true")
    policy_check.set_defaults(handler=_cmd_policy_check)
    return parser


def _add_common_attestation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subject", dest="subject_inputs", action=_SubjectArgument, default=[])
    parser.add_argument(
        "--subject-binding",
        dest="subject_inputs",
        type=Path,
        action=_SubjectArgument,
    )
    parser.add_argument("--profile", type=Path, action="append", default=[])
    parser.add_argument("--schema-catalog", type=Path, action="append", default=[])
    parser.add_argument("--extensions", type=Path)
    parser.add_argument("--event-id")
    parser.add_argument("--occurred-at")
    parser.add_argument("--key", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--force", action="store_true")


def _cmd_digest(args: argparse.Namespace) -> int:
    with args.artifact.open("rb") as stream:
        result = digest_object(sha256_stream(stream))
    _emit(result if args.json else f"sha256:{result['sha256']}", json_output=args.json)
    return 0


def _cmd_key_generate(args: argparse.Namespace) -> int:
    if args.private_out == args.public_out:
        raise CliInputError("private and public outputs must be different")
    key = SigningKey.generate()
    _atomic_write(args.private_out, key.private_pkcs8_pem(), mode=0o600)
    _atomic_write(args.public_out, key.public_spki_pem(), mode=0o644)
    return 0


def _cmd_key_inspect(args: argparse.Namespace) -> int:
    spki = spki_from_pem(args.public.read_bytes())
    value = {"keyid": keyid_from_spki(spki), "type": "ed25519"}
    _emit(value if args.json else value["keyid"], json_output=args.json)
    return 0


def _cmd_envelope_inspect(args: argparse.Namespace) -> int:
    envelope = _strict_object(args.envelope)
    validate_core("envelope", envelope, repository_root=REPOSITORY_ROOT)
    payload = canonical_b64decode(envelope["payload"])
    value = {
        "payloadDigest": digest_object(sha256_bytes(payload)),
        "payloadType": envelope["payloadType"],
        "signatureKeyIds": [item["keyid"] for item in envelope["signatures"]],
    }
    _emit(value if args.json else json.dumps(value, indent=2), json_output=args.json)
    return 0


def _cmd_envelope_cosign(args: argparse.Namespace) -> int:
    if args.envelope.resolve() == args.out.resolve():
        raise CliInputError("cosign input and output must be different files")
    envelope = _strict_object(args.envelope)
    validate_core("envelope", envelope, repository_root=REPOSITORY_ROOT)
    key = _signing_keys(args.key)[0]
    if any(item["keyid"] == key.keyid() for item in envelope["signatures"]):
        raise CliInputError("envelope already contains this key ID")
    payload = canonical_b64decode(envelope["payload"])
    signature = key.sign(pae(envelope["payloadType"], payload))
    envelope["signatures"].append({"keyid": key.keyid(), "sig": canonical_b64encode(signature)})
    envelope["signatures"].sort(key=lambda item: item["keyid"].encode())
    validate_core("envelope", envelope, repository_root=REPOSITORY_ROOT)
    _write_json(args.out, envelope, force=args.force)
    return 0


def _cmd_attest_origin(args: argparse.Namespace) -> int:
    artifacts = _subjects(args.subject_inputs)
    profiles = [_strict_object(path) for path in args.profile]
    metadata = _strict_object(args.source_metadata) if args.source_metadata else {}
    extensions = _strict_object(args.extensions) if args.extensions else None
    attestation = create_origin(
        artifacts=artifacts,
        event_id=args.event_id or f"urn:uuid:{uuid.uuid4()}",
        occurred_at=args.occurred_at or _now_timestamp(),
        source_kind=args.source_kind,
        signing_key=_signing_keys(args.key),
        repository_root=REPOSITORY_ROOT,
        source_uri=args.source_uri,
        source_name=metadata.get("name"),
        source_media_type=metadata.get("mediaType"),
        retrieved_at=metadata.get("retrievedAt"),
        source_version=metadata.get("version"),
        profiles=profiles,
        extensions=extensions,
    )
    _validate_claimed_profiles(attestation.statement, artifacts, profiles, args.schema_catalog)
    _write_json(args.out, attestation.envelope, force=args.force)
    return 0


def _cmd_attest_transform(args: argparse.Namespace) -> int:
    artifacts = _subjects(args.subject_inputs)
    inputs: list[TransformationInput] = []
    for binding_path in args.input_binding:
        binding = _binding_object(
            binding_path,
            required={"name", "path", "predecessor", "subjectName"},
            optional={"entryName", "predecessorMaterial"},
        )
        entry_name = binding.get("entryName")
        predecessor_material = binding.get("predecessorMaterial")
        if (entry_name is None) != (predecessor_material is None):
            raise CliInputError("input binding requires entryName and predecessorMaterial together")
        base = binding_path.parent
        predecessor = load_attestation(
            base / binding["predecessor"], repository_root=REPOSITORY_ROOT
        )
        artifact = Artifact.from_path(base / binding["path"], name=binding["name"])
        if entry_name is not None and predecessor_material is not None:
            manifest = Artifact.from_path(
                base / predecessor_material,
                name=binding["subjectName"],
            )
            try:
                predecessor_subject = predecessor.subject(binding["subjectName"])
            except ValueError as error:
                raise CliInputError(str(error)) from error
            if predecessor_subject["digest"] != manifest.digest():
                raise CliInputError(
                    "predecessor material bytes do not match the selected predecessor subject"
                )
            expected_profile = core_dataset_manifest_profile_reference(
                binding["subjectName"], repository_root=REPOSITORY_ROOT
            )
            if expected_profile not in predecessor.statement["predicate"].get("profiles", []):
                raise CliInputError(
                    "partition input predecessor lacks the exact mandatory dataset profile"
                )
            try:
                manifest_index = parse_dataset_manifest(
                    manifest.data, repository_root=REPOSITORY_ROOT
                )
            except DatasetManifestError as error:
                raise CliInputError(f"predecessor dataset manifest is invalid: {error}") from error
            member = manifest_index.member(entry_name)
            if member is None:
                raise CliInputError("partition input is not a member of the predecessor manifest")
            if member.digest != artifact.digest()["sha256"]:
                raise CliInputError(
                    "partition input bytes do not match the predecessor manifest member"
                )
            if member.size is not None and member.size != len(artifact.data):
                raise CliInputError(
                    "partition input byte count does not match the predecessor manifest member"
                )
        inputs.append(
            TransformationInput(
                binding["name"],
                artifact,
                predecessor,
                binding["subjectName"],
                entry_name,
            )
        )
    profiles = [_strict_object(path) for path in args.profile]
    metadata = _strict_object(args.operation_metadata) if args.operation_metadata else {}
    extensions = _strict_object(args.extensions) if args.extensions else None
    attestation = create_transform(
        artifacts=artifacts,
        inputs=inputs,
        event_id=args.event_id or f"urn:uuid:{uuid.uuid4()}",
        occurred_at=args.occurred_at or _now_timestamp(),
        operation_type=args.operation_type,
        operation_name=args.operation_name,
        signing_key=_signing_keys(args.key),
        repository_root=REPOSITORY_ROOT,
        tool=metadata.get("tool"),
        parameters_digest=metadata.get("parametersDigest"),
        profiles=profiles,
        extensions=extensions,
    )
    _validate_claimed_profiles(attestation.statement, artifacts, profiles, args.schema_catalog)
    _write_json(args.out, attestation.envelope, force=args.force)
    return 0


def _cmd_handoff_create(args: argparse.Namespace) -> int:
    selected_paths = sorted(args.attestations.iterdir(), key=lambda path: path.name.encode())
    selected_paths = [path for path in selected_paths if path.name.endswith(".dsse.json")]
    attestations = [
        load_attestation(path, repository_root=REPOSITORY_ROOT) for path in selected_paths
    ]
    by_path = {
        path.resolve(): attestation
        for path, attestation in zip(selected_paths, attestations, strict=True)
    }
    heads: list[Attestation] = []
    for path in args.head:
        resolved = path.resolve()
        if resolved not in by_path:
            raise CliInputError(f"head is not selected by --attestations: {path}")
        heads.append(by_path[resolved])
    final_artifacts: list[tuple[Artifact, Attestation]] = []
    for binding_path in args.artifact_binding:
        binding = _binding_object(
            binding_path,
            required={"head", "subjectName", "path"},
            optional={"mediaType"},
        )
        head_path = (binding_path.parent / binding["head"]).resolve()
        head = by_path.get(head_path)
        if head is None:
            raise CliInputError(f"artifact binding head is not selected: {head_path}")
        artifact = Artifact.from_path(
            binding_path.parent / binding["path"],
            name=binding["subjectName"],
            media_type=binding.get("mediaType"),
        )
        final_artifacts.append((artifact, head))
    historical_artifacts: list[tuple[Artifact, Attestation]] = []
    dataset_manifests: list[tuple[Artifact, Attestation]] = []
    for binding_path in args.artifact_material:
        binding = _binding_object(
            binding_path,
            required={"statement", "subjectName", "path"},
        )
        statement_path = (binding_path.parent / binding["statement"]).resolve()
        statement = by_path.get(statement_path)
        if statement is None:
            raise CliInputError(f"artifact material statement is not selected: {statement_path}")
        artifact = Artifact.from_path(
            binding_path.parent / binding["path"], name=binding["subjectName"]
        )
        dataset_profile = core_dataset_manifest_profile_reference(
            artifact.name, repository_root=REPOSITORY_ROOT
        )
        if dataset_profile in statement.statement["predicate"].get("profiles", []):
            dataset_manifests.append((artifact, statement))
        else:
            historical_artifacts.append((artifact, statement))
    dataset_entries: list[tuple[Artifact, Attestation, str, str]] = []
    for binding_path in args.dataset_entry_binding:
        binding = _binding_object(
            binding_path,
            required={"manifestStatement", "manifestSubjectName", "entryName", "path"},
        )
        statement_path = (binding_path.parent / binding["manifestStatement"]).resolve()
        statement = by_path.get(statement_path)
        if statement is None:
            raise CliInputError(
                f"dataset entry manifest statement is not selected: {statement_path}"
            )
        artifact = Artifact.from_path(
            binding_path.parent / binding["path"], name=binding["entryName"]
        )
        dataset_entries.append(
            (artifact, statement, binding["manifestSubjectName"], binding["entryName"])
        )
    required_profiles = [_strict_object(path) for path in args.required_profile_binding]
    write_handoff_bundle(
        attestations=attestations,
        heads=heads,
        final_artifacts=final_artifacts,
        bundle_id=args.bundle_id or f"urn:uuid:{uuid.uuid4()}",
        issued_at=args.issued_at or _now_timestamp(),
        signing_key=_signing_keys(args.key),
        output=args.out,
        repository_root=REPOSITORY_ROOT,
        recipient=args.recipient,
        nonce=args.nonce,
        required_profiles=required_profiles,
        historical_artifacts=historical_artifacts,
        dataset_manifests=dataset_manifests,
        dataset_entries=dataset_entries,
        schema_catalog_paths=args.schema_catalog,
        external_profiles=[_strict_object(path) for path in args.external_profile],
        force=args.force,
    )
    return 0


def _cmd_verify_bundle(args: argparse.Namespace) -> int:
    if args.temp_parent is not None and (
        args.temp_parent.is_symlink() or not args.temp_parent.is_dir()
    ):
        raise CliInputError("--temp-parent must be a real directory")
    expected_artifacts = tuple(_consumer_expected_artifact(path) for path in args.expected_artifact)
    artifact_materials = tuple(_consumer_artifact_material(path) for path in args.artifact_material)
    dataset_entry_bindings = tuple(
        _consumer_dataset_entry(path) for path in args.dataset_entry_binding
    )
    timing = VerificationTiming() if args.timing else None
    request = VerificationRequest(
        bundle_root=args.bundle_directory,
        policy_path=args.policy,
        repository_root=REPOSITORY_ROOT,
        schema_catalogs=tuple(args.schema_catalog),
        expected_manifest=args.expected_manifest,
        expected_heads=tuple(args.expected_head),
        expected_artifacts=expected_artifacts,
        expected_recipient=args.expected_recipient,
        expected_nonce=args.expected_nonce,
        evaluation_time=args.evaluation_time,
        artifact_materials=artifact_materials,
        dataset_entry_bindings=dataset_entry_bindings,
        consumer_metadata_paths=(
            *args.expected_artifact,
            *args.artifact_material,
            *args.dataset_entry_binding,
        ),
        temp_parent=args.temp_parent,
        timing=timing,
    )
    report = verify_bundle(request)
    if args.json:
        sys.stdout.buffer.write(report_bytes(report))
    else:
        _print_human_report(report)
    if timing is not None:
        sys.stderr.buffer.write(canonical_json(timing.as_dict()) + b"\n")
    return 0 if report["decision"] == "allow" else 1


def _cmd_schema_validate(args: argparse.Namespace) -> int:
    if args.profile_reference:
        if args.schema_digest is not None:
            raise CliInputError("--schema-digest cannot be used with --profile-reference")
        reference = _strict_object(args.profile_reference)
        validate_core("profile-reference", reference, repository_root=REPOSITORY_ROOT)
        try:
            instance_bytes = args.instance.read_bytes()
        except OSError as error:
            return _invalid_schema_instance(args, str(error))
        if reference.get("target") == "artifact" and reference.get("mediaType") == (
            "application/x-ndjson"
        ):
            instances_or_error = _strict_ndjson_instances(instance_bytes)
            if isinstance(instances_or_error, str):
                return _invalid_schema_instance(args, instances_or_error)
            for line_number, instance_index, instance in instances_or_error:
                result = validate_with_catalog(
                    instance,
                    reference,
                    catalog_paths=args.schema_catalog,
                    repository_root=REPOSITORY_ROOT,
                )
                if not result.valid:
                    detail = f"line {line_number}, instance {instance_index}: " + "; ".join(
                        result.errors
                    )
                    return _invalid_schema_instance(args, detail)
        else:
            try:
                instance = strict_json_loads(instance_bytes)
            except StrictJsonError as error:
                return _invalid_schema_instance(args, str(error))
            result = validate_with_catalog(
                instance,
                reference,
                catalog_paths=args.schema_catalog,
                repository_root=REPOSITORY_ROOT,
            )
            if not result.valid:
                return _invalid_schema_instance(args, "; ".join(result.errors))
    else:
        try:
            instance = strict_json_loads(args.instance.read_bytes())
        except (StrictJsonError, OSError) as error:
            return _invalid_schema_instance(args, str(error))
        schema_argument = str(args.schema)
        legacy_name = schema_argument.removesuffix(".schema.json")
        legacy_path = REPOSITORY_ROOT / "schemas" / "v0.2" / f"{legacy_name}.schema.json"
        if legacy_path.is_file() and "/" not in schema_argument and "\\" not in schema_argument:
            if args.schema_digest is not None:
                actual_digest = sha256_bytes(legacy_path.read_bytes())
                if actual_digest != args.schema_digest["sha256"]:
                    raise CliInputError("schema digest does not match the selected schema")
            try:
                validate_core(legacy_name, instance, repository_root=REPOSITORY_ROOT)
            except CoreValidationError as error:
                return _invalid_schema_instance(args, str(error))
        else:
            schema_bytes, expected_identifier = _resolve_standalone_schema(
                schema_argument,
                schema_digest=(
                    args.schema_digest["sha256"] if args.schema_digest is not None else None
                ),
                catalog_paths=args.schema_catalog,
            )
            result = validate_with_schema_bytes(
                instance,
                schema_bytes,
                expected_identifier=expected_identifier,
                expected_digest=(
                    args.schema_digest["sha256"] if args.schema_digest is not None else None
                ),
                repository_root=REPOSITORY_ROOT,
            )
            if not result.valid:
                return _invalid_schema_instance(args, "; ".join(result.errors))
    print("valid")
    return 0


def _invalid_schema_instance(args: argparse.Namespace, detail: str) -> int:
    print("invalid")
    if args.verbose:
        print(detail, file=sys.stderr)
    return 1


def _strict_ndjson_instances(data: bytes) -> list[tuple[int, int, object]] | str:
    instances: list[tuple[int, int, object]] = []
    segments = data.split(b"\n")
    for line_number, raw_segment in enumerate(segments, start=1):
        if line_number == len(segments) and not raw_segment and data.endswith(b"\n"):
            continue
        segment = raw_segment[:-1] if raw_segment.endswith(b"\r") else raw_segment
        if not segment or all(byte in (0x20, 0x09) for byte in segment):
            continue
        instance_index = len(instances)
        try:
            instance = strict_json_loads(segment)
        except StrictJsonError as error:
            return f"line {line_number}, instance {instance_index}: {error}"
        instances.append((line_number, instance_index, instance))
    if not instances:
        return "NDJSON input contains zero instances"
    return instances


def _resolve_standalone_schema(
    argument: str,
    *,
    schema_digest: str | None,
    catalog_paths: list[Path],
) -> tuple[bytes, str | None]:
    is_windows_drive = (
        len(argument) >= 3
        and argument[0].isalpha()
        and argument[1] == ":"
        and argument[2] in ("/", "\\")
    )
    is_local = argument.startswith(("./", "../", "/", "\\\\")) or is_windows_drive
    if is_local:
        return Path(argument).read_bytes(), None

    parsed = urlsplit(argument)
    if not parsed.scheme or parsed.fragment:
        raise CliInputError("--schema must be an absolute fragmentless URI or explicit path")
    if schema_digest is None:
        raise CliInputError("URI --schema requires --schema-digest")
    resources = load_catalog_resources(catalog_paths, repository_root=REPOSITORY_ROOT)
    resource = resources.get((argument, schema_digest))
    if resource is None:
        raise CliInputError("URI schema is unavailable at the selected digest")
    return resource.exact_bytes, argument


def _cmd_profile_create(args: argparse.Namespace) -> int:
    reference = create_profile_reference(
        args.schema_root,
        target=args.target,
        critical=args.critical,
        catalog_paths=args.schema_catalog,
        subject_name=args.subject_name,
        media_type=args.media_type,
        repository_root=REPOSITORY_ROOT,
    )
    _write_json(args.out, reference, force=args.force)
    return 0


def _cmd_policy_check(args: argparse.Namespace) -> int:
    policy = TrustPolicy.from_path(args.policy, repository_root=REPOSITORY_ROOT)
    if args.json:
        _emit({"policyDigest": policy.digest(), "valid": True, "warnings": []}, json_output=True)
    else:
        print("valid")
    return 0


def _subjects(values: list[tuple[str, str | Path]]) -> list[Artifact]:
    if not values:
        raise CliInputError("at least one --subject or --subject-binding is required")
    artifacts: list[Artifact] = []
    names: set[str] = set()
    for option, value in values:
        if option == "--subject-binding":
            if not isinstance(value, Path):
                raise CliInputError("--subject-binding must name a file")
            binding = _binding_object(value, required={"name", "path"})
            name = binding["name"]
            artifact_path = value.parent / binding["path"]
        else:
            if not isinstance(value, str) or "=" not in value:
                raise CliInputError("--subject must use name=path")
            name, raw_path = value.split("=", 1)
            artifact_path = Path(raw_path)
        if not name or name in names:
            raise CliInputError("subject names must be nonempty and unique")
        names.add(name)
        artifacts.append(Artifact.from_path(artifact_path, name=name))
    return artifacts


def _validate_claimed_profiles(
    statement: dict[str, Any],
    artifacts: list[Artifact],
    profiles: list[dict[str, Any]],
    catalogs: list[Path],
) -> None:
    for profile in profiles:
        target = profile["target"]
        if target == "statement":
            instance: object = statement
        elif target == "predicate":
            instance = statement["predicate"]
        else:
            matches = [
                artifact for artifact in artifacts if artifact.name == profile["subjectName"]
            ]
            if len(matches) != 1:
                raise CliInputError("artifact profile names no unique subject")
            media_type = profile["mediaType"]
            if media_type != "application/json" and not (
                media_type.startswith("application/") and media_type.endswith("+json")
            ):
                raise CliInputError(
                    "producer supports only application/json and application/*+json "
                    f"profiles, got {media_type}"
                )
            instance = strict_json_loads(matches[0].data)
        result = validate_with_catalog(
            instance,
            profile,
            catalog_paths=catalogs,
            repository_root=REPOSITORY_ROOT,
        )
        if not result.valid:
            raise CliInputError("profile claim is false: " + "; ".join(result.errors))


def _strict_object(path: Path) -> dict[str, Any]:
    value = strict_json_loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CliInputError(f"{path} must contain one JSON object")
    return cast(dict[str, Any], value)


def _binding_object(
    path: Path,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    value = _strict_object(path)
    allowed = required | (optional or set())
    actual = set(value)
    if not required.issubset(actual) or not actual.issubset(allowed):
        missing = sorted(required - actual)
        extra = sorted(actual - allowed)
        raise CliInputError(f"invalid binding shape {path}: missing={missing!r} extra={extra!r}")
    if any(not isinstance(value[key], str) or not value[key] for key in allowed if key in value):
        raise CliInputError(f"binding strings must be nonempty: {path}")
    return value


def _digest_object_member(value: object, *, field: str, path: Path) -> str:
    if not isinstance(value, dict) or set(value) != {"sha256"}:
        raise CliInputError(f"{field} in {path} must be an exact sha256 digest object")
    digest = value.get("sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise CliInputError(f"{field} in {path} must contain 64 lowercase hex characters")
    return digest


def _consumer_artifact_material(path: Path) -> ArtifactMaterialSource:
    value = _strict_object(path)
    required = {"statementDigest", "subjectName", "digest", "path"}
    if set(value) != required:
        raise CliInputError(f"consumer artifact-material binding has the wrong shape: {path}")
    if not isinstance(value["subjectName"], str) or not value["subjectName"]:
        raise CliInputError(f"consumer artifact subjectName must be nonempty: {path}")
    if not isinstance(value["path"], str) or not value["path"]:
        raise CliInputError(f"consumer artifact path must be nonempty: {path}")
    material_path = path.parent / value["path"]
    if material_path.is_symlink() or not material_path.is_file():
        raise CliInputError(f"consumer artifact material is not a real file: {material_path}")
    return ArtifactMaterialSource(
        statement_digest=_digest_object_member(
            value["statementDigest"], field="statementDigest", path=path
        ),
        subject_name=value["subjectName"],
        digest=_digest_object_member(value["digest"], field="digest", path=path),
        path=material_path,
    )


def _consumer_expected_artifact(path: Path) -> dict[str, Any]:
    value = _strict_object(path)
    if set(value) != {"head", "subjectName", "digest"}:
        raise CliInputError(f"expected-artifact binding has the wrong shape: {path}")
    if not isinstance(value["subjectName"], str) or not value["subjectName"]:
        raise CliInputError(f"expected-artifact subjectName must be nonempty: {path}")
    return {
        "head": {"sha256": _digest_object_member(value["head"], field="head", path=path)},
        "subjectName": value["subjectName"],
        "digest": {"sha256": _digest_object_member(value["digest"], field="digest", path=path)},
    }


def _consumer_dataset_entry(path: Path) -> DatasetEntrySource:
    value = _strict_object(path)
    required = {
        "manifestStatementDigest",
        "manifestSubjectName",
        "entryName",
        "digest",
        "path",
    }
    if set(value) != required:
        raise CliInputError(f"consumer dataset-entry binding has the wrong shape: {path}")
    for field in ("manifestSubjectName", "entryName", "path"):
        if not isinstance(value[field], str) or not value[field]:
            raise CliInputError(f"consumer dataset-entry {field} must be nonempty: {path}")
    material_path = path.parent / value["path"]
    if material_path.is_symlink() or not material_path.is_file():
        raise CliInputError(f"consumer dataset-entry material is not a real file: {material_path}")
    return DatasetEntrySource(
        manifest_statement_digest=_digest_object_member(
            value["manifestStatementDigest"], field="manifestStatementDigest", path=path
        ),
        manifest_subject_name=value["manifestSubjectName"],
        entry_name=value["entryName"],
        digest=_digest_object_member(value["digest"], field="digest", path=path),
        path=material_path,
    )


def _signing_keys(paths: list[Path] | Path) -> list[SigningKey]:
    values = [paths] if isinstance(paths, Path) else paths
    if not values:
        raise CliInputError("at least one signing key is required")
    keys = [SigningKey.from_pem(path.read_bytes()) for path in values]
    key_ids = [key.keyid() for key in keys]
    if len(key_ids) != len(set(key_ids)):
        raise CliInputError("signing key IDs must be unique")
    return keys


def _digest_flag(value: str) -> dict[str, str]:
    prefix = "sha256:"
    digest = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise argparse.ArgumentTypeError("digest must be sha256:<64 lowercase hex>")
    return digest_object(digest)


def _boolean(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("boolean must be true or false")


def _write_json(path: Path, value: object, *, force: bool) -> None:
    if path.exists() and not force:
        raise CliInputError(f"output already exists: {path}")
    _atomic_write(path, canonical_json(value) + b"\n", mode=0o644)


def _atomic_write(path: Path, data: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _emit(value: object, *, json_output: bool) -> None:
    if json_output:
        sys.stdout.buffer.write(canonical_json(value) + b"\n")
    else:
        print(value)


def _print_human_report(report: dict[str, Any]) -> None:
    for check in report["checks"]:
        print(f"{check['status'].upper():11} {check['id']}")
    print(f"{report['decision'].upper():11} decision")
    if report["manifestDigest"]:
        print(f"manifest sha256:{report['manifestDigest']['sha256']}")
    for error in report["errors"]:
        print(f"{error['code']}: {error['message']}")


def _now_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    try:
        parser = _parser()
        args = parser.parse_args()
        return int(args.handler(args))
    except (
        CliInputError,
        BundleError,
        DsseError,
        ProfileResolutionError,
        FileNotFoundError,
        ValueError,
    ) as error:
        _emit_tool_error("invalid-input", error)
        return 2
    except Exception as error:
        _emit_tool_error("internal", error)
        return 3


def _emit_tool_error(error_class: str, error: BaseException) -> None:
    message = str(error).encode("ascii", errors="backslashreplace").decode("ascii")
    sys.stderr.buffer.write(canonical_json({"errorClass": error_class, "message": message}) + b"\n")


if __name__ == "__main__":
    raise SystemExit(main())
