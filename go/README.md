# Makoto for Go

This module reads and writes Makoto v0.2 documents without invoking the Python
CLI. It validates documents against the embedded v0.2 Draft 2020-12 schemas,
implements RFC 8785 canonical JSON and exact-byte SHA-256 digests, and signs or
verifies Makoto's Ed25519 DSSE profile.

Makoto v0.2 remains an unreleased release candidate. Use a reviewed commit or
tag when you need a reproducible dependency.

## Install

```bash
go get github.com/makoto-project/makoto/go
```

The module requires Go 1.26 or newer.

## Read, validate, and write

```go
input := strings.NewReader(bundleJSON)
bundle, err := makoto.DecodeBundle(input)
if err != nil {
	return err
}
if err := bundle.Validate(); err != nil {
	return err
}
return makoto.Encode(output, bundle)
```

[`Example_readValidateWrite`](example_test.go) contains a complete executable
example. Tests run it with `go test` so the published API cannot drift away
from the documentation.

Decoded document structs and their typed child objects retain unknown fields in
`UnknownFields`. Origin and transform predicates also retain application fields
inside `Extensions`. Schema validation still rejects unknown core fields where
the v0.2 schema sets `additionalProperties` to `false`.

## Support boundary

| Capability | Status |
|---|---|
| Typed Statement, origin, transform, DSSE, handoff, dataset manifest, bundle, trust policy, and verification report documents | Supported |
| JSON read and write with unknown-field preservation | Supported |
| Embedded v0.2 Draft 2020-12 schema validation | Supported |
| RFC 8785 canonical JSON and exact-byte SHA-256 | Supported |
| Ed25519 DSSE signing and per-signature verification | Supported |
| Full bundle loading and artifact-byte verification | Not yet supported |
| Receiver graph and authorization-policy evaluation | Not yet supported |
| Private profile and dataset-content evaluation | Not yet supported |
| Assurance tracks, VSA assessment, and VSA summaries | Not yet supported |

`Validate` methods enforce the embedded JSON Schemas. They do not claim the
additional graph, policy, private-profile, resource-limit, or report-folding
checks performed by the Python reference verifier.

## Development

From the repository root, run the Go gate directly:

```bash
./scripts/check-go.sh
```

The repository-wide `./scripts/check.sh` also runs it. The gate checks the
embedded schema copy byte for byte against `schemas/v0.2`, verifies formatting,
runs `go vet`, and runs every Go test. Its cross-implementation test compares
canonical bytes and digests with the Python implementation through `uv` when
`uv` is installed.
