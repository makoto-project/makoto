from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from makoto.schema import strict_json_loads

ROOT = Path(__file__).resolve().parents[1]


def _object_variants(schema: dict[str, Any]) -> list[dict[str, Any]]:
    variants = []
    if schema.get("type") == "object":
        variants.append(schema)
    for keyword in ("oneOf", "anyOf", "allOf"):
        for child in schema.get(keyword, []):
            if isinstance(child, dict):
                variants.extend(_object_variants(child))
    return variants


@pytest.mark.parametrize("version", ["0.2", "0.3"])
def test_diagnostic_map_closes_codes_owners_contexts_and_multiplicity(version: str) -> None:
    schema_path = ROOT / "schemas" / f"v{version}" / "verification-report.schema.json"
    map_path = ROOT / "testdata" / f"v{version}" / "diagnostic-map.json"
    report_schema = strict_json_loads(schema_path.read_bytes())
    diagnostic_map = strict_json_loads(map_path.read_bytes())
    assert isinstance(report_schema, dict)
    assert isinstance(diagnostic_map, dict)
    Draft202012Validator.check_schema(report_schema)

    rows = diagnostic_map["rows"]
    assert diagnostic_map["version"] == version
    assert rows
    assert len({row["triggerId"] for row in rows}) == len(rows)
    assert len({(row["code"], row["step"], row["triggerId"]) for row in rows}) == len(rows)

    definitions = report_schema["$defs"]
    expected_codes = set(definitions["errorCode"]["enum"]) | set(definitions["warningCode"]["enum"])
    assert {row["code"] for row in rows} == expected_codes

    expected_tuples: set[tuple[str, int, str, str]] = set()
    for diagnostic_class in ("error", "warning"):
        for branch in definitions[diagnostic_class]["oneOf"]:
            properties = branch["properties"]
            expected_tuples.add(
                (
                    properties["code"]["const"],
                    properties["step"]["const"],
                    properties["causedByCheck"]["const"],
                    diagnostic_class,
                )
            )
    assert {
        (row["code"], row["step"], row["owner"], row["class"]) for row in rows
    } == expected_tuples

    for row in rows:
        assert row["triggerId"].isascii()
        assert row["multiplicityKey"]
        assert len(row["multiplicityKey"]) == len(set(row["multiplicityKey"]))
        fragment = row["contextSchema"].split("#/$defs/", 1)[1]
        context_schema = definitions[fragment]
        variants = _object_variants(context_schema)
        assert variants
        assert any(
            set(row["multiplicityKey"]).issubset(set(variant.get("required", [])))
            and set(row["multiplicityKey"]).issubset(set(variant.get("properties", {})))
            for variant in variants
        ), row["triggerId"]
        assert row["prerequisiteBehavior"].keys() == {
            "blockedChecks",
            "emitsWhenBlocked",
        }
        assert row["continuation"]["scope"] in {
            "continue",
            "skip-record",
            "skip-dependent-checks",
            "stop-evidence",
        }
        assert row["continuation"]["cache"] in {
            "retain",
            "discard",
            "not-applicable",
        }
