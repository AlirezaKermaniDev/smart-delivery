from __future__ import annotations

import math
from datetime import datetime
from typing import Iterable

from .config import settings


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine distance in meters.
    """
    R = 6371000.0
    from math import radians, sin, cos, atan2

    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)

    a = sin(dphi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2.0) ** 2
    c = 2 * atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _decay_params_for_mode() -> tuple[float, float]:
    """
    Choose effective distance/time decay based on delivery type.

    - car: more tolerant to distance
    - motorcycle: baseline
    - bicycle: more sensitive to distance and time
    """
    base_d0 = 800.0  # meters
    base_t0 = settings.T0_MIN
    mode = getattr(settings, "DELIVERY_TYPE", "motorcycle")

    if mode == "car":
        d0 = base_d0 * 1.4
        t0 = base_t0 * 1.0
    elif mode == "bicycle":
        d0 = base_d0 * 0.7
        t0 = base_t0 * 0.8
    else:  # motorcycle (default)
        d0 = base_d0
        t0 = base_t0
    return d0, t0


def score_slot(
    user_lat: float,
    user_lon: float,
    slot,
    neighbors: Iterable,
) -> float:
    """
    Score how batchable this slot is for a given user + set of neighbors.
    neighbors: iterable of ScheduledStop-like objects with .lat, .lon, .scheduled_at
    """
    d0, t0 = _decay_params_for_mode()
    score = 0.0
    for n in neighbors:
        dist = haversine_m(user_lat, user_lon, n.lat, n.lon)
        dt_min = abs((slot.start_at - n.scheduled_at).total_seconds()) / 60.0
        score += math.exp(-dist / d0) * math.exp(-dt_min / t0)
    return score


def discount_from_score(score: float) -> float:
    """
    Convert dimensionless score → discount fraction [0, max_discount].
    """
    if score <= 0:
        return 0.0
    max_d = settings.MAX_DISCOUNT
    k = settings.K
    return max_d * (1 - math.exp(-k * score))


def clamp_fee(base_fee_cents: int, discount_pct: float) -> tuple[int, int, int]:
    """
    Apply discount and clamp to min delivery fee.
    Returns: final_fee_cents, discount_cents, base_fee_cents
    """
    base_fee = base_fee_cents
    raw_discount = int(round(base_fee * discount_pct))
    discounted = base_fee - raw_discount
    final_fee = max(discounted, settings.MIN_DELIVERY_FEE_CENTS)
    applied_discount = base_fee - final_fee
    return final_fee, applied_discount, base_fee


def solo_minimum_required(score: float, neighbor_count: int) -> bool:
    """
    Decide whether the 'solo minimum units' rule should apply for this slot.
    """
    if neighbor_count == 0:
        return True
    if score < settings.S_MIN:
        return True
    return False
