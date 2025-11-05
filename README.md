# Smart Delivery API – Developer Guide

**Version:** 1.0
**Audience:** Backend/Frontend engineers, QA, Integrators
**Base URL (local dev):** `http://localhost:8000`
**Auth:** None (demo). Add your gateway in front for prod.
**Time zone:** All timestamps are **UTC** ISO‑8601.

---

## Quick Start

1. Run the API (Docker or local Python).
2. Seed sample stops with **`POST /dev/mock-data`**.
3. Create a cart with **`POST /cart`**.
4. Resolve a location with **`POST /locations/resolve`**.
5. Fetch slot offers with **`GET /delivery/slots`**.
6. Create a quote with **`POST /checkout/quote`**.
7. Create a payment intent and simulate webhook success.

> Explore interactively at **`/docs`** (Swagger UI) or **`/redoc`**.

---

## Conventions

* **Money:** Integer cents (e.g., 450 = €4.50).
* **Percentages:** Decimals (0.12 = 12%).
* **Coordinates:** WGS‑84 lat/lon (float).
* **Units:** `unit_factor` per product; solo‑minimum rule uses the sum of unit factors.
* **Discount logic:** See “Slot Scoring & Discounts” in the system documentation.

---

## 1) Create/Update Cart – `POST /cart`

Create a cart and compute a quick subtotal.

### Request

```json
{
  "items": [
    {"productId": "p_1", "qty": 2},
    {"productId": "p_2", "qty": 1}
  ]
}
```

**Fields**

* `items[]` – Array of line items.

  * `productId` – String; must match a known product (seeded in memory).
  * `qty` – Integer ≥ 1.

### Response

```json
{
  "cartId": "c_a1b2c3d4e5",
  "subtotalCents": 950,
  "items": [
    {"productId": "p_1", "qty": 2},
    {"productId": "p_2", "qty": 1}
  ]
}
```

**Fields**

* `cartId` – Use in later calls.
* `subtotalCents` – Sum of product prices × qty.

### Errors

* `400` – Invalid payload.
* `404` – Unknown product id (filtered out in demo; customize for prod).

---

## 2) Resolve Location – `POST /locations/resolve`

Geocodes an address to lat/lon. (Demo uses a fixed coordinate.)

### Request

```json
{ "address": "Erottajankatu 1, Helsinki" }
```

**Fields**

* `address` – Free‑form string.

### Response

```json
{
  "locationId": "loc_12345",
  "lat": 60.1699,
  "lon": 24.9384,
  "addressText": "Erottajankatu 1, Helsinki"
}
```

**Fields**

* `locationId` – Use in quoting/checkout.
* `lat`, `lon` – Doubles; WGS‑84.
* `addressText` – Canonicalized address string.

---

## 3) List Delivery Slots – `GET /delivery/slots`

Returns candidate slots with dynamic discounts.

### Query Parameters

* `cartId` *(required)* – Cart identifier from `/cart`.
* `lat`, `lon` *(required)* – User location.
* `fromISO` *(optional)* – ISO‑8601 start filter (UTC).
* `toISO` *(optional)* – ISO‑8601 end filter (UTC).

### Example

```
GET /delivery/slots?cartId=c_a1b2&lat=60.1699&lon=24.9384
```

### Response

```json
{
  "computedAt": "2025-11-05T10:00:00Z",
  "params": {
    "radiusM": 3000.0,
    "t0Min": 30.0,
    "d0M": 800.0,
    "maxDiscount": 0.2,
    "k": 1.0,
    "sMin": 0.05,
    "minSoloUnits": 6
  },
  "slots": [
    {
      "slotId": "sl_abc",
      "startAt": "2025-11-05T16:00:00Z",
      "endAt": "2025-11-05T16:30:00Z",
      "baseDeliveryFeeCents": 450,
      "discountPct": 0.12,
      "discountCents": 54,
      "finalDeliveryFeeCents": 396,
      "label": "Best deal",
      "capacity": {"total": 12, "used": 8},
      "requiresSoloMinUnits": false,
      "soloMinUnits": 6
    },
    {
      "slotId": "sl_xyz",
      "startAt": "2025-11-05T17:00:00Z",
      "endAt": "2025-11-05T17:30:00Z",
      "baseDeliveryFeeCents": 450,
      "discountPct": 0.00,
      "discountCents": 0,
      "finalDeliveryFeeCents": 450,
      "label": "Standard",
      "capacity": {"total": 12, "used": 0},
      "requiresSoloMinUnits": true,
      "soloMinUnits": 6
    }
  ]
}
```

**Important fields**

* `discountPct` – Decimal fraction (e.g., `0.12` = 12%).
* `finalDeliveryFeeCents` – After discount and fee floor.
* `label` – UI hint: `Best deal | Good deal | Standard`.
* `requiresSoloMinUnits` – **true** if the slot has no neighbors / too low score → cart must reach `soloMinUnits` units.
* `params` – Snapshot of scoring config used for transparency & debugging.

### Errors

* `404` – Cart not found.

---

## 4) Create Quote – `POST /checkout/quote`

Locks the delivery price for a slot (15‑min TTL in demo) and enforces the solo‑minimum rule.

### Request

```json
{
  "cartId": "c_a1b2c3",
  "slotId": "sl_abc",
  "locationId": "loc_123"
}
```

**Fields**

* `cartId` – From `/cart`.
* `slotId` – From `/delivery/slots`.
* `locationId` – From `/locations/resolve`.

### Response

```json
{
  "quoteId": "q_9f8e7d6c",
  "lockedUntil": "2025-11-05T10:15:00Z",
  "amounts": {
    "subtotalCents": 950,
    "deliveryFeeCents": 396,
    "discountCents": 54,
    "totalCents": 1346
  }
}
```

**Fields**

* `lockedUntil` – After this time the quote is stale; re‑quote required.
* `deliveryFeeCents` – Final delivery fee after discount and floor.
* `discountCents` – Savings applied to delivery fee.

### Errors

* `404` – cart/slot/location not found.
* `400 SOLO_MIN_UNITS_REQUIRED` – When the selected slot has no neighbors and the cart’s units sum < required.

**Error example**

```json
{
  "detail": {
    "error": "SOLO_MIN_UNITS_REQUIRED",
    "message": "This time has no nearby deliveries. Add at least 6 items or choose a discounted time.",
    "soloMinUnits": 6
  }
}
```

---

## 5) Create Payment Intent – `POST /payments/create`

Returns a mock client secret for the quote. Replace with your PSP integration.

### Request

```json
{ "quoteId": "q_9f8e7d6c" }
```

### Response

```json
{ "clientSecret": "pi_secret_q_9f8e7d6c", "paymentProvider": "stub-pay" }
```

### Errors

* `404` – Quote not found.

---

## 6) Payment Webhook – `POST /webhooks/payment`

PSP calls this when the payment succeeds. The demo immediately confirms the order and increments slot capacity usage.

### Request (success)

```json
{ "event": "payment_succeeded", "quoteId": "q_9f8e7d6c" }
```

### Response

```json
{ "status": "ok" }
```

> In production, make this endpoint **idempotent** and verify PSP signatures.

---

## 7) Seed Mock Data – `POST /dev/mock-data`

Creates synthetic **scheduled stops** near a center point to test batching/discounts.

### Request

```json
{
  "centerLat": 60.1699,
  "centerLon": 24.9384,
  "days": 1,
  "density": "medium"
}
```

**Fields**

* `centerLat`, `centerLon` – Center for spatial jitter (~2 km).
* `days` – Currently informational; demo distributes stops across ~12 hours.
* `density` – `low | medium | high` → number of stops created.

### Response

```json
{ "createdStops": ["st_123", "st_456", "st_789"], "count": 25 }
```

---

## End‑to‑End Example (cURL)

```bash
# 1) Seed neighbors around Helsinki center
curl -X POST http://localhost:8000/dev/mock-data \
  -H 'Content-Type: application/json' \
  -d '{"centerLat":60.1699,"centerLon":24.9384,"density":"medium"}'

# 2) Create a cart
curl -X POST http://localhost:8000/cart \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"productId":"p_1","qty":2},{"productId":"p_2","qty":1}]}'
# => grab cartId

# 3) Resolve a location (mock geocode)
curl -X POST http://localhost:8000/locations/resolve \
  -H 'Content-Type: application/json' \
  -d '{"address":"Erottajankatu 1, Helsinki"}'
# => grab locationId, lat, lon

# 4) List slots near that location
curl "http://localhost:8000/delivery/slots?cartId=<cartId>&lat=60.1699&lon=24.9384"
# => pick a slotId

# 5) Create a quote
curl -X POST http://localhost:8000/checkout/quote \
  -H 'Content-Type: application/json' \
  -d '{"cartId":"<cartId>","slotId":"<slotId>","locationId":"<locationId>"}'
# => grab quoteId

# 6) Create payment intent
curl -X POST http://localhost:8000/payments/create \
  -H 'Content-Type: application/json' \
  -d '{"quoteId":"<quoteId>"}'

# 7) Simulate PSP webhook success
curl -X POST http://localhost:8000/webhooks/payment \
  -H 'Content-Type: application/json' \
  -d '{"event":"payment_succeeded","quoteId":"<quoteId>"}'
```

---

## Field Reference (by object)

### SlotOut

* `slotId` – Slot identifier.
* `startAt`, `endAt` – ISO‑8601 UTC timestamps for the 30‑min window.
* `baseDeliveryFeeCents` – Fee before discount.
* `discountPct` – Decimal fraction (0.2 → 20%).
* `discountCents` – Integer cents saved on delivery fee.
* `finalDeliveryFeeCents` – Fee after discount/floor.
* `label` – UI label (`Best deal | Good deal | Standard`).
* `capacity` – Object `{ total, used }`.
* `requiresSoloMinUnits` – If **true**, cart must meet `soloMinUnits`.
* `soloMinUnits` – Minimum units required for solo slots.

### QuoteOut

* `quoteId` – Use to create payment intent.
* `lockedUntil` – Quote expiry time.
* `amounts` – `{ subtotalCents, deliveryFeeCents, discountCents, totalCents }`.

### MockDataIn

* `centerLat`, `centerLon` – Where synthetic stops will cluster.
* `days` – Informational; future enhancement to spread across N days.
* `density` – `low|medium|high` number of stops.

---

## Common Errors

* `400 SOLO_MIN_UNITS_REQUIRED` – Slot has no neighbors and cart hasn’t reached `soloMinUnits` (default 6).
* `404 Cart not found` – Unknown cart id in slots/quote.
* `404 Quote not found` – Unknown quote in payments.
* `404 cart/slot/location not found` – During quoting.

---

## Tips & Best Practices

* Always call **`/delivery/slots`** just before quoting to show fresh discounts.
* Cache slot lists for 1–2 minutes in UI to reduce flicker.
* Respect **`requiresSoloMinUnits`** and guide users to high‑discount slots when possible.
* Use **idempotency keys** for write operations in production.
* Make your webhook handler idempotent and verify signatures with your PSP.

---

## Configuration (env vars)

* `MAX_DISCOUNT` – e.g., `0.20` for 20% cap.
* `K` – Steepness of discount curve (higher = faster growth).
* `D0_M`, `T0_MIN` – Spatial/time decay parameters.
* `RADIUS_M` – Neighbor search radius (meters).
* `S_MIN` – Minimum score threshold to avoid solo rule.
* `MIN_SOLO_UNITS` – Minimum units when solo rule applies.
* `BASE_DELIVERY_FEE_CENTS`, `MIN_DELIVERY_FEE_CENTS` – Pricing floors.

---

## Change Log

* **v1.0** – Initial release: carts, location resolve, slots with discounts, quote, payments stub, webhook, mock seeder.
