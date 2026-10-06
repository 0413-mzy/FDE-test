"""Pure evidence projection: immutable pointers and explicit quality limits."""

import hashlib
import json
from datetime import datetime
from itertools import combinations
from uuid import UUID

from app.context.collector import FetchRecord, validate_records
from app.context.models import CaseContext, Evidence, FreshnessPolicy
from app.integrations.models import (
    OrderSnapshot,
    ParcelSnapshot,
    ShipmentSnapshot,
    SupportInquiry,
    WarehouseNoteSnapshot,
)

ORDER_STATUSES = {
    "PAID",
    "WAITING_STOCK",
    "PACKED",
    "SHIPPED",
    "PARTIALLY_SHIPPED",
    "PROCESSING",
    "DELIVERED",
}
SHIPMENT_STATUSES = {
    "LABEL_CREATED",
    "NOT_COLLECTED",
    "PICKED_UP",
    "IN_TRANSIT",
    "DELIVERED",
    "EXCEPTION",
}
HANDOVER_PHRASES = (
    "not handed to carrier today",
    "not been handed to carrier today",
    "not handed to the carrier today",
    "not been handed to the carrier today",
)


def build_context(
    *,
    context_id: UUID,
    inquiry_id: UUID,
    run_id: UUID,
    version: int,
    team_id: UUID,
    assigned_agent_id: UUID,
    external_order_id: str,
    fetches: list[FetchRecord],
    now: datetime,
    policy: FreshnessPolicy | None = None,
) -> CaseContext:
    policy = policy or FreshnessPolicy()
    evidence = []
    unknowns = []
    missing = []
    conflicts = []
    parcels = []
    required = {
        op: [f for f in fetches if f.operation == op]
        for op in ("get_inquiry", "get_order", "get_parcels")
    }
    if any(len(v) != 1 or v[0].outcome not in ("SUCCESS", "EMPTY") for v in required.values()):
        raise ValueError("Required source result unavailable")
    if len({f.id for f in fetches}) != len(fetches):
        raise ValueError("Duplicate snapshot identity")
    canonical_types = {
        "get_inquiry": SupportInquiry,
        "get_order": OrderSnapshot,
        "get_parcels": ParcelSnapshot,
        "get_shipment": ShipmentSnapshot,
        "get_notes": WarehouseNoteSnapshot,
    }
    for fetch in fetches:
        if fetch.outcome in ("SUCCESS", "EMPTY"):
            if (
                not isinstance(fetch.payload, dict)
                or set(fetch.payload) != {"records"}
                or not isinstance(fetch.payload["records"], list)
            ):
                raise ValueError("Canonical records envelope required")
            records = [
                canonical_types[fetch.operation].model_validate_json(json.dumps(record))
                for record in fetch.payload["records"]
            ]
            if (not records) != (fetch.outcome == "EMPTY"):
                raise ValueError("Source outcome disagrees with payload")
            validate_records(fetch.operation, records, fetch.target_id, external_order_id)
        elif fetch.payload is not None or fetch.fetched_at is not None:
            raise ValueError("Failed source cannot contain usable canonical payload")
    inquiry_fetch = required["get_inquiry"][0]
    inquiry = inquiry_fetch.payload["records"][0]
    order_fetch = required["get_order"][0]
    order = order_fetch.payload["records"][0]
    if (
        inquiry["inquiry_id"] != inquiry_fetch.target_id
        or inquiry["external_order_id"] != external_order_id
        or order["external_order_id"] != external_order_id
    ):
        raise ValueError("Source binding mismatch")

    def stamp(value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value

    def add(fetch, record, pointer, value, kind, category):
        eid = "ev-" + hashlib.sha256(f"{fetch.id}\n{pointer}".encode()).hexdigest()
        updated = stamp(record["source_updated_at"])
        fetched = stamp(record["fetched_at"])
        age = (now - fetched).total_seconds()
        codes = []
        if fetched > now or (updated is not None and updated > now):
            freshness = "UNKNOWN"
            codes.append("CLOCK_ANOMALY")
        elif updated is None:
            freshness = "UNKNOWN"
            codes.append("UNKNOWN_SOURCE_TIME")
        elif (now - updated).total_seconds() > getattr(
            policy.source_max_age_seconds, category
        ) or age > policy.fetch_max_age_seconds:
            freshness = "STALE"
        else:
            freshness = "FRESH"
        if age > policy.fetch_max_age_seconds:
            codes.append("OLD_FETCH")
        ev = Evidence(
            id=eid,
            kind=kind,
            source_system=record["source_system"],
            source_record_id=record["source_record_id"],
            snapshot_id=fetch.id,
            snapshot_version=version,
            pointer=pointer,
            value=value,
            source_updated_at=updated,
            fetched_at=fetched,
            occurred_at=stamp(record["occurred_at"]) if category == "shipment_event" else None,
            freshness_status=freshness,
        )
        evidence.append(ev)
        unknowns.extend({"code": c, "evidence_ids": [eid]} for c in codes)
        return eid

    order_id = add(order_fetch, order, "/records/0/status", order["status"], "FACT", "order")
    add(order_fetch, order, "/records/0/items", order["items"], "FACT", "order")
    if order["status"] not in ORDER_STATUSES:
        unknowns.append({"code": "UNKNOWN_STATUS", "evidence_ids": [order_id]})
    parcel_records = required["get_parcels"][0].payload["records"]
    parcel_ids = [p["parcel_id"] for p in parcel_records]
    identities = [(f.operation, f.target_id) for f in fetches]
    allowed = {
        ("get_inquiry", inquiry_fetch.target_id),
        ("get_order", external_order_id),
        ("get_parcels", external_order_id),
        ("get_notes", external_order_id),
    } | {("get_shipment", p) for p in parcel_ids}
    if len(set(identities)) != len(identities) or set(identities) != allowed:
        raise ValueError("Unexpected or duplicated operation target")
    if len(set(parcel_ids)) != len(parcel_ids):
        raise ValueError("Duplicate parcel identity")
    if not parcel_records:
        missing.append({"code": "NO_PARCELS", "scope": external_order_id, "evidence_ids": []})
    shipments = {}
    notes = []
    event_groups = {}
    for i, parcel in enumerate(parcel_records):
        if parcel["external_order_id"] != external_order_id:
            raise ValueError("Parcel binding mismatch")
        parcel_id = parcel["parcel_id"]
        fetch = required["get_parcels"][0]
        tracking = add(
            fetch,
            parcel,
            f"/records/{i}/tracking_number",
            parcel["tracking_number"],
            "FACT",
            "parcel",
        )
        add(fetch, parcel, f"/records/{i}/carrier", parcel["carrier"], "FACT", "parcel")
        shipment_fetches = [
            f for f in fetches if f.operation == "get_shipment" and f.target_id == parcel_id
        ]
        if len(shipment_fetches) != 1:
            raise ValueError("Parcel outcome missing or duplicated")
        sf = shipment_fetches[0]
        shipment_status = None
        event_ids = []
        if sf.outcome == "SUCCESS":
            shipment = sf.payload["records"][0]
            if shipment["parcel_id"] != parcel_id:
                raise ValueError("Shipment binding mismatch")
            shipment_status = add(
                sf, shipment, "/records/0/status", shipment["status"], "FACT", "shipment"
            )
            shipments[parcel_id] = (shipment, shipment_status)
            if shipment["status"] not in SHIPMENT_STATUSES:
                unknowns.append({"code": "UNKNOWN_STATUS", "evidence_ids": [shipment_status]})
            if not shipment["events"]:
                missing.append(
                    {"code": "NO_EVENTS", "scope": parcel_id, "evidence_ids": [shipment_status]}
                )
            seen = set()
            for j, event in enumerate(shipment["events"]):
                identity = (event["source_system"], event["source_record_id"])
                if event["parcel_id"] != parcel_id or identity in seen:
                    raise ValueError("Event binding or duplicate identity")
                seen.add(identity)
                eid = add(
                    sf,
                    event,
                    f"/records/0/events/{j}/status",
                    event["status"],
                    "FACT",
                    "shipment_event",
                )
                event_ids.append(eid)
                add(
                    sf,
                    event,
                    f"/records/0/events/{j}/description",
                    event["description"],
                    "SOURCE_TEXT",
                    "shipment_event",
                )
                if event["status"] not in SHIPMENT_STATUSES:
                    unknowns.append({"code": "UNKNOWN_STATUS", "evidence_ids": [eid]})
                event_groups.setdefault((parcel_id, stamp(event["occurred_at"])), []).append(
                    (event["status"], eid)
                )
        parcels.append(
            {
                "parcel_id": parcel_id,
                "tracking_number_evidence_id": tracking,
                "shipment_status_evidence_id": shipment_status,
                "event_evidence_ids": event_ids,
            }
        )
    notes_fetches = [f for f in fetches if f.operation == "get_notes"]
    if len(notes_fetches) != 1 or notes_fetches[0].target_id != external_order_id:
        raise ValueError("Order notes outcome missing or duplicated")
    nf = notes_fetches[0]
    if nf.outcome in ("SUCCESS", "EMPTY"):
        seen = set()
        for i, note in enumerate(nf.payload["records"]):
            identity = (note["source_system"], note["source_record_id"])
            if (
                note["external_order_id"] != external_order_id
                or note["note_id"] in seen
                or identity in seen
            ):
                raise ValueError("Note binding or duplicate identity")
            seen.update((note["note_id"], identity))
            eid = add(
                nf,
                note,
                f"/records/{i}/note_text",
                note["note_text"],
                "SOURCE_TEXT",
                "warehouse_note",
            )
            notes.append((note, eid))
        if not notes:
            missing.append(
                {"code": "NO_WAREHOUSE_NOTES", "scope": external_order_id, "evidence_ids": []}
            )
    for f in fetches:
        if f.outcome not in ("SUCCESS", "EMPTY"):
            missing.append(
                {
                    "code": "NO_TRACKING" if f.outcome == "NO_TRACKING" else "SOURCE_" + f.outcome,
                    "scope": f.target_id,
                    "evidence_ids": [],
                }
            )

    def conflict(code, ids, explanation):
        ids = sorted(ids)
        cid = "conflict-" + hashlib.sha256((code + "\n" + "\n".join(ids)).encode()).hexdigest()
        conflicts.append({"id": cid, "code": code, "evidence_ids": ids, "explanation": explanation})

    for events in event_groups.values():
        for left, right in combinations(events, 2):
            if left[0] != right[0]:
                conflict(
                    "INCOMPATIBLE_EVENT_STATUS",
                    [left[1], right[1]],
                    "Different structured statuses at the same parcel occurrence time.",
                )
    for note, nid in notes:
        if any(phrase in note["note_text"].lower() for phrase in HANDOVER_PHRASES):
            for shipment, sid in shipments.values():
                if (
                    shipment["status"] in {"PICKED_UP", "IN_TRANSIT", "DELIVERED"}
                    and shipment["source_updated_at"] is not None
                    and stamp(note["created_at"]).date()
                    == stamp(shipment["source_updated_at"]).date()
                ):
                    conflict(
                        "POSSIBLE_HANDOVER_CONFLICT",
                        [nid, sid],
                        "Same-day warehouse wording may conflict with logistics handover status; "
                        "neither source is adjudicated.",
                    )
    # Group equal quality codes to give one stable disclosure per code.
    grouped = {}
    for u in unknowns:
        grouped.setdefault(u["code"], set()).update(u["evidence_ids"])
    unknowns = [
        {"code": code, "evidence_ids": sorted(ids)} for code, ids in sorted(grouped.items())
    ]
    flags = set()
    if any(e.freshness_status == "STALE" for e in evidence):
        flags.add("STALE_DATA")
    if any(e.freshness_status == "UNKNOWN" for e in evidence):
        flags.add("UNKNOWN_FRESHNESS")
    if any(f.outcome not in ("SUCCESS", "EMPTY") for f in fetches):
        flags.add("PARTIAL_SOURCE_FAILURE")
    if missing:
        flags.add("MISSING_INFORMATION")
    if conflicts:
        flags.add("CONFLICTING_SOURCES")
    if "UNKNOWN_STATUS" in grouped:
        flags.add("UNKNOWN_STATUS")
    if "CLOCK_ANOMALY" in grouped:
        flags.add("CLOCK_ANOMALY")
    return CaseContext(
        context_id=context_id,
        inquiry_id=inquiry_id,
        run_id=run_id,
        context_version=version,
        created_at=now,
        freshness_policy=policy,
        authorization_scope={
            "inquiry_id": inquiry_id,
            "external_order_id": external_order_id,
            "team_id": team_id,
            "assigned_agent_id": assigned_agent_id,
        },
        question={
            "text": inquiry["customer_message"],
            "source_system": inquiry_fetch.source_system,
            "source_record_id": inquiry["inquiry_id"],
            "created_at": stamp(inquiry["created_at"]),
        },
        order={"external_order_id": external_order_id, "status_evidence_id": order_id},
        parcels=parcels,
        source_outcomes=[
            {
                "fetch_id": f.id,
                "operation": f.operation,
                "target_id": f.target_id,
                "outcome": f.outcome,
                "error_code": f.error_code,
                "fetched_at": f.fetched_at,
            }
            for f in fetches
        ],
        evidence=evidence,
        facts=[e.id for e in evidence if e.kind == "FACT"],
        source_texts=[e.id for e in evidence if e.kind == "SOURCE_TEXT"],
        unknowns=unknowns,
        missing_information=sorted(missing, key=lambda m: (m["code"], m["scope"])),
        conflicts=sorted(conflicts, key=lambda c: (c["code"], c["id"])),
        quality="DEGRADED" if flags else "COMPLETE",
        risk_flags=sorted(flags),
    )
