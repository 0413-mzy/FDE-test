"""Environment configuration; /health never requires a database connection."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    commerce_public_demo: bool = False
    commerce_public_demo_bootstrap: bool = False
    commerce_public_demo_local_acceptance: bool = False
    commerce_demo_password: SecretStr | None = None
    commerce_operator_password: SecretStr | None = None
    commerce_public_origin: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "commerce_public_origin", "COMMERCE_PUBLIC_ORIGIN", "RENDER_EXTERNAL_URL"
        ),
    )
    commerce_static_dir: Path | None = None
    commerce_image_quota_bytes: int = Field(default=32 * 1024 * 1024, gt=0)
    commerce_mailbox_dir: Path | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = Field(default="deepseek-flash", min_length=1, max_length=100)
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

    @model_validator(mode="after")
    def public_demo_configuration(self):
        if self.commerce_public_demo:
            if self.app_env != "production":
                raise ValueError("Public demo requires explicit production mode")
            origins = self.cors_origins([self.commerce_public_origin or ""])
            local_acceptance = self.commerce_public_demo_local_acceptance and HttpUrl(
                origins[0]
            ).host in {"localhost", "127.0.0.1", "::1"}
            if not origins[0].startswith("https://") and not local_acceptance:
                raise ValueError("Public demo requires an explicit HTTPS origin")
            public = (
                self.commerce_demo_password.get_secret_value()
                if self.commerce_demo_password
                else ""
            )
            operator = (
                self.commerce_operator_password.get_secret_value()
                if self.commerce_operator_password
                else ""
            )
            if not 12 <= len(public) <= 128 or not 20 <= len(operator) <= 128 or public == operator:
                raise ValueError("Public demo requires distinct public and private passwords")
            self.commerce_public_origin = origins[0]
            self.cors_allowed_origins = list(
                dict.fromkeys([*self.cors_allowed_origins, origins[0]])
            )
        return self
