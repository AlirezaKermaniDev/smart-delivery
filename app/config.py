# OLD:
# from pydantic import BaseSettings
# NEW:
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    D0_M: float = 800.0
    T0_MIN: float = 30.0
    RADIUS_M: float = 3000.0
    K: float = 1.0
    MAX_DISCOUNT: float = 0.20
    S_MIN: float = 0.05
    MIN_SOLO_UNITS: int = 6
    NEAR_FULL_THRESHOLD: float = 0.8
    CAPACITY_HALF_MULTIPLIER: float = 0.5

    BASE_DELIVERY_FEE_CENTS: int = 450
    MIN_DELIVERY_FEE_CENTS: int = 300

    SLOT_MINUTES: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
