from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from makoto import cli
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.schema import create_profile_reference, strict_json_loads


def _run(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> int:
    monkeypatch.setattr(cli.sys, "argv", ["makoto", *arguments])
    return cli.main()


def test_singleton_option_duplicate_is_rejected_before_input_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "must-not-open.bin"

    assert _run(monkeypatch, "digest", str(missing), "--json", "--json") == 2

    output = capsys.readouterr()
    assert output.out == ""
    assert strict_json_loads(output.err.encode()) == {
        "errorClass": "invalid-input",
        "message": "singleton option may be supplied only once: --json",
    }


@pytest.mark.parametrize("raw", [b"{}\n", b"{\n", b'[{"not":"a statement"}]\n'])
def test_schema_validate_invalid_instance_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
) -> None:
    instance = tmp_path / "instance.json"
    instance.write_bytes(raw)

    assert _run(monkeypatch, "schema", "validate", str(instance), "--schema", "statement") == 1

    output = capsys.readouterr()
    assert output.out == "invalid\n"
    assert output.err == ""


def test_schema_validate_digest_pin_mismatch_is_invalid_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    instance = tmp_path / "instance.json"
    instance.write_bytes(b"{}\n")

    assert (
        _run(
            monkeypatch,
            "schema",
            "validate",
            str(instance),
            "--schema",
            "statement",
            "--schema-digest",
            f"sha256:{'0' * 64}",
        )
        == 2
    )

    output = capsys.readouterr()
    assert output.out == ""
    assert strict_json_loads(output.err.encode())["errorClass"] == "invalid-input"


def test_schema_validate_matching_digest_pin_reaches_instance_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    instance = tmp_path / "instance.json"
    instance.write_bytes(b"{}\n")
    schema_path = cli.REPOSITORY_ROOT / "schemas" / "v0.2" / "statement.schema.json"

    assert (
        _run(
            monkeypatch,
            "schema",
            "validate",
            str(instance),
            "--schema",
            "statement",
            "--schema-digest",
            f"sha256:{sha256_bytes(schema_path.read_bytes())}",
        )
        == 1
    )
    assert capsys.readouterr().out == "invalid\n"


def _standalone_profile_schema(tmp_path: Path) -> tuple[Path, Path, str]:
    identifier = "https://schemas.example.test/makoto/public-record-v1.json"
    schema_path = tmp_path / "public-record.schema.json"
    schema_bytes = (
        canonical_json(
            {
                "$schema": "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json",
                "$id": identifier,
                "type": "object",
                "required": ["classification"],
                "properties": {"classification": {"const": "public"}},
                "additionalProperties": False,
            }
        )
        + b"\n"
    )
    schema_path.write_bytes(schema_bytes)
    digest = sha256_bytes(schema_bytes)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(
        canonical_json(
            {
                "version": "0.2",
                "resources": [
                    {
                        "id": identifier,
                        "digest": {"sha256": digest},
                        "path": schema_path.name,
                    }
                ],
            }
        )
        + b"\n"
    )
    return schema_path, catalog_path, identifier


def test_schema_validate_supports_explicit_local_profile_dialect_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema_path, _catalog_path, _identifier = _standalone_profile_schema(tmp_path)
    instance = tmp_path / "instance.json"
    instance.write_bytes(b'{"classification":"public"}\n')

    assert (
        _run(
            monkeypatch,
            "schema",
            "validate",
            str(instance),
            "--schema",
            str(schema_path),
        )
        == 0
    )
    assert capsys.readouterr().out == "valid\n"


def test_schema_validate_supports_digest_pinned_catalog_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema_path, catalog_path, identifier = _standalone_profile_schema(tmp_path)
    instance = tmp_path / "instance.json"
    instance.write_bytes(b'{"classification":"restricted"}\n')

    assert (
        _run(
            monkeypatch,
            "schema",
            "validate",
            str(instance),
            "--schema",
            identifier,
            "--schema-digest",
            f"sha256:{sha256_bytes(schema_path.read_bytes())}",
            "--schema-catalog",
            str(catalog_path),
        )
        == 1
    )
    assert capsys.readouterr().out == "invalid\n"


def test_schema_validate_profile_reference_supports_ndjson(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema_path, catalog_path, _identifier = _standalone_profile_schema(tmp_path)
    reference = create_profile_reference(
        schema_path,
        target="artifact",
        critical=True,
        subject_name="records.ndjson",
        media_type="application/x-ndjson",
        catalog_paths=[catalog_path],
        repository_root=cli.REPOSITORY_ROOT,
    )
    reference_path = tmp_path / "profile-reference.json"
    reference_path.write_bytes(canonical_json(reference) + b"\n")
    instance = tmp_path / "records.ndjson"
    instance.write_bytes(b'  \r\n{"classification":"public"}\r\n\t\n{"classification":"public"}')

    assert (
        _run(
            monkeypatch,
            "schema",
            "validate",
            str(instance),
            "--profile-reference",
            str(reference_path),
            "--schema-catalog",
            str(catalog_path),
        )
        == 0
    )
    assert capsys.readouterr().out == "valid\n"


def test_schema_validate_profile_reference_rejects_zero_instance_ndjson(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    schema_path, catalog_path, _identifier = _standalone_profile_schema(tmp_path)
    reference = create_profile_reference(
        schema_path,
        target="artifact",
        critical=True,
        subject_name="records.ndjson",
        media_type="application/x-ndjson",
        catalog_paths=[catalog_path],
        repository_root=cli.REPOSITORY_ROOT,
    )
    reference_path = tmp_path / "profile-reference.json"
    reference_path.write_bytes(canonical_json(reference) + b"\n")
    instance = tmp_path / "records.ndjson"
    instance.write_bytes(b" \r\n\t\n")

    assert (
        _run(
            monkeypatch,
            "schema",
            "validate",
            str(instance),
            "--profile-reference",
            str(reference_path),
            "--schema-catalog",
            str(catalog_path),
        )
        == 1
    )
    assert capsys.readouterr().out == "invalid\n"


def test_unexpected_handler_failure_uses_exit_three_jcs_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")

    def fail(_args: object) -> int:
        raise RuntimeError("unexpected tool failure")

    monkeypatch.setattr(cli, "_cmd_digest", fail)

    assert _run(monkeypatch, "digest", str(artifact)) == 3
    output = capsys.readouterr()
    assert output.out == ""
    assert strict_json_loads(output.err.encode()) == {
        "errorClass": "internal",
        "message": "unexpected tool failure",
    }


def test_verify_timing_emits_one_jcs_object_after_completed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report: dict[str, Any] = {
        "decision": "allow",
        "checks": [{"id": "decision", "status": "pass"}],
        "manifestDigest": None,
        "errors": [],
    }
    monkeypatch.setattr(cli, "verify_bundle", lambda _request: report)

    assert (
        _run(
            monkeypatch,
            "verify",
            "bundle",
            str(tmp_path / "bundle"),
            "--policy",
            str(tmp_path / "policy.json"),
            "--timing",
        )
        == 0
    )

    output = capsys.readouterr()
    assert output.out.endswith("ALLOW       decision\n")
    timing = strict_json_loads(output.err.encode())
    assert set(timing) == {"steps", "totalNanoseconds"}
    assert set(timing["steps"]) == {str(step) for step in range(1, 15)}
    assert timing["totalNanoseconds"] >= 0
    assert canonical_json(timing) + b"\n" == output.err.encode()
