#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repository_root}"

./scripts/check.sh

benchmark_result="${repository_root}/.codex-work/release-benchmark.json"
mkdir -p "$(dirname "${benchmark_result}")"
uv run python -m makoto.bench \
  --fixtures testdata/v0.2/benchmarks \
  --samples 20 \
  --json-out "${benchmark_result}"
uv run python -m makoto.bench_check "${benchmark_result}"
