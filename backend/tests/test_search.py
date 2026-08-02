"""Tests for GET /search and LastfmClient.search_tracks."""

import json
from pathlib import Path
from unittest.mock import patch

import fakeredis.aioredis
import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from nexttrack.api import app
from nexttrack.cache import LastfmCache
from nexttrack.config import get_settings
from nexttrack.lastfm.client import BASE_URL, LastfmClient

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "track_search_radiohead.json").read_text()
)


@pytest.fixture
async def _app_ctx(monkeypatch):
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


# (a) fixture parses to correct TrackHit fields; largest non-empty image wins
@respx.mock
async def test_search_parses_artist_title_and_image():
    respx.get(
        BASE_URL,
        params={"method": "track.search", "track": "radiohead"},
    ).mock(return_value=httpx.Response(200, json=FIXTURE))

    async with httpx.AsyncClient() as client:
        lf = LastfmClient(client, "test_key")
        hits = await lf.search_tracks("radiohead", limit=3)

    assert len(hits) == 3
    assert hits[0]["artist"] == "Radiohead"
    assert hits[0]["title"] == "Creep"
    # Creep has all sizes populated; extralarge must be selected
    assert (
        hits[0]["image"] == "https://lastfm.freetls.fastly.net/i/u/300x300/abc123.png"
    )

    assert hits[1]["title"] == "Karma Police"
    # No Surprises: only medium populated; medium must be selected
    assert hits[2]["title"] == "No Surprises"
    assert hits[2]["image"] == "https://lastfm.freetls.fastly.net/i/u/64s/xyz789.png"


# (b) track with all-empty image #text fields yields image=None
@respx.mock
async def test_search_empty_images_yield_none():
    respx.get(
        BASE_URL,
        params={"method": "track.search", "track": "radiohead"},
    ).mock(return_value=httpx.Response(200, json=FIXTURE))

    async with httpx.AsyncClient() as client:
        lf = LastfmClient(client, "test_key")
        hits = await lf.search_tracks("radiohead", limit=3)

    assert hits[1]["image"] is None  # Karma Police: all #text are empty


# (c) q shorter than 2 stripped chars returns [] with zero outbound requests
@respx.mock
async def test_search_short_query_returns_empty_no_network(_app_ctx):
    route = respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=FIXTURE))

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get("/search", params={"q": "a"})

    assert r.status_code == 200
    assert r.json() == []
    assert not route.called


# (d) repeated identical query is served from cache on second call
@respx.mock
async def test_search_cache_hit_on_repeat():
    route = respx.get(
        BASE_URL,
        params={"method": "track.search", "track": "radiohead"},
    ).mock(return_value=httpx.Response(200, json=FIXTURE))

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = LastfmCache(fake_redis, ttl=3600)

    async with httpx.AsyncClient() as client:
        lf = LastfmClient(client, "test_key", cache=cache)
        hits1 = await lf.search_tracks("radiohead", limit=3)
        hits2 = await lf.search_tracks("radiohead", limit=3)

    assert hits1 == hits2
    assert route.call_count == 1  # Last.fm only called once
    assert cache.hits == 1
    assert cache.misses == 1

    await fake_redis.aclose()
