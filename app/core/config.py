from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_name: str = "ATS Recruitment Platform"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str  # postgresql+asyncpg://...

    # -------------------------------------------------------------------------
    # JWT
    # -------------------------------------------------------------------------
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # -------------------------------------------------------------------------
    # Google OAuth
    # -------------------------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # -------------------------------------------------------------------------
    # SMTP
    # -------------------------------------------------------------------------
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "ATS Platform"
    smtp_from_email: str = "no-reply@example.com"
    smtp_tls: bool = True

    # -------------------------------------------------------------------------
    # File Storage
    # -------------------------------------------------------------------------
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 10

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    # -------------------------------------------------------------------------
    # Frontend
    # -------------------------------------------------------------------------
    frontend_url: str = "http://localhost:3000"

    # -------------------------------------------------------------------------
    # Derived helpers
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cv_upload_dir(self) -> str:
        return f"{self.upload_dir}/cv"

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import this everywhere."""
    return Settings()


settings = get_settings()
