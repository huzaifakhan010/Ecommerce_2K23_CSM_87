"""Runtime configuration, read from environment variables (a .env file is supported)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # does not override variables that are already set


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    jwt_algorithm: str
    access_token_minutes: int
    bcrypt_rounds: int


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://printstudio:printstudio@localhost:5432/printstudio",
        ),
        jwt_secret=os.getenv("JWT_SECRET", ""),
        jwt_algorithm="HS256",
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "60")),
        bcrypt_rounds=int(os.getenv("BCRYPT_ROUNDS", "12")),
    )
