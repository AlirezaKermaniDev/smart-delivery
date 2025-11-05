import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from .models import (Product, DeliverySlot, Cart, CartItem, Location,
                     Order, Quote, ScheduledStop)

# In-memory stores (swap for DB later)
PRODUCTS: Dict[str, Product] = {}
CARTS: Dict[str, Cart] = {}
LOCATIONS: Dict[str, Location] = {}
SLOTS: Dict[str, DeliverySlot] = {}
QUOTES: Dict[str, Quote] = {}
ORDERS: Dict[str, Order] = {}
STOPS: Dict[str, ScheduledStop] = {}

def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def upsert_cart(items: List[Tuple[str, int]], user_id=None) -> Cart:
    # Create new cart every time for demo
    cart_id = gen_id("c")
    cart = Cart(id=cart_id, user_id=user_id, items=[CartItem(product_id=i, qty=q) for i, q in items])
    CARTS[cart_id] = cart
    return cart

def calc_cart_subtotal_cents(cart: Cart) -> int:
    total = 0
    for it in cart.items:
        p = PRODUCTS.get(it.product_id)
        if not p or not p.active:
            continue
        total += p.price_cents * it.qty
    return total

def cart_units_total(cart: Cart) -> int:
    total = 0
    for it in cart.items:
        p = PRODUCTS.get(it.product_id)
        if not p or not p.active:
            continue
        total += p.unit_factor * it.qty
    return total

def ensure_products():
    if PRODUCTS:
        return
    PRODUCTS["p_1"] = Product(id="p_1", name="Classic Cookie", price_cents=300, unit_factor=1)
    PRODUCTS["p_2"] = Product(id="p_2", name="Double Choc", price_cents=350, unit_factor=1)
    PRODUCTS["p_3"] = Product(id="p_3", name="Party Box (6)", price_cents=1600, unit_factor=6)

def ensure_slots(horizon_days=7, slot_minutes=30, start_hour=10, end_hour=20):
    if SLOTS:
        return
    from datetime import datetime, timedelta
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    for d in range(horizon_days):
        day = now + timedelta(days=d)
        for h in range(start_hour, end_hour):
            for m in (0, 30):
                start_at = day.replace(hour=h, minute=m)
                end_at = start_at + timedelta(minutes=slot_minutes)
                sid = gen_id("sl")
                SLOTS[sid] = DeliverySlot(id=sid, start_at=start_at, end_at=end_at,
                                          capacity_total=12, capacity_used=0)

def add_location(address: str, lat: float, lon: float) -> Location:
    loc = Location(id=gen_id("loc"), address=address, lat=lat, lon=lon)
    LOCATIONS[loc.id] = loc
    return loc
