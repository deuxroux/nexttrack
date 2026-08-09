from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#  .env relative path for loading regardless of cwd
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    lastfm_api_key: str
    user_agent_contact: str

    app_name: str = "NextTrack"
    app_version: str = "0.1"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_lastfm_seconds: int = 14 * 24 * 3600  # days * hours * seconds

    #  /resolve-spotify-url returns 503 if either field is empty.
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    cache_ttl_spotify_seconds: int = 14 * 24 * 3600

    # comma-separated list for local host origins. can add "[...], http://localhost:3000"
    cors_allowed_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8")

    @property
    def user_agent(self) -> str:
        return f"{self.app_name}/{self.app_version} ({self.user_agent_contact})"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache  # save so this doesn't reparse every time.
def get_settings() -> Settings:
    # NOTE flags error statically but doesn't actually get built at runtime so ignored.
    return Settings()  # type: ignore[call-arg]
