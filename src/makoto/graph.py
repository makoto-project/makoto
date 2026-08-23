"""Deterministic Makoto statement-graph construction and integrity checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from makoto.model import ORIGIN_PREDICATE_TYPE, TRANSFORM_PREDICATE_TYPE


@dataclass(frozen=True)
class GraphProblem:
    code: str
    statement_digest: str
    message: str


@dataclass(frozen=True)
class GraphResult:
    roots: tuple[str, ...]
    heads: tuple[str, ...]
    reachable: tuple[str, ...]
    predecessors: Mapping[str, tuple[str, ...]]
    consumed_subjects: frozenset[tuple[str, str, str]]
    problems: tuple[GraphProblem, ...]

    @property
    def valid(self) -> bool:
        return not self.problems


def build_graph(
    statements: Mapping[str, Mapping[str, Any]],
    *,
    dataset_memberships: Mapping[tuple[str, str, str], str] | None = None,
    verified_dataset_subjects: frozenset[tuple[str, str]] | None = None,
) -> GraphResult:
    memberships = dataset_memberships or {}
    verified_datasets = verified_dataset_subjects or frozenset()
    predecessors: dict[str, tuple[str, ...]] = {}
    problems: list[GraphProblem] = []
    consumed_subjects: set[tuple[str, str, str]] = set()
    event_ids: dict[str, str] = {}

    for digest in sorted(statements):
        statement = statements[digest]
        event_id = statement.get("predicate", {}).get("event", {}).get("id")
        if isinstance(event_id, str):
            previous = event_ids.get(event_id)
            if previous is not None:
                problems.append(
                    GraphProblem(
                        "E_EVENT_ID_DUPLICATE",
                        digest,
                        f"event ID duplicates statement {previous}",
                    )
                )
            else:
                event_ids[event_id] = digest
        predicate_type = statement["predicateType"]
        if predicate_type == ORIGIN_PREDICATE_TYPE:
            predecessors[digest] = ()
            continue
        if predicate_type != TRANSFORM_PREDICATE_TYPE:
            problems.append(
                GraphProblem(
                    "E_PREDICATE_SEMANTICS_UNSUPPORTED",
                    digest,
                    f"unsupported predicate type {predicate_type!r}",
                )
            )
            predecessors[digest] = ()
            continue

        predecessor_values: list[str] = []
        inputs = sorted(
            statement["predicate"]["inputs"],
            key=lambda item: (
                item["provenance"]["statementDigest"]["sha256"],
                item["provenance"]["subjectName"].encode(),
                (item["provenance"].get("entryName") or "").encode(),
                item["name"].encode(),
                item["digest"]["sha256"],
            ),
        )
        for item in inputs:
            predecessor_digest = item["provenance"]["statementDigest"]["sha256"]
            predecessor_values.append(predecessor_digest)
            if predecessor_digest not in statements:
                problems.append(
                    GraphProblem(
                        "E_PREDECESSOR_MISSING",
                        digest,
                        f"predecessor {predecessor_digest} is absent",
                    )
                )
                continue
            predecessor = statements[predecessor_digest]
            subject_name = item["provenance"]["subjectName"]
            matches = [
                subject for subject in predecessor["subject"] if subject["name"] == subject_name
            ]
            if len(matches) != 1:
                problems.append(
                    GraphProblem(
                        "E_PREDECESSOR_SUBJECT",
                        digest,
                        f"predecessor does not contain subject {subject_name!r}",
                    )
                )
                continue
            entry_name = item["provenance"].get("entryName")
            if entry_name is None:
                if matches[0]["digest"] != item["digest"]:
                    problems.append(
                        GraphProblem(
                            "E_INPUT_DIGEST",
                            digest,
                            f"input {item['name']!r} digest differs from predecessor subject",
                        )
                    )
                consumed_subjects.add((predecessor_digest, subject_name, item["digest"]["sha256"]))
            else:
                membership_key = (predecessor_digest, subject_name, entry_name)
                member_digest = memberships.get(membership_key)
                if member_digest is None:
                    code = (
                        "E_PREDECESSOR_SUBJECT"
                        if (predecessor_digest, subject_name) in verified_datasets
                        else "E_DATASET_MANIFEST_REQUIRED"
                    )
                    problems.append(
                        GraphProblem(
                            code,
                            digest,
                            (
                                f"verified dataset manifest lacks entry {entry_name!r}"
                                if code == "E_PREDECESSOR_SUBJECT"
                                else (
                                    f"dataset entry {entry_name!r} has no verified "
                                    "manifest membership"
                                )
                            ),
                        )
                    )
                elif member_digest != item["digest"]["sha256"]:
                    problems.append(
                        GraphProblem(
                            "E_INPUT_DIGEST",
                            digest,
                            f"input {item['name']!r} digest differs from dataset member",
                        )
                    )
        predecessors[digest] = tuple(sorted(set(predecessor_values)))

    cycle_members = _cycle_members(predecessors)
    for digest in cycle_members:
        problems.append(GraphProblem("E_GRAPH_CYCLE", digest, "statement belongs to a cycle"))

    roots = tuple(sorted(digest for digest, values in predecessors.items() if not values))
    for digest in roots:
        if statements[digest]["predicateType"] != ORIGIN_PREDICATE_TYPE:
            problems.append(GraphProblem("E_ROOT_INVALID", digest, "graph root is not an origin"))
    terminal_statements = {
        digest
        for digest, statement in statements.items()
        if any(
            (digest, subject["name"], subject["digest"]["sha256"]) not in consumed_subjects
            for subject in statement["subject"]
        )
    }
    heads = tuple(sorted(terminal_statements))
    return GraphResult(
        roots=roots,
        heads=heads,
        reachable=tuple(sorted(statements)),
        predecessors=predecessors,
        consumed_subjects=frozenset(consumed_subjects),
        problems=tuple(problems),
    )


def reachable_from_heads(
    heads: list[str], predecessors: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    reached: set[str] = set()
    pending = list(reversed(sorted(heads)))
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(reversed(predecessors.get(current, ())))
    return tuple(sorted(reached))


def _cycle_members(predecessors: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    state: dict[str, int] = {}
    stack: list[str] = []
    cyclic: set[str] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for predecessor in predecessors.get(node, ()):
            if predecessor not in predecessors:
                continue
            if state.get(predecessor, 0) == 0:
                visit(predecessor)
            elif state.get(predecessor) == 1:
                cyclic.update(stack[stack.index(predecessor) :])
        stack.pop()
        state[node] = 2

    for node in sorted(predecessors):
        if state.get(node, 0) == 0:
            visit(node)
    return tuple(sorted(cyclic))
