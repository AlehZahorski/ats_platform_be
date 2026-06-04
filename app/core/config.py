from functools import lru_cache
from typing import Literal

from pydantic import field_validator
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
    app_name: str = "wakanta.pl"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str

    # Observability (Faza 4): "json" emits one structured JSON object per log
    # line on stdout (with request_id correlation + PII redaction) ready for a
    # log collector; "text" keeps the human-readable default for local dev.
    log_format: Literal["text", "json"] = "text"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str  # postgresql+asyncpg://...

    # -------------------------------------------------------------------------
    # JWT
    # -------------------------------------------------------------------------
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # audit_rodo_gdpr F-15 (storage limitation, art. 5(1)(e) GDPR): default
    # window for keeping a candidate's application before the cleanup job
    # auto-anonymises it. UODO guidance for PL recruitment data is 12 months
    # without consent for future recruitments. Per-company override lives in
    # the `companies` table; this is the global fallback.
    application_retention_months: int = 12

    # audit_performance B-06 / B-09: DB pool tunables surfaced as env vars so
    # ops can scale per environment without a code change. Defaults raised
    # for production-like behaviour; statement_timeout is a guardrail against
    # a single misbehaving query eating the whole pool.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_statement_timeout_ms: int = 15000
    db_idle_in_transaction_timeout_ms: int = 60000

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
    smtp_from_name: str = "wakanta.pl"
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
    # F-H3 / F-M10 (audit_api): extra origins to allow through CORS, comma-
    # separated. Use for staging / preview deploys. Example:
    # ``CORS_EXTRA_ORIGINS=https://staging.wakanta.pl,https://pr-42.wakanta.pl``.
    cors_extra_origins: str = ""

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Final list of origins allowed by the CORS middleware.

        Localhost variants only in non-production environments to avoid
        accidentally accepting them from a prod deploy.
        """
        origins: list[str] = []
        if self.app_env != "production":
            origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])
        if self.frontend_url:
            origins.append(self.frontend_url)
        for extra in self.cors_extra_origins.split(","):
            extra = extra.strip()
            if extra:
                origins.append(extra)
        # Dedupe while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for origin in origins:
            if origin not in seen:
                seen.add(origin)
                unique.append(origin)
        return unique

    # -------------------------------------------------------------------------
    # LLM Integration
    # -------------------------------------------------------------------------
    anthropic_api_key: str = ""
    llm_cv_model: str = "claude-haiku-4-5-20251001"
    llm_match_model: str = "claude-sonnet-4-6"

    # F-07: request timeout (seconds) for every Anthropic call. Default 30s
    # matches the empirical p99 latency for our prompts; raise only for batch.
    llm_request_timeout_seconds: float = 30.0
    # F-07: retry attempts on top of the initial call. Total tries = retries + 1.
    llm_max_retries: int = 2

    # F-13: limits on raw user-controlled text shipped to Claude. Keep these
    # tight — longer text rarely improves extraction and always raises cost.
    llm_cv_raw_text_limit: int = 8000
    llm_job_raw_text_limit: int = 16000
    # F-15: hard ceiling on the post-extract CV text we keep in memory
    # before truncation. Caps a 200-page CV from eating worker RAM.
    llm_cv_extract_char_limit: int = 200_000

    # F-03: enable ephemeral prompt caching on system prompts. Toggle for
    # tests / local Haiku trials where the 1024-token minimum is not met.
    llm_prompt_cache_enabled: bool = True

    # F-02: contact PII (email / phone) is redacted before ANY CV text leaves
    # the EU process for the LLM — unconditionally, regardless of AI-profiling
    # consent. This backs the public promise on /ai-info ("przed wysłaniem
    # czegokolwiek do modelu automatycznie redagujemy dane osobowe").
    # Consent still gates the *matching* call (see cv_parsing.run), not this.
    # Set to False only for local development.
    llm_redact_pii: bool = True

    # F-05: per-company daily budget in USD. When sum(api_usage_logs.cost_usd)
    # in the last rolling 24h exceeds this, new LLM endpoints return 429.
    # Set to 0 to disable (use only in dev).
    llm_daily_budget_usd_per_company: float = 10.0

    # F-10: circuit breaker tuning (see app.services.llm.circuit).
    llm_breaker_threshold: int = 5
    llm_breaker_window_seconds: float = 60.0
    llm_breaker_cool_down_seconds: float = 60.0

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

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
