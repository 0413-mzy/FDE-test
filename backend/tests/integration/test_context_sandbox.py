"""Stage 4 collector and Evidence through the independent Sandbox's real HTTP."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.context.builder import build_context
from app.context.collector import ProviderBundle, collect
from app.core.clock import FixedClock
from app.core.config import Settings
from app.integrations.sandbox.client import SandboxClient
from app.integrations.sandbox.providers import (
    SandboxLogisticsProvider,
    SandboxMessageProvider,
    SandboxOrderProvider,
    SandboxWarehouseProvider,
)

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
T0 = datetime(2026, 9, 20, 6, tzinfo=UTC)


@pytest.fixture
async def providers(request):
    url = request.config.getoption("--sandbox-url")
    if not url:
        import os

        url = os.environ.get("INTEGRATION_SANDBOX_URL")
    if not url:
        pytest.skip("Real Stage 4 HTTP tests require --sandbox-url")
    async with SandboxClient(
        Settings(_env_file=None, sandbox_base_url=url), FixedClock(T0)
    ) as client:
        yield ProviderBundle(
            order=SandboxOrderProvider(client),
            logistics=SandboxLogisticsProvider(client),
            warehouse=SandboxWarehouseProvider(client),
            message=SandboxMessageProvider(client),
        )


@pytest.mark.parametrize(
    "number,state,flag,outcome",
    [
        (1, "SUCCEEDED", "MISSING_INFORMATION", "EMPTY"),
        (2, "SUCCEEDED", "UNKNOWN_FRESHNESS", "SUCCESS"),
        (4, "SUCCEEDED", "UNKNOWN_FRESHNESS", "SUCCESS"),
        (5, "SUCCEEDED", "UNKNOWN_FRESHNESS", "SUCCESS"),
        (6, "SUCCEEDED", "UNKNOWN_FRESHNESS", "SUCCESS"),
        (7, "SUCCEEDED", "STALE_DATA", "SUCCESS"),
        (8, "PARTIAL", "PARTIAL_SOURCE_FAILURE", "TIMEOUT"),
        (9, "PARTIAL", "PARTIAL_SOURCE_FAILURE", "UNAVAILABLE"),
        (10, "PARTIAL", "PARTIAL_SOURCE_FAILURE", "NOT_FOUND"),
        (11, "SUCCEEDED", "CONFLICTING_SOURCES", "SUCCESS"),
    ],
)
async def test_real_source_outcomes_and_traceable_quality(providers, number, state, flag, outcome):
    order_id = f"ORD-DEMO-{number:03}"
    collection = await collect(
        providers, f"INQ-DEMO-{number:03}", order_id, FixedClock(T0), "stage4-http"
    )
    assert collection.run_state == state and collection.error_code is None
    assert outcome in {fetch.outcome for fetch in collection.fetches}
    context = build_context(
        context_id=uuid4(), inquiry_id=uuid4(), run_id=uuid4(), version=1,
        team_id=uuid4(), assigned_agent_id=uuid4(), external_order_id=order_id,
        fetches=collection.fetches, now=T0,
    )
    assert context.quality == "DEGRADED" and flag in context.risk_flags
    payloads = {str(fetch.id): fetch.payload for fetch in collection.fetches}
    for evidence in context.evidence:
        value = payloads[str(evidence.snapshot_id)]
        for part in evidence.pointer.lstrip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        assert type(value) is type(evidence.value) and value == evidence.value
        assert evidence.snapshot_version == 1
    assert set(context.facts).isdisjoint(context.source_texts)
    assert set(context.facts) | set(context.source_texts) == {ev.id for ev in context.evidence}
    for fetch in collection.fetches:
        if fetch.outcome not in {"SUCCESS", "EMPTY"}:
            assert fetch.payload is None and fetch.fetched_at is None
    if number == 4:
        assert len(context.parcels) == 2
    if number == 6:
        notes = [ev for ev in context.evidence if ev.pointer.endswith("/note_text")]
        assert notes and all(ev.kind == "SOURCE_TEXT" for ev in notes)
    if number == 7:
        shipment = next(ev for ev in context.evidence if ev.freshness_status == "STALE")
        assert shipment.fetched_at == T0 and shipment.source_updated_at < T0
    if number == 11:
        assert any(c.code == "POSSIBLE_HANDOVER_CONFLICT" for c in context.conflicts)


async def test_real_missing_required_order_stops_without_context(providers):
    collection = await collect(
        providers, "INQ-DEMO-012", "ORD-DEMO-012", FixedClock(T0), "stage4-required-404"
    )
    assert collection.run_state == "FAILED"
    assert collection.error_code == "SOURCE_NOT_FOUND"
    assert [fetch.operation for fetch in collection.fetches] == ["get_inquiry", "get_order"]
    assert collection.fetches[-1].payload is None
