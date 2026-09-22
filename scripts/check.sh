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
bash ./scripts/demo.sh --acceptance
if [[ "${MAKOTO_SKIP_GO_CHECK:-0}" != "1" ]]; then
  bash ./scripts/check-go.sh
fi
