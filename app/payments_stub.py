# app/payments_stub.py
from sqlalchemy import select
from .db import db_session
from .models import Quote, Order, DeliverySlot, ScheduledStop
from .util import gen_id

def create_payment_intent(quote_id: str) -> str:
    return f"pi_secret_{quote_id}"

def finalize_quote(quote_id: str):
    with db_session() as db:
        q = db.get(Quote, quote_id)
        if not q:
            return
        slot = db.get(DeliverySlot, q.slot_id)
        if slot:
            slot.capacity_used += 1

        # create the order (keeping coords for traceability)
        ord_id = gen_id("ord")
        db.add(Order(
            id=ord_id,
            user_id=None,
            cart_id=q.cart_id,
            slot_id=q.slot_id,
            subtotal_cents=q.subtotal_cents,
            delivery_fee_cents=q.delivery_fee_cents,
            discount_cents=q.discount_cents,
            total_cents=q.total_cents,
            status="confirmed",
            lat=q.lat,   # <-- ensure Quote has lat/lon columns
            lon=q.lon,
        ))

        # create the neighbor stop for batching
        db.add(ScheduledStop(
            id=gen_id("st"),
            order_id=ord_id,
            lat=q.lat,
            lon=q.lon,
            scheduled_at=slot.start_at,  # within the slot window
            status="scheduled",
            weight=1.0,
        ))
