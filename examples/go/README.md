# Go examples

Makoto's language-independent contract is the published JSON Schema set in
[`schemas/v0.2`](../../schemas/v0.2). These examples deliberately decode JSON
into `map[string]any`; they do not define a Go representation of the protocol.

Each directory is a small executable example:

- [`validate`](validate) loads the Draft 2020-12 schemas and validates generic
  JSON documents without network access.
- [`canonical`](canonical) applies RFC 8785 JCS and computes SHA-256.
- [`dsse`](dsse) signs and verifies Ed25519 DSSE envelopes with `crypto/ed25519`.
- [`verify`](verify) invokes the Python reference verifier and decodes its JSON
  report generically.

The module requires Go 1.26 or newer. From the repository root, run all examples
and their fixture-backed tests with:

```bash
./scripts/check-go.sh
```

The tests use the checked-in positive demo and negative conformance fixtures.
The canonicalization test also compares Go output byte for byte with the Python
implementation when `uv` is installed.

## Support boundary

| Capability | Example |
|---|---|
| Validate generic JSON against the published v0.2 schemas | `validate` |
| RFC 8785 canonical JSON and SHA-256 | `canonical` |
| Ed25519 DSSE signing and signature verification | `dsse` |
| Complete receiver verification | `verify`, through the Python reference CLI |
| Native Go protocol types or a Go SDK | Not provided |
| Native Go graph, policy, profile, assurance, or VSA verification | Not provided |

The examples are integration recipes, not a supported Go API. Applications
should keep JSON Schema as the contract and use the Python CLI when they need
the complete receiver-verification semantics.
