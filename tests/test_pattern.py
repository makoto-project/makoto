from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from makoto.canonical import canonical_json
from makoto.pattern import PatternError, PatternLimitError, compile_pattern
from makoto.schema import create_profile_reference, validate_with_catalog

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("pattern", "accepted", "rejected"),
    [
        ("^public$", "public", "not-public"),
        ("a", "cat", "xyz"),
        ("[a.]", ".", "+"),
        ("[a+]", "+", "."),
        ("[{]", "{", "}"),
        ("[a\\-]", "-", "+"),
        ("[a-a]", "a", "b"),
        ("a|^b", "b", "c"),
        ("^$", "", "x"),
        ("(ab)+", "zzababyy", "ac"),
        ("[^a]", "\x00", "a"),
        (".", "🙂", "\n"),
    ],
)
def test_bounded_pattern_search(pattern: str, accepted: str, rejected: str) -> None:
    compiled = compile_pattern(pattern)
    assert compiled.search(accepted)
    assert not compiled.search(rejected)


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "a|",
        "()",
        "[]",
        "[a-]",
        "[-a]",
        "[a-b-c]",
        "[а-я]",
        "(a*)+",
        "a++",
        "a^b",
        "a(^b)",
        "$+",
        "\\w",
        "\\-",
        "a{01}",
        "a{2,1}",
        "a{1001}",
        "\t",
    ],
)
def test_bounded_pattern_rejects_unsupported_syntax(pattern: str) -> None:
    with pytest.raises(PatternError):
        compile_pattern(pattern)


def test_bounded_pattern_state_counts_and_limits() -> None:
    assert compile_pattern("a{0}").state_count == 1
    assert compile_pattern("a{0,0}").state_count == 1
    assert compile_pattern("a{0,}").state_count == 3
    assert compile_pattern("a+").state_count == 3
    assert compile_pattern("a{1,}").state_count == 4
    assert compile_pattern("a{0}").search("anything")
    assert compile_pattern("a{0,0}").search("anything")
    assert compile_pattern("a{0,}").search("anything")
    assert compile_pattern("^a{0}$").search("")
    assert not compile_pattern("^a{0}$").search("x")
    assert compile_pattern("(" + "a" * 131 + "){1000}" + "b" * 70).state_count == 131_071
    assert compile_pattern("(" + "a" * 131 + "){1000}" + "b" * 71).state_count == 131_072
    with pytest.raises(PatternLimitError, match="131073 states"):
        compile_pattern("(" + "a" * 131 + "){1000}" + "b" * 72)


def test_profile_evaluation_enforces_makoto_pattern(tmp_path: Path) -> None:
    schema = {
        "$schema": "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json",
        "$id": "https://schemas.example.test/classification-v1.json",
        "type": "string",
        "makotoPattern": "^public$",
    }
    schema_bytes = canonical_json(schema) + b"\n"
    schema_path = tmp_path / "classification.schema.json"
    schema_path.write_bytes(schema_bytes)
    catalog = {
        "version": "0.2",
        "resources": [
            {
                "id": schema["$id"],
                "digest": {"sha256": hashlib.sha256(schema_bytes).hexdigest()},
                "path": schema_path.name,
            }
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(canonical_json(catalog) + b"\n")
    reference = create_profile_reference(
        schema_path,
        target="predicate",
        critical=True,
        catalog_paths=[catalog_path],
        repository_root=ROOT,
    )
    assert validate_with_catalog(
        "public", reference, catalog_paths=[catalog_path], repository_root=ROOT
    ).valid
    result = validate_with_catalog(
        "private", reference, catalog_paths=[catalog_path], repository_root=ROOT
    )
    assert not result.valid
    assert "makotoPattern" in result.errors[0]


def test_pattern_fixture_json_is_strictly_decoded() -> None:
    assert json.loads(r'"[a\\-]"') == "[a\\-]"
