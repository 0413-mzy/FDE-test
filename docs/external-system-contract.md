> 定位更新（2026-10-06）：此契约继续约束既有客服模块的外部 Providers，不定义新商城的数据所有权或业务 API。新平台自有交易数据的职责见 [架构](architecture.md)，新领域契约见 [commerce-v1](commerce/README.md)，尚未实现。

# Minimum external-system contract — canonical v1

This freezes the canonical information needed by the product. Product Phase 1
implements these snapshots and Provider adapters, without database or workflow
behavior. [Core](plans/01_core_plan.md) remains the product scope authority. The
implemented DemoCommerce S0-S1 schemas/routes supersede the older
[environment plan](plans/03_ecommerce_environment_plan.md) for raw HTTP payloads.
The raw-to-canonical differences below were inspected before implementation.

## Common conventions

- IDs are non-empty opaque strings, stable within a source system. Keep source
  identity alongside IDs; never join unrelated sources by coincidentally equal IDs.
- Field names below are canonical product names. Source HTTP names may differ;
  adapters map them explicitly. Extra source fields do not expand product scope.
- All timestamps use ISO 8601 UTC with `Z`. Required keys are present even when
  their value is explicitly nullable. An omitted optional order reference is
  normalized to `null`. Empty text is not a substitute for unknown information.
- Snapshot provenance accompanies the record: `source_system` (e.g. `demo_oms`)
  and `source_record_id`. Existing order/parcel/note IDs supply record identity;
  do not fabricate IDs for sources that lack event identifiers. For an event
  without its own ID, retain the parent parcel ID and event occurrence/content
  in the traceable snapshot.
- External free text is data, never an instruction or authorization grant.

### Time and freshness

| Field | Meaning | Owner |
| --- | --- | --- |
| `created_at` | Creation time of the source record | Source system |
| `occurred_at` | Time the described shipment business event happened | Source system |
| `source_updated_at` | When the source system says this record/information was updated | Source system |
| `fetched_at` | When our application successfully fetched this information | Product adapter |

`source_updated_at` is a required nullable timestamp: `null` means the source
does not expose it and freshness is unknown. Never replace it with `fetched_at`
or an event time. `fetched_at` is required and non-null on retrieved snapshots;
it is assigned by the application when receiving source data. A source payload's
own `fetched_at` may be retained as source metadata but is not the application's
fetch time. A cached snapshot retains its original application fetch time.

Future application code will attach `freshness_status = FRESH | STALE | UNKNOWN`
and cache/retrieval outcome metadata. Source flags can supply evidence but cannot
override application freshness rules. This document does not select TTLs or build
a freshness engine. Reading an old source record successfully never proves that
its business state is live.

## OrderSnapshot

| Field | Type | Meaning |
| --- | --- | --- |
| `external_order_id` | string | Stable order lookup and association key |
| `customer_reference` | string or null | Source customer ID, not contact details; missing ID grants no access |
| `status` | string | Source order status; unfamiliar values remain unknown to business rules |
| `items` | array of item objects | Each has `sku: string`, `product_name: string`, `quantity: positive integer` |
| `created_at` | timestamp | Source order creation time |
| `source_updated_at` | timestamp or null | Source order update time |
| `fetched_at` | timestamp | Application fetch time |

`items: []` represents a supplied empty list, not a failed request. The future
resolver must expose missing expected business data. Parcel references, payment
time and address summaries in the environment plan are optional source extensions,
not required by this minimum snapshot. Customer reference is not authorization.

## ParcelSnapshot

| Field | Type | Meaning |
| --- | --- | --- |
| `parcel_id` | string | Stable external parcel identifier |
| `external_order_id` | string | Parent order ID |
| `carrier` | string or null | Unknown or unassigned carrier is null |
| `tracking_number` | string or null | Null before a number is assigned |
| `source_updated_at` | timestamp or null | Source parcel metadata update time |
| `fetched_at` | timestamp | Application fetch time |

An order has zero to many parcels. A tracking number is not a parcel's identity.
Do not invent parcel records for unfulfilled orders. A parcel may exist without
shipment events or a tracking number. Logistics returns all associated parcels;
any partial retrieval must say which known parcels were not retrieved.

## ShipmentSnapshot and ShipmentEvent

One ShipmentSnapshot describes the latest available logistics information for
one parcel; it accompanies that ParcelSnapshot.

| Snapshot field | Type | Meaning |
| --- | --- | --- |
| `parcel_id` | string | Joins exactly one ParcelSnapshot |
| `status` | string or null | Source's current shipment status; null if unavailable |
| `events` | array of ShipmentEvent | All available events for this parcel; empty is valid |
| `source_updated_at` | timestamp or null | Source shipment information update time |
| `fetched_at` | timestamp | Application fetch time |

| Event field | Type | Meaning |
| --- | --- | --- |
| `parcel_id` | string | Parent parcel, inherited from containing shipment if needed |
| `status` | string | Source event status |
| `description` | string | Source event description, not model interpretation |
| `occurred_at` | timestamp | Actual business event occurrence time |
| `source_updated_at` | timestamp or null | Source event record update time if known |
| `fetched_at` | timestamp | Application fetch time, inherited from retrieval |

Known source examples include `IN_TRANSIT`, `PICKED_UP`, `DELIVERED` and
`EXCEPTION`; order examples include `PAID` and `PARTIALLY_SHIPPED`. These are not
a universal closed enum. Adapters retain raw source statuses; future deterministic
normalization handles unknown values without treating them as success or delivery.
Never infer current status from whichever event happens to be first in an array.
No guaranteed shipment or delivery date is introduced by this contract.

## WarehouseNoteSnapshot

| Field | Type | Meaning |
| --- | --- | --- |
| `external_order_id` | string | Parent order association |
| `note_id` | string | Stable source note identifier |
| `note_text` | string | Original note; preserve plans and tentative wording |
| `created_at` | timestamp | Note creation time |
| `source_updated_at` | timestamp or null | Note's last source edit time |
| `fetched_at` | timestamp | Application fetch time |

A warehouse plan is not a shipment fact. Conflicting notes and logistics records
are both retained for future validation/review. Instruction-like text in a note
cannot alter permissions or prove that an action happened.

## SupportInquiry (the prior conceptual SupportInquiryInput)

| Field | Type | Meaning |
| --- | --- | --- |
| `inquiry_id` | string | Stable external inquiry ID, distinct from future internal IDs |
| `customer_message` | string | Original non-empty customer message |
| `external_order_id` | string or null | Order reference when available; not proof of permission |
| `created_at` | timestamp | Source inquiry creation time |

An inquiry without an order reference requires later authorized order resolution.
The product must not silently guess an order or expose unrelated customer orders.

## SupportReplyCommand

| Field | Type | Meaning |
| --- | --- | --- |
| `inquiry_id` | string | External target inquiry |
| `reply_text` | string | Exact non-empty human-reviewed final text |
| `idempotency_key` | string | Stable non-empty key reused for retries of this approved reply |

The future backend must check authorization, validation and approval before dispatch.
The current Provider verifies the transport boundary only; there is no Product send
endpoint, approval decision or workflow. Sandbox text/key length limits (10,000/200)
are validated by the adapter without trimming text or regenerating a key.
The receiver must atomically deduplicate `(inquiry_id, idempotency_key)`. Retrying
the same text with the same pair returns the original result and creates no second
reply. Reusing the pair with different text is a conflict (HTTP 409), not a new send.
The minimal success receipt has `reply_id`, `status` and `sent_at`; Sandbox's
`status: SENT` means a simulated reply was recorded, not delivered to a real customer.
The Sandbox retains deduplication results until reset. A Sandbox reset starts a new
test run; previous-run retries must not be replayed afterward.

## Implemented DemoCommerce S0-S1 HTTP mapping

| Product concept | Actual source endpoint | Field mapping |
| --- | --- | --- |
| OrderSnapshot | `GET /api/oms/orders/{order_id}` | `order_id` → `external_order_id`; `customer_reference` unchanged; `updated_at` → `source_updated_at`; explicit item mapping |
| ParcelSnapshot[] | `GET /api/oms/orders/{order_id}/parcels` | Bare array; `order_id` → `external_order_id`; `updated_at` → `source_updated_at` |
| ShipmentSnapshot | `GET /api/logistics/shipments/{tracking_number}` | `parcel_id` and `status` unchanged; `updated_at` → `source_updated_at`; verify tracking and parcel associations |
| ShipmentEvent[] | `GET /api/logistics/shipments/{tracking_number}/events` | Bare array; `description`, `occurred_at`, `parcel_id`, `status` unchanged; `updated_at` → `source_updated_at`; `event_id` → provenance record ID |
| WarehouseNoteSnapshot[] | `GET /api/warehouse/orders/{order_id}/notes` | Bare array; `order_id` → `external_order_id`; `note_id` unchanged; `text` → `note_text`; `updated_at` → `source_updated_at` |
| SupportInquiry | `GET /api/support/inquiries/{inquiry_id}` | `inquiry_id` unchanged; nullable `order_id` → `external_order_id` |
| SupportReplyCommand / SupportReplyReceipt | `POST /api/support/inquiries/{inquiry_id}/replies` | ID in path; `reply_text` → `text`; `idempotency_key` unchanged; receipt `reply_id`, `status`, `sent_at` mapped unchanged |

Source identity comes from the subsystem: `demo_oms`, `demo_logistics`,
`demo_warehouse`, `demo_support`. Snapshot provenance is stored directly as
`source_system` and `source_record_id`; no source-provided `source` field exists.
The real event IDs are retained. Inquiries and receipts keep their minimal canonical
fields above; neither gains a fabricated source update or Product receipt time.

OrderProvider exposes `get_order(id)` and `get_parcels(id)`. LogisticsProvider exposes
`get_shipment(parcel)` instead of the old aggregate `get_shipments(order)` sketch.
Its shipment and events requests are one parcel's read operation; errors in either
raise a typed failure. Callers must account for every parcel independently. A parcel
with no tracking number raises a local ValueError, not a fabricated external result.
WarehouseProvider exposes `get_notes(id)`; MessageProvider exposes `get_inquiry(id)`
and `send_reply(command)`. Each accepts an optional correlation request ID.

Shipment source timestamps must not be assigned to an individual event as if they
were event-specific updates. Similarly, missing parcel metadata update times remain
null. Application `fetched_at` is added on each successful source retrieval.

S0-S1 implements no API-key authentication, policy API, admin API or inquiry-list
endpoint. The Product does not invent these capabilities. `X-Request-Id` is propagated
or generated per operation and the source echoes it. Any future service credentials
will not replace Product user authorization.

## Result and failure semantics

- Success with `[]` means the source successfully reports no records. S01 and S05
  return an empty OMS parcel array. There is no `reason` envelope in S0-S1.
- A missing requested order/inquiry/shipment is 404 → ExternalNotFound. **S10 has
  an OMS parcel but logistics returns 404**, not a successful empty result. S12's
  inquiry exists but its order does not. Neither 404 may become `[]`.
- 504 and HTTPX timeout → ExternalTimeout; 5xx/429 or transport failure →
  ExternalUnavailable; 409 → ExternalConflict; other 4xx → ExternalRejected.
  S08 returns an immediate 504, not a socket timeout. S09 returns warehouse 503.
- Malformed success JSON, missing required fields, invalid timestamps, mismatched
  identities or duplicate record IDs → ExternalInvalidResponse. Source statuses
  remain open strings. Redirects and unexpected success status codes are rejected.
- Timeout, rate limit (429), and upstream 5xx are retrieval failures. They do not
  establish a parcel's business state. No automatic retry policy is implemented here.
- Use the environment plan's unified error object:
  `{"error":{"code":"LOGISTICS_TEMPORARILY_UNAVAILABLE","message":"...","request_id":"..."}}`.
  Its earlier scalar error example is illustrative; use the structured envelope.
- S0-S1 has no HTTP partial-result envelope or aggregate shipment-list endpoint.
  The older proposed `partial`/`failed_parcel_ids` envelope is not implemented.
  Providers return complete results for their narrow operation or raise; a future
  orchestrator must preserve individual failed parcels rather than dropping them.
- Cached fallback retains source provenance and original timestamps and is marked
  stale by the product; no cache miss may be fabricated into business data.

## Worked canonical example (documentation only)

```json
{
  "parcel": {
    "parcel_id": "PAR-DEMO-031",
    "external_order_id": "ORD-DEMO-003",
    "carrier": "DemoExpress",
    "tracking_number": "TRK000031",
    "source_updated_at": null,
    "fetched_at": "2026-09-20T06:12:10Z",
    "source_system": "demo_oms",
    "source_record_id": "PAR-DEMO-031"
  },
  "shipment": {
    "parcel_id": "PAR-DEMO-031",
    "status": "IN_TRANSIT",
    "source_updated_at": "2026-09-20T06:10:00Z",
    "fetched_at": "2026-09-20T06:12:10Z",
    "source_system": "demo_logistics",
    "source_record_id": "PAR-DEMO-031",
    "events": [{
      "parcel_id": "PAR-DEMO-031",
      "status": "IN_TRANSIT",
      "description": "Departed sorting facility",
      "occurred_at": "2026-09-20T06:10:00Z",
      "source_updated_at": null,
      "fetched_at": "2026-09-20T06:12:10Z",
      "source_system": "demo_logistics",
      "source_record_id": "PAR-DEMO-031"
    }]
  }
}
```

## Verification and remaining boundaries

The actual implementation was inspected in the independent sibling checkout
`demo-commerce-sandbox`: `app/schemas.py`, `app/routers/*`, `docs/api-contract.md`
and `docs/scenarios.md`. Generated `/openapi.json` is checked by real HTTP tests.
The initial Phase 1 inspection found uncommitted S0-S1 implementation files.
On 2026-10-03 the independent repository was clean at committed revision
`4131f1c4be7af6a6981e15379214d238228e8fa2` (also fetched origin/main), and Product's
real HTTP tests were rerun successfully against that baseline. No Sandbox files
or existing database were changed. See [the validation record](verification/2026-10-03-repository-sync-validation.md).

Scenario numbering differs from the original plan. S02/S04/S06/S07/S08/S09/S10/S11/S12
are tested against actual HTTP, with S01 for successful emptiness and S05 for null
updates. Seed reference time is fixed at `2026-09-20T06:00:00Z`, not reset time.
Unknown statuses and malformed responses are not available in S0-S1 seed data and
are tested with supplemental mock transports, not claimed as live scenario coverage.
Integration tests never import Sandbox code or inspect its database. Freshness
thresholds, retry budgets, aggregation, authorization and Evidence remain out of scope.
