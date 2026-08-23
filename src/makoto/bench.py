"""Small reproducible release benchmark for core canonicalization and signatures."""

from __future__ import annotations

import argparse
import platform
import statistics
import time
from pathlib import Path

from makoto.canonical import canonical_json
from makoto.dsse import SigningKey, sign_envelope, verify_envelope_signature


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    key = SigningKey.from_seed(bytes(range(32)))
    payload = canonical_json({"fixture": str(args.fixtures), "rows": list(range(100))})
    samples: list[float] = []
    for _ in range(args.samples):
        started = time.perf_counter()
        envelope = sign_envelope("application/vnd.in-toto+json", payload, key)
        verify_envelope_signature(envelope, public_spki=key.public_spki())
        samples.append((time.perf_counter() - started) * 1000)
    result = {
        "version": "0.2",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "samples": args.samples,
        "signatureRoundTripMilliseconds": {
            "median": statistics.median(samples),
            "p95": sorted(samples)[max(0, int(len(samples) * 0.95) - 1)],
            "maximum": max(samples),
        },
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_bytes(canonical_json(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
