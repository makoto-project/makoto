# Keyless pull-request lineage

[`keyless-lineage.yml`](keyless-lineage.yml) is a reference workflow, not a
workflow used by this repository. Copy it to
`.github/workflows/keyless-lineage.yml` on the default branch.

The job runs on `pull_request_target` so the OIDC subject and workflow ref are
bound to the reviewed default-branch workflow. It does not check out or execute
pull-request code. The signed subject is a small file containing the exact pull
request head commit. The temporary Ed25519 signature lets the existing
attestation command build the envelope; a receiver can leave that key unknown
and authorize only the added keyless identity.

The generated `identity.json` contains the exact claims a receiver places in
`keylessIdentities`: GitHub's issuer, workflow subject, repository, base-branch
workflow ref, and `pull_request_target` event. Its deterministic ID belongs in
the rule's `authorizedIdentityIds`. The receiver must also pin and separately
supply the Sigstore production trusted-root JSON bytes.

Pin the checkout, setup, and upload actions to reviewed commit SHAs before
using this as a production control. The version tags below keep the example
readable; tags are not immutable trust anchors.
