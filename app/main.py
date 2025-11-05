from datetime import datetime, timedelta
from typing import List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import storage
from .models import ScheduledStop
from .schemas import (
    CartCreateIn, CartSummaryOut, LocationResolveIn, LocationOut,
    SlotsResponse, SlotOut, QuoteIn, QuoteOut,
    PaymentCreateIn, PaymentCreateOut, WebhookIn, MockDataIn
)
from .scoring import (
    score_slot, discount_from_score, label_for_discount,
    clamp_fee, solo_minimum_required, params_snapshot, haversine_m
)
from .payments_stub import create_payment_intent, finalize_quote

app = FastAPI(title="Smart Delivery API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Bootstrap defaults
storage.ensure_products()
storage.ensure_slots()

@app.post("/cart", response_model=CartSummaryOut)
def create_cart(payload: CartCreateIn):
    items = [(i.productId, i.qty) for i in payload.items]
    cart = storage.upsert_cart(items)
    subtotal = storage.calc_cart_subtotal_cents(cart)
    return CartSummaryOut(cartId=cart.id, subtotalCents=subtotal, items=payload.items)

@app.post("/locations/resolve", response_model=LocationOut)
def resolve_location(payload: LocationResolveIn):
    # Demo: mock geocoding by returning a fixed coordinate if not matched.
    # Replace with real geocoding in production.
    # For determinism, place everything around a city center.
    loc = storage.add_location(
        address=payload.address,
        lat=60.1699,  # Helsinki center
        lon=24.9384
    )
    return LocationOut(locationId=loc.id, lat=loc.lat, lon=loc.lon, addressText=loc.address)

@app.get("/delivery/slots", response_model=SlotsResponse)
def get_slots(
    cartId: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    fromISO: str | None = Query(None),
    toISO: str | None = Query(None),
):
    cart = storage.CARTS.get(cartId)
    if not cart:
        raise HTTPException(404, "Cart not found")

    # Filter slots by time window
    now = datetime.utcnow()
    start_time = datetime.fromisoformat(fromISO) if fromISO else now
    end_time = datetime.fromisoformat(toISO) if toISO else now + timedelta(days=7)

    # Build list of candidate slots
    candidates = [s for s in storage.SLOTS.values() if start_time <= s.start_at <= end_time]
    # Collect neighbors for each slot (simple time & space filter)
    slots_out: List[SlotOut] = []
    for s in sorted(candidates, key=lambda x: x.start_at):
        # Neighbor window ± T0_MIN
        win_start = s.start_at - timedelta(minutes=settings.T0_MIN)
        win_end = s.end_at + timedelta(minutes=settings.T0_MIN)
        neighbors = []
        for stop in storage.STOPS.values():
            if win_start <= stop.scheduled_at <= win_end:
                # distance gate
                d = haversine_m(lat, lon, stop.lat, stop.lon)
                if d <= settings.RADIUS_M:
                    neighbors.append(stop)

        score = score_slot(lat, lon, s, neighbors)
        disc_pct = discount_from_score(score)
        final_fee, discount_cents, base_fee = clamp_fee(settings.BASE_DELIVERY_FEE_CENTS, disc_pct)

        requires_solo = solo_minimum_required(score, len(neighbors))
        label = label_for_discount(disc_pct)

        slots_out.append(SlotOut(
            slotId=s.id,
            startAt=s.start_at, endAt=s.end_at,
            baseDeliveryFeeCents=base_fee,
            discountPct=round(disc_pct, 4),
            discountCents=discount_cents,
            finalDeliveryFeeCents=final_fee,
            label=label,
            capacity={"total": s.capacity_total, "used": s.capacity_used},
            requiresSoloMinUnits=requires_solo,
            soloMinUnits=settings.MIN_SOLO_UNITS
        ))

    return SlotsResponse(computedAt=now, params=params_snapshot(), slots=slots_out)

@app.post("/checkout/quote", response_model=QuoteOut)
def checkout_quote(payload: QuoteIn):
    cart = storage.CARTS.get(payload.cartId)
    slot = storage.SLOTS.get(payload.slotId)
    loc = storage.LOCATIONS.get(payload.locationId)
    if not (cart and slot and loc):
        raise HTTPException(404, "cart/slot/location not found")

    # Compute neighbors again (authoritative check)
    win_start = slot.start_at - timedelta(minutes=settings.T0_MIN)
    win_end = slot.end_at + timedelta(minutes=settings.T0_MIN)
    neighbors = []
    for stop in storage.STOPS.values():
        if win_start <= stop.scheduled_at <= win_end:
            d = haversine_m(loc.lat, loc.lon, stop.lat, stop.lon)
            if d <= settings.RADIUS_M:
                neighbors.append(stop)

    score = score_slot(loc.lat, loc.lon, slot, neighbors)
    disc_pct = discount_from_score(score)
    final_fee, discount_cents, base_fee = clamp_fee(settings.BASE_DELIVERY_FEE_CENTS, disc_pct)

    # Solo minimum enforcement
    if solo_minimum_required(score, len(neighbors)):
        units = storage.cart_units_total(cart)
        if units < settings.MIN_SOLO_UNITS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "SOLO_MIN_UNITS_REQUIRED",
                    "message": f"This time has no nearby deliveries. Add at least {settings.MIN_SOLO_UNITS} items or choose a discounted time.",
                    "soloMinUnits": settings.MIN_SOLO_UNITS
                }
            )

    subtotal = storage.calc_cart_subtotal_cents(cart)
    total = subtotal + final_fee

    qid = storage.gen_id("q")
    quote = storage.Quote(
        id=qid, cart_id=cart.id, slot_id=slot.id, location_id=loc.id,
        subtotal_cents=subtotal, delivery_fee_cents=final_fee,
        discount_cents=discount_cents, total_cents=total,
        locked_until=datetime.utcnow() + timedelta(minutes=15)
    )
    storage.QUOTES[qid] = quote
    # (Optional) capacity holds could be modeled with a separate counter.

    return QuoteOut(
        quoteId=quote.id,
        lockedUntil=quote.locked_until,
        amounts=dict(
            subtotalCents=subtotal,
            deliveryFeeCents=final_fee,
            discountCents=discount_cents,
            totalCents=total
        )
    )

@app.post("/payments/create", response_model=PaymentCreateOut)
def payments_create(payload: PaymentCreateIn):
    if payload.quoteId not in storage.QUOTES:
        raise HTTPException(404, "Quote not found")
    secret = create_payment_intent(payload.quoteId)
    return PaymentCreateOut(clientSecret=secret)

@app.post("/webhooks/payment")
def webhook_payment(payload: WebhookIn):
    # Minimal stub: finalize immediately on success
    if payload.event == "payment_succeeded":
        finalize_quote(payload.quoteId)
        return {"status": "ok"}
    return {"status": "ignored"}

# --- Mock data seeder for testing ---

@app.post("/dev/mock-data")
def create_mock_data(in_: MockDataIn):
    """
    Seeds:
      - a location (user provides via /locations/resolve in real flow)
      - a bunch of scheduled stops distributed around centerLat/Lon across the next day
    density: low ≈ 10, medium ≈ 25, high ≈ 60
    """
    density_map = {"low": 10, "medium": 25, "high": 60}
    n = density_map.get(in_.density, 25)

    # Ensure slots exist
    storage.ensure_slots()

    now = datetime.utcnow().replace(second=0, microsecond=0)
    created_ids = []
    for i in range(n):
        minutes_ahead = (i * 20) % (12 * 60)  # spread across 12h
        when = now + timedelta(minutes=minutes_ahead)
        # jitter location within ~2km radius
        # ~0.018 deg ≈ 2 km latitude
        jitter_lat = in_.centerLat + (0.018 * (i % 5 - 2) / 2)
        jitter_lon = in_.centerLon + (0.036 * (i % 7 - 3) / 2)  # ~2km in Helsinki

        sid = storage.gen_id("st")
        storage.STOPS[sid] = ScheduledStop(
            id=sid, order_id=None, lat=jitter_lat, lon=jitter_lon,
            scheduled_at=when, status="scheduled", weight=1.0
        )
        created_ids.append(sid)

    return {"createdStops": created_ids, "count": len(created_ids)}
