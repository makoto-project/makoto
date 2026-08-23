"""Pure-Python Unicode 15.0.0 NFC and full case folding from vendored tables."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes

UNICODE_VERSION = "15.0.0"
_EXPECTED_FILES = (
    ("CaseFolding.txt", 84690, "cdd49e55eae3bbf1f0a3f6580c974a0263cb86a6a08daa10fbf705b4808a56f7"),
    (
        "CompositionExclusions.txt",
        8911,
        "3b019c0a33c3140cbc920c078f4f9af2680ba4f71869c8d4de5190667c70b6a3",
    ),
    (
        "DerivedNormalizationProps.txt",
        837688,
        "d5687a48c95c7d6e1ec59cb29c0f2e8b052018eb069a4371b7368d0561e12a29",
    ),
    (
        "UnicodeData.txt",
        1913704,
        "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73",
    ),
)

_SBASE = 0xAC00
_LBASE = 0x1100
_VBASE = 0x1161
_TBASE = 0x11A7
_LCOUNT = 19
_VCOUNT = 21
_TCOUNT = 28
_NCOUNT = _VCOUNT * _TCOUNT
_SCOUNT = _LCOUNT * _NCOUNT


class UnicodeDataError(RuntimeError):
    """Raised when the pinned Unicode inputs or generated tables drift."""


def unicode_directory() -> Path:
    return Path(__file__).parent / "unicode" / UNICODE_VERSION


@lru_cache(maxsize=2)
def verify_unicode_data(*, check_generated: bool = True) -> None:
    root = unicode_directory()
    catalog_bytes = (root / "unicode-catalog.json").read_bytes()
    try:
        catalog = json.loads(catalog_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnicodeDataError("Unicode catalog is not strict JSON") from error
    expected_catalog = {
        "files": [
            {"bytes": size, "digest": {"sha256": digest}, "path": path}
            for path, size, digest in _EXPECTED_FILES
        ],
        "version": UNICODE_VERSION,
    }
    if catalog != expected_catalog or catalog_bytes != canonical_json(catalog) + b"\n":
        raise UnicodeDataError("Unicode catalog differs from the pinned v0.2 inventory")
    expected_names = {"unicode-catalog.json", *(path for path, _, _ in _EXPECTED_FILES)}
    actual_names = {path.name for path in root.iterdir() if path.is_file()}
    if check_generated or "tables.json" in actual_names:
        expected_names.add("tables.json")
    if actual_names != expected_names:
        raise UnicodeDataError("Unicode file inventory differs from the pinned v0.2 inventory")
    for path, size, digest in _EXPECTED_FILES:
        exact_bytes = (root / path).read_bytes()
        if len(exact_bytes) != size or sha256_bytes(exact_bytes) != digest:
            raise UnicodeDataError(f"Unicode input identity mismatch: {path}")


@lru_cache(maxsize=1)
def _tables() -> dict[str, Any]:
    verify_unicode_data()
    raw = (unicode_directory() / "tables.json").read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnicodeDataError("Unicode generated tables are not strict JSON") from error
    if not isinstance(value, dict) or raw != canonical_json(value) + b"\n":
        raise UnicodeDataError("Unicode generated tables are not JCS plus LF")
    if value.get("version") != UNICODE_VERSION:
        raise UnicodeDataError("Unicode generated table version mismatch")
    expected_digests = {path: digest for path, _, digest in _EXPECTED_FILES}
    if value.get("sourceDigests") != expected_digests:
        raise UnicodeDataError("Unicode generated tables do not bind the pinned inputs")
    return value


def _decompose_scalar(code_point: int, table: dict[str, list[int]], output: list[int]) -> None:
    s_index = code_point - _SBASE
    if 0 <= s_index < _SCOUNT:
        output.append(_LBASE + s_index // _NCOUNT)
        output.append(_VBASE + (s_index % _NCOUNT) // _TCOUNT)
        trailing = _TBASE + s_index % _TCOUNT
        if trailing != _TBASE:
            output.append(trailing)
        return
    mapped = table.get(str(code_point))
    if mapped is None:
        output.append(code_point)
        return
    for child in mapped:
        _decompose_scalar(child, table, output)


def _hangul_compose(first: int, second: int) -> int | None:
    l_index = first - _LBASE
    if 0 <= l_index < _LCOUNT:
        v_index = second - _VBASE
        if 0 <= v_index < _VCOUNT:
            return _SBASE + (l_index * _VCOUNT + v_index) * _TCOUNT
    s_index = first - _SBASE
    if 0 <= s_index < _SCOUNT and s_index % _TCOUNT == 0:
        t_index = second - _TBASE
        if 0 < t_index < _TCOUNT:
            return first + t_index
    return None


def normalize_nfc(value: str) -> str:
    """Return NFC using only the checked Unicode 15.0.0 generated tables."""

    tables = _tables()
    decomposition: dict[str, list[int]] = tables["decomposition"]
    combining: dict[str, int] = tables["combiningClass"]
    composition: dict[str, int] = tables["composition"]
    decomposed: list[int] = []
    for character in value:
        _decompose_scalar(ord(character), decomposition, decomposed)

    ordered: list[int] = []
    for code_point in decomposed:
        current_class = int(combining.get(str(code_point), 0))
        position = len(ordered)
        if current_class:
            while position > 0:
                previous_class = int(combining.get(str(ordered[position - 1]), 0))
                if previous_class == 0 or previous_class <= current_class:
                    break
                position -= 1
        ordered.insert(position, code_point)
    if not ordered:
        return ""

    result = [ordered[0]]
    starter_position = 0
    starter = ordered[0]
    last_class = int(combining.get(str(starter), 0))
    for code_point in ordered[1:]:
        current_class = int(combining.get(str(code_point), 0))
        composite = _hangul_compose(starter, code_point)
        if composite is None:
            composite = composition.get(f"{starter} {code_point}")
        if composite is not None and (last_class == 0 or last_class < current_class):
            result[starter_position] = int(composite)
            starter = int(composite)
            continue
        if current_class == 0:
            starter_position = len(result)
            starter = code_point
        result.append(code_point)
        last_class = current_class
    return "".join(chr(code_point) for code_point in result)


def casefold(value: str) -> str:
    """Apply Unicode 15.0.0 default full case folding without normalization."""

    table: dict[str, list[int]] = _tables()["casefold"]
    return "".join(
        "".join(chr(code_point) for code_point in table.get(str(ord(character)), [ord(character)]))
        for character in value
    )


def is_control(value: str) -> bool:
    code_point = ord(value)
    return code_point <= 0x1F or 0x7F <= code_point <= 0x9F
