# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- The normative protocol design is in `spec/v0.2.md`; its assurance tracks,
  verified properties, source inventory, and threat mapping are completed by
  `spec/failure-mode-coverage.md`.
- Run the repository's complete local gate with `./scripts/check.sh`.
- The native binding is a separate Go module in `go/`; its focused gate is
  `./scripts/check-go.sh`, which also checks the embedded schema copy for drift.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
