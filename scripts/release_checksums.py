#!/usr/bin/env python3
"""Generate or verify the Makoto candidate or release checksum inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release/v0.3/checksums.json"
V02_MANIFEST = ROOT / "release/v0.2/checksums.json"
SCHEMA = ROOT / "release/checksums.schema.json"
PREFIXES = (
    "demos/end-to-end",
    "docs",
    "examples/github-actions",
    "examples/go",
    "schemas/v0.2",
    "schemas/v0.3",
    "scripts",
    "src/makoto",
    "testdata/v0.2",
    "testdata/v0.3",
    "tests",
)
V02_PREFIXES = (
    "demos/end-to-end",
    "docs",
    "examples/go",
    "schemas/v0.2",
    "scripts",
    "src/makoto",
    "testdata/v0.2",
    "tests",
)
EXACT_PATHS = (
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "release/checksums.schema.json",
    "spec/v0.2.md",
    "spec/v0.3.md",
    "uv.lock",
)
V02_EXACT_PATHS = (
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "release/checksums.schema.json",
    "spec/v0.2.md",
    "uv.lock",
)
FORBIDDEN_SEGMENTS = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".work",
    "__pycache__",
}


class ChecksumError(ValueError):
    """The release inventory is incomplete, malformed, or has changed bytes."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    parser.add_argument(
        "--tag",
        choices=("v0.3.0",),
        help="set only when writing the approved tagged release inventory",
    )
    parser.add_argument(
        "--exact",
        action="store_true",
        help="with --check, require even a candidate inventory to match the working tree",
    )
    args = parser.parse_args()
    if args.check and args.tag is not None:
        parser.error("--tag can only be combined with --write")
    if args.exact and not args.check:
        parser.error("--exact can only be combined with --check")
    return args


def _included_paths(
    root: Path,
    prefixes: tuple[str, ...],
    exact_paths: tuple[str, ...],
) -> tuple[str, ...]:
    paths = set(exact_paths)
    for prefix in prefixes:
        directory = root / prefix
        if not directory.is_dir():
            raise ChecksumError(f"required release directory is absent: {prefix}")
        for path in directory.rglob("*"):
            if path.is_file() and not FORBIDDEN_SEGMENTS.intersection(path.parts):
                paths.add(path.relative_to(root).as_posix())
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        raise ChecksumError(f"required release files are absent: {sorted(missing)!r}")
    if any(path.endswith("/checksums.json") for path in paths):
        raise ChecksumError("checksum manifest cannot include itself")
    return tuple(sorted(paths, key=str.encode))


def included_paths(root: Path = ROOT) -> tuple[str, ...]:
    return _included_paths(root, PREFIXES, EXACT_PATHS)


def included_v02_paths(root: Path = ROOT) -> tuple[str, ...]:
    return _included_paths(root, V02_PREFIXES, V02_EXACT_PATHS)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(root: Path = ROOT, *, tag: str | None = None) -> dict[str, Any]:
    return {
        "version": "1",
        "tag": tag,
        "files": [
            {"path": relative, "digest": {"sha256": sha256(root / relative)}}
            for relative in included_paths(root)
        ],
    }


def build_v02_manifest(root: Path = ROOT) -> dict[str, Any]:
    return {
        "version": "1",
        "tag": None,
        "files": [
            {"path": relative, "digest": {"sha256": sha256(root / relative)}}
            for relative in included_v02_paths(root)
        ],
    }


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )


def strict_json(path: Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ChecksumError(f"{path}: UTF-8 BOM is forbidden")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ChecksumError(f"{path}: duplicate key {key!r}")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def check_shape(value: Any, schema: Any) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise ChecksumError("; ".join(error.message for error in errors))
    paths = [item["path"] for item in value["files"]]
    if paths != sorted(paths, key=str.encode) or len(paths) != len(set(paths)):
        raise ChecksumError("checksum paths are not sorted and unique")
    if any(path != unicodedata.normalize("NFC", path) for path in paths):
        raise ChecksumError("checksum paths must be NFC")


def _verify_manifest(
    root: Path,
    manifest_path: str,
    expected: dict[str, Any],
    *,
    exact: bool,
) -> bool:
    """Verify the checked-in inventory and report whether it matches the working tree.

    A tagged inventory, or any inventory when ``exact`` is set, must match byte for byte.
    A null-tag candidate is not release evidence (spec/v0.3.md), so the routine gate only
    requires it to be well formed and regenerable: dependency updates may change included
    bytes such as uv.lock without rewriting it, and release-check.sh enforces exactness.
    """
    path = root / manifest_path
    value = strict_json(path)
    schema = strict_json(root / "release/checksums.schema.json")
    Draft202012Validator.check_schema(schema)
    check_shape(value, schema)
    if path.read_bytes() != canonical_bytes(value):
        raise ChecksumError("checksum manifest is not canonical JSON plus one LF")
    check_shape(expected, schema)
    current = value == expected
    if not current and (exact or value["tag"] is not None):
        raise ChecksumError("checksum inclusion set or file digests differ")
    return current


def verify_manifest(root: Path = ROOT, *, exact: bool = False) -> bool:
    value = strict_json(root / "release/v0.3/checksums.json")
    expected = build_manifest(root, tag=value["tag"])
    return _verify_manifest(
        root,
        "release/v0.3/checksums.json",
        expected,
        exact=exact,
    )


def verify_v02_manifest(root: Path = ROOT, *, exact: bool = False) -> bool:
    return _verify_manifest(
        root,
        "release/v0.2/checksums.json",
        build_v02_manifest(root),
        exact=exact,
    )


def main() -> int:
    args = parse_args()
    if args.write:
        if args.tag is None:
            V02_MANIFEST.write_bytes(canonical_bytes(build_v02_manifest()))
            print(f"wrote {V02_MANIFEST.relative_to(ROOT)}")
        MANIFEST.write_bytes(canonical_bytes(build_manifest(tag=args.tag)))
        print(f"wrote {MANIFEST.relative_to(ROOT)}")
    else:
        v02_current = verify_v02_manifest(exact=args.exact)
        v03_current = verify_manifest(exact=args.exact)
        if v02_current and v03_current:
            print("release checksums valid")
        else:
            print("release checksums valid; candidate digests trail the tree until release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
