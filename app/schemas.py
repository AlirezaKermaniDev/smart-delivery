from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from typing import List
from pydantic import BaseModel, Field

class CartItemIn(BaseModel):
    productId: str
    qty: int

class CartCreateIn(BaseModel):
    items: List[CartItemIn]

class CartSummaryOut(BaseModel):
    cartId: str
    subtotalCents: int
    items: List[CartItemIn]

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
    lat: float
    lon: float

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
    
class AvailabilityWindow(BaseModel):
    daysOfWeek: List[int] = Field(
        ..., description="List of ISO weekdays (1=Mon ... 7=Sun)"
    )
    # HH:MM 24h strings – easier to store in JSON
    startTime: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    endTime: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class AppSettings(BaseModel):
    baseDeliveryFeeCents: int
    minDeliveryFeeCents: int
    maxDiscount: float
    k: float
    radiusM: int
    t0Min: int
    minSoloUnits: int
    availability: List[AvailabilityWindow]
