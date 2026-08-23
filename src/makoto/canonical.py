"""RFC 8785 JSON Canonicalization Scheme encoding."""

from __future__ import annotations

from typing import Any

import rfc8785


class CanonicalizationError(ValueError):
    """Raised when a value is outside the RFC 8785 input domain."""


def canonical_json(value: Any) -> bytes:
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError, TypeError) as error:
        raise CanonicalizationError("value cannot be encoded as RFC 8785 JSON") from error
