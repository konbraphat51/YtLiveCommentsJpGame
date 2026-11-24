"""Runtime settings read from environment variables and .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paths and credentials; secrets come only from the environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    youtube_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("YOUTUBE_API_KEY", "YT_API"))
    data_dir: Path = Field(default=Path("Data"), validation_alias=AliasChoices("DATA_DIR"))
    config_dir: Path = Field(default=Path("Config"), validation_alias=AliasChoices("CONFIG_DIR"))

    @property
    def catalog_path(self) -> Path:
        """Path of the SQLite catalog."""
        return self.data_dir / "Catalog.sqlite"

    @property
    def raw_dir(self) -> Path:
        """Root of the raw store."""
        return self.data_dir / "Raw"

    def require_api_key(self) -> str:
        """Returns the API key or raises if it is not configured."""
        if self.youtube_api_key is None:
            raise RuntimeError("Set YOUTUBE_API_KEY (or YT_API) in the environment or .env")
        return self.youtube_api_key.get_secret_value()
