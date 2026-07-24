"""Global settings, sourced from the environment with sensible defaults.

Anything secret (API keys) lives here so it is read once, from the environment,
and never hard-coded. Everything is overridable via ``REFORGE_*`` env vars.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REFORGE_", env_file=".env", extra="ignore")

    output_root: Path = Field(default=Path("runs"))
    default_network: str = Field(default="none")


def get_settings() -> Settings:
    return Settings()
