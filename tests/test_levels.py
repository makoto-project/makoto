from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from makoto import cli
from makoto.levels import assurance_level
from makoto.schema import strict_json_loads

REPORTS = Path(__file__).resolve().parents[1] / "demos/v0.2-end-to-end/generated/reports"


def _report(name: str) -> dict[str, Any]:
    value = strict_json_loads((REPORTS / f"{name}.json").read_bytes())
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize(
    ("name", "level"),
    [
        ("positive", "L3"),
        ("mutated-final-data", "L1"),
        ("removed-predecessor", "L1"),
        ("private-schema-violation", "L1"),
        ("unauthorized-signer", "L1"),
        ("edited-signed-metadata", None),
        ("rewired-step", None),
        ("statement-digest-mismatch", None),
    ],
)
def test_demo_reports_reach_expected_level(name: str, level: str | None) -> None:
    assert assurance_level(_report(name))["level"] == level


def test_waived_freshness_allows_but_stops_at_l2() -> None:
    report = _report("positive")
    for check in report["checks"]:
        if check["id"] == "freshness-anchors":
            check["status"] = "not_checked"

    result = assurance_level(report)

    assert result["level"] == "L2"
    assert result["levels"][2]["unmetChecks"] == [
        {"id": "freshness-anchors", "status": "not_checked"}
    ]


def test_optional_checks_may_be_not_checked_for_l2() -> None:
    report = _report("positive")
    for check in report["checks"]:
        if check["id"] in {"metadata-profiles", "graph-dependency-artifacts", "artifact-profiles"}:
            check["status"] = "not_checked"

    assert assurance_level(report)["level"] == "L3"


def test_level_never_skips_an_unmet_lower_level() -> None:
    report = copy.deepcopy(_report("positive"))
    for check in report["checks"]:
        if check["id"] == "signatures":
            check["status"] = "fail"

    result = assurance_level(report)

    assert result["level"] is None
    assert [entry["satisfied"] for entry in result["levels"]] == [False, False, False]


def _run(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> int:
    monkeypatch.setattr(cli.sys, "argv", ["makoto", *arguments])
    return cli.main()


def test_report_level_cli_json_and_required_level(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(REPORTS / "mutated-final-data.json")

    assert _run(monkeypatch, "report", "level", path, "--require", "L1", "--json") == 0
    result = strict_json_loads(capsys.readouterr().out.encode())
    assert isinstance(result, dict)
    assert (result["level"], result["required"], result["meetsRequired"]) == ("L1", "L1", True)

    assert _run(monkeypatch, "report", "level", path, "--require", "L2") == 1
    output = capsys.readouterr().out
    assert "FAIL        L2 Provenance is authorized and complete: artifact-bytes fail" in output
    assert output.endswith("LEVEL       L1\nREQUIRED    L2 not met\n")


def test_report_level_rejects_non_report_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(b'{"decision":"allow"}\n')

    assert _run(monkeypatch, "report", "level", str(path)) == 2
    assert strict_json_loads(capsys.readouterr().err.encode())["errorClass"] == "invalid-input"  # type: ignore[index]
