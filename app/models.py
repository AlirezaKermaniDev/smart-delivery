from datetime import datetime, timedelta
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy import JSON
from .util import gen_id 
class Base(DeclarativeBase): pass


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)  # stores a JSON blob

class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    price_cents: Mapped[int] = mapped_column(Integer)
    unit_factor: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class DeliverySlot(Base):
    __tablename__ = "delivery_slots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    region_id: Mapped[str] = mapped_column(String, default="default")
    capacity_total: Mapped[int] = mapped_column(Integer, default=12)
    capacity_used: Mapped[int] = mapped_column(Integer, default=0)

class Cart(Base):
    __tablename__ = "carts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("c"))
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")

class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[int] = mapped_column(Integer)
    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[str] = mapped_column(String, primary_key=True,default=lambda: gen_id("q"))
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"))
    slot_id: Mapped[str] = mapped_column(ForeignKey("delivery_slots.id"))
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    delivery_fee_cents: Mapped[int] = mapped_column(Integer)
    discount_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    locked_until: Mapped[datetime] = mapped_column(DateTime)
    # NEW
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: gen_id("or"))
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"))
    slot_id: Mapped[str] = mapped_column(ForeignKey("delivery_slots.id"))
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    delivery_fee_cents: Mapped[int] = mapped_column(Integer)
    discount_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="confirmed")
    # NEW (optional but recommended)
    lat: Mapped[float] = mapped_column(Float, default=0.0)
    lon: Mapped[float] = mapped_column(Float, default=0.0)

class ScheduledStop(Base):
    __tablename__ = "scheduled_stops"
    id: Mapped[str] = mapped_column(String, primary_key=True,default=lambda: gen_id("st"))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="scheduled")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
