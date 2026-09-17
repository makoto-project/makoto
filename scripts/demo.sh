#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec bash "${repository_root}/scripts/demo-v0.2.sh" "$@"
