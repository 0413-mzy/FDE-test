"""Environment configuration; /health never requires a database connection."""

from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    sandbox_base_url: HttpUrl | None = None
    sandbox_timeout_seconds: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    cors_allowed_origins: list[str] = Field(default_factory=list)

    @field_validator("cors_allowed_origins")
    @classmethod
    def cors_origins(cls, values: list[str]) -> list[str]:
        result = []
        for value in values:
            origin = HttpUrl(value)
            if (
                "*" in value
                or origin.username
                or origin.password
                or origin.query
                or origin.fragment
                or origin.path not in (None, "/")
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins")
            result.append(str(origin).rstrip("/"))
        return list(dict.fromkeys(result))

    @field_validator("sandbox_base_url")
    @classmethod
    def sandbox_origin(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and (
            value.username
            or value.password
            or value.query
            or value.fragment
            or value.path not in (None, "/")
        ):
            raise ValueError("SANDBOX_BASE_URL must be an HTTP(S) origin without credentials")
        return value
