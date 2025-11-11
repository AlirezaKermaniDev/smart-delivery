import math
from datetime import datetime
from typing import List, Dict, Any
from .config import settings
from .models import ScheduledStop, DeliverySlot

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    import math as m
    phi1, phi2 = m.radians(lat1), m.radians(lat2)
    dphi = m.radians(lat2 - lat1)
    dl = m.radians(lon2 - lon1)
    a = m.sin(dphi/2)**2 + m.cos(phi1) * m.cos(phi2) * m.sin(dl/2)**2
    return 2 * R * m.asin(m.sqrt(a))

def score_slot(user_lat: float, user_lon: float, slot: DeliverySlot, neighbors: List[ScheduledStop]) -> float:
    mid = slot.start_at + (slot.end_at - slot.start_at)/2
    score = 0.0
    for n in neighbors:
        dist = haversine_m(user_lat, user_lon, n.lat, n.lon)
        dt_min = abs((mid - n.scheduled_at).total_seconds()) / 60.0
        score += n.weight * math.exp(-dist / settings.D0_M) * math.exp(-dt_min / settings.T0_MIN)
    if slot.capacity_used >= slot.capacity_total:
        return 0.0
    util = slot.capacity_used / max(1, slot.capacity_total)
    if util >= settings.NEAR_FULL_THRESHOLD:
        score *= settings.CAPACITY_HALF_MULTIPLIER
    return score

def discount_from_score(score: float) -> float:
    return settings.MAX_DISCOUNT * (1 - math.exp(-settings.K * score))

def label_for_discount(p: float) -> str:
    if p >= 0.15: return "Best deal"
    if p >= 0.08: return "Good deal"
    return "Standard"

def clamp_fee(base_fee_cents: int, discount_pct: float) -> tuple[int, int, int]:
    """
    Returns (final_fee_cents, discount_cents, base_fee_cents).
    Applies discount but never goes below MIN_DELIVERY_FEE_CENTS.
    """
    # guard against negative or >100% discounts
    discount_pct = max(0.0, min(1.0, discount_pct))

    discounted = int(round(base_fee_cents * (1 - discount_pct)))
    final_fee = max(discounted, settings.MIN_DELIVERY_FEE_CENTS)
    discount_cents = max(0, base_fee_cents - final_fee)
    return final_fee, discount_cents, base_fee_cents


def solo_minimum_required(score: float, neighbor_count: int) -> bool:
    return neighbor_count == 0 or score < settings.S_MIN

def params_snapshot() -> Dict[str, Any]:
    return dict(
        radiusM=settings.RADIUS_M,
        t0Min=settings.T0_MIN,
        d0M=settings.D0_M,
        maxDiscount=settings.MAX_DISCOUNT,
        k=settings.K,
        sMin=settings.S_MIN,
        minSoloUnits=settings.MIN_SOLO_UNITS
    )
