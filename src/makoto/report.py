"""Stable Makoto v0.2 verification-report construction and serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from makoto.canonical import canonical_json

CHECK_IDS = (
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


@dataclass(frozen=True)
class Diagnostic:
    code: str
    step: int
    message: str
    owner: str
    context: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "step": self.step,
            "message": self.message,
            "context": self.context,
            "causedByCheck": self.owner,
        }


def empty_summary() -> dict[str, int | None]:
    return {
        "statementsTotal": 0,
        "quarantinedStatementsTotal": 0,
        "statementsReachable": 0,
        "statementsValid": 0,
        "statementsAuthorized": 0,
        "signaturesTotal": 0,
        "signaturesChecked": 0,
        "signaturesValid": 0,
        "manifestSignaturesRequired": 0,
        "manifestSignaturesValid": 0,
        "manifestSignaturesAuthorized": 0,
        "roots": 0,
        "heads": 0,
        "artifactsDeclared": 0,
        "artifactsChecked": 0,
        "historicalMaterialsDeclared": 0,
        "historicalMaterialsChecked": 0,
        "profilesDeclared": 0,
        "profilesValidated": 0,
    }


def new_report(
    *,
    evaluation_time: str,
    policy_digest: dict[str, str],
    core_catalog_digest: dict[str, str],
) -> dict[str, Any]:
    return {
        "reportVersion": "0.2",
        "decision": "deny",
        "reportTruncated": False,
        "primaryError": None,
        "bundleId": None,
        "evaluationTime": evaluation_time,
        "policyDigest": policy_digest,
        "policyDigestEncoding": "exact-input-bytes",
        "coreCatalogDigest": core_catalog_digest,
        "manifestDigest": None,
        "expectedManifestDigest": None,
        "handoff": {
            "signatures": [],
            "authorization": "skipped",
            "completeness": "skipped",
            "freshnessMethod": "none",
            "freshnessChecks": {
                "expected-manifest": "not_checked",
                "expected-heads": "not_checked",
                "expected-artifacts": "not_checked",
                "nonce": "not_checked",
                "max-age": "not_checked",
            },
            "freshnessStatus": "skipped",
        },
        "expectedHeads": [],
        "actualHeads": [],
        "expectedArtifacts": [],
        "expectedRecipient": None,
        "actualRecipient": None,
        "recipientStatus": "not_checked",
        "expectedNonce": None,
        "actualNonce": None,
        "nonceStatus": "not_checked",
        "roots": [],
        "summary": empty_summary(),
        "statements": [],
        "profiles": [],
        "artifacts": [],
        "unindexedEnvelopes": [],
        "quarantinedStatements": [],
        "datasetEntries": [],
        "unreferencedFiles": [],
        "checks": [
            {"id": check_id, "status": "not_checked", "prerequisiteChecks": []}
            for check_id in CHECK_IDS
        ],
        "warnings": [],
        "errors": [],
        "tool": {"name": "makoto", "version": "0.2.0a0"},
    }


def set_check(
    report: dict[str, Any],
    check_id: str,
    status: str,
    prerequisites: list[str] | None = None,
) -> None:
    record = report["checks"][CHECK_IDS.index(check_id)]
    record["status"] = status
    record["prerequisiteChecks"] = prerequisites or []


def add_error(report: dict[str, Any], diagnostic: Diagnostic) -> None:
    report["errors"].append(diagnostic.as_dict())


def add_warning(report: dict[str, Any], diagnostic: Diagnostic) -> None:
    report["warnings"].append(diagnostic.as_dict())


def finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report["errors"].sort(
        key=lambda item: (
            item["step"],
            item["code"].encode(),
            item["causedByCheck"].encode(),
            canonical_json(item["context"]),
        )
    )
    report["warnings"].sort(
        key=lambda item: (
            item["step"],
            item["code"].encode(),
            item["causedByCheck"].encode(),
            canonical_json(item["context"]),
        )
    )
    report["primaryError"] = report["errors"][0]["code"] if report["errors"] else None
    report["decision"] = "deny" if report["errors"] else "allow"
    set_check(report, "decision", "pass")
    return report


def report_bytes(report: dict[str, Any]) -> bytes:
    return canonical_json(report) + b"\n"
