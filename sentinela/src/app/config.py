from __future__ import annotations

from functools import lru_cache
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDERS = {"", "troque-em-producao", "chave-compartilhada-supreme-sentinela", "change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+asyncpg://sentinela:sentinela@db:5432/sentinela"
    secret_key: str = Field(..., min_length=32)
    supreme_api_key: str = Field(..., min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    bootstrap_token: str = ""
    allowed_origins: str = "http://localhost:8001"
    auto_init_db: bool = False
    enable_docs: bool = False
    environment: str = "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @field_validator("algorithm")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("Apenas HS256 está habilitado nesta implantação")
        return value

    @model_validator(mode="after")
    def reject_placeholders(self) -> "Settings":
        if self.environment.lower() == "production" and "*" in self.allowed_origins_list:
            raise ValueError("ALLOWED_ORIGINS não pode conter * em produção")
        for field in ("secret_key", "supreme_api_key"):
            if getattr(self, field) in _PLACEHOLDERS:
                raise ValueError(f"{field.upper()} deve ser definido com valor secreto forte")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
