# THIS SUITE: prove statelessness. no endpoint must ever emit a Set-Cookie header.
# Each route is hit with a minimal payload checking no cookie is set.

import pytest
import httpx
import fakeredis.aioredis
from unittest.mock import patch
from httpx import ASGITransport
from asgi_lifespan import LifespanManager

from nexttrack.api import app
from nexttrack.config import get_settings


@pytest.fixture(autouse=True)
async def _override_settings(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "test_key")
    monkeypatch.setenv("USER_AGENT_CONTACT", "test@example.com")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "")
    get_settings.cache_clear()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("nexttrack.api.redis_asyncio.from_url", return_value=fake_redis):
        async with LifespanManager(app):
            yield
    get_settings.cache_clear()


# Payloads are chosen to get response (422/400/503)
_ROUTES = [
    ("GET", "/health", None),
    ("GET", "/metrics", None),
    # Empty seeds generate 422 before any I/O
    ("POST", "/seed-profile", {"seeds": []}),
    (
        "POST",
        "/recommend",
        {"seeds": [], "params": {"novelty": 50, "artist_diversity": 3, "length": 10}},
    ),
    (
        "POST",
        "/recommend/stream",
        {"seeds": [], "params": {"novelty": 50, "artist_diversity": 3, "length": 10}},
    ),
    # No Spotify creds configured generates 503 before any Spotify I/O
    (
        "POST",
        "/resolve-spotify-url",
        {"url": "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"},
    ),
]


@pytest.mark.parametrize("method,path,payload", _ROUTES)
async def test_no_set_cookie(method: str, path: str, payload) -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        if method == "GET":
            r = await ac.get(path)
        else:
            r = await ac.post(path, json=payload)

    assert "set-cookie" not in r.headers, (
        f"{method} {path} returned Set-Cookie: {r.headers.get('set-cookie')}"
    )
