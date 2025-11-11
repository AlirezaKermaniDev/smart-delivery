from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Scoring / discount params
    D0_M: float = 800.0
    T0_MIN: float = 30.0
    RADIUS_M: float = 3000.0
    K: float = 1.0
    MAX_DISCOUNT: float = 0.20
    S_MIN: float = 0.05
    MIN_SOLO_UNITS: int = 6
    NEAR_FULL_THRESHOLD: float = 0.8
    CAPACITY_HALF_MULTIPLIER: float = 0.5

    # Pricing
    BASE_DELIVERY_FEE_CENTS: int = 450
    MIN_DELIVERY_FEE_CENTS: int = 300

    # Slots
    SLOT_MINUTES: int = 30
    SERVICE_START_HOUR: int = 10
    SERVICE_END_HOUR: int = 20
    HORIZON_DAYS: int = 7

    # Database
    DATABASE_URL: str = "postgresql://smart:smart@db:5432/smart"  # docker-compose default

    class Config:
        env_file = ".env"

settings = Settings()
