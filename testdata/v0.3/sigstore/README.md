# Sigstore test vectors

These files are recorded verification material. Tests do not contact Fulcio,
Rekor, a timestamp authority, TUF, or an OIDC provider.

- `dsse-bundle.json` comes from sigstore/sigstore-conformance v0.0.28,
  `test/assets/bundle-verify/happy-path-intoto-in-dsse-v3/bundle.sigstore.json`
  (blob `c2c3b4d31b79cfaa99e60a53dfbef9740c4a8623`).
- `trusted-root.json` comes from sigstore/sigstore-python v4.4.0,
  `sigstore/_store/https%3A%2F%2Ftuf-repo-cdn.sigstore.dev/trusted_root.json`
  (blob `effb0a19e6a0b3f69b3f0a2c72b5c2a02a0ddeea`).

Both upstream projects publish these files under Apache-2.0. The recorded
bundle verifies offline against the recorded root. Tests mutate copies for
the tampered-log and invalid-time cases.
