"""Source dependency and canonical binding regression tests."""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.context.collector import ProviderBundle, collect
from app.core.clock import FixedClock
from app.integrations.errors import ExternalTimeout
from app.integrations.models import (
    OrderSnapshot,
    ParcelSnapshot,
    ShipmentSnapshot,
    SupportInquiry,
    WarehouseNoteSnapshot,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


CASE = json.loads(
    (Path(__file__).parents[2] / "docs/contracts/examples/core-contexts.json").read_text()
)["cases"][0]
NOW = datetime.fromisoformat(CASE["clock"])


class Sources:
    def __init__(self, fail=None, alter=None):
        self.calls = []
        self.fail = fail
        self.payloads = {
            s["operation"]: copy.deepcopy(s["payload"]["records"])
            for s in CASE["snapshots"].values()
        }
        if alter:
            alter(self.payloads)

    def read(self, op, model):
        self.calls.append(op)
        if self.fail == op:
            raise ExternalTimeout(service="test", operation=op, request_id="test")
        return [model.model_validate_json(json.dumps(x)) for x in self.payloads[op]]

    async def get_inquiry(self, ident, **kw):
        return self.read("get_inquiry", SupportInquiry)[0]

    async def get_order(self, ident, **kw):
        return self.read("get_order", OrderSnapshot)[0]

    async def get_parcels(self, ident, **kw):
        return self.read("get_parcels", ParcelSnapshot)

    async def get_shipment(self, parcel, **kw):
        return self.read("get_shipment", ShipmentSnapshot)[0]

    async def get_notes(self, ident, **kw):
        return self.read("get_notes", WarehouseNoteSnapshot)


async def run(s):
    return await collect(
        ProviderBundle(s, s, s, s), "INQ-FIXTURE-001", "ORD-FIXTURE-001", FixedClock(NOW), "test"
    )


@pytest.mark.anyio
async def test_success_dependency_order_and_original_payload_time():
    s = Sources()
    result = await run(s)
    assert s.calls == ["get_inquiry", "get_order", "get_parcels", "get_shipment", "get_notes"]
    assert result.run_state == "SUCCEEDED"
    assert result.fetches[0].payload["records"][0].get("fetched_at") is None


@pytest.mark.anyio
async def test_fetch_record_preserves_original_record_time():
    old = NOW - timedelta(minutes=5)
    s = Sources(alter=lambda p: p["get_order"][0].update(fetched_at=old.isoformat()))
    assert (await run(s)).fetches[1].fetched_at == old


@pytest.mark.anyio
@pytest.mark.parametrize(
    "op,expected,count",
    [
        ("get_inquiry", "FAILED", 1),
        ("get_order", "FAILED", 2),
        ("get_parcels", "FAILED", 3),
        ("get_shipment", "PARTIAL", 5),
        ("get_notes", "PARTIAL", 5),
    ],
)
async def test_failures_stop_required_or_preserve_partial_without_retry(op, expected, count):
    s = Sources(fail=op)
    result = await run(s)
    assert result.run_state == expected and len(s.calls) == count
    assert next(f for f in result.fetches if f.operation == op).outcome == "TIMEOUT"
    assert next(f for f in result.fetches if f.operation == op).payload is None


@pytest.mark.anyio
async def test_inquiry_binding_mismatch_stops_before_order():
    s = Sources(alter=lambda p: p["get_inquiry"][0].update(external_order_id="OTHER"))
    result = await run(s)
    assert result.error_code == "SOURCE_BINDING_MISMATCH" and s.calls == ["get_inquiry"]


@pytest.mark.anyio
async def test_invalid_inquiry_is_not_a_binding_mismatch():
    s = Sources(alter=lambda p: p["get_inquiry"][0].update(customer_message=""))
    assert (await run(s)).error_code == "SOURCE_INVALID_RESPONSE"


@pytest.mark.anyio
async def test_no_tracking_skips_logistics_but_preserves_outcome():
    s = Sources(alter=lambda p: p["get_parcels"][0].update(tracking_number=None))
    result = await run(s)
    assert "get_shipment" not in s.calls and result.run_state == "PARTIAL"
    assert any(f.outcome == "NO_TRACKING" and f.error_code == "NO_TRACKING" for f in result.fetches)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "op,field",
    [
        ("get_order", "external_order_id"),
        ("get_parcels", "external_order_id"),
        ("get_shipment", "parcel_id"),
        ("get_notes", "external_order_id"),
    ],
)
async def test_wrong_parent_records_discarded(op, field):
    s = Sources(alter=lambda p: p[op][0].update({field: "OTHER"}))
    failed = next(f for f in (await run(s)).fetches if f.operation == op)
    assert failed.outcome == "INVALID_RESPONSE" and failed.payload is None


@pytest.mark.anyio
@pytest.mark.parametrize("op", ["get_parcels", "get_notes", "events"])
async def test_duplicate_identities_rejected(op):
    def alter(p):
        records = p["get_shipment"][0]["events"] if op == "events" else p[op]
        records.append(dict(records[0]))

    operation = "get_shipment" if op == "events" else op
    assert (
        next(
            f for f in (await run(Sources(alter=alter))).fetches if f.operation == operation
        ).outcome
        == "INVALID_RESPONSE"
    )


@pytest.mark.anyio
async def test_mutated_canonical_nested_event_is_revalidated():
    s = Sources()
    original = s.get_shipment

    async def malformed(*args, **kwargs):
        shipment = await original(*args, **kwargs)
        shipment.events.append({"status": "DELIVERED"})
        return shipment

    s.get_shipment = malformed
    assert (
        next(f for f in (await run(s)).fetches if f.operation == "get_shipment").outcome
        == "INVALID_RESPONSE"
    )


@pytest.mark.anyio
async def test_list_operation_rejects_single_canonical_object():
    s = Sources()
    original = s.get_parcels

    async def malformed(*args, **kwargs):
        return (await original(*args, **kwargs))[0]

    s.get_parcels = malformed
    assert (await run(s)).error_code == "SOURCE_INVALID_RESPONSE"
