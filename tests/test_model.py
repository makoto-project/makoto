from __future__ import annotations

from pathlib import Path

import pytest

from makoto.canonical import canonical_json
from makoto.dsse import SigningKey, verify_envelope_signature
from makoto.graph import build_graph
from makoto.model import (
    HANDOFF_PAYLOAD_TYPE,
    STATEMENT_PAYLOAD_TYPE,
    Artifact,
    TransformationInput,
    create_handoff,
    create_origin,
    create_transform,
)

ROOT = Path(__file__).resolve().parents[1]


def build_chain() -> tuple[Artifact, object, object, object]:
    raw = Artifact(
        "customers.raw.json", b'[{"age":34,"email":"a@example.test"}]\n', "application/json"
    )
    normalized = Artifact(
        "customers.normalized.json",
        b'[{"age":34,"email":"a@example.test"}]',
        "application/json",
    )
    public = Artifact("customers.public.json", b'[{"ageBucket":"30-39"}]', "application/json")
    origin = create_origin(
        artifacts=[raw],
        event_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        occurred_at="2026-09-16T16:00:00Z",
        source_kind="urn:makoto:demo:source:synthetic-file",
        source_uri="urn:makoto:demo:v0.2:source:customers-raw",
        source_media_type="application/json",
        signing_key=SigningKey.from_seed(bytes([1]) * 32),
        repository_root=ROOT,
    )
    normalize = create_transform(
        artifacts=[normalized],
        inputs=[TransformationInput("raw", raw, origin, raw.name)],
        event_id="urn:uuid:22222222-2222-4222-8222-222222222222",
        occurred_at="2026-09-16T16:01:00Z",
        operation_type="urn:makoto:demo:operation:normalize",
        signing_key=SigningKey.from_seed(bytes([2]) * 32),
        repository_root=ROOT,
    )
    public_safe = create_transform(
        artifacts=[public],
        inputs=[TransformationInput("normalized", normalized, normalize, normalized.name)],
        event_id="urn:uuid:33333333-3333-4333-8333-333333333333",
        occurred_at="2026-09-16T16:02:00Z",
        operation_type="urn:makoto:demo:operation:public-safe",
        signing_key=SigningKey.from_seed(bytes([3]) * 32),
        repository_root=ROOT,
    )
    return public, origin, normalize, public_safe


def test_source_first_chain_is_hash_linked_and_signed() -> None:
    public, origin, normalize, public_safe = build_chain()
    assert (
        normalize.statement["predicate"]["inputs"][0]["provenance"]["statementDigest"]
        == origin.digest()
    )
    assert (
        public_safe.statement["predicate"]["inputs"][0]["provenance"]["statementDigest"]
        == normalize.digest()
    )
    assert public_safe.subject(public.name)["digest"] == public.digest()
    assert origin.payload == canonical_json(origin.statement)
    verify_envelope_signature(
        origin.envelope,
        public_spki=SigningKey.from_seed(bytes([1]) * 32).public_spki(),
    )


def test_handoff_anchors_exact_graph_and_final_artifact() -> None:
    public, origin, normalize, public_safe = build_chain()
    handoff_key = SigningKey.from_seed(bytes([4]) * 32)
    handoff = create_handoff(
        statements=[origin, normalize, public_safe],
        roots=[origin],
        final_artifacts=[(public, public_safe)],
        bundle_id="urn:uuid:55555555-5555-4555-8555-555555555555",
        issued_at="2026-09-16T16:03:00Z",
        signing_key=handoff_key,
        repository_root=ROOT,
        recipient="example:downstream-team",
    )
    assert handoff.manifest["roots"] == [origin.digest()]
    assert handoff.manifest["heads"] == [public_safe.digest()]
    assert handoff.manifest["artifacts"][0]["digest"] == public.digest()
    verify_envelope_signature(handoff.envelope, public_spki=handoff_key.public_spki())
    assert handoff.envelope["payloadType"] == HANDOFF_PAYLOAD_TYPE


def test_transform_rejects_bytes_that_do_not_match_predecessor() -> None:
    _public, origin, _normalize, _public_safe = build_chain()
    changed = Artifact("customers.raw.json", b"changed")
    with pytest.raises(ValueError, match="do not match"):
        create_transform(
            artifacts=[Artifact("output.json", b"output")],
            inputs=[TransformationInput("raw", changed, origin, "customers.raw.json")],
            event_id="urn:uuid:99999999-9999-4999-8999-999999999999",
            occurred_at="2026-09-16T16:04:00Z",
            operation_type="urn:makoto:test:operation",
            signing_key=SigningKey.from_seed(bytes([9]) * 32),
            repository_root=ROOT,
        )


def test_statement_and_handoff_payload_types_are_distinct() -> None:
    _public, origin, _normalize, _public_safe = build_chain()
    assert origin.envelope["payloadType"] == STATEMENT_PAYLOAD_TYPE
    assert STATEMENT_PAYLOAD_TYPE != HANDOFF_PAYLOAD_TYPE


def test_duplicate_event_ids_are_graph_failures() -> None:
    _public, origin, normalize, _public_safe = build_chain()
    normalize.statement["predicate"]["event"]["id"] = origin.statement["predicate"]["event"]["id"]
    graph = build_graph(
        {
            origin.digest()["sha256"]: origin.statement,
            normalize.digest()["sha256"]: normalize.statement,
        }
    )
    assert "E_EVENT_ID_DUPLICATE" in {problem.code for problem in graph.problems}


def test_dataset_entry_edge_fails_closed_without_verified_membership() -> None:
    _public, origin, normalize, _public_safe = build_chain()
    normalize.statement["predicate"]["inputs"][0]["provenance"]["entryName"] = "part-000.json"
    normalize.statement["predicate"]["inputs"][0]["digest"] = {"sha256": "0" * 64}
    graph = build_graph(
        {
            origin.digest()["sha256"]: origin.statement,
            normalize.digest()["sha256"]: normalize.statement,
        }
    )
    assert "E_DATASET_MANIFEST_REQUIRED" in {problem.code for problem in graph.problems}
