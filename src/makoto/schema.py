"""Strict JSON loading and v0.2 core-schema validation."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, ValidationError, validators
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from makoto.canonical import canonical_json
from makoto.digest import digest_object, sha256_bytes
from makoto.dsse import (
    DsseError,
    canonical_b64decode,
    keyid_from_spki,
    validate_payload_type,
)
from makoto.pattern import PatternError, compile_pattern
from makoto.schema_catalog import SCHEMA_NAMES, schema_directory
from makoto.standard_registry import verify_standard_registry
from makoto.unicode15 import casefold, is_control, normalize_nfc

T = TypeVar("T")

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TIMESTAMP = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})T"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?Z$"
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}$")
_URN = re.compile(r"^urn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:[^\s#]+$")
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)$")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")
_URI_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~:/?#[]@!$&'()*+,;=%"
)
_ANCHOR = re.compile(r"^[A-Za-z_][-A-Za-z0-9._]*$")
DATASET_MANIFEST_SCHEMA_ID = "https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json"
DATASET_MANIFEST_MEDIA_TYPE = "application/vnd.makoto.dataset-manifest.v0.2+json"
_RESERVED_PATH_BASENAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
    "com¹",
    "com²",
    "com³",
    "lpt¹",
    "lpt²",
    "lpt³",
}
_FORBIDDEN_PATH_CHARACTERS = frozenset('\\\x00<>:"|?*')
_CHECK_ORDER = (
    "load-safely",
    "parse-strictly",
    "index-payloads",
    "core-schemas",
    "signatures",
    "authorization-thresholds",
    "metadata-profiles",
    "authorization",
    "graph-dependency-artifacts",
    "graph",
    "roots-and-heads",
    "completeness-anchor",
    "freshness-anchors",
    "artifact-bytes",
    "artifact-profiles",
    "decision",
)
_CHECK_IDS = frozenset(_CHECK_ORDER)
_PROFILE_PREREQUISITE_ORDER = (
    "authorization-thresholds",
    "metadata-profiles",
    "authorization",
    "graph-dependency-artifacts",
    "graph",
    "artifact-bytes",
    "artifact-profiles",
    "resolution",
)
_RECORD_PREREQUISITE_ORDER = (
    "index-payloads",
    "core-schemas",
    "signatures",
    "authorization-thresholds",
    "metadata-profiles",
    "authorization",
    "graph-dependency-artifacts",
    "graph",
    "completeness-anchor",
    "artifact-bytes",
)
_DIAGNOSTIC_CONTEXT_KEYS = frozenset(
    {
        "actual",
        "actualSize",
        "artifactDigest",
        "bundleId",
        "candidateRuleId",
        "cycleMembers",
        "declared",
        "declaredSize",
        "entryName",
        "evaluationTime",
        "eventId",
        "expected",
        "head",
        "inputName",
        "issuedAt",
        "keyid",
        "lessConstrainedRuleId",
        "limit",
        "manifestDigest",
        "manifestStatementDigest",
        "manifestSubjectName",
        "mediaType",
        "moreConstrainedRuleId",
        "operationType",
        "path",
        "predecessorStatementDigest",
        "predecessorSubjectName",
        "predicateType",
        "profileClosureDigest",
        "profileDigest",
        "profileId",
        "profileTarget",
        "resourceId",
        "ruleId",
        "sourceKind",
        "sourceUri",
        "statementDigest",
        "subjectName",
        "value",
    }
)
_SCHEMA_MAP_KEYWORDS = {"$defs", "properties", "dependentSchemas"}
_SCHEMA_ARRAY_KEYWORDS = {"allOf", "anyOf", "oneOf", "prefixItems"}
_SCHEMA_KEYWORDS = {
    "not",
    "if",
    "then",
    "else",
    "additionalProperties",
    "unevaluatedProperties",
    "propertyNames",
    "items",
    "contains",
    "unevaluatedItems",
    "contentSchema",
}
_PROFILE_KEYWORDS = {
    "$schema",
    "$id",
    "$comment",
    "$ref",
    "$defs",
    "$anchor",
    "type",
    "enum",
    "const",
    "multipleOf",
    "maximum",
    "exclusiveMaximum",
    "minimum",
    "exclusiveMinimum",
    "maxLength",
    "minLength",
    "makotoPattern",
    "maxItems",
    "minItems",
    "uniqueItems",
    "maxContains",
    "minContains",
    "maxProperties",
    "minProperties",
    "required",
    "dependentRequired",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "properties",
    "additionalProperties",
    "unevaluatedProperties",
    "propertyNames",
    "dependentSchemas",
    "prefixItems",
    "items",
    "contains",
    "unevaluatedItems",
    "title",
    "description",
    "default",
    "deprecated",
    "readOnly",
    "writeOnly",
    "examples",
    "contentEncoding",
    "contentMediaType",
    "contentSchema",
    "format",
}
_PROHIBITED_PROFILE_KEYWORDS = {
    "pattern",
    "patternProperties",
    "$dynamicRef",
    "$dynamicAnchor",
    "$vocabulary",
}


def _validate_makoto_pattern(
    validator: object,
    pattern: object,
    instance: object,
    schema: object,
) -> Iterator[ValidationError]:
    del validator, schema
    if not isinstance(instance, str) or not isinstance(pattern, str):
        return
    try:
        compiled = compile_pattern(pattern)
        valid = compiled.search(instance)
    except PatternError as error:
        yield ValidationError(f"unsupported makotoPattern: {error}")
        return
    if not valid:
        yield ValidationError(f"{instance!r} does not match makotoPattern {pattern!r}")


MakotoProfileValidator = validators.extend(  # type: ignore[no-untyped-call]
    Draft202012Validator,
    {"makotoPattern": _validate_makoto_pattern},
)


@dataclass(frozen=True)
class CoreViolation:
    path: str
    message: str


class StrictJsonError(ValueError):
    """Raised when bytes are not strict Makoto JSON."""


class CoreValidationError(ValueError):
    """Raised when an instance violates schema or schema-adjacent semantics."""

    def __init__(self, violations: Iterable[CoreViolation]) -> None:
        self.violations = tuple(violations)
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in self.violations))


class ProfileResolutionError(ValueError):
    """Raised when a digest-pinned organizational profile cannot be resolved."""


@dataclass(frozen=True)
class CatalogResource:
    identifier: str
    digest: str
    exact_bytes: bytes
    schema: dict[str, Any]


@dataclass(frozen=True)
class ProfileResult:
    valid: bool
    errors: tuple[str, ...]


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise StrictJsonError(f"non-finite JSON number {value!r}")


def _reject_surrogates(value: object, path: str = "$") -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise StrictJsonError(f"unpaired Unicode surrogate at {path}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_surrogates(child, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, child in value.items():
            _reject_surrogates(key, f"{path}.<key>")
            _reject_surrogates(child, f"{path}.{key}")


def strict_json_loads(data: bytes) -> object:
    """Parse UTF-8 RFC 8259 JSON without BOMs, duplicate keys, or surrogate scalars."""

    if data.startswith(b"\xef\xbb\xbf"):
        raise StrictJsonError("UTF-8 BOM is forbidden")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise StrictJsonError("input is not valid UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except StrictJsonError:
        raise
    except (json.JSONDecodeError, ValueError) as error:
        raise StrictJsonError("input is not strict JSON") from error
    _reject_surrogates(value)
    return value


def load_core_schemas(repository_root: Path | None = None) -> dict[str, dict[str, Any]]:
    directory = schema_directory(repository_root)
    schemas: dict[str, dict[str, Any]] = {}
    for name in SCHEMA_NAMES:
        value = strict_json_loads((directory / f"{name}.schema.json").read_bytes())
        if not isinstance(value, dict):
            raise StrictJsonError(f"core schema {name!r} is not an object")
        schemas[name] = cast(dict[str, Any], value)
    return schemas


def build_registry(schemas: Mapping[str, Mapping[str, Any]]) -> Registry[Any]:
    registry: Registry[Any] = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def _uri_lexically_valid(value: str) -> bool:
    if not value or any(character not in _URI_CHARACTERS for character in value):
        return False
    index = 0
    while index < len(value):
        if value[index] == "%":
            if index + 2 >= len(value) or not all(
                character in "0123456789abcdefABCDEF" for character in value[index + 1 : index + 3]
            ):
                return False
            index += 3
        else:
            index += 1
    try:
        urlsplit(value)
    except ValueError:
        return False
    return True


def _absolute_uri(value: str) -> bool:
    if not _uri_lexically_valid(value):
        return False
    scheme, separator, _remainder = value.partition(":")
    return bool(separator and _URI_SCHEME.fullmatch(scheme))


def _fragmentless_absolute_uri(value: str) -> bool:
    if "#" in value or not _absolute_uri(value):
        return False
    for match in re.finditer(r"%([0-9A-Fa-f]{2})", value):
        decoded = chr(int(match.group(1), 16))
        if decoded.isascii() and (decoded.isalnum() or decoded in "-._~"):
            return False
    return True


def _uri_reference(value: str) -> bool:
    return _uri_lexically_valid(value)


def _extension_key_valid(value: str) -> bool:
    if value.startswith("https://"):
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.netloc)
    return _URN.fullmatch(value) is not None


def _media_type_valid(value: str) -> bool:
    return _MEDIA_TYPE.fullmatch(value) is not None


def _digest_valid(value: str) -> bool:
    return _DIGEST.fullmatch(value) is not None


def _key_id_valid(value: str) -> bool:
    return _KEY_ID.fullmatch(value) is not None


def _logical_path_violations(value: str, path: str) -> list[CoreViolation]:
    violations: list[CoreViolation] = []
    encoded = value.encode("utf-8")
    if len(encoded) > 1024:
        violations.append(CoreViolation(path, "logical path exceeds 1024 UTF-8 bytes"))
    if value != normalize_nfc(value):
        violations.append(CoreViolation(path, "logical path is not NFC-normalized"))
    if value.startswith("/") or "\\" in value:
        violations.append(CoreViolation(path, "logical path must be relative and slash-separated"))
    if any(character in _FORBIDDEN_PATH_CHARACTERS for character in value) or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in value
    ):
        violations.append(CoreViolation(path, "logical path contains a forbidden character"))
    segments = value.split("/")
    if len(segments) > 64:
        violations.append(CoreViolation(path, "logical path exceeds 64 segments"))
    if any(segment in {"", ".", ".."} for segment in segments):
        violations.append(CoreViolation(path, "logical path contains an empty or dot segment"))
    for segment in segments:
        if len(segment.encode("utf-8")) > 255:
            violations.append(CoreViolation(path, "logical path segment exceeds 255 UTF-8 bytes"))
        if segment.endswith((" ", ".")):
            violations.append(CoreViolation(path, "logical path segment ends in space or dot"))
        basename = _ascii_lower(segment.split(".", 1)[0])
        if basename in _RESERVED_PATH_BASENAMES:
            violations.append(CoreViolation(path, "logical path uses a reserved basename"))
    return violations


def _owned_string_violations(value: object, path: str = "$") -> list[CoreViolation]:
    """Apply the protocol-wide UTF-8 byte ceiling outside opaque content fields."""

    violations: list[CoreViolation] = []
    exempt_values = {"payload", "sig", "publicKey", "message"}
    exempt_subtrees = {"extensions"}
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in exempt_subtrees:
                continue
            if len(key.encode("utf-8")) > 4096:
                violations.append(
                    CoreViolation(child_path, "object member exceeds 4096 UTF-8 bytes")
                )
            if key in exempt_values:
                continue
            violations.extend(_owned_string_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_owned_string_violations(child, f"{path}[{index}]"))
    elif isinstance(value, str) and len(value.encode("utf-8")) > 4096:
        violations.append(CoreViolation(path, "string exceeds 4096 UTF-8 bytes"))
    return violations


def _ascii_lower(value: str) -> str:
    return "".join(
        chr(ord(character) + 0x20) if "A" <= character <= "Z" else character for character in value
    )


def _digest_violations(value: Mapping[str, Any], path: str) -> list[CoreViolation]:
    if not _digest_valid(str(value["sha256"])):
        return [CoreViolation(f"{path}.sha256", "digest must be 64 lowercase hexadecimal digits")]
    return []


def _prefix(violations: Iterable[CoreViolation], prefix: str) -> list[CoreViolation]:
    return [CoreViolation(f"{prefix}{item.path[1:]}", item.message) for item in violations]


def _report_digest_violations(value: object, path: str = "$") -> list[CoreViolation]:
    violations: list[CoreViolation] = []
    if isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_report_digest_violations(child, f"{path}[{index}]"))
    elif isinstance(value, dict):
        if set(value) == {"sha256"}:
            violations.extend(_digest_violations(value, path))
        else:
            for key, child in value.items():
                if key != "context":
                    violations.extend(_report_digest_violations(child, f"{path}.{key}"))
    return violations


def _status_prerequisite_violations(
    status: str,
    prerequisites: Sequence[str],
    path: str,
    *,
    allowed_order: Sequence[str] = _CHECK_ORDER,
) -> list[CoreViolation]:
    violations: list[CoreViolation] = []
    order = {name: index for index, name in enumerate(allowed_order)}
    expected_order = sorted(prerequisites, key=lambda name: order.get(name, len(order)))
    if len(prerequisites) != len(set(prerequisites)) or list(prerequisites) != expected_order:
        violations.append(CoreViolation(path, "prerequisites must be sorted and unique"))
    if any(item not in order for item in prerequisites):
        violations.append(CoreViolation(path, "prerequisite check is invalid"))
    if status == "skipped" and not prerequisites:
        violations.append(CoreViolation(path, "skipped status requires a prerequisite"))
    if status != "skipped" and prerequisites:
        violations.append(CoreViolation(path, "non-skipped status forbids prerequisites"))
    return violations


def _timestamp_valid(value: str) -> bool:
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        return False
    values = {name: int(number) for name, number in match.groupdict(default="0").items()}
    if not 1 <= values["year"] <= 9999:
        return False
    if values["hour"] > 23 or values["minute"] > 59 or values["second"] > 59:
        return False
    try:
        date(values["year"], values["month"], values["day"])
    except ValueError:
        return False
    return True


def _timestamp_order_key(value: str) -> tuple[int, ...]:
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError("invalid timestamp")
    parts = match.groupdict(default="0")
    fraction = parts["fraction"].ljust(9, "0")
    return tuple(
        int(parts[name]) for name in ("year", "month", "day", "hour", "minute", "second")
    ) + (int(fraction),)


def _event_id_valid(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith("urn:uuid:"):
        return value.startswith("urn:uuid:") and _UUID.fullmatch(value[9:]) is not None
    return _UUID.fullmatch(value) is not None or _absolute_uri(value)


def _sorted_unique(
    values: Sequence[T],
    key: Callable[[T], tuple[object, ...]],
    path: str,
) -> list[CoreViolation]:
    keys = [key(value) for value in values]
    violations: list[CoreViolation] = []
    if keys != sorted(keys):
        violations.append(CoreViolation(path, "array is not in canonical order"))
    if len(keys) != len(set(keys)):
        violations.append(CoreViolation(path, "array contains a duplicate logical identity"))
    return violations


def _digest(value: Mapping[str, Any]) -> str:
    return str(value["sha256"])


def _profile_key(value: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        str(value["id"]).encode(),
        _digest(value["digest"]),
        _digest(value["closureDigest"]),
        str(value["target"]).encode(),
        str(value.get("subjectName", "")).encode(),
        str(value.get("mediaType", "")).encode(),
    )


def _profile_reference_violations(profile: Mapping[str, Any], path: str) -> list[CoreViolation]:
    violations: list[CoreViolation] = []
    if not _fragmentless_absolute_uri(str(profile["id"])):
        violations.append(
            CoreViolation(f"{path}.id", "schema ID must be absolute and fragmentless")
        )
    violations.extend(_digest_violations(profile["digest"], f"{path}.digest"))
    violations.extend(_digest_violations(profile["closureDigest"], f"{path}.closureDigest"))
    resources = profile["resources"]
    violations.extend(
        _sorted_unique(
            resources,
            lambda item: (str(item["id"]).encode(), _digest(item["digest"])),
            f"{path}.resources",
        )
    )
    for index, resource in enumerate(resources):
        resource_path = f"{path}.resources[{index}]"
        if not _fragmentless_absolute_uri(str(resource["id"])):
            violations.append(
                CoreViolation(
                    f"{resource_path}.id", "resource ID must be absolute and fragmentless"
                )
            )
        violations.extend(_digest_violations(resource["digest"], f"{resource_path}.digest"))
    descriptor = {
        "resources": resources,
        "root": {"digest": profile["digest"], "id": profile["id"]},
    }
    expected_closure = sha256_bytes(canonical_json(descriptor))
    if _digest(profile["closureDigest"]) != expected_closure:
        violations.append(
            CoreViolation(f"{path}.closureDigest", "closure digest does not match its descriptor")
        )
    if profile.get("target") == "artifact" and not _media_type_valid(str(profile["mediaType"])):
        violations.append(CoreViolation(f"{path}.mediaType", "media type is invalid"))
    return violations


def _profile_constraint_key(value: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        str(value["id"]).encode(),
        str(value["target"]).encode(),
        _digest(value["digest"]) if "digest" in value else "",
        _digest(value["closureDigest"]) if "closureDigest" in value else "",
    )


def _profile_semantics(profile_schema: object) -> list[CoreViolation]:
    violations: list[CoreViolation] = []
    if not isinstance(profile_schema, dict):
        violations.append(CoreViolation("$", "profile resource root must be an object"))
        return violations
    if profile_schema.get("$schema") != (
        "https://usemakoto.dev/schema/v0.2/profile-dialect.schema.json"
    ):
        violations.append(CoreViolation("$.$schema", "profile dialect identifier is required"))
    root_id = profile_schema.get("$id")
    if not isinstance(root_id, str) or not _fragmentless_absolute_uri(root_id):
        violations.append(
            CoreViolation("$.$id", "profile resource ID must be absolute and fragmentless")
        )
    anchors: dict[str, str] = {}

    def walk(schema: object, path: str, *, root: bool = False) -> None:
        if isinstance(schema, bool):
            return
        if not isinstance(schema, dict):
            violations.append(CoreViolation(path, "schema location must be an object or boolean"))
            return
        for keyword in schema:
            if keyword in _PROHIBITED_PROFILE_KEYWORDS:
                violations.append(CoreViolation(f"{path}.{keyword}", "keyword is prohibited"))
            elif keyword not in _PROFILE_KEYWORDS:
                violations.append(CoreViolation(f"{path}.{keyword}", "unknown profile keyword"))
        if not root and "$schema" in schema:
            violations.append(CoreViolation(f"{path}.$schema", "nested $schema is prohibited"))
        nested_id = schema.get("$id")
        if not root and nested_id is not None:
            violations.append(CoreViolation(f"{path}.$id", "nested $id is prohibited"))
        elif nested_id is not None and (
            not isinstance(nested_id, str) or not _fragmentless_absolute_uri(nested_id)
        ):
            violations.append(CoreViolation(f"{path}.$id", "resource ID is invalid"))

        string_keywords = {
            "$schema",
            "$id",
            "$comment",
            "$ref",
            "$anchor",
            "makotoPattern",
            "title",
            "description",
            "contentEncoding",
            "contentMediaType",
            "format",
        }
        boolean_keywords = {"uniqueItems", "deprecated", "readOnly", "writeOnly"}
        nonnegative_integer_keywords = {
            "maxLength",
            "minLength",
            "maxItems",
            "minItems",
            "maxContains",
            "minContains",
            "maxProperties",
            "minProperties",
        }
        number_keywords = {
            "multipleOf",
            "maximum",
            "exclusiveMaximum",
            "minimum",
            "exclusiveMinimum",
        }
        for keyword in string_keywords & schema.keys():
            if not isinstance(schema[keyword], str):
                violations.append(CoreViolation(f"{path}.{keyword}", "keyword must be a string"))
            elif (
                keyword in {"$schema", "$id", "$ref", "$anchor"}
                and len(schema[keyword].encode("utf-8")) > 4096
            ):
                violations.append(
                    CoreViolation(f"{path}.{keyword}", "identifier exceeds 4096 UTF-8 bytes")
                )
        anchor = schema.get("$anchor")
        if isinstance(anchor, str):
            if _ANCHOR.fullmatch(anchor) is None:
                violations.append(CoreViolation(f"{path}.$anchor", "anchor name is invalid"))
            elif anchor in anchors:
                violations.append(
                    CoreViolation(
                        f"{path}.$anchor",
                        f"anchor duplicates the location {anchors[anchor]}",
                    )
                )
            else:
                anchors[anchor] = f"{path}.$anchor"
        pattern = schema.get("makotoPattern")
        if isinstance(pattern, str):
            try:
                compile_pattern(pattern)
            except PatternError as error:
                violations.append(CoreViolation(f"{path}.makotoPattern", str(error)))
        for keyword in boolean_keywords & schema.keys():
            if not isinstance(schema[keyword], bool):
                violations.append(CoreViolation(f"{path}.{keyword}", "keyword must be a boolean"))
        for keyword in nonnegative_integer_keywords & schema.keys():
            value = schema[keyword]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                violations.append(
                    CoreViolation(f"{path}.{keyword}", "keyword must be a nonnegative integer")
                )
        for keyword in number_keywords & schema.keys():
            value = schema[keyword]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                violations.append(CoreViolation(f"{path}.{keyword}", "keyword must be a number"))
        if (
            "multipleOf" in schema
            and isinstance(schema["multipleOf"], (int, float))
            and (isinstance(schema["multipleOf"], bool) or schema["multipleOf"] <= 0)
        ):
            violations.append(CoreViolation(f"{path}.multipleOf", "multipleOf must be positive"))
        if "type" in schema:
            allowed_types = {"null", "boolean", "object", "array", "number", "string", "integer"}
            value = schema["type"]
            valid_type = isinstance(value, str) and value in allowed_types
            valid_types = (
                isinstance(value, list)
                and bool(value)
                and all(isinstance(item, str) and item in allowed_types for item in value)
                and len(value) == len(set(value))
            )
            if not (valid_type or valid_types):
                violations.append(CoreViolation(f"{path}.type", "type keyword is invalid"))
        for keyword in ("required",):
            if keyword in schema:
                value = schema[keyword]
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    violations.append(
                        CoreViolation(f"{path}.{keyword}", "keyword must be a string array")
                    )
                elif len(value) != len(set(value)):
                    violations.append(CoreViolation(f"{path}.{keyword}", "array must be unique"))
        if "dependentRequired" in schema:
            value = schema["dependentRequired"]
            if not isinstance(value, dict):
                violations.append(
                    CoreViolation(f"{path}.dependentRequired", "keyword must be an object")
                )
            else:
                for name, dependencies in value.items():
                    if not isinstance(dependencies, list) or not all(
                        isinstance(item, str) for item in dependencies
                    ):
                        violations.append(
                            CoreViolation(
                                f"{path}.dependentRequired.{name}",
                                "dependency must be a string array",
                            )
                        )
        for keyword in _SCHEMA_MAP_KEYWORDS:
            if keyword in schema and not isinstance(schema[keyword], dict):
                violations.append(CoreViolation(f"{path}.{keyword}", "keyword must be an object"))
        for keyword in _SCHEMA_ARRAY_KEYWORDS:
            if keyword in schema and (not isinstance(schema[keyword], list) or not schema[keyword]):
                violations.append(
                    CoreViolation(f"{path}.{keyword}", "keyword must be a nonempty array")
                )
        for keyword in _SCHEMA_KEYWORDS:
            if keyword in schema and not isinstance(schema[keyword], (bool, dict)):
                violations.append(
                    CoreViolation(f"{path}.{keyword}", "keyword must be a schema object or boolean")
                )
        for keyword in _SCHEMA_MAP_KEYWORDS:
            children = schema.get(keyword)
            if isinstance(children, dict):
                for name, child in children.items():
                    walk(child, f"{path}.{keyword}.{name}")
        for keyword in _SCHEMA_ARRAY_KEYWORDS:
            children = schema.get(keyword)
            if isinstance(children, list):
                for index, child in enumerate(children):
                    walk(child, f"{path}.{keyword}[{index}]")
        for keyword in _SCHEMA_KEYWORDS:
            if keyword in schema:
                walk(schema[keyword], f"{path}.{keyword}")

    walk(profile_schema, "$", root=True)
    return violations


def semantic_violations(schema_name: str, instance: Mapping[str, Any]) -> list[CoreViolation]:
    violations = _owned_string_violations(instance)
    if schema_name == "statement":
        names = [subject["name"] for subject in instance["subject"]]
        if len(names) != len(set(names)):
            violations.append(CoreViolation("$.subject", "subject names must be unique"))
        for index, subject in enumerate(instance["subject"]):
            violations.extend(_digest_violations(subject["digest"], f"$.subject[{index}].digest"))
        predicate_type = str(instance["predicateType"])
        if not _absolute_uri(predicate_type):
            violations.append(
                CoreViolation("$.predicateType", "predicate type must be an absolute URI")
            )
        nested_schema = {
            "https://usemakoto.dev/predicate/v0.2/origin": "origin",
            "https://usemakoto.dev/predicate/v0.2/transform": "transform",
        }.get(predicate_type)
        if nested_schema is not None:
            violations.extend(
                _prefix(semantic_violations(nested_schema, instance["predicate"]), "$.predicate")
            )
    elif schema_name in {"origin", "transform"}:
        event = instance["event"]
        if not _event_id_valid(event["id"]):
            violations.append(
                CoreViolation("$.event.id", "event ID is not an absolute URI or canonical UUID")
            )
        if not _timestamp_valid(event["occurredAt"]):
            violations.append(
                CoreViolation("$.event.occurredAt", "timestamp is not a valid UTC RFC 3339 instant")
            )
        profiles = instance.get("profiles", [])
        profile_keys = [_profile_key(profile) for profile in profiles]
        if len(profile_keys) != len(set(profile_keys)):
            violations.append(CoreViolation("$.profiles", "profile references must be unique"))
        for index, profile in enumerate(profiles):
            violations.extend(_profile_reference_violations(profile, f"$.profiles[{index}]"))
        for extension_key in instance.get("extensions", {}):
            if len(extension_key.encode("utf-8")) > 4096:
                violations.append(
                    CoreViolation(
                        f"$.extensions.{extension_key}",
                        "extension key exceeds 4096 UTF-8 bytes",
                    )
                )
            if not _extension_key_valid(extension_key):
                violations.append(
                    CoreViolation(
                        f"$.extensions.{extension_key}", "extension key is not HTTPS or URN"
                    )
                )
        if schema_name == "origin":
            source = instance["source"]
            if not _absolute_uri(source["kind"]):
                violations.append(
                    CoreViolation("$.source.kind", "source kind must be an absolute URI")
                )
            if "retrievedAt" in source and not _timestamp_valid(source["retrievedAt"]):
                violations.append(CoreViolation("$.source.retrievedAt", "timestamp is invalid"))
            if "uri" in source and not _uri_reference(str(source["uri"])):
                violations.append(CoreViolation("$.source.uri", "source URI-reference is invalid"))
            if "mediaType" in source and not _media_type_valid(str(source["mediaType"])):
                violations.append(CoreViolation("$.source.mediaType", "media type is invalid"))
        else:
            inputs = instance["inputs"]
            names = [item["name"] for item in inputs]
            if len(names) != len(set(names)):
                violations.append(CoreViolation("$.inputs", "input names must be unique"))
            identities = [
                (
                    item["name"],
                    _digest(item["provenance"]["statementDigest"]),
                    item["provenance"]["subjectName"],
                    item["provenance"].get("entryName"),
                    _digest(item["digest"]),
                )
                for item in inputs
            ]
            if len(identities) != len(set(identities)):
                violations.append(
                    CoreViolation("$.inputs", "input provenance identities must be unique")
                )
            if not _absolute_uri(instance["operation"]["type"]):
                violations.append(
                    CoreViolation("$.operation.type", "operation type must be an absolute URI")
                )
            for index, item in enumerate(inputs):
                violations.extend(_digest_violations(item["digest"], f"$.inputs[{index}].digest"))
                violations.extend(
                    _digest_violations(
                        item["provenance"]["statementDigest"],
                        f"$.inputs[{index}].provenance.statementDigest",
                    )
                )
                entry_name = item["provenance"].get("entryName")
                if entry_name is not None:
                    violations.extend(
                        _logical_path_violations(
                            entry_name,
                            f"$.inputs[{index}].provenance.entryName",
                        )
                    )
            operation = instance["operation"]
            if "parametersDigest" in operation:
                violations.extend(
                    _digest_violations(
                        operation["parametersDigest"], "$.operation.parametersDigest"
                    )
                )
            tool = operation.get("tool")
            if isinstance(tool, dict):
                if "uri" in tool and not _absolute_uri(str(tool["uri"])):
                    violations.append(CoreViolation("$.operation.tool.uri", "tool URI is invalid"))
                if "digest" in tool:
                    violations.extend(_digest_violations(tool["digest"], "$.operation.tool.digest"))
    elif schema_name == "profile-reference":
        violations.extend(_profile_reference_violations(instance, "$"))
    elif schema_name == "profile-dialect":
        violations.extend(_profile_semantics(instance))
    elif schema_name == "catalog":
        violations.extend(
            _sorted_unique(
                instance["resources"],
                lambda item: (str(item["id"]).encode(), _digest(item["digest"])),
                "$.resources",
            )
        )
        for index, resource in enumerate(instance["resources"]):
            if not _fragmentless_absolute_uri(str(resource["id"])):
                violations.append(
                    CoreViolation(f"$.resources[{index}].id", "resource ID is invalid")
                )
            violations.extend(
                _digest_violations(resource["digest"], f"$.resources[{index}].digest")
            )
            violations.extend(
                _logical_path_violations(resource["path"], f"$.resources[{index}].path")
            )
    elif schema_name == "dataset-manifest":
        violations.extend(
            _sorted_unique(
                instance["entries"],
                lambda item: (str(item["name"]).encode(),),
                "$.entries",
            )
        )
        normalized_names: dict[str, int] = {}
        folded_names: dict[str, int] = {}
        for index, entry in enumerate(instance["entries"]):
            name = str(entry["name"])
            violations.extend(_logical_path_violations(name, f"$.entries[{index}].name"))
            normalized = normalize_nfc(name)
            previous_normalized = normalized_names.get(normalized)
            if previous_normalized is not None:
                violations.append(
                    CoreViolation(
                        f"$.entries[{index}].name",
                        "dataset entry name duplicates "
                        f"$.entries[{previous_normalized}].name after NFC normalization",
                    )
                )
            else:
                normalized_names[normalized] = index
            folded = casefold(normalized)
            previous_folded = folded_names.get(folded)
            if previous_folded is not None:
                violations.append(
                    CoreViolation(
                        f"$.entries[{index}].name",
                        "dataset entry name duplicates "
                        f"$.entries[{previous_folded}].name after Unicode 15.0 full case folding",
                    )
                )
            else:
                folded_names[folded] = index
            violations.extend(_digest_violations(entry["digest"], f"$.entries[{index}].digest"))
            if "mediaType" in entry and not _media_type_valid(str(entry["mediaType"])):
                violations.append(
                    CoreViolation(f"$.entries[{index}].mediaType", "media type is invalid")
                )
    elif schema_name == "handoff":
        for field in ("roots", "heads", "statements"):
            violations.extend(
                _sorted_unique(
                    instance[field],
                    lambda item: (_digest(item),),
                    f"$.{field}",
                )
            )
            for index, digest in enumerate(instance[field]):
                violations.extend(_digest_violations(digest, f"$.{field}[{index}]"))
        violations.extend(
            _sorted_unique(
                instance["artifacts"],
                lambda item: (
                    _digest(item["head"]),
                    str(item["name"]).encode(),
                    _digest(item["digest"]),
                ),
                "$.artifacts",
            )
        )
        violations.extend(
            _sorted_unique(
                instance["requiredProfiles"],
                lambda item: (
                    (_digest(item["head"]),) + _profile_key(item) + (str(item["scope"]).encode(),)
                ),
                "$.requiredProfiles",
            )
        )
        if not _timestamp_valid(instance["issuedAt"]):
            violations.append(CoreViolation("$.issuedAt", "timestamp is invalid"))
        if not _event_id_valid(str(instance["bundleId"])):
            violations.append(CoreViolation("$.bundleId", "bundle ID is invalid"))
        for index, artifact in enumerate(instance["artifacts"]):
            violations.extend(_digest_violations(artifact["head"], f"$.artifacts[{index}].head"))
            violations.extend(
                _digest_violations(artifact["digest"], f"$.artifacts[{index}].digest")
            )
            if "mediaType" in artifact and not _media_type_valid(str(artifact["mediaType"])):
                violations.append(
                    CoreViolation(f"$.artifacts[{index}].mediaType", "media type is invalid")
                )
        for index, required in enumerate(instance["requiredProfiles"]):
            required_path = f"$.requiredProfiles[{index}]"
            if not _fragmentless_absolute_uri(str(required["id"])):
                violations.append(CoreViolation(f"{required_path}.id", "schema ID is invalid"))
            violations.extend(_digest_violations(required["digest"], f"{required_path}.digest"))
            violations.extend(
                _digest_violations(required["closureDigest"], f"{required_path}.closureDigest")
            )
            if not _media_type_valid(str(required["mediaType"])):
                violations.append(
                    CoreViolation(f"{required_path}.mediaType", "media type is invalid")
                )
            violations.extend(
                _digest_violations(required["head"], f"$.requiredProfiles[{index}].head")
            )
        for field in ("recipient", "nonce"):
            if field in instance and any(is_control(character) for character in instance[field]):
                violations.append(CoreViolation(f"$.{field}", "control scalar is prohibited"))
    elif schema_name == "bundle":
        sort_rules: tuple[tuple[str, Callable[[Mapping[str, Any]], tuple[object, ...]]], ...] = (
            ("attestations", lambda item: (_digest(item["statementDigest"]),)),
            (
                "artifacts",
                lambda item: (
                    _digest(item["statementDigest"]),
                    str(item["subjectName"]).encode(),
                    _digest(item["digest"]),
                ),
            ),
            (
                "datasetEntries",
                lambda item: (
                    _digest(item["manifestStatementDigest"]),
                    str(item["manifestSubjectName"]).encode(),
                    str(item["entryName"]).encode(),
                ),
            ),
        )
        for field, key in sort_rules:
            violations.extend(_sorted_unique(instance.get(field, []), key, f"$.{field}"))
        path_fields: list[tuple[str, str]] = [("$.manifest", instance["manifest"])]
        if "schemaCatalog" in instance:
            path_fields.append(("$.schemaCatalog", instance["schemaCatalog"]))
        for field in ("attestations", "artifacts", "datasetEntries"):
            for index, item in enumerate(instance.get(field, [])):
                path_fields.append((f"$.{field}[{index}].path", item["path"]))
        for path, value in path_fields:
            violations.extend(_logical_path_violations(value, path))
        for index, item in enumerate(instance["attestations"]):
            violations.extend(
                _digest_violations(
                    item["statementDigest"], f"$.attestations[{index}].statementDigest"
                )
            )
        for index, item in enumerate(instance["artifacts"]):
            violations.extend(
                _digest_violations(item["statementDigest"], f"$.artifacts[{index}].statementDigest")
            )
            violations.extend(_digest_violations(item["digest"], f"$.artifacts[{index}].digest"))
        for index, item in enumerate(instance.get("datasetEntries", [])):
            violations.extend(
                _digest_violations(
                    item["manifestStatementDigest"],
                    f"$.datasetEntries[{index}].manifestStatementDigest",
                )
            )
            violations.extend(
                _digest_violations(item["digest"], f"$.datasetEntries[{index}].digest")
            )
    elif schema_name == "envelope":
        try:
            validate_payload_type(str(instance["payloadType"]), require_supported=False)
        except DsseError as error:
            violations.append(CoreViolation("$.payloadType", str(error)))
        try:
            canonical_b64decode(str(instance["payload"]))
        except DsseError as error:
            violations.append(CoreViolation("$.payload", str(error)))
        key_ids: list[str] = []
        for index, signature in enumerate(instance["signatures"]):
            key_id = str(signature["keyid"])
            key_ids.append(key_id)
            if not _key_id_valid(key_id):
                violations.append(
                    CoreViolation(f"$.signatures[{index}].keyid", "key ID is invalid")
                )
            try:
                canonical_b64decode(str(signature["sig"]), expected_length=64)
            except DsseError as error:
                violations.append(CoreViolation(f"$.signatures[{index}].sig", str(error)))
        if len(key_ids) != len(set(key_ids)):
            violations.append(CoreViolation("$.signatures", "signature key IDs must be unique"))
    elif schema_name == "verification-report":
        violations.extend(_report_digest_violations(instance))
        if not _timestamp_valid(str(instance["evaluationTime"])):
            violations.append(CoreViolation("$.evaluationTime", "timestamp is invalid"))
        for signature_group_path, signatures in (
            ("$.handoff.signatures", instance["handoff"]["signatures"]),
        ):
            for index, signature in enumerate(signatures):
                if not _key_id_valid(str(signature["keyid"])):
                    violations.append(
                        CoreViolation(f"{signature_group_path}[{index}].keyid", "key ID is invalid")
                    )
        for statement_index, statement_record in enumerate(instance["statements"]):
            for signature_index, signature in enumerate(statement_record["signatures"]):
                if not _key_id_valid(str(signature["keyid"])):
                    violations.append(
                        CoreViolation(
                            f"$.statements[{statement_index}].signatures[{signature_index}].keyid",
                            "key ID is invalid",
                        )
                    )
            for status_field, prerequisites_field in (
                ("coreSchema", "coreSchemaPrerequisiteChecks"),
                ("authorization", "authorizationPrerequisiteChecks"),
                ("graph", "graphPrerequisiteChecks"),
            ):
                violations.extend(
                    _status_prerequisite_violations(
                        statement_record[status_field],
                        statement_record[prerequisites_field],
                        f"$.statements[{statement_index}].{prerequisites_field}",
                        allowed_order=_RECORD_PREREQUISITE_ORDER,
                    )
                )
        for profile_index, profile_record in enumerate(instance["profiles"]):
            prerequisites = profile_record["prerequisiteChecks"]
            violations.extend(
                _status_prerequisite_violations(
                    profile_record["validation"],
                    prerequisites,
                    f"$.profiles[{profile_index}].prerequisiteChecks",
                    allowed_order=_PROFILE_PREREQUISITE_ORDER,
                )
            )
        for artifact_index, artifact in enumerate(instance["artifacts"]):
            for status_field, prerequisites_field in (
                ("digestStatus", "digestPrerequisiteChecks"),
                ("profileStatus", "profilePrerequisiteChecks"),
            ):
                violations.extend(
                    _status_prerequisite_violations(
                        artifact[status_field],
                        artifact[prerequisites_field],
                        f"$.artifacts[{artifact_index}].{prerequisites_field}",
                        allowed_order=_RECORD_PREREQUISITE_ORDER,
                    )
                )
        for entry_index, entry in enumerate(instance["datasetEntries"]):
            if (
                entry["declaredSize"] is not None
                and _DECIMAL.fullmatch(entry["declaredSize"]) is None
            ):
                violations.append(
                    CoreViolation(
                        f"$.datasetEntries[{entry_index}].declaredSize", "decimal is invalid"
                    )
                )
            for status_field, prerequisites_field in (
                ("digestStatus", "digestPrerequisiteChecks"),
                ("sizeStatus", "sizePrerequisiteChecks"),
            ):
                violations.extend(
                    _status_prerequisite_violations(
                        entry[status_field],
                        entry[prerequisites_field],
                        f"$.datasetEntries[{entry_index}].{prerequisites_field}",
                        allowed_order=_RECORD_PREREQUISITE_ORDER,
                    )
                )
        for check_index, check in enumerate(instance["checks"]):
            violations.extend(
                _status_prerequisite_violations(
                    check["status"],
                    check["prerequisiteChecks"],
                    f"$.checks[{check_index}].prerequisiteChecks",
                    allowed_order=_CHECK_ORDER[:check_index],
                )
            )
        for collection in ("warnings", "errors"):
            for index, diagnostic in enumerate(instance[collection]):
                path = f"$.{collection}[{index}]"
                if diagnostic["causedByCheck"] not in _CHECK_IDS:
                    violations.append(
                        CoreViolation(f"{path}.causedByCheck", "diagnostic owner is invalid")
                    )
                unknown_context = set(diagnostic["context"]) - _DIAGNOSTIC_CONTEXT_KEYS
                if unknown_context:
                    violations.append(
                        CoreViolation(
                            f"{path}.context",
                            "diagnostic context contains unknown members "
                            f"{sorted(unknown_context)!r}",
                        )
                    )
    elif schema_name == "trust-policy":
        violations.extend(
            _sorted_unique(instance["rules"], lambda item: (str(item["id"]).encode(),), "$.rules")
        )
        violations.extend(
            _sorted_unique(instance["requiredProfiles"], _profile_key, "$.requiredProfiles")
        )
        trust_key_ids = set(instance["keys"])
        for key_id, key in instance["keys"].items():
            if not _key_id_valid(str(key_id)):
                violations.append(CoreViolation(f"$.keys.{key_id}", "key ID is invalid"))
            try:
                spki = canonical_b64decode(str(key["publicKey"]), expected_length=44)
                computed_key_id = keyid_from_spki(spki)
            except DsseError as error:
                violations.append(CoreViolation(f"$.keys.{key_id}.publicKey", str(error)))
            else:
                if computed_key_id != key_id:
                    violations.append(
                        CoreViolation(f"$.keys.{key_id}", "key ID does not match public key bytes")
                    )
            for endpoint in ("validFrom", "validUntil"):
                if endpoint in key and not _timestamp_valid(str(key[endpoint])):
                    violations.append(
                        CoreViolation(f"$.keys.{key_id}.{endpoint}", "timestamp is invalid")
                    )
            if (
                "validFrom" in key
                and "validUntil" in key
                and _timestamp_valid(str(key["validFrom"]))
                and _timestamp_valid(str(key["validUntil"]))
                and _timestamp_order_key(str(key["validFrom"]))
                >= _timestamp_order_key(str(key["validUntil"]))
            ):
                violations.append(
                    CoreViolation(f"$.keys.{key_id}", "validFrom must be earlier than validUntil")
                )
        for path, rule in (("$.handoff", instance["handoff"]),) + tuple(
            (f"$.rules[{index}]", rule) for index, rule in enumerate(instance["rules"])
        ):
            authorized = rule["authorizedKeyIds"]
            if authorized != sorted(authorized, key=str.encode) or len(authorized) != len(
                set(authorized)
            ):
                violations.append(
                    CoreViolation(f"{path}.authorizedKeyIds", "key IDs must be sorted and unique")
                )
            if not set(authorized).issubset(trust_key_ids):
                violations.append(CoreViolation(f"{path}.authorizedKeyIds", "unknown key ID"))
            if rule["minimumSignatures"] > len(set(authorized)):
                violations.append(
                    CoreViolation(f"{path}.minimumSignatures", "threshold exceeds authorized keys")
                )
        core_origin = "https://usemakoto.dev/predicate/v0.2/origin"
        core_transform = "https://usemakoto.dev/predicate/v0.2/transform"
        for index, rule in enumerate(instance["rules"]):
            path = f"$.rules[{index}]"
            if not _absolute_uri(str(rule["id"])):
                violations.append(CoreViolation(f"{path}.id", "rule ID must be an absolute URI"))
            scalar_arrays = (
                "predicateTypes",
                "authorizedKeyIds",
                "sourceKinds",
                "sourceUris",
                "operationTypes",
            )
            for field in scalar_arrays:
                if field not in rule:
                    continue
                values = rule[field]
                if values != sorted(values, key=str.encode) or len(values) != len(set(values)):
                    violations.append(
                        CoreViolation(f"{path}.{field}", "array must be sorted and unique")
                    )
            for field in ("predicateTypes", "sourceKinds", "operationTypes"):
                for item_index, value in enumerate(rule.get(field, [])):
                    if not _absolute_uri(str(value)):
                        violations.append(
                            CoreViolation(f"{path}.{field}[{item_index}]", "URI is invalid")
                        )
            for item_index, value in enumerate(rule.get("sourceUris", [])):
                if not _uri_reference(str(value)):
                    violations.append(
                        CoreViolation(
                            f"{path}.sourceUris[{item_index}]", "URI-reference is invalid"
                        )
                    )
            predicates = set(rule["predicateTypes"])
            has_source_selector = "sourceKinds" in rule or "sourceUris" in rule
            has_operation_selector = "operationTypes" in rule
            if not predicates.intersection({core_origin, core_transform}):
                violations.append(CoreViolation(path, "rule has no supported core predicate"))
            if has_source_selector and core_origin not in predicates:
                violations.append(CoreViolation(path, "source selector cannot match this rule"))
            if has_operation_selector and core_transform not in predicates:
                violations.append(CoreViolation(path, "operation selector cannot match this rule"))
            if has_source_selector and has_operation_selector:
                violations.append(CoreViolation(path, "source and operation selectors conflict"))
            constraints = rule.get("profileConstraints", [])
            violations.extend(
                _sorted_unique(constraints, _profile_constraint_key, f"{path}.profileConstraints")
            )
            for constraint_index, constraint in enumerate(constraints):
                constraint_path = f"{path}.profileConstraints[{constraint_index}]"
                if not _fragmentless_absolute_uri(str(constraint["id"])):
                    violations.append(
                        CoreViolation(f"{constraint_path}.id", "schema ID is invalid")
                    )
                for digest_field in ("digest", "closureDigest"):
                    if digest_field in constraint:
                        violations.extend(
                            _digest_violations(
                                constraint[digest_field], f"{constraint_path}.{digest_field}"
                            )
                        )
        for index, required in enumerate(instance["requiredProfiles"]):
            path = f"$.requiredProfiles[{index}]"
            if not _fragmentless_absolute_uri(str(required["id"])):
                violations.append(CoreViolation(f"{path}.id", "schema ID is invalid"))
            if not _media_type_valid(str(required["mediaType"])):
                violations.append(CoreViolation(f"{path}.mediaType", "media type is invalid"))
            violations.extend(_digest_violations(required["digest"], f"{path}.digest"))
            violations.extend(
                _digest_violations(required["closureDigest"], f"{path}.closureDigest")
            )
        required_media: dict[str, set[str]] = {}
        for required in instance["requiredProfiles"]:
            required_media.setdefault(str(required["subjectName"]), set()).add(
                str(required["mediaType"])
            )
        for subject_name, media_types in sorted(required_media.items()):
            if len(media_types) > 1:
                violations.append(
                    CoreViolation(
                        "$.requiredProfiles",
                        f"required profiles disagree on media type for {subject_name!r}",
                    )
                )
    return violations


def validate_core(
    schema_name: str,
    instance: object,
    *,
    repository_root: Path | None = None,
) -> None:
    if schema_name not in SCHEMA_NAMES:
        raise ValueError(f"unknown core schema {schema_name!r}")
    schemas = load_core_schemas(repository_root)
    validator = Draft202012Validator(schemas[schema_name], registry=build_registry(schemas))
    schema_errors = sorted(
        validator.iter_errors(instance), key=lambda error: list(error.absolute_path)
    )
    violations = [
        CoreViolation(
            "$" + "".join(f"[{part!r}]" for part in error.absolute_path),
            error.message,
        )
        for error in schema_errors
    ]
    if not violations and schema_name == "profile-dialect":
        violations.extend(_profile_semantics(instance))
    elif not violations and isinstance(instance, dict):
        violations.extend(semantic_violations(schema_name, instance))
    if violations:
        raise CoreValidationError(violations)


def load_catalog_resources(
    catalog_paths: Sequence[Path], *, repository_root: Path | None = None
) -> dict[tuple[str, str], CatalogResource]:
    """Load strict, local-only catalogs and verify every declared resource binding."""

    resources: dict[tuple[str, str], CatalogResource] = {}
    for catalog_path in catalog_paths:
        parsed = strict_json_loads(catalog_path.read_bytes())
        if not isinstance(parsed, dict):
            raise ProfileResolutionError(f"catalog {catalog_path} is not an object")
        validate_core("catalog", parsed, repository_root=repository_root)
        for item in parsed["resources"]:
            resource_path = catalog_path.parent / item["path"]
            exact_bytes = resource_path.read_bytes()
            digest = sha256_bytes(exact_bytes)
            if digest != item["digest"]["sha256"]:
                raise ProfileResolutionError(f"catalog resource digest mismatch: {item['id']}")
            value = strict_json_loads(exact_bytes)
            if not isinstance(value, dict) or value.get("$id") != item["id"]:
                raise ProfileResolutionError(f"catalog resource ID mismatch: {item['id']}")
            key = (item["id"], digest)
            candidate = CatalogResource(item["id"], digest, exact_bytes, value)
            previous = resources.get(key)
            if previous is not None and previous.exact_bytes != exact_bytes:
                raise ProfileResolutionError(
                    f"conflicting bytes for catalog resource: {item['id']}"
                )
            resources[key] = candidate
    return resources


def validate_with_catalog(
    instance: object,
    profile_reference: Mapping[str, Any],
    *,
    catalog_paths: Sequence[Path],
    repository_root: Path | None = None,
) -> ProfileResult:
    """Resolve one exact profile closure offline and validate an instance."""

    verify_standard_registry()
    validate_core("profile-reference", profile_reference, repository_root=repository_root)
    if profile_reference["id"] == DATASET_MANIFEST_SCHEMA_ID:
        subject_name = profile_reference.get("subjectName")
        if not isinstance(subject_name, str) or profile_reference != (
            core_dataset_manifest_profile_reference(subject_name, repository_root=repository_root)
        ):
            raise ProfileResolutionError(
                "dataset-manifest profile does not match the immutable core identity"
            )
        try:
            validate_core("dataset-manifest", instance, repository_root=repository_root)
        except CoreValidationError as error:
            return ProfileResult(valid=False, errors=(str(error),))
        return ProfileResult(valid=True, errors=())
    resources = load_catalog_resources(catalog_paths, repository_root=repository_root)
    root_key = (profile_reference["id"], profile_reference["digest"]["sha256"])
    root = resources.get(root_key)
    if root is None:
        raise ProfileResolutionError(f"profile root is unavailable: {profile_reference['id']}")
    declared_keys = {
        (item["id"], item["digest"]["sha256"]) for item in profile_reference["resources"]
    }
    discovered_keys = _discover_external_resources(root.schema, root.identifier, resources)
    if discovered_keys != declared_keys:
        raise ProfileResolutionError(
            "declared resources do not equal the transitive schema closure"
        )
    resolved: list[CatalogResource] = [root]
    for key in sorted(declared_keys):
        resource = resources.get(key)
        if resource is None:
            raise ProfileResolutionError(f"profile resource is unavailable: {key[0]}")
        resolved.append(resource)
    for resource in resolved:
        validate_core("profile-dialect", resource.schema, repository_root=repository_root)
    registry: Registry[Any] = Registry()
    for core_schema in load_core_schemas(repository_root).values():
        registry = registry.with_resource(core_schema["$id"], Resource.from_contents(core_schema))
    for resource in resolved:
        registry = registry.with_resource(
            resource.identifier,
            Resource.from_contents(resource.schema, default_specification=DRAFT202012),
        )
    validator = MakotoProfileValidator(root.schema, registry=registry)
    errors = tuple(
        error.message
        for error in sorted(
            validator.iter_errors(instance), key=lambda error: list(error.absolute_path)
        )
    )
    return ProfileResult(valid=not errors, errors=errors)


def validate_with_schema_bytes(
    instance: object,
    schema_bytes: bytes,
    *,
    expected_identifier: str | None = None,
    expected_digest: str | None = None,
    repository_root: Path | None = None,
) -> ProfileResult:
    """Validate one instance against a standalone, offline profile-dialect schema.

    Bare-schema mode deliberately has no ambient resolver. The root may use local
    fragments and immutable Makoto core resources, but every organizational
    dependency must instead be expressed through a digest-pinned profile reference.
    """

    if len(schema_bytes) > 16 * 1024 * 1024:
        raise ProfileResolutionError("schema resource exceeds the 16 MiB bootstrap ceiling")
    actual_digest = sha256_bytes(schema_bytes)
    if expected_digest is not None and actual_digest != expected_digest:
        raise ProfileResolutionError("schema digest does not match the selected schema")
    root = strict_json_loads(schema_bytes)
    if not isinstance(root, dict):
        raise ProfileResolutionError("schema root must be one JSON object")
    validate_core("profile-dialect", root, repository_root=repository_root)
    root_identifier = root.get("$id")
    if expected_identifier is not None and root_identifier != expected_identifier:
        raise ProfileResolutionError("schema $id does not match the selected URI")

    for reference in _schema_references(root):
        identifier = reference.split("#", 1)[0]
        if not identifier:
            continue
        if not identifier.startswith("https://usemakoto.dev/schema/v0.2/"):
            raise ProfileResolutionError(
                f"bare schema has a non-core external reference: {identifier}"
            )

    registry: Registry[Any] = Registry()
    for core_schema in load_core_schemas(repository_root).values():
        registry = registry.with_resource(core_schema["$id"], Resource.from_contents(core_schema))
    validator = MakotoProfileValidator(root, registry=registry)
    errors = tuple(
        error.message
        for error in sorted(
            validator.iter_errors(instance), key=lambda error: list(error.absolute_path)
        )
    )
    return ProfileResult(valid=not errors, errors=errors)


def create_profile_reference(
    root_path: Path,
    *,
    target: str,
    critical: bool,
    catalog_paths: Sequence[Path],
    subject_name: str | None = None,
    media_type: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Create a digest-pinned reference for a root with an explicitly cataloged closure."""

    root_bytes = root_path.read_bytes()
    root_value = strict_json_loads(root_bytes)
    if not isinstance(root_value, dict):
        raise ProfileResolutionError("profile root must be an object")
    root_id = root_value["$id"]
    if root_id == DATASET_MANIFEST_SCHEMA_ID:
        expected_bytes = (
            schema_directory(repository_root) / "dataset-manifest.schema.json"
        ).read_bytes()
        if root_bytes != expected_bytes:
            raise ProfileResolutionError(
                "dataset-manifest profile root must be the exact immutable core schema"
            )
        if (
            target != "artifact"
            or not critical
            or subject_name is None
            or media_type != DATASET_MANIFEST_MEDIA_TYPE
            or catalog_paths
        ):
            raise ProfileResolutionError(
                "dataset-manifest profile requires target=artifact, critical=true, the "
                "core media type, a subject name, and no external catalog"
            )
        return core_dataset_manifest_profile_reference(
            subject_name, repository_root=repository_root
        )
    validate_core("profile-dialect", root_value, repository_root=repository_root)
    resources = load_catalog_resources(catalog_paths, repository_root=repository_root)
    root_digest = sha256_bytes(root_bytes)
    declared_resources = _discover_external_resources(root_value, root_id, resources)
    resource_refs = [
        {"id": identifier, "digest": {"sha256": digest}}
        for identifier, digest in sorted(declared_resources)
    ]
    descriptor = {
        "resources": resource_refs,
        "root": {"digest": {"sha256": root_digest}, "id": root_id},
    }
    reference: dict[str, Any] = {
        "id": root_id,
        "digest": {"sha256": root_digest},
        "closureDigest": {"sha256": sha256_bytes(canonical_json(descriptor))},
        "target": target,
        "critical": critical,
        "resources": resource_refs,
    }
    if target == "artifact":
        if subject_name is None or media_type is None:
            raise ProfileResolutionError("artifact profile requires subject name and media type")
        reference.update(subjectName=subject_name, mediaType=media_type)
    elif subject_name is not None or media_type is not None:
        raise ProfileResolutionError("non-artifact profile forbids subject name and media type")
    validate_core("profile-reference", reference, repository_root=repository_root)
    return reference


def core_dataset_manifest_profile_reference(
    subject_name: str,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Return the sole exact core profile identity for one dataset-manifest subject."""

    if not subject_name:
        raise ProfileResolutionError("dataset-manifest profile requires a subject name")
    root_path = schema_directory(repository_root) / "dataset-manifest.schema.json"
    root_bytes = root_path.read_bytes()
    actual_digest = sha256_bytes(root_bytes)
    catalog_value = strict_json_loads(
        (schema_directory(repository_root) / "catalog.json").read_bytes()
    )
    if not isinstance(catalog_value, dict):
        raise ProfileResolutionError("core schema catalog is not an object")
    matches = [
        resource
        for resource in catalog_value.get("resources", [])
        if isinstance(resource, dict) and resource.get("id") == DATASET_MANIFEST_SCHEMA_ID
    ]
    if len(matches) != 1 or matches[0].get("digest") != {"sha256": actual_digest}:
        raise ProfileResolutionError(
            "dataset-manifest schema bytes do not match the immutable core catalog"
        )
    root_digest = cast(dict[str, str], matches[0]["digest"])
    descriptor = {
        "resources": [],
        "root": {"digest": root_digest, "id": DATASET_MANIFEST_SCHEMA_ID},
    }
    reference: dict[str, Any] = {
        "id": DATASET_MANIFEST_SCHEMA_ID,
        "digest": root_digest,
        "closureDigest": digest_object(sha256_bytes(canonical_json(descriptor))),
        "target": "artifact",
        "subjectName": subject_name,
        "mediaType": DATASET_MANIFEST_MEDIA_TYPE,
        "critical": True,
        "resources": [],
    }
    validate_core("profile-reference", reference, repository_root=repository_root)
    return reference


def _discover_external_resources(
    root: Mapping[str, Any],
    root_id: str,
    resources: Mapping[tuple[str, str], CatalogResource],
) -> set[tuple[str, str]]:
    by_id: dict[str, list[CatalogResource]] = {}
    for resource in resources.values():
        by_id.setdefault(resource.identifier, []).append(resource)
    discovered: set[tuple[str, str]] = set()
    pending: list[tuple[Mapping[str, Any], str]] = [(root, root_id)]
    while pending:
        schema, base_id = pending.pop()
        for reference in _schema_references(schema):
            resolved = urlsplit(reference)
            identifier = reference.split("#", 1)[0]
            if not identifier or identifier == base_id:
                continue
            if identifier.startswith("https://usemakoto.dev/schema/v0.2/"):
                continue
            if not resolved.scheme:
                from urllib.parse import urljoin

                identifier = urljoin(base_id, identifier)
            if identifier.startswith("https://usemakoto.dev/schema/v0.2/"):
                continue
            candidates = by_id.get(identifier, [])
            if len(candidates) != 1:
                raise ProfileResolutionError(
                    f"external resource {identifier!r} must resolve to exactly one digest"
                )
            resource = candidates[0]
            key = (resource.identifier, resource.digest)
            if key not in discovered:
                discovered.add(key)
                pending.append((resource.schema, resource.identifier))
    return discovered


def _schema_references(schema: object) -> list[str]:
    references: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, dict):
            return
        reference = value.get("$ref")
        if isinstance(reference, str):
            references.append(reference)
        for keyword in _SCHEMA_MAP_KEYWORDS:
            children = value.get(keyword)
            if isinstance(children, dict):
                for child in children.values():
                    walk(child)
        for keyword in _SCHEMA_ARRAY_KEYWORDS:
            children = value.get(keyword)
            if isinstance(children, list):
                for child in children:
                    walk(child)
        for keyword in _SCHEMA_KEYWORDS:
            if keyword in value:
                walk(value[keyword])

    walk(schema)
    return references
