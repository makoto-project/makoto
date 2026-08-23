from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

release_checksums = import_module("scripts.release_checksums")


def test_release_checksum_manifest_matches_exact_working_tree_bytes() -> None:
    release_checksums.verify_manifest()


def test_release_checksum_inclusion_set_is_sorted_and_excludes_itself() -> None:
    paths = release_checksums.included_paths()

    assert paths == tuple(sorted(paths, key=str.encode))
    assert "release/v0.2/checksums.json" not in paths
    assert "release/checksums.schema.json" in paths
