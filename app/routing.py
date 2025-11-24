import httpx
from typing import Literal
from .config import settings

OSRM_PROFILE = Literal["driving", "cycling", "walking"]


class RoutingError(Exception):
    pass


async def call_osrm_route(
    profile: OSRM_PROFILE,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> tuple[float, float]:
    """
    Call OSRM /route API and return (distance_meters, duration_seconds)
    for the given profile.
    """
    base = settings.ROUTING_BASE_URL.rstrip("/")
    # OSRM expects lon,lat order
    url = (
        f"{base}/route/v1/{profile}/"
        f"{from_lon},{from_lat};{to_lon},{to_lat}"
        "?overview=false&alternatives=false&steps=false"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        raise RoutingError(f"OSRM error: HTTP {r.status_code} - {r.text}")

    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM error: {data.get('message', 'no routes')}")

    route = data["routes"][0]
    distance_m = float(route["distance"])   # meters
    duration_s = float(route["duration"])   # seconds
    return distance_m, duration_s


async def get_travel_estimates(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> dict:
    """
    Returns a dict with distance and durations for car/motorcycle/bicycle.
    """
    # car: driving profile
    dist_car, dur_car = await call_osrm_route(
        "driving", from_lat, from_lon, to_lat, to_lon
    )

    # try real cycling, otherwise approximate
    try:
        dist_bike, dur_bike = await call_osrm_route(
            "cycling", from_lat, from_lon, to_lat, to_lon
        )
    except RoutingError:
        dist_bike, dur_bike = dist_car, dur_car * 2.5  # slower than car

    # motorcycle as “faster car”
    dist_motorcycle = dist_car
    dur_motorcycle = dur_car * 0.8

    return {
        "distanceMeters": dist_car,
        "durationsSeconds": {
            "car": dur_car,
            "motorcycle": dur_motorcycle,
            "bicycle": dur_bike,
        },
        "provider": "osrm",
    }