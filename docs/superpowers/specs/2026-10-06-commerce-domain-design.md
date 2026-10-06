# Commerce Step 2 design

Date: 2026-10-06. User authorized the next step after the positioning delivery.
This design freezes contract documentation only; it does not authorize starting Step 3.

## Chosen design and trade-offs

Multi-merchant physical-goods simulation, one currency (CNY integer minor units),
zero shipping/tax in the baseline. One Cart creates independent shop Orders in an
atomic Checkout; each Order pays and fulfills independently. This is simpler to
explain and test than cross-shop payment allocation/settlement, while preserving
real associations across the two interfaces. A single-shop-only product was not
chosen because merchant isolation is part of the user's target.

Reserve inventory for 15 minutes at order creation and consume on payment. Reserving
only at payment avoids abandoned reservations but makes a created order's availability
less clear; indefinite reservations can block the demo. This design explicitly shows
expiry and commits whole-order release on affected business writes or a targeted demo
command, rather than claiming an unimplemented scheduler.

Use separate CommerceAccount/Session and shop memberships, reusing security primitives
but not redefining existing support roles. Preserve the old domain as a compatible
optional module. This costs a new identity boundary but prevents accidental permission
inheritance and migration rewrites.

Orders, finance, shipments and after-sales have distinct state machines. Partial
shipments and line-level refund quantities remain explicit. Messages are persistent
customer/shop conversations with optional own-order binding, initially refreshed
through HTTP. No AI, real money, external delivery or production claims.

## Authoritative package

- [Index and frozen decisions](../../commerce/README.md)
- [Domain and relationships](../../commerce/domain.md)
- [Authorization](../../commerce/permissions.md)
- [Lifecycle and transactions](../../commerce/lifecycle.md)
- [Planned API](../../commerce/api.md)
- [Acceptance matrix](../../commerce/acceptance.md)

Self-review checks identity isolation, price confirmation, quantity/money conservation,
expiry/replay ordering, aggregate versions, refund restocking, endpoint permissions,
source timestamps and phase scope. All acceptance scenarios remain NOT_RUN.
No implementation plan is executed in this documentation task; Step 3 must first be
split into identity/catalog, checkout/payment and fulfillment vertical slices.
