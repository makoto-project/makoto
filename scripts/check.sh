#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repository_root}"

uv sync --locked --dev
uv run scripts/build_schema_catalog.py --check
uv run scripts/generate_unicode_tables.py --check
uv run scripts/check_internal_schemas.py
uv run scripts/release_checksums.py --check
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
./scripts/demo-v0.2.sh --acceptance
