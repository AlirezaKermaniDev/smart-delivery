from datetime import datetime, timedelta, time as dtime

from .db import engine, db_session
from .models import Base, Product, DeliverySlot, Setting
from .config import settings as cfg


def create_schema():
    Base.metadata.create_all(bind=engine)


def seed_products():
    with db_session() as db:
        count = db.query(Product).count()
        if count > 0:
            return

        products = [
            Product(id="p_1", name="Classic Cookie", price_cents=300, unit_factor=1),
            Product(id="p_2", name="Double Choc", price_cents=350, unit_factor=1),
            Product(id="p_3", name="Party Box (6)", price_cents=1600, unit_factor=6),
        ]
        db.add_all(products)


def seed_slots():
    """
    Ensure we always have delivery slots for the next N days.
    """
    days_ahead = 3

    with db_session() as db:
        today = datetime.utcnow().date()

        for i in range(days_ahead):
            day = today + timedelta(days=i)
            for hour in range(12, 20):  # 12:00–20:00
                slot_id = f"sl_{day.strftime('%Y%m%d')}_{hour}"
                existing = db.get(DeliverySlot, slot_id)
                if existing:
                    continue

                start = datetime.combine(day, dtime(hour, 0))
                end = start + timedelta(hours=1)

                slot = DeliverySlot(
                    id=slot_id,
                    start_at=start,
                    end_at=end,
                    capacity_total=10,
                    capacity_used=0,
                )
                db.add(slot)


def seed_settings():
    with db_session() as db:
        existing = db.get(Setting, "global")
        if existing:
            return

        default = {
            "baseDeliveryFeeCents": cfg.BASE_DELIVERY_FEE_CENTS,
            "minDeliveryFeeCents": cfg.MIN_DELIVERY_FEE_CENTS,
            "maxDiscount": cfg.MAX_DISCOUNT,
            "k": cfg.K,
            "radiusM": cfg.RADIUS_M,
            "t0Min": cfg.T0_MIN,
            "minSoloUnits": cfg.MIN_SOLO_UNITS,
            "availability": [
                {
                    "daysOfWeek": [1, 2, 3, 4, 5],  # Mon–Fri
                    "startTime": "13:00",
                    "endTime": "17:00",
                }
            ],
            "deliveryType": "motorcycle",
        }
        s = Setting(key="global", value=default)
        db.add(s)


def bootstrap():
    create_schema()
    seed_products()
    seed_slots()
    seed_settings()
