#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repository_root}"

if [[ "${1:-}" != "--acceptance" || "$#" -gt 3 ]]; then
  echo "usage: ./scripts/demo-v0.2.sh --acceptance [--export <repository-path>]" >&2
  exit 2
fi

if [[ "$#" -eq 3 && "${2:-}" != "--export" ]]; then
  echo "usage: ./scripts/demo-v0.2.sh --acceptance [--export <repository-path>]" >&2
  exit 2
fi

uv run demos/v0.2-end-to-end/run_demo.py "$@"
