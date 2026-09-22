#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repository_root}"

if ! command -v go >/dev/null 2>&1; then
  echo "go is not installed; skipping Go formatting, vet, and tests"
  exit 0
fi

export GO111MODULE=on

unformatted="$(gofmt -l examples/go)"
if [[ -n "${unformatted}" ]]; then
  echo "Go files require gofmt:" >&2
  echo "${unformatted}" >&2
  exit 1
fi

cd examples/go
go vet ./...
go test ./...
