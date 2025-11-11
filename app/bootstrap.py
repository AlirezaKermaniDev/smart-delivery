from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .db import engine, db_session
from .models import Base, Product, DeliverySlot
from .config import settings
from .util import gen_id

def create_schema():
    Base.metadata.create_all(bind=engine)

def seed_products():
    with db_session() as db:
        if db.scalar(select(Product).limit(1)) is None:
            db.add_all([
                Product(id="p_1", name="Classic Cookie", price_cents=300, unit_factor=1),
                Product(id="p_2", name="Double Choc",   price_cents=350, unit_factor=1),
                Product(id="p_3", name="Party Box (6)", price_cents=1600, unit_factor=6),
            ])

def seed_slots():
    with db_session() as db:
        has_any = db.execute(select(DeliverySlot).limit(1)).first()
        if has_any: return
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for d in range(settings.HORIZON_DAYS):
            day = now + timedelta(days=d)
            for h in range(settings.SERVICE_START_HOUR, settings.SERVICE_END_HOUR):
                for m in (0,30):
                    start_at = day.replace(hour=h, minute=m)
                    end_at = start_at + timedelta(minutes=settings.SLOT_MINUTES)
                    db.add(DeliverySlot(
                        id=gen_id("sl"),
                        start_at=start_at, end_at=end_at,
                        capacity_total=12, capacity_used=0
                    ))

def bootstrap():
    create_schema()
    seed_products()
    seed_slots()
