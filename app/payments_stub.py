from .storage import gen_id, QUOTES, ORDERS, SLOTS
from .models import Order

def create_payment_intent(quote_id: str) -> str:
    # Return a fake client secret
    return f"pi_secret_{quote_id}"

def finalize_quote(quote_id: str):
    q = QUOTES.get(quote_id)
    if not q:
        return
    # create Order and commit capacity
    SLOTS[q.slot_id].capacity_used += 1
    ORDERS[q.id] = Order(
        id=gen_id("ord"),
        user_id=None,
        cart_id=q.cart_id,
        location_id=q.location_id,
        slot_id=q.slot_id,
        subtotal_cents=q.subtotal_cents,
        delivery_fee_cents=q.delivery_fee_cents,
        discount_cents=q.discount_cents,
        total_cents=q.total_cents,
        status="confirmed",
    )
