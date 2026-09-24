from __future__ import annotations

import shutil
import sys
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

release_checksums = import_module("scripts.release_checksums")


def test_release_checksum_manifest_is_well_formed_and_regenerable() -> None:
    release_checksums.verify_manifest()


def test_release_checksum_inclusion_set_is_sorted_and_excludes_itself() -> None:
    paths = release_checksums.included_paths()

    assert paths == tuple(sorted(paths, key=str.encode))
    assert "release/v0.3/checksums.json" not in paths
    assert "release/checksums.schema.json" in paths
    assert "examples/go/go.mod" in paths


def test_candidate_and_release_checksum_status_are_explicit() -> None:
    assert release_checksums.build_manifest()["tag"] is None
    assert release_checksums.build_manifest(tag="v0.3.0")["tag"] == "v0.3.0"


def release_tree(root: Path, *, tag: str | None) -> Path:
    for prefix in release_checksums.PREFIXES:
        (root / prefix).mkdir(parents=True)
        (root / prefix / "file.txt").write_bytes(b"included\n")
    for exact in release_checksums.EXACT_PATHS:
        (root / exact).parent.mkdir(parents=True, exist_ok=True)
        (root / exact).write_bytes(b"included\n")
    shutil.copyfile(ROOT / "release/checksums.schema.json", root / "release/checksums.schema.json")
    manifest = root / "release/v0.3/checksums.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes(
        release_checksums.canonical_bytes(release_checksums.build_manifest(root, tag=tag))
    )
    return manifest


def test_current_candidate_passes_routine_and_exact_checks(tmp_path: Path) -> None:
    release_tree(tmp_path, tag=None)

    assert release_checksums.verify_manifest(tmp_path) is True
    assert release_checksums.verify_manifest(tmp_path, exact=True) is True


def test_stale_candidate_passes_routine_check_but_fails_exact_check(tmp_path: Path) -> None:
    release_tree(tmp_path, tag=None)
    (tmp_path / "uv.lock").write_bytes(b"dependency update\n")

    assert release_checksums.verify_manifest(tmp_path) is False
    with pytest.raises(release_checksums.ChecksumError, match="digests differ"):
        release_checksums.verify_manifest(tmp_path, exact=True)


def test_stale_tagged_manifest_fails_routine_check(tmp_path: Path) -> None:
    release_tree(tmp_path, tag="v0.3.0")
    (tmp_path / "uv.lock").write_bytes(b"dependency update\n")

    with pytest.raises(release_checksums.ChecksumError, match="digests differ"):
        release_checksums.verify_manifest(tmp_path)


def test_stale_candidate_must_still_be_regenerable(tmp_path: Path) -> None:
    release_tree(tmp_path, tag=None)
    (tmp_path / "uv.lock").unlink()

    with pytest.raises(release_checksums.ChecksumError, match="uv.lock"):
        release_checksums.verify_manifest(tmp_path)


def test_candidate_must_stay_canonical(tmp_path: Path) -> None:
    manifest = release_tree(tmp_path, tag=None)
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(release_checksums.ChecksumError, match="canonical"):
        release_checksums.verify_manifest(tmp_path)
