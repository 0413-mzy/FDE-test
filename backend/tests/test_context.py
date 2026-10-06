"""Deterministic context contracts and quality boundaries."""

import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.context.builder import build_context
from app.context.collector import FetchRecord
from app.context.models import CaseContext, FreshnessPolicy

CASES = json.loads(
    (Path(__file__).parents[2] / "docs/contracts/examples/core-contexts.json").read_text()
)["cases"]


def build(case, *, now=None):
    ctx = case["context"]
    fetches = []
    for o in ctx["source_outcomes"]:
        snap = case["snapshots"].get(o["fetch_id"])
        stamp = datetime.fromisoformat(case["clock"])
        fetches.append(
            FetchRecord(
                UUID(o["fetch_id"]),
                o["operation"],
                o["target_id"],
                snap["source_system"] if snap else "demo_logistics",
                o["outcome"],
                stamp,
                stamp,
                datetime.fromisoformat(o["fetched_at"]) if o["fetched_at"] else None,
                o["error_code"],
                snap["payload"] if snap else None,
            )
        )
    return build_context(
        context_id=UUID(ctx["context_id"]),
        inquiry_id=UUID(ctx["inquiry_id"]),
        run_id=UUID(ctx["run_id"]),
        version=ctx["context_version"],
        team_id=UUID(ctx["authorization_scope"]["team_id"]),
        assigned_agent_id=UUID(ctx["authorization_scope"]["assigned_agent_id"]),
        external_order_id=ctx["order"]["external_order_id"],
        fetches=fetches,
        now=now or datetime.fromisoformat(case["clock"]),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_documented_context_quality_and_references(case):
    result = build(case)
    assert result.quality == case["context"]["quality"]
    assert result.risk_flags == case["context"]["risk_flags"]
    assert result.model_dump(mode="json") == build(case).model_dump(mode="json")
    for ev in result.evidence:
        value = case["snapshots"][str(ev.snapshot_id)]["payload"]
        for token in ev.pointer.split("/")[1:]:
            value = value[int(token)] if isinstance(value, list) else value[token]
        assert type(ev.value) is type(value) and ev.value == value
        assert (
            ev.id == "ev-" + hashlib.sha256(f"{ev.snapshot_id}\n{ev.pointer}".encode()).hexdigest()
        )
    expected = {e["id"]: e for e in case["context"]["evidence"]}
    actual = {e.id: e.model_dump(mode="json") for e in result.evidence}
    assert expected.items() <= actual.items()
    assert set(result.facts).isdisjoint(result.source_texts)
    assert set(result.facts + result.source_texts) == set(actual)


def altered(record_kind, field, value):
    case = copy.deepcopy(CASES[0])
    for snap in case["snapshots"].values():
        if snap["operation"] == record_kind:
            snap["payload"]["records"][0][field] = value
    return case


@pytest.mark.parametrize("seconds,expected", [(1800, "FRESH"), (1800.000001, "STALE")])
def test_fetch_threshold_exact(seconds, expected):
    case = CASES[0]
    now = datetime.fromisoformat(case["clock"]) + timedelta(seconds=seconds)
    assert {e.freshness_status for e in build(case, now=now).evidence} == {expected}


@pytest.mark.parametrize("seconds,expected", [(86400, "FRESH"), (86400.000001, "STALE")])
def test_source_threshold_exact(seconds, expected):
    now = datetime.fromisoformat(CASES[0]["clock"])
    case = altered("get_order", "source_updated_at", (now - timedelta(seconds=seconds)).isoformat())
    assert (
        next(e for e in build(case).evidence if e.pointer == "/records/0/items").freshness_status
        == expected
    )


def test_unknown_time_old_fetch_and_future_are_disclosed():
    case = altered("get_order", "source_updated_at", None)
    ctx = build(case, now=datetime.fromisoformat(case["clock"]) + timedelta(seconds=1801))
    assert {"UNKNOWN_SOURCE_TIME", "OLD_FETCH"} <= {u.code for u in ctx.unknowns}
    case = altered("get_order", "source_updated_at", "2026-09-21T06:00:00Z")
    assert "CLOCK_ANOMALY" in build(case).risk_flags


def test_event_timestamp_does_not_inherit_shipment_timestamp():
    case = copy.deepcopy(CASES[0])
    for snap in case["snapshots"].values():
        if snap["operation"] == "get_shipment":
            snap["payload"]["records"][0]["events"][0]["source_updated_at"] = None
    ctx = build(case)
    assert (
        next(
            e
            for e in ctx.evidence
            if e.pointer == "/records/0/status" and e.source_system == "demo_logistics"
        ).freshness_status
        == "FRESH"
    )
    assert (
        next(e for e in ctx.evidence if e.pointer.endswith("/events/0/status")).freshness_status
        == "UNKNOWN"
    )


@pytest.mark.parametrize("status", [None, "ALIEN"])
def test_unknown_shipment_status_preserves_raw_value(status):
    ctx = build(altered("get_shipment", "status", status))
    assert "UNKNOWN_STATUS" in ctx.risk_flags
    assert any(e.value == status and e.pointer == "/records/0/status" for e in ctx.evidence)


def test_closed_schema_and_cross_context_reference_rejected():
    payload = build(CASES[0]).model_dump(mode="json")
    with pytest.raises(ValidationError):
        CaseContext.model_validate_json(json.dumps({**payload, "tools": []}))
    payload["facts"].append("ev-" + "0" * 64)
    with pytest.raises(ValidationError):
        CaseContext.model_validate_json(json.dumps(payload))
    with pytest.raises(ValidationError):
        FreshnessPolicy(fetch_max_age_seconds=0)


@pytest.mark.parametrize(
    "mutation",
    [
        "stray",
        "wrong_order_target",
        "duplicate_operation",
        "wrong_event_parent",
        "wrong_note_parent",
    ],
)
def test_foreign_or_duplicate_collection_is_rejected(mutation):
    case = copy.deepcopy(CASES[0])
    ctx = case["context"]
    outcomes = ctx["source_outcomes"]
    if mutation == "stray":
        outcomes.append(
            {
                **outcomes[3],
                "fetch_id": "90000000-0000-4000-8000-000000000001",
                "target_id": "OTHER",
                "outcome": "TIMEOUT",
                "fetched_at": None,
                "error_code": "TIMEOUT",
            }
        )
    elif mutation == "wrong_order_target":
        outcomes[1]["target_id"] = "OTHER"
    elif mutation == "duplicate_operation":
        outcomes.append({**outcomes[4], "fetch_id": "90000000-0000-4000-8000-000000000001"})
        case["snapshots"]["90000000-0000-4000-8000-000000000001"] = case["snapshots"][
            outcomes[4]["fetch_id"]
        ]
    elif mutation == "wrong_event_parent":
        case["snapshots"][outcomes[3]["fetch_id"]]["payload"]["records"][0]["events"][0][
            "parcel_id"
        ] = "OTHER"
    else:
        case["snapshots"][outcomes[4]["fetch_id"]]["payload"]["records"][0]["external_order_id"] = (
            "OTHER"
        )
    with pytest.raises(ValueError):
        build(case)


def test_duplicate_partition_rejected():
    payload = build(CASES[0]).model_dump(mode="json")
    payload["facts"].append(payload["facts"][0])
    with pytest.raises(ValidationError):
        CaseContext.model_validate_json(json.dumps(payload))


def test_empty_records_are_missing_without_inventing_business_status():
    case = copy.deepcopy(CASES[0])
    for fetch in case["context"]["source_outcomes"]:
        if fetch["operation"] in ("get_parcels", "get_notes"):
            fetch["outcome"] = "EMPTY"
            case["snapshots"][fetch["fetch_id"]]["payload"]["records"] = []
    case["context"]["source_outcomes"] = [
        f for f in case["context"]["source_outcomes"] if f["operation"] != "get_shipment"
    ]
    ctx = build(case)
    assert {m.code for m in ctx.missing_information} == {"NO_PARCELS", "NO_WAREHOUSE_NOTES"}
    assert not ctx.parcels and all(e.source_system == "demo_oms" for e in ctx.evidence)


def test_same_instant_event_status_conflict_keeps_both_and_source_text():
    case = copy.deepcopy(CASES[0])
    sf = next(s for s in case["snapshots"].values() if s["operation"] == "get_shipment")
    event = copy.deepcopy(sf["payload"]["records"][0]["events"][0])
    event.update(
        status="LABEL_CREATED",
        source_record_id="EVT-SECOND",
        occurred_at="2026-09-20T05:50:00+00:00",
    )
    sf["payload"]["records"][0]["events"].append(event)
    ctx = build(case)
    assert any(c.code == "INCOMPATIBLE_EVENT_STATUS" for c in ctx.conflicts)
    assert len(ctx.parcels[0].event_evidence_ids) == 2


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_documented_quality_disclosures_preserved(case):
    ctx = build(case)
    for expected in case["context"]["unknowns"]:
        assert any(
            u.code == expected["code"] and set(expected["evidence_ids"]) <= set(u.evidence_ids)
            for u in ctx.unknowns
        )
    for expected in case["context"]["missing_information"]:
        assert any(
            m.code == expected["code"] and m.scope == expected["scope"]
            for m in ctx.missing_information
        )
    for expected in case["context"]["conflicts"]:
        assert any(
            c.code == expected["code"] and set(c.evidence_ids) == set(expected["evidence_ids"])
            for c in ctx.conflicts
        )


def test_different_time_event_status_is_history_not_conflict():
    case = copy.deepcopy(CASES[0])
    sf = next(s for s in case["snapshots"].values() if s["operation"] == "get_shipment")
    event = copy.deepcopy(sf["payload"]["records"][0]["events"][0])
    event.update(
        status="LABEL_CREATED", source_record_id="EVT-SECOND", occurred_at="2026-09-20T04:50:00Z"
    )
    sf["payload"]["records"][0]["events"].append(event)
    assert not build(case).conflicts


def test_pure_builder_rejects_noncanonical_order_item():
    case = altered("get_order", "items", [{"sku": "MUG", "product_name": "Mug", "quantity": True}])
    with pytest.raises(ValueError):
        build(case)
