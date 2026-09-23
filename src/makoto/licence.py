"""Makoto v0.3 standard licence-claim profile semantics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

LICENSE_PROFILE_ID = "https://usemakoto.dev/profile/v0.3/license-claim-v1.schema.json"
LICENSE_CLAIM_ID = "https://usemakoto.dev/claim/v0.3/license"

_IDENTIFIER = re.compile(
    r"(?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+"
    r"|[A-Za-z0-9][A-Za-z0-9.-]*\+?"
)
_TOKEN = re.compile(
    r"\s*(?:(AND|OR|WITH)|([()])|"
    r"((?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+|"
    r"[A-Za-z0-9][A-Za-z0-9.-]*\+?))"
)


class SpdxExpressionError(ValueError):
    """An SPDX expression is not syntactically valid."""


@dataclass
class _Tokens:
    values: list[str]
    index: int = 0

    def peek(self) -> str | None:
        return self.values[self.index] if self.index < len(self.values) else None

    def take(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None:
            raise SpdxExpressionError("unexpected end of SPDX expression")
        if expected is not None and token != expected:
            raise SpdxExpressionError(f"expected {expected!r}, got {token!r}")
        self.index += 1
        return token


def validate_spdx_expression(expression: str) -> None:
    """Validate the SPDX 2.x expression grammar without a mutable licence list."""

    values: list[str] = []
    position = 0
    while position < len(expression):
        match = _TOKEN.match(expression, position)
        if match is None:
            raise SpdxExpressionError(f"invalid SPDX token at byte {position}")
        operator, punctuation, identifier = match.groups()
        values.append(operator or punctuation or identifier)
        position = match.end()
    if not values or expression[-1:].isspace():
        raise SpdxExpressionError("SPDX expression is empty or has trailing whitespace")

    tokens = _Tokens(values)

    def primary() -> None:
        token = tokens.peek()
        if token == "(":
            tokens.take("(")
            disjunction()
            tokens.take(")")
            return
        if token is None or _IDENTIFIER.fullmatch(token) is None or token in {"AND", "OR", "WITH"}:
            raise SpdxExpressionError(f"expected SPDX licence identifier, got {token!r}")
        tokens.take()
        if tokens.peek() == "WITH":
            tokens.take("WITH")
            exception = tokens.take()
            if _IDENTIFIER.fullmatch(exception) is None or "LicenseRef-" in exception:
                raise SpdxExpressionError("WITH requires an SPDX exception identifier")

    def conjunction() -> None:
        primary()
        while tokens.peek() == "AND":
            tokens.take("AND")
            primary()

    def disjunction() -> None:
        conjunction()
        while tokens.peek() == "OR":
            tokens.take("OR")
            conjunction()

    disjunction()
    if tokens.peek() is not None:
        raise SpdxExpressionError(f"unexpected SPDX token {tokens.peek()!r}")


def licence_claim_errors(statement: Mapping[str, Any]) -> tuple[str, ...]:
    """Return deterministic cross-field errors for the standard profile."""

    subjects = statement.get("subject", [])
    predicate = statement.get("predicate", {})
    extensions = predicate.get("extensions", {}) if isinstance(predicate, Mapping) else {}
    extension = extensions.get(LICENSE_CLAIM_ID, {}) if isinstance(extensions, Mapping) else {}
    claims = extension.get("claims", []) if isinstance(extension, Mapping) else []
    errors: list[str] = []
    subject_names = [item.get("name") for item in subjects if isinstance(item, Mapping)]
    claim_names = [item.get("subjectName") for item in claims if isinstance(item, Mapping)]
    if claim_names != sorted(claim_names, key=lambda item: str(item).encode()):
        errors.append("licence claims must be sorted by subjectName")
    if len(claim_names) != len(set(claim_names)):
        errors.append("licence claims contain duplicate subjectName values")
    if set(claim_names) != set(subject_names):
        errors.append("licence claims must cover every statement subject exactly once")
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            continue
        expression = claim.get("spdxExpression")
        if isinstance(expression, str):
            try:
                validate_spdx_expression(expression)
            except SpdxExpressionError as error:
                errors.append(f"licence claim {index} has invalid SPDX expression: {error}")
        evidence_url = claim.get("evidenceUrl")
        if isinstance(evidence_url, str):
            try:
                parsed = urlsplit(evidence_url)
            except ValueError:
                parsed = None
            if parsed is None or parsed.scheme != "https" or not parsed.netloc or parsed.fragment:
                errors.append(
                    f"licence claim {index} evidenceUrl must be an absolute HTTPS URL "
                    "without a fragment"
                )
    return tuple(errors)
