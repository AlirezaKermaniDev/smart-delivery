from datetime import datetime, timedelta, time as dtime

from .db import engine, db_session          # engine + session from db.py
from .models import Base, Product, DeliverySlot, Setting  # Base from models
from .config import settings as cfg


def create_schema():
    Base.metadata.create_all(bind=engine)


def seed_products():
    with db_session() as db:
        count = db.query(Product).count()
        if count > 0:
            return

        products = [
            Product(
                id="p_1",
                name="Classic Cookie",
                price_cents=300,
                unit_factor=1,
            ),
            Product(
                id="p_2",
                name="Double Choc",
                price_cents=350,
                unit_factor=1,
            ),
            Product(
                id="p_3",
                name="Party Box (6)",
                price_cents=1600,
                unit_factor=6,
            ),
        ]
        db.add_all(products)


def seed_slots():
    """
    Very simple seeding of delivery slots for the next 3 days.
    Actual business availability is enforced by settings.availability.
    """
    with db_session() as db:
        count = db.query(DeliverySlot).count()
        if count > 0:
            return

        now = datetime.utcnow()
        days = 3
        for i in range(days):
            day = now.date() + timedelta(days=i)
            # create slots every hour from 12–20 as an example
            for hour in range(12, 20):
                start = datetime.combine(day, dtime(hour, 0))
                end = start + timedelta(minutes=60)
                slot = DeliverySlot(
                    id=f"sl_{day.strftime('%Y%m%d')}_{hour}",
                    start_at=start,
                    end_at=end,
                    capacity_total=10,
                    capacity_used=0,
                )
                db.add(slot)


def seed_settings():
    """
    Seed a single global settings row if not present.
    """
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
