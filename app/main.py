# app/main.py
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, and_, func, delete, text
import math
from .config import settings
from .db import db_session, engine
from .bootstrap import bootstrap, seed_products, seed_slots
from .util import gen_id
from .models import (
    Product,
    Cart,
    CartItem,
    DeliverySlot,
    ScheduledStop,
    Quote,
)
from .schemas import (
    CartCreateIn,
    CartSummaryOut,
    SlotsResponse,
    SlotOut,
    QuoteIn,
    QuoteOut,
    PaymentCreateIn,
    PaymentCreateOut,
    WebhookIn,
    MockDataIn,
)
from .scoring import (
    score_slot,
    discount_from_score,
    label_for_discount,
    clamp_fee,
    solo_minimum_required,
    params_snapshot,
    haversine_m,
)
from .payments_stub import create_payment_intent, finalize_quote


app = FastAPI(title="Smart Delivery API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # open for test stage
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables and seed products/slots on startup
bootstrap()


# ---------- helpers ----------

def parse_iso_z(s: str) -> datetime:
    """Parse ISO-8601 allowing 'Z' suffix; return timezone-aware UTC."""
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calc_cart_subtotal_cents_by_id(cart_id: str) -> int:
    """Compute subtotal (in cents) using a single DB session by cart_id."""
    with db_session() as db:
        q = (
            select(func.coalesce(func.sum(Product.price_cents * CartItem.qty), 0))
            .join(CartItem, CartItem.product_id == Product.id)
            .where(CartItem.cart_id == cart_id)
        )
        return int(db.execute(q).scalar() or 0)


def cart_units_total_by_id(cart_id: str) -> int:
    """Sum of unit_factor * qty for solo-minimum rule, by cart_id."""
    with db_session() as db:
        q = (
            select(func.coalesce(func.sum(Product.unit_factor * CartItem.qty), 0))
            .join(CartItem, CartItem.product_id == Product.id)
            .where(CartItem.cart_id == cart_id)
        )
        return int(db.execute(q).scalar() or 0)


# ---------- endpoints ----------

@app.post("/cart", response_model=CartSummaryOut)
def create_cart(payload: CartCreateIn):
    """
    Create a cart with items and return a subtotal.
    """
    with db_session() as db:
        c = Cart(id=gen_id("c"), user_id=None)
        db.add(c)
        db.flush()  # ensure c.id is persisted

        for i in payload.items:
            if not db.get(Product, i.productId):
                raise HTTPException(404, detail=f"Unknown product {i.productId}")
            db.add(CartItem(cart_id=c.id, product_id=i.productId, qty=i.qty))

        db.flush()
        subtotal = calc_cart_subtotal_cents_by_id(c.id)

        return CartSummaryOut(
            cartId=c.id,
            subtotalCents=subtotal,
            items=payload.items,
        )


@app.get("/delivery/slots", response_model=SlotsResponse)
def get_slots(
    cartId: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    fromISO: str | None = Query(None),
    toISO: str | None = Query(None),
):
    """
    List candidate slots with dynamic discounts for a given user location (lat/lon).
    """
    with db_session() as db:
        cart = db.get(Cart, cartId)
        if not cart:
            raise HTTPException(404, detail="Cart not found")

        now = datetime.now(timezone.utc)
        start_time = parse_iso_z(fromISO) if fromISO else now
        end_time = parse_iso_z(toISO) if toISO else now + timedelta(days=7)

        # fetch candidate slots
        slots = (
            db.execute(
                select(DeliverySlot).where(
                    and_(
                        DeliverySlot.start_at >= start_time,
                        DeliverySlot.start_at <= end_time,
                    )
                )
            )
            .scalars()
            .all()
        )

        out: List[SlotOut] = []
        for s in sorted(slots, key=lambda x: x.start_at):
            # window for temporal neighbor filter
            win_start = s.start_at - timedelta(minutes=settings.T0_MIN)
            win_end = s.end_at + timedelta(minutes=settings.T0_MIN)

            # get time neighbors, then spatial filter them by radius
            neigh = (
                db.execute(
                    select(ScheduledStop).where(
                        and_(
                            ScheduledStop.scheduled_at >= win_start,
                            ScheduledStop.scheduled_at <= win_end,
                        )
                    )
                )
                .scalars()
                .all()
            )
            neighbors = [
                n for n in neigh
                if haversine_m(lat, lon, n.lat, n.lon) <= settings.RADIUS_M
            ]

            score = score_slot(lat, lon, s, neighbors)
            disc_pct = discount_from_score(score)
            final_fee, discount_cents, base_fee = clamp_fee(
                settings.BASE_DELIVERY_FEE_CENTS, disc_pct
            )
            requires_solo = solo_minimum_required(score, len(neighbors))
            label = label_for_discount(disc_pct)

            out.append(
                SlotOut(
                    slotId=s.id,
                    startAt=s.start_at,
                    endAt=s.end_at,
                    baseDeliveryFeeCents=base_fee,
                    discountPct=round(disc_pct, 4),
                    discountCents=discount_cents,
                    finalDeliveryFeeCents=final_fee,
                    label=label,
                    capacity={"total": s.capacity_total, "used": s.capacity_used},
                    requiresSoloMinUnits=requires_solo,
                    soloMinUnits=settings.MIN_SOLO_UNITS,
                )
            )

        return SlotsResponse(computedAt=now, params=params_snapshot(), slots=out)


@app.post("/checkout/quote", response_model=QuoteOut)
def checkout_quote(payload: QuoteIn):
    """
    Price a cart for a given slot and user coordinates; enforce solo-minimum if needed.
    """
    with db_session() as db:
        cart = db.get(Cart, payload.cartId)
        slot = db.get(DeliverySlot, payload.slotId)
        if not (cart and slot):
            raise HTTPException(404, detail="cart/slot not found")

        # neighbors around the slot
        win_start = slot.start_at - timedelta(minutes=settings.T0_MIN)
        win_end = slot.end_at + timedelta(minutes=settings.T0_MIN)
        neigh = (
            db.execute(
                select(ScheduledStop).where(
                    and_(
                        ScheduledStop.scheduled_at >= win_start,
                        ScheduledStop.scheduled_at <= win_end,
                    )
                )
            )
            .scalars()
            .all()
        )
        neighbors = [
            n for n in neigh
            if haversine_m(payload.lat, payload.lon, n.lat, n.lon) <= settings.RADIUS_M
        ]

        score = score_slot(payload.lat, payload.lon, slot, neighbors)
        disc_pct = discount_from_score(score)
        final_fee, discount_cents, base_fee = clamp_fee(
            settings.BASE_DELIVERY_FEE_CENTS, disc_pct
        )

        # enforce solo-minimum if applicable
        if solo_minimum_required(score, len(neighbors)):
            units = cart_units_total_by_id(cart.id)
            if units < settings.MIN_SOLO_UNITS:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "SOLO_MIN_UNITS_REQUIRED",
                        "message": f"This time has no nearby deliveries. Add at least {settings.MIN_SOLO_UNITS} items or choose a discounted time.",
                        "soloMinUnits": settings.MIN_SOLO_UNITS,
                    },
                )

        subtotal = calc_cart_subtotal_cents_by_id(cart.id)
        total = subtotal + final_fee

        qid = gen_id("q")
        q = Quote(
            id=qid,
            cart_id=cart.id,
            slot_id=slot.id,
            subtotal_cents=subtotal,
            delivery_fee_cents=final_fee,
            discount_cents=discount_cents,
            total_cents=total,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=15),
            # store user coordinates on the quote so payment finalization can create a ScheduledStop
            lat=payload.lat,
            lon=payload.lon,
        )
        db.add(q)

        return QuoteOut(
            quoteId=q.id,
            lockedUntil=q.locked_until,
            amounts=dict(
                subtotalCents=subtotal,
                deliveryFeeCents=final_fee,
                discountCents=discount_cents,
                totalCents=total,
            ),
        )


@app.post("/payments/create", response_model=PaymentCreateOut)
def payments_create(payload: PaymentCreateIn):
    """
    Stub PSP: returns a fake clientSecret for the given quoteId.
    """
    secret = create_payment_intent(payload.quoteId)
    return PaymentCreateOut(clientSecret=secret)


@app.post("/webhooks/payment")
def webhook_payment(payload: WebhookIn):
    """
    PSP webhook: on success, finalize the quote, create Order and a ScheduledStop.
    """
    if payload.event == "payment_succeeded":
        finalize_quote(payload.quoteId)
        return {"status": "ok"}
    return {"status": "ignored"}


@app.post("/dev/mock-data")
def create_mock_data(in_: MockDataIn):
    """
    Create synthetic scheduled stops near a center point to test discounts/batching.
    density: low ≈10, medium ≈25, high ≈60
    """
    from math import cos, pi

    with db_session() as db:
        created = []
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        target = {"low": 10, "medium": 25, "high": 60}.get(in_.density, 25)

        for i in range(target):
            minutes_ahead = (i * 20) % (12 * 60)  # spread across ~12h
            when = now + timedelta(minutes=minutes_ahead)

            # jitter ~2km
            dlat = (0.018 * (i % 5 - 2) / 2.0)
            dlon = (0.036 * (i % 7 - 3) / 2.0) * cos(in_.centerLat * pi / 180.0)

            s = ScheduledStop(
                id=gen_id("st"),
                order_id=None,
                lat=in_.centerLat + dlat,
                lon=in_.centerLon + dlon,
                scheduled_at=when,
                status="scheduled",
                weight=1.0,
            )
            db.add(s)
            created.append(s.id)

        return {"createdStops": created, "count": len(created)}


@app.post("/dev/clear-db")
def clear_db(full: bool = Query(False, description="If true, also clears & reseeds slots (products are kept).")):
    """
    DEV-ONLY: Clear database data without any token (test stage).
      - soft (default): clears carts, cart_items, quotes, orders, scheduled_stops; resets slot capacity_used.
      - full=true: ALSO clears delivery_slots and then reseeds slots. Products are KEPT.
    """
    # ---- Phase 1: do the TRUNCATE in its own transaction (no nested sessions) ----
    try:
        with engine.begin() as conn:
            if full:
                # Keep products; drop & reseed only slots and dynamic data
                conn.execute(text("""
                    TRUNCATE TABLE
                        scheduled_stops,
                        orders,
                        quotes,
                        cart_items,
                        carts,
                        delivery_slots
                    RESTART IDENTITY CASCADE;
                """))
            else:
                # Soft wipe: keep products & slots; just clear dynamic data and reset capacity
                conn.execute(text("""
                    TRUNCATE TABLE
                        scheduled_stops,
                        orders,
                        quotes,
                        cart_items,
                        carts
                    RESTART IDENTITY CASCADE;
                """))
                conn.execute(text("UPDATE delivery_slots SET capacity_used = 0;"))
    except Exception:
        # Portable fallback (e.g., SQLite)
        with db_session() as db:
            db.execute(delete(ScheduledStop))
            db.execute(delete(Quote))
            db.execute(delete(CartItem))
            db.execute(delete(Cart))
            if full:
                db.execute(delete(DeliverySlot))
            else:
                db.execute(text("UPDATE delivery_slots SET capacity_used = 0;"))

    # ---- Phase 2: reseed (outside the TRUNCATE transaction to avoid locks) ----
    if full:
        # Keep products, only reseed slots
        seed_slots()
        return {
            "status": "ok",
            "mode": "full",
            "wiped": ["delivery_slots", "carts", "cart_items", "quotes", "orders", "scheduled_stops"],
            "products": "kept",
            "slots": "reseeded",
            "reseeded": True,
        }
    else:
        return {
            "status": "ok",
            "mode": "soft",
            "wiped": ["carts", "cart_items", "quotes", "orders", "scheduled_stops"],
            "products": "kept",
            "slots": "kept (capacity_used reset)",
            "reseeded": False,
        }

# Debug: inspect neighbors & score for a specific slot / location
@app.get("/dev/debug-neighbors")
def debug_neighbors(slotId: str, lat: float, lon: float):
    from sqlalchemy import and_
    now = datetime.now(timezone.utc)
    with db_session() as db:
        slot = db.get(DeliverySlot, slotId)
        if not slot:
            raise HTTPException(404, "slot not found")

        win_start = slot.start_at - timedelta(minutes=settings.T0_MIN)
        win_end = slot.end_at + timedelta(minutes=settings.T0_MIN)
        neigh = (
            db.execute(
                select(ScheduledStop).where(
                    and_(
                        ScheduledStop.scheduled_at >= win_start,
                        ScheduledStop.scheduled_at <= win_end,
                    )
                )
            ).scalars().all()
        )

        # Keep only within radius
        within = []
        for n in neigh:
            d = haversine_m(lat, lon, n.lat, n.lon)
            if d <= settings.RADIUS_M:
                within.append({"id": n.id, "dist_m": round(d, 2), "when": n.scheduled_at.isoformat()})
        score = score_slot(lat, lon, slot, [db.get(ScheduledStop, x["id"]) for x in within])

        return {
            "slot": {"id": slot.id, "start_at": slot.start_at.isoformat()},
            "t0_min": settings.T0_MIN,
            "radius_m": settings.RADIUS_M,
            "neighbors_in_time": len(neigh),
            "neighbors_within_radius": within,
            "score": score,
            "expected_discount_pct": round(settings.MAX_DISCOUNT * (1 - math.exp(-settings.K * score)), 6),
        }
