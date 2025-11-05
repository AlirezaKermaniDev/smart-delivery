from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass
class Product:
    id: str
    name: str
    price_cents: int
    unit_factor: int = 1
    active: bool = True

@dataclass
class DeliverySlot:
    id: str
    start_at: datetime
    end_at: datetime
    region_id: str = "default"
    capacity_total: int = 10
    capacity_used: int = 0

@dataclass
class Location:
    id: str
    lat: float
    lon: float
    address: str

@dataclass
class CartItem:
    product_id: str
    qty: int

@dataclass
class Cart:
    id: str
    user_id: Optional[str]
    items: List[CartItem] = field(default_factory=list)

@dataclass
class Quote:
    id: str
    cart_id: str
    slot_id: str
    location_id: str
    subtotal_cents: int
    delivery_fee_cents: int
    discount_cents: int
    total_cents: int
    locked_until: datetime

@dataclass
class Order:
    id: str
    user_id: Optional[str]
    cart_id: str
    location_id: str
    slot_id: str
    subtotal_cents: int
    delivery_fee_cents: int
    discount_cents: int
    total_cents: int
    status: str = "confirmed"

@dataclass
class ScheduledStop:
    id: str
    order_id: Optional[str]
    lat: float
    lon: float
    scheduled_at: datetime
    status: str = "scheduled"
    weight: float = 1.0  # batching weight (not physical)
