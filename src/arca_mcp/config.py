from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    HOMOLOGACION = "homologacion"
    PRODUCCION = "produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCA_", env_file=".env")

    environment: Environment = Environment.HOMOLOGACION

    # Certificados
    cert_path: Path | None = None
    key_path: Path | None = None

    # CUIT del emisor
    cuit: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCCION


settings = Settings()
