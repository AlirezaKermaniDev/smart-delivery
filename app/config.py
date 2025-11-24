from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core DB
    DATABASE_URL: str = "postgresql://smart:smart@db:5432/smart"

    # Scoring / discounts
    BASE_DELIVERY_FEE_CENTS: int = 450
    MIN_DELIVERY_FEE_CENTS: int = 350
    MAX_DISCOUNT: float = 0.20
    K: float = 1.0  # curve parameter
    RADIUS_M: int = 3000
    T0_MIN: int = 30
    MIN_SOLO_UNITS: int = 6
    S_MIN: float = 0.05  # minimum score to be considered batchable

    # Delivery mode used by scoring (affects decay)
    # Allowed: "car", "motorcycle", "bicycle"
    DELIVERY_TYPE: str = "motorcycle"

    # Routing
    ROUTING_BASE_URL: str = "https://router.project-osrm.org"

    # Optional: used for CORS / frontend
    APP_DOMAIN: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
