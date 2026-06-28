from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "sqlite:///./restaurante.db"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    alegra_email: Optional[str] = None
    alegra_token: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
