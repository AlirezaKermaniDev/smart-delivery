from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class CartItemIn(BaseModel):
    productId: str
    qty: int

class CartCreateIn(BaseModel):
    items: List[CartItemIn]

class CartSummaryOut(BaseModel):
    cartId: str
    subtotalCents: int
    items: List[CartItemIn]

class LocationResolveIn(BaseModel):
    address: str

class LocationOut(BaseModel):
    locationId: str
    lat: float
    lon: float
    addressText: str

class SlotOut(BaseModel):
    slotId: str
    startAt: datetime
    endAt: datetime
    baseDeliveryFeeCents: int
    discountPct: float
    discountCents: int
    finalDeliveryFeeCents: int
    label: str
    capacity: dict
    requiresSoloMinUnits: bool
    soloMinUnits: int

class SlotsResponse(BaseModel):
    computedAt: datetime
    params: dict
    slots: List[SlotOut]

class QuoteIn(BaseModel):
    cartId: str
    slotId: str
    locationId: str

class QuoteOut(BaseModel):
    quoteId: str
    lockedUntil: datetime
    amounts: dict

class PaymentCreateIn(BaseModel):
    quoteId: str

class PaymentCreateOut(BaseModel):
    clientSecret: str
    paymentProvider: str = "stub-pay"

class WebhookIn(BaseModel):
    event: str
    quoteId: str
    intentId: Optional[str] = None

class MockDataIn(BaseModel):
    centerLat: float
    centerLon: float
    days: int = 1
    density: str = "medium"  # low/medium/high

class SlotsQuery(BaseModel):
    cartId: str
    lat: float
    lon: float
    fromISO: Optional[str] = None
    toISO: Optional[str] = None
