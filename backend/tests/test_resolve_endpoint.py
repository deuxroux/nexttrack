# endpoint testing of spotify URL resolver's HTTP contract
import pytest
import httpx
import respx
import fakeredis.aioredis
from unittest.mock import patch
from httpx import ASGITransport
from asgi_lifespan import LifespanManager

from nexttrack.api import app
from nexttrack.config import get_settings

# test fixtures. remember that the track ID does not actually matter since it gets mocked
#we need to still test shape though since we have error handling.
TRACK_ID = "55q3Ro66yXWi9rsEddeEN4"
TOKEN_URL = "https://accounts.spotify.com/api/token"
TRACK_URL = f"https://api.spotify.com/v1/tracks/{TRACK_ID}"

#mock logic
_TOKEN_BODY = {"access_token": "tok_test", "token_type": "Bearer", "expires_in": 3600}
_TRACK_BODY = {
    "id": TRACK_ID,
    "name": "Pyramid Song",
    "artists": [{"id": "4Z8W4fKeB5YxbusRsdQVPb", "name": "Radiohead"}],
}


@pytest.fixture(autouse=True)
async def _override_settings(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "test_key")
    monkeypatch.setenv("USER_AGENT_CONTACT", "test@example.com")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_csecret")
    get_settings.cache_clear()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("nexttrack.api.redis_asyncio.from_url", return_value=fake_redis):
        async with LifespanManager(app):
            yield
    get_settings.cache_clear()


# Happy path returns good
# ---------------------------------------------------------------------

@respx.mock
async def test_resolve_happy_path():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))
    respx.get(TRACK_URL).mock(return_value=httpx.Response(200, json=_TRACK_BODY))

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/resolve-spotify-url",
            json={"url": f"https://open.spotify.com/track/{TRACK_ID}"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["artist"] == "Radiohead"
    assert body["title"] == "Pyramid Song"


@respx.mock
async def test_resolve_accepts_intl_url():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))
    respx.get(TRACK_URL).mock(return_value=httpx.Response(200, json=_TRACK_BODY))

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/resolve-spotify-url",
            json={"url": f"https://open.spotify.com/intl-en/track/{TRACK_ID}"},
        )

    assert r.status_code == 200
    assert r.json()["artist"] == "Radiohead"


# Invalid URL
# ---------------------------------------------------------------------------


async def test_resolve_invalid_url_returns_400():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post("/resolve-spotify-url", json={"url": "not-a-spotify-url"})

    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "invalid_url"


async def test_resolve_wrong_domain_returns_400():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/resolve-spotify-url",
            json={"url": f"https://music.apple.com/track/{TRACK_ID}"},
        )

    assert r.status_code == 400
    assert r.json()["error"] == "invalid_url"


# Missing credentials
# ---------------------------------------------------------------------------


async def test_resolve_missing_credentials_returns_503(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "")
    get_settings.cache_clear()

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/resolve-spotify-url",
            json={"url": f"https://open.spotify.com/track/{TRACK_ID}"},
        )

    get_settings.cache_clear()
    assert r.status_code == 503
    body = r.json()
    assert body["error"] == "spotify_unavailable"
    assert "configured" in body["detail"].lower()

@respx.mock
async def test_resolve_token_failure_returns_502():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/resolve-spotify-url",
            json={"url": f"https://open.spotify.com/track/{TRACK_ID}"},
        )

    assert r.status_code == 502
    assert r.json()["error"] == "spotify_unavailable"
