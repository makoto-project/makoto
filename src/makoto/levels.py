"""Makoto assurance levels derived from a completed verification report.

Levels are a read-only classification of the report's top-level check statuses
(specification Section 8.3). They never change a check, a diagnostic, or the
allow/deny decision; a receiver still gates on the decision or on a minimum level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from makoto.report import CHECK_IDS

LEVEL_NAMES = ("L1", "L2", "L3")
_CHECK_ORDER = {check_id: index for index, check_id in enumerate(CHECK_IDS)}


@dataclass(frozen=True)
class LevelRequirement:
    level: str
    title: str
    passing: tuple[str, ...]
    optional: tuple[str, ...] = ()
    requires_allow: bool = False


# Each level includes every requirement of the level below it.
REQUIREMENTS = (
    LevelRequirement(
        "L1",
        "Provenance is authentic",
        passing=("load-safely", "parse-strictly", "index-payloads", "core-schemas", "signatures"),
    ),
    LevelRequirement(
        "L2",
        "Provenance is authorized and complete",
        passing=(
            "authorization-thresholds",
            "authorization",
            "graph",
            "roots-and-heads",
            "completeness-anchor",
            "artifact-bytes",
        ),
        # not_checked is only ever an optional, waived, or empty population (Section 15.1).
        optional=("metadata-profiles", "graph-dependency-artifacts", "artifact-profiles"),
    ),
    LevelRequirement(
        "L3",
        "Provenance is anchored",
        passing=("freshness-anchors",),
        requires_allow=True,
    ),
)


def assurance_level(report: dict[str, Any]) -> dict[str, Any]:
    """Return the highest satisfied level and, for every level, the checks that fell short.

    The caller must pass a report that already validated against the core
    verification-report schema.
    """
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    achieved: str | None = None
    blocked = False
    levels = []
    for requirement in REQUIREMENTS:
        unmet = [
            {"id": check_id, "status": statuses[check_id]}
            for check_id in requirement.passing
            if statuses[check_id] != "pass"
        ]
        unmet += [
            {"id": check_id, "status": statuses[check_id]}
            for check_id in requirement.optional
            if statuses[check_id] not in ("pass", "not_checked")
        ]
        unmet.sort(key=lambda item: _CHECK_ORDER[item["id"]])
        decision_unmet = requirement.requires_allow and report["decision"] != "allow"
        satisfied = not unmet and not decision_unmet and not blocked
        if satisfied:
            achieved = requirement.level
        else:
            blocked = True
        levels.append(
            {
                "decisionRequired": requirement.requires_allow,
                "level": requirement.level,
                "satisfied": satisfied,
                "title": requirement.title,
                "unmetChecks": unmet,
            }
        )
    return {"decision": report["decision"], "level": achieved, "levels": levels}


def level_rank(level: str | None) -> int:
    return 0 if level is None else LEVEL_NAMES.index(level) + 1
