"""
Configuração do SUPREME V4 Backend.
Fail-closed: segredos críticos não possuem defaults inseguros em produção.
"""

from __future__ import annotations

from functools import lru_cache
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_VALUES = {
    "",
    "DEFINA_SECRET_KEY_EM_PRODUCAO",
    "DEFINA_SALT_OFFLINE",
    "change-me",
    "troque-em-producao",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"
    rq_queue_analytics: str = "analytics"
    rq_queue_events: str = "events"
    rq_queue_dead_letter: str = "dead_letter"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False
    api_secret_key: str = Field(..., min_length=32)
    api_ingest_token: str = Field(..., min_length=32)
    allowed_origins: str = "http://localhost:8000,http://localhost:8001"
    log_level: str = "INFO"

    supreme_salt: str = Field(..., min_length=32)

    study_start_date: str = "2026-01-01"
    window_days: int = 14
    min_baseline_windows: int = 4
    max_baseline_windows: int = 8
    dq_min_threshold: float = 0.5
    rq_max_retries: int = 3
    rq_retry_delay_s: int = 60

    sentinela_url: str = ""
    sentinela_api_key: str = ""

    enable_docs: bool = False
    enable_metrics: bool = True
    environment: str = "production"
    algorithm_version: str = "IEO-1.0.0"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL invalido")
        return upper

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def reject_insecure_defaults(self) -> "Settings":
        if self.environment.lower() == "production" and "*" in self.allowed_origins_list:
            raise ValueError("ALLOWED_ORIGINS não pode conter * em produção")
        # api_debug=True permite desenvolvimento local, mas não relaxa segredos críticos.
        for field in ("api_secret_key", "api_ingest_token", "supreme_salt"):
            value = getattr(self, field)
            if value in _PLACEHOLDER_VALUES:
                raise ValueError(f"{field.upper()} deve ser definido com valor secreto forte")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
