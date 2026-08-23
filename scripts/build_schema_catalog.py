"""Build the deterministic Makoto v0.2 core schema catalog."""

import argparse

from makoto.schema_catalog import build_catalog, schema_directory, serialize, write_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail without writing when catalog.json differs from the schema bytes",
    )
    arguments = parser.parse_args()
    if arguments.check:
        expected = serialize(build_catalog())
        actual = (schema_directory() / "catalog.json").read_bytes()
        if actual != expected:
            parser.error("schemas/v0.2/catalog.json is stale; run this script without --check")
        return 0
    write_catalog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
