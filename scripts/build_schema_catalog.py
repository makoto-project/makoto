"""Build deterministic Makoto core schema catalogs."""

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
        for version in ("0.2", "0.3"):
            expected = serialize(build_catalog(version=version))
            actual = (schema_directory(version=version) / "catalog.json").read_bytes()
            if actual != expected:
                parser.error(
                    f"schemas/v{version}/catalog.json is stale; run this script without --check"
                )
        return 0
    for version in ("0.2", "0.3"):
        write_catalog(version=version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
