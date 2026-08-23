from __future__ import annotations

from pathlib import Path

import pytest

from makoto.canonical import canonical_json
from makoto.dataset import DatasetManifestError, parse_dataset_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_parse_dataset_manifest_builds_exact_member_index() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {
                "name": "year=2026/month=09/part-00000.parquet",
                "digest": {"sha256": "a" * 64},
                "size": 48127,
                "mediaType": "application/vnd.apache.parquet",
            }
        ],
    }

    index = parse_dataset_manifest(canonical_json(value), repository_root=ROOT)

    member = index.member("year=2026/month=09/part-00000.parquet")
    assert member is not None
    assert member.digest == "a" * 64
    assert member.size == 48127
    assert member.media_type == "application/vnd.apache.parquet"
    assert index.member("missing.parquet") is None


def test_parse_dataset_manifest_distinguishes_strict_json_failure() -> None:
    with pytest.raises(DatasetManifestError) as caught:
        parse_dataset_manifest(b'{"version":"0.2","version":"0.2"}', repository_root=ROOT)

    assert caught.value.phase == "parse"


def test_parse_dataset_manifest_rejects_nonportable_member_names() -> None:
    value = {
        "version": "0.2",
        "entries": [
            {"name": "part/STRASSE.json", "digest": {"sha256": "a" * 64}},
            {"name": "part/Straße.json", "digest": {"sha256": "b" * 64}},
        ],
    }

    with pytest.raises(DatasetManifestError) as caught:
        parse_dataset_manifest(canonical_json(value), repository_root=ROOT)

    assert caught.value.phase == "semantic"
    assert "Unicode 15.0 full case folding" in str(caught.value)


def test_parse_dataset_manifest_distinguishes_structural_schema_failure() -> None:
    with pytest.raises(DatasetManifestError) as caught:
        parse_dataset_manifest(canonical_json({"version": "0.2"}), repository_root=ROOT)

    assert caught.value.phase == "schema"
