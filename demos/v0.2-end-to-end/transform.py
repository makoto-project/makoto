"""Deterministic synthetic transformations for the Makoto v0.2 demo."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

FIELDS = {"customer_id", "email", "region", "age", "marketing_consent"}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("input must be a JSON array")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("every row must contain exactly the five raw fields")
        if not isinstance(row["customer_id"], str) or not row["customer_id"]:
            raise ValueError("customer_id must be a nonempty string")
        if row["customer_id"] in seen_ids:
            raise ValueError("customer_id values must be unique")
        seen_ids.add(row["customer_id"])
        if not isinstance(row["email"], str) or not isinstance(row["region"], str):
            raise ValueError("email and region must be strings")
        if not isinstance(row["marketing_consent"], str):
            raise ValueError("marketing_consent must be a string")
        age = row["age"]
        if isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 130:
            raise ValueError("age must be an integer from 0 through 130")
        rows.append(row)
    return rows


def normalize(source: Path, destination: Path) -> None:
    output: list[dict[str, Any]] = []
    for row in _read_rows(source):
        email = row["email"].strip(" ").lower()
        region = row["region"].strip(" ")
        if len(region) != 2 or not region.isascii() or not region.isalpha():
            raise ValueError("region must contain exactly two ASCII letters")
        consent_text = row["marketing_consent"].strip(" ").lower()
        if consent_text in {"yes", "true", "1"}:
            consent = True
        elif consent_text in {"no", "false", "0"}:
            consent = False
        else:
            raise ValueError("marketing_consent is invalid")
        output.append(
            {
                "age": row["age"],
                "customer_id": row["customer_id"],
                "email": email,
                "marketing_consent": consent,
                "region": region.upper(),
            }
        )
    _write_json(destination, output)


def public_safe(source: Path, destination: Path, *, reintroduce_email: bool = False) -> None:
    value = json.loads(source.read_text(encoding="utf-8"))
    output: list[dict[str, Any]] = []
    pseudonyms: set[str] = set()
    for row in value:
        pseudonym = hashlib.sha256(f"makoto-demo-v0.2:{row['customer_id']}".encode()).hexdigest()[
            :20
        ]
        if pseudonym in pseudonyms:
            raise ValueError("pseudonym collision")
        pseudonyms.add(pseudonym)
        public_row: dict[str, Any] = {
            "age_band": _age_band(row["age"]),
            "customer_id": pseudonym,
            "marketing_consent": row["marketing_consent"],
            "region": row["region"],
        }
        if reintroduce_email:
            public_row["email"] = row["email"]
        output.append(public_row)
    output.sort(key=lambda row: row["customer_id"])
    _write_json(destination, output)


def _age_band(age: int) -> str:
    for upper, label in (
        (17, "0-17"),
        (24, "18-24"),
        (34, "25-34"),
        (44, "35-44"),
        (54, "45-54"),
        (64, "55-64"),
        (130, "65+"),
    ):
        if age <= upper:
            return label
    raise ValueError("age is out of range")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("normalize", "public-safe"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--reintroduce-email", action="store_true")
    args = parser.parse_args()
    if args.operation == "normalize":
        normalize(args.source, args.destination)
    else:
        public_safe(
            args.source,
            args.destination,
            reintroduce_email=args.reintroduce_email,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
