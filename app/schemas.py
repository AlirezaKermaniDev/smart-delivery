from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Literal

from pydantic import BaseModel, Field


# ----------------------
# Core cart / slot / quote
# ----------------------


class CartItemIn(BaseModel):
    productId: str
    qty: int = Field(..., ge=1)


class CreateCartRequest(BaseModel):
    items: List[CartItemIn]


class CreateCartResponse(BaseModel):
    cartId: str


class SlotCapacity(BaseModel):
    total: int
    used: int


class SlotOut(BaseModel):
    slotId: str
    startAt: datetime
    endAt: datetime
    baseDeliveryFeeCents: int
    discountPct: float
    discountCents: int
    finalDeliveryFeeCents: int
    label: str
    capacity: SlotCapacity
    requiresSoloMinUnits: bool
    soloMinUnits: int


class SlotsResponse(BaseModel):
    computedAt: datetime
    params: Dict[str, float | int | str]
    slots: List[SlotOut]


class QuoteIn(BaseModel):
    cartId: str
    slotId: str
    lat: float
    lon: float


class QuoteAmounts(BaseModel):
    subtotalCents: int
    deliveryFeeCents: int
    discountCents: int
    totalCents: int


class QuoteOut(BaseModel):
    quoteId: str
    lockedUntil: datetime
    amounts: QuoteAmounts


class PaymentCreateIn(BaseModel):
    quoteId: str


class PaymentCreateOut(BaseModel):
    paymentIntentId: str
    status: str


class WebhookPaymentIn(BaseModel):
    event: str
    quoteId: str


# ----------------------
# Settings & availability
# ----------------------


class AvailabilityWindow(BaseModel):
    daysOfWeek: List[int] = Field(
        ..., description="ISO weekdays, 1=Mon..7=Sun"
    )
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
    deliveryType: Literal["car", "motorcycle", "bicycle"] = "motorcycle"


# ----------------------
# Routing
# ----------------------


class TravelDurations(BaseModel):
    car: float
    motorcycle: float
    bicycle: float


class RoutingEstimateResponse(BaseModel):
    fromLat: float
    fromLon: float
    toLat: float
    toLon: float
    distanceMeters: float
    durationsSeconds: TravelDurations
    provider: str
