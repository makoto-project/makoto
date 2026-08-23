from __future__ import annotations

import hashlib
from pathlib import Path

from makoto.unicode15 import casefold, normalize_nfc, unicode_directory, verify_unicode_data

ROOT = Path(__file__).resolve().parents[1]
NORMALIZATION_TEST = ROOT / "testdata" / "v0.2" / "unicode" / "NormalizationTest.txt"


def _scalars(field: str) -> str:
    return "".join(chr(int(value, 16)) for value in field.split())


def test_unicode_inputs_and_generated_tables_are_current() -> None:
    verify_unicode_data()
    assert hashlib.sha256(NORMALIZATION_TEST.read_bytes()).hexdigest() == (
        "fb9ac8cc154a80cad6caac9897af55a4e75176af6f4e2bb6edc2bf8b1d57f326"
    )


def test_pinned_unicode_15_nfc_vectors() -> None:
    assert normalize_nfc("e\u0301") == "é"
    assert normalize_nfc("Å") == "Å"
    assert normalize_nfc("각") == "각"
    assert normalize_nfc("क़") == "क़"


def test_pinned_unicode_15_full_casefold_vectors() -> None:
    assert casefold("Straße") == "strasse"
    assert casefold("İ") == "i\u0307"
    assert casefold("ΐ") == "ι\u0308\u0301"
    assert casefold("Σς") == "σσ"
    assert casefold("ﬃ") == "ffi"


def test_all_official_unicode_15_normalization_vectors() -> None:
    for line in NORMALIZATION_TEST.read_text(encoding="utf-8").splitlines():
        record = line.split("#", 1)[0].strip()
        if not record or record.startswith("@"):
            continue
        columns = [field.strip() for field in record.split(";")]
        c1, c2, c3, c4, c5 = (_scalars(field) for field in columns[:5])
        assert normalize_nfc(c1) == c2
        assert normalize_nfc(c2) == c2
        assert normalize_nfc(c3) == c2
        assert normalize_nfc(c4) == c4
        assert normalize_nfc(c5) == c4


def test_all_default_full_casefold_mappings() -> None:
    casefold_data = unicode_directory() / "CaseFolding.txt"
    for line in casefold_data.read_text(encoding="utf-8").splitlines():
        record = line.split("#", 1)[0].strip()
        if not record:
            continue
        code_point, status, mapping = (field.strip() for field in record.split(";")[:3])
        if status in {"C", "F"}:
            assert casefold(chr(int(code_point, 16))) == _scalars(mapping)
