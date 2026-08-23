"""Validate the release benchmark result and conservative latency threshold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    value = json.loads(args.result.read_text(encoding="utf-8"))
    if value.get("version") != "0.2" or value.get("samples") != 20:
        parser.error("benchmark result has the wrong contract")
    maximum = value["signatureRoundTripMilliseconds"]["maximum"]
    if not isinstance(maximum, (int, float)) or maximum > 50:
        parser.error(f"signature round trip exceeds 50 ms: {maximum}")
    print("benchmark valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
