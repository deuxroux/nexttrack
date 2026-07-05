from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file so it loads regardless of working directory
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    lastfm_api_key: str = ""
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8")


@lru_cache #save so this doesn't reparse every time.
def get_settings() -> Settings:
    return Settings()
