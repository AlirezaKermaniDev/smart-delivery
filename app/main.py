from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone, time as dtime
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, and_
import httpx

from .config import settings
from .db import db_session
from .models import (
    Product,
    Cart,
    CartItem,
    DeliverySlot,
    Quote,
    ScheduledStop,
    Setting,
    Order
)
from .bootstrap import bootstrap
from .scoring import (
    score_slot,
    discount_from_score,
    clamp_fee,
    solo_minimum_required,
    haversine_m,
)
from .schemas import (
    CreateCartRequest,
    CreateCartResponse,
    SlotsResponse,
    SlotOut,
    SlotCapacity,
    QuoteIn,
    QuoteOut,
    QuoteAmounts,
    PaymentCreateIn,
    PaymentCreateOut,
    WebhookPaymentIn,
    AppSettings,
    AvailabilityWindow,
    RoutingEstimateResponse,
    TravelDurations,
)

# Ensure schema + seed on startup import
bootstrap()

app = FastAPI(title="Smart Delivery API")


# ----------------------
# CORS
# ----------------------

origins = ["*"]
if settings.APP_DOMAIN:
    origins = [f"https://{settings.APP_DOMAIN}", f"http://{settings.APP_DOMAIN}"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------
# Utility helpers
# ----------------------


def parse_iso_z(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def params_snapshot() -> dict:
    return {
        "baseDeliveryFeeCents": settings.BASE_DELIVERY_FEE_CENTS,
        "minDeliveryFeeCents": settings.MIN_DELIVERY_FEE_CENTS,
        "maxDiscount": settings.MAX_DISCOUNT,
        "k": settings.K,
        "radiusM": settings.RADIUS_M,
        "t0Min": settings.T0_MIN,
        "minSoloUnits": settings.MIN_SOLO_UNITS,
        "deliveryType": getattr(settings, "DELIVERY_TYPE", "motorcycle"),
    }


def calc_cart_subtotal_cents_by_id(db, cart_id: str) -> int:
    cart = db.get(Cart, cart_id)
    if not cart:
        raise HTTPException(404, detail="Cart not found")
    subtotal = 0
    for item in cart.items:
        subtotal += item.qty * item.product.price_cents
    return subtotal


def cart_units_total_by_id(db, cart_id: str) -> int:
    cart = db.get(Cart, cart_id)
    if not cart:
        raise HTTPException(404, detail="Cart not found")
    total_units = 0
    for item in cart.items:
        total_units += item.qty * item.product.unit_factor
    return total_units


# ----------------------
# Settings helpers
# ----------------------


def load_app_settings(db) -> AppSettings:
    rec = db.get(Setting, "global")
    if rec:
        return AppSettings(**rec.value)

    # Fallback to env defaults if row missing
    return AppSettings(
        baseDeliveryFeeCents=settings.BASE_DELIVERY_FEE_CENTS,
        minDeliveryFeeCents=settings.MIN_DELIVERY_FEE_CENTS,
        maxDiscount=settings.MAX_DISCOUNT,
        k=settings.K,
        radiusM=settings.RADIUS_M,
        t0Min=settings.T0_MIN,
        minSoloUnits=settings.MIN_SOLO_UNITS,
        availability=[
            AvailabilityWindow(
                daysOfWeek=[1, 2, 3, 4, 5], startTime="13:00", endTime="17:00"
            )
        ],
        deliveryType="motorcycle",
    )


def apply_settings_to_runtime(cfg_model: AppSettings):
    settings.BASE_DELIVERY_FEE_CENTS = cfg_model.baseDeliveryFeeCents
    settings.MIN_DELIVERY_FEE_CENTS = cfg_model.minDeliveryFeeCents
    settings.MAX_DISCOUNT = cfg_model.maxDiscount
    settings.K = cfg_model.k
    settings.RADIUS_M = cfg_model.radiusM
    settings.T0_MIN = cfg_model.t0Min
    settings.MIN_SOLO_UNITS = cfg_model.minSoloUnits
    settings.DELIVERY_TYPE = cfg_model.deliveryType


def slot_allowed(start_at: datetime, cfg_model: AppSettings) -> bool:
    dow = start_at.isoweekday()
    t = start_at.time()
    for w in cfg_model.availability:
        if dow not in w.daysOfWeek:
            continue
        sh, sm = map(int, w.startTime.split(":"))
        eh, em = map(int, w.endTime.split(":"))
        start_t = dtime(sh, sm)
        end_t = dtime(eh, em)
        if start_t <= t <= end_t:
            return True
    return False


# ----------------------
# Settings endpoints
# ----------------------


@app.get("/settings", response_model=AppSettings)
def get_app_settings():
    with db_session() as db:
        cfg_model = load_app_settings(db)
        apply_settings_to_runtime(cfg_model)
        return cfg_model


@app.put("/settings", response_model=AppSettings)
def update_app_settings(payload: AppSettings):
    with db_session() as db:
        rec = db.get(Setting, "global")
        if rec:
            rec.value = payload.dict()
        else:
            rec = Setting(key="global", value=payload.dict())
            db.add(rec)
        db.flush()
        apply_settings_to_runtime(payload)
        return payload


# ----------------------
# Cart
# ----------------------


@app.post("/cart", response_model=CreateCartResponse)
def create_cart(body: CreateCartRequest):
    if not body.items:
        raise HTTPException(400, detail="Cart must have at least one item")

    with db_session() as db:
        # validate products
        product_ids = [i.productId for i in body.items]
        products = {
            p.id: p for p in db.execute(select(Product).where(Product.id.in_(product_ids))).scalars()
        }
        if len(products) != len(set(product_ids)):
            raise HTTPException(400, detail="Unknown productId in items")

        cart = Cart()
        db.add(cart)
        db.flush()

        for item in body.items:
            if item.qty <= 0:
                continue
            ci = CartItem(
                cart_id=cart.id,
                product_id=item.productId,
                qty=item.qty,
            )
            db.add(ci)

        db.flush()
        return CreateCartResponse(cartId=cart.id)


# ----------------------
# Slot listing
# ----------------------


@app.get("/delivery/slots", response_model=SlotsResponse)
def get_slots(
    cartId: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    fromISO: str | None = Query(None),
    toISO: str | None = Query(None),
):
    with db_session() as db:
        cart = db.get(Cart, cartId)
        if not cart:
            raise HTTPException(404, detail="Cart not found")

        cfg_model = load_app_settings(db)
        apply_settings_to_runtime(cfg_model)

        now = datetime.now(timezone.utc)
        start_time = parse_iso_z(fromISO) if fromISO else now
        end_time = parse_iso_z(toISO) if toISO else now + timedelta(days=7)

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

        # Filter by availability windows
        slots = [s for s in slots if slot_allowed(s.start_at, cfg_model)]

        out: List[SlotOut] = []

        for s in sorted(slots, key=lambda x: x.start_at):
            # neighbor time window around slot
            win_start = s.start_at - timedelta(minutes=settings.T0_MIN)
            win_end = s.end_at + timedelta(minutes=settings.T0_MIN)

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
                n
                for n in neigh
                if haversine_m(lat, lon, n.lat, n.lon) <= settings.RADIUS_M
            ]

            score = score_slot(lat, lon, s, neighbors)
            disc_pct = discount_from_score(score)
            final_fee, discount_cents, base_fee = clamp_fee(
                cfg_model.baseDeliveryFeeCents, disc_pct
            )
            requires_solo = solo_minimum_required(score, len(neighbors))

            if disc_pct >= settings.MAX_DISCOUNT * 0.7:
                label = "Best deal"
            elif disc_pct >= settings.MAX_DISCOUNT * 0.3:
                label = "Good deal"
            else:
                label = "Standard"

            out.append(
                SlotOut(
                    slotId=s.id,
                    startAt=s.start_at.replace(tzinfo=timezone.utc),
                    endAt=s.end_at.replace(tzinfo=timezone.utc),
                    baseDeliveryFeeCents=base_fee,
                    discountPct=round(disc_pct, 4),
                    discountCents=discount_cents,
                    finalDeliveryFeeCents=final_fee,
                    label=label,
                    capacity=SlotCapacity(
                        total=s.capacity_total, used=s.capacity_used
                    ),
                    requiresSoloMinUnits=requires_solo,
                    soloMinUnits=cfg_model.minSoloUnits,
                )
            )

        return SlotsResponse(
            computedAt=now,
            params=params_snapshot(),
            slots=out,
        )


# ----------------------
# Checkout / Quote
# ----------------------


@app.post("/checkout/quote", response_model=QuoteOut)
def checkout_quote(payload: QuoteIn):
    with db_session() as db:
        cart = db.get(Cart, payload.cartId)
        slot = db.get(DeliverySlot, payload.slotId)
        if not (cart and slot):
            raise HTTPException(404, detail="cart/slot not found")

        cfg_model = load_app_settings(db)
        apply_settings_to_runtime(cfg_model)

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
            n
            for n in neigh
            if haversine_m(payload.lat, payload.lon, n.lat, n.lon)
            <= settings.RADIUS_M
        ]

        score = score_slot(payload.lat, payload.lon, slot, neighbors)
        disc_pct = discount_from_score(score)
        final_fee, discount_cents, base_fee = clamp_fee(
            cfg_model.baseDeliveryFeeCents, disc_pct
        )

        # enforce solo-minimum if applicable
        if solo_minimum_required(score, len(neighbors)):
            units = cart_units_total_by_id(db, cart.id)
            if units < cfg_model.minSoloUnits:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "SOLO_MIN_UNITS_REQUIRED",
                        "message": f"This time has no nearby deliveries. Add at least {cfg_model.minSoloUnits} items or choose a discounted time.",
                        "soloMinUnits": cfg_model.minSoloUnits,
                    },
                )

        subtotal = calc_cart_subtotal_cents_by_id(db, cart.id)
        total = subtotal + final_fee

        q = Quote(
            cart_id=cart.id,
            slot_id=slot.id,
            subtotal_cents=subtotal,
            delivery_fee_cents=final_fee,
            discount_cents=discount_cents,
            total_cents=total,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=15),
            lat=payload.lat,
            lon=payload.lon,
        )
        db.add(q)
        db.flush()

        return QuoteOut(
            quoteId=q.id,
            lockedUntil=q.locked_until,
            amounts=QuoteAmounts(
                subtotalCents=subtotal,
                deliveryFeeCents=final_fee,
                discountCents=discount_cents,
                totalCents=total,
            ),
        )


# ----------------------
# Payments (stub)
# ----------------------


@app.post("/payments/create", response_model=PaymentCreateOut)
def create_payment_intent(body: PaymentCreateIn):
    # Stub implementation
    return PaymentCreateOut(
        paymentIntentId=f"pi_{body.quoteId}",
        status="requires_confirmation",
    )

@app.post("/webhooks/payment")
def payment_webhook(body: WebhookPaymentIn):
    if body.event != "payment_succeeded":
        return {"status": "ignored"}

    with db_session() as db:
        q = db.get(Quote, body.quoteId)
        if not q:
            raise HTTPException(404, detail="Quote not found")

        slot = db.get(DeliverySlot, q.slot_id)
        if not slot:
            raise HTTPException(404, detail="Slot not found for quote")

        # Either find an existing order for this cart+slot, or create a new one
        order = (
            db.execute(
                select(Order).where(
                    Order.cart_id == q.cart_id,
                    Order.slot_id == q.slot_id,
                )
            )
            .scalars()
            .first()
        )

        if not order:
            order = Order(
                # id will be generated by default = gen_id("or")
                user_id=None,  # or set a real user id if you have it
                cart_id=q.cart_id,
                slot_id=q.slot_id,
                subtotal_cents=q.subtotal_cents,
                delivery_fee_cents=q.delivery_fee_cents,
                discount_cents=q.discount_cents,
                total_cents=q.total_cents,
                status="confirmed",
                lat=q.lat,
                lon=q.lon,
            )
            db.add(order)
            db.flush()  # ensure order.id is available for FK

        # Now create the scheduled stop, linked to the *order* id
        stop = ScheduledStop(
            order_id=order.id,
            lat=q.lat,
            lon=q.lon,
            scheduled_at=slot.start_at,
        )
        db.add(stop)

        # bump slot used capacity
        slot.capacity_used = min(
            slot.capacity_total,
            (slot.capacity_used or 0) + 1,
        )

    return {"status": "ok"}


# ----------------------
# Dev endpoints
# ----------------------


@app.post("/dev/clear-db")
def dev_clear_db(full: bool = False):
    """
    Development helper: clear runtime data.

    - Always clears: scheduled_stops, quotes, orders, cart_items, carts.
    - Never clears: products.
    - If full=True: also resets delivery slot capacity_used to 0
      (but keeps the slots themselves).
    """
    with db_session() as db:
        # Delete in foreign-key-safe order
        db.query(ScheduledStop).delete()  # FK -> orders.id
        db.query(Quote).delete()          # FK -> carts.id, delivery_slots.id
        db.query(Order).delete()          # FK -> carts.id
        db.query(CartItem).delete()       # FK -> carts.id
        db.query(Cart).delete()

        if full:
            # Do NOT delete products (per requirement).
            # Just reset slot utilization so scoring starts fresh.
            db.query(DeliverySlot).update({DeliverySlot.capacity_used: 0})

        return {"status": "ok"}



@app.get("/dev/debug-neighbors")
def debug_neighbors(
    slotId: str,
    lat: float,
    lon: float,
):
    with db_session() as db:
        slot = db.get(DeliverySlot, slotId)
        if not slot:
            raise HTTPException(404, detail="slot not found")

        cfg_model = load_app_settings(db)
        apply_settings_to_runtime(cfg_model)

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
            n
            for n in neigh
            if haversine_m(lat, lon, n.lat, n.lon) <= settings.RADIUS_M
        ]

        score = score_slot(lat, lon, slot, neighbors)
        disc_pct = discount_from_score(score)
        final_fee, discount_cents, base_fee = clamp_fee(
            cfg_model.baseDeliveryFeeCents, disc_pct
        )

        return {
            "slotId": slotId,
            "neighborsCount": len(neighbors),
            "score": score,
            "discountPct": disc_pct,
            "finalFeeCents": final_fee,
            "discountCents": discount_cents,
            "baseFeeCents": base_fee,
            "deliveryType": getattr(settings, "DELIVERY_TYPE", "motorcycle"),
        }


# ----------------------
# Routing API (OSRM)
# ----------------------


class RoutingError(Exception):
    pass


async def call_osrm_route(profile: str, from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> tuple[float, float]:
    base = settings.ROUTING_BASE_URL.rstrip("/")
    url = (
        f"{base}/route/v1/{profile}/"
        f"{from_lon},{from_lat};{to_lon},{to_lat}"
        "?overview=false&alternatives=false&steps=false"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        raise RoutingError(f"OSRM error: HTTP {r.status_code} - {r.text}")
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM error: {data.get('message', 'no routes')}")
    route = data["routes"][0]
    return float(route["distance"]), float(route["duration"])


@app.get("/routing/estimate", response_model=RoutingEstimateResponse)
async def routing_estimate(
    fromLat: float = Query(...),
    fromLon: float = Query(...),
    toLat: float = Query(...),
    toLon: float = Query(...),
):
    """
    OSRM-based distance + duration for car/motorcycle/bicycle.
    Motorcycle currently approximated from car.
    """
    # car
    dist_car, dur_car = await call_osrm_route(
        "driving", fromLat, fromLon, toLat, toLon
    )

    # bike
    try:
        dist_bike, dur_bike = await call_osrm_route(
            "cycling", fromLat, fromLon, toLat, toLon
        )
    except RoutingError:
        dist_bike, dur_bike = dist_car, dur_car * 2.5

    # motorcycle as faster car
    dist_moto, dur_moto = dist_car, dur_car * 0.8

    return RoutingEstimateResponse(
        fromLat=fromLat,
        fromLon=fromLon,
        toLat=toLat,
        toLon=toLon,
        distanceMeters=dist_car,
        durationsSeconds=TravelDurations(
            car=dur_car,
            motorcycle=dur_moto,
            bicycle=dur_bike,
        ),
        provider="osrm",
    )
