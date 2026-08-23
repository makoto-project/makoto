"""Generate deterministic Unicode 15.0.0 NFC and case-fold runtime tables."""

from __future__ import annotations

import argparse
from typing import Any

from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
from makoto.unicode15 import UNICODE_VERSION, unicode_directory, verify_unicode_data


def _code_points(field: str) -> list[int]:
    if ".." in field:
        start, end = field.split("..", 1)
        return list(range(int(start, 16), int(end, 16) + 1))
    return [int(field, 16)]


def build_tables() -> dict[str, Any]:
    verify_unicode_data(check_generated=False)
    root = unicode_directory()
    combining: dict[str, int] = {}
    decomposition: dict[str, list[int]] = {}
    for line in (root / "UnicodeData.txt").read_text(encoding="utf-8").splitlines():
        fields = line.split(";")
        code_point = int(fields[0], 16)
        combining_class = int(fields[3])
        if combining_class:
            combining[str(code_point)] = combining_class
        raw_decomposition = fields[5]
        if raw_decomposition and not raw_decomposition.startswith("<"):
            decomposition[str(code_point)] = [int(value, 16) for value in raw_decomposition.split()]

    full_exclusions: set[int] = set()
    for line in (root / "DerivedNormalizationProps.txt").read_text(encoding="utf-8").splitlines():
        record = line.split("#", 1)[0].strip()
        if not record:
            continue
        fields = [field.strip() for field in record.split(";")]
        if len(fields) >= 2 and fields[1] == "Full_Composition_Exclusion":
            full_exclusions.update(_code_points(fields[0]))

    explicit_exclusions: set[int] = set()
    for line in (root / "CompositionExclusions.txt").read_text(encoding="utf-8").splitlines():
        record = line.split("#", 1)[0].strip()
        if record:
            explicit_exclusions.update(_code_points(record))
    if not explicit_exclusions <= full_exclusions:
        raise RuntimeError("CompositionExclusions is not a subset of Full_Composition_Exclusion")

    composition: dict[str, int] = {}
    for code_point_text, values in decomposition.items():
        code_point = int(code_point_text)
        if len(values) == 2 and code_point not in full_exclusions:
            composition[f"{values[0]} {values[1]}"] = code_point

    casefold: dict[str, list[int]] = {}
    for line in (root / "CaseFolding.txt").read_text(encoding="utf-8").splitlines():
        record = line.split("#", 1)[0].strip()
        if not record:
            continue
        code_point, status, mapping = (part.strip() for part in record.split(";")[:3])
        if status in {"C", "F"}:
            casefold[str(int(code_point, 16))] = [int(value, 16) for value in mapping.split()]

    source_digests = {
        name: sha256_bytes((root / name).read_bytes())
        for name in (
            "CaseFolding.txt",
            "CompositionExclusions.txt",
            "DerivedNormalizationProps.txt",
            "UnicodeData.txt",
        )
    }
    return {
        "casefold": casefold,
        "combiningClass": combining,
        "composition": composition,
        "decomposition": decomposition,
        "sourceDigests": source_digests,
        "version": UNICODE_VERSION,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    output = unicode_directory() / "tables.json"
    expected = canonical_json(build_tables()) + b"\n"
    if arguments.check:
        if not output.exists() or output.read_bytes() != expected:
            parser.error("Unicode tables are stale; regenerate them without --check")
        return 0
    output.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
