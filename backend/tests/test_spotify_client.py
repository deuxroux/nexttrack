import pytest
import httpx
import respx
import fakeredis.aioredis
from unittest.mock import AsyncMock, patch

from nexttrack.cache import LastfmCache
from nexttrack.spotify.client import SpotifyClient, SpotifyUnavailable

TRACK_ID = "4iV5W9uYEdYUVa79Axb7Rh"
TOKEN_URL = "https://accounts.spotify.com/api/token"
TRACK_URL = f"https://api.spotify.com/v1/tracks/{TRACK_ID}"

_TOKEN_BODY = {"access_token": "tok_abc", "token_type": "Bearer", "expires_in": 3600}
_TRACK_BODY = {
    "id": TRACK_ID,
    "name": "Pyramid Song",
    "artists": [{"id": "4Z8W4fKeB5YxbusRsdQVPb", "name": "Radiohead"}],
}


def _make_client() -> SpotifyClient:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = LastfmCache(fake_redis, ttl=30 * 24 * 3600)
    http = httpx.AsyncClient()
    return SpotifyClient(http, "cid", "csecret", cache)


# Token is receved?
# ---------------------------------------------------------------------------


@respx.mock
async def test_token_acquired_on_first_call():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))
    respx.get(TRACK_URL).mock(return_value=httpx.Response(200, json=_TRACK_BODY))

    client = _make_client()
    result = await client.get_track(TRACK_ID)

    assert result["name"] == "Pyramid Song"
    token_calls = [c for c in respx.calls if "api/token" in str(c.request.url)]
    assert len(token_calls) == 1


@respx.mock
async def test_token_reused_on_second_call():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))
    respx.get(TRACK_URL).mock(return_value=httpx.Response(200, json=_TRACK_BODY))

    client = _make_client()
    await client.get_track(TRACK_ID)
    calls_after_first = len(respx.calls)

    # Second call hits Redis cache — no HTTP at all
    await client.get_track(TRACK_ID)

    assert len(respx.calls) == calls_after_first  # no new HTTP calls


# 401 → forced token refresh, single retry
# ---------------------------------------------------------------------------


@respx.mock
async def test_forced_refresh_on_401():
    token_count = 0

    def token_side_effect(request):
        nonlocal token_count
        token_count += 1
        return httpx.Response(200, json=_TOKEN_BODY)

    track_count = 0

    def track_side_effect(request):
        nonlocal track_count
        track_count += 1
        return (
            httpx.Response(401)
            if track_count == 1
            else httpx.Response(200, json=_TRACK_BODY)
        )

    respx.post(TOKEN_URL).mock(side_effect=token_side_effect)
    respx.get(TRACK_URL).mock(side_effect=track_side_effect)

    client = _make_client()
    result = await client.get_track(TRACK_ID)

    assert result["name"] == "Pyramid Song"
    assert token_count == 2  # initial + forced refresh
    assert track_count == 2  # first 401, then success


# 429 status-- Retry-After sleep, single retry
# ---------------------------------------------------------------------------


@respx.mock
async def test_retry_after_on_429():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))

    track_count = 0

    def track_side_effect(request):
        nonlocal track_count
        track_count += 1
        if track_count == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json=_TRACK_BODY)

    respx.get(TRACK_URL).mock(side_effect=track_side_effect)

    client = _make_client()
    with patch(
        "nexttrack.spotify.client.asyncio.sleep", new=AsyncMock(return_value=None)
    ) as mock_sleep:
        result = await client.get_track(TRACK_ID)

    assert result["name"] == "Pyramid Song"
    mock_sleep.assert_called_once_with(2)


@respx.mock
async def test_double_429_raises_spotify_unavailable():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))
    respx.get(TRACK_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )

    client = _make_client()
    with patch(
        "nexttrack.spotify.client.asyncio.sleep", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(SpotifyUnavailable, match="max retries exceeded"):
            await client.get_track(TRACK_ID)


# check SpotifyUnavailable using mock values for statuses
# --------------------------------------------------------------------


@respx.mock
async def test_5xx_on_track_raises_spotify_unavailable():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_BODY))
    respx.get(TRACK_URL).mock(return_value=httpx.Response(503))

    client = _make_client()
    with pytest.raises(SpotifyUnavailable):
        await client.get_track(TRACK_ID)


@respx.mock
async def test_5xx_on_token_raises_spotify_unavailable():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(503))

    client = _make_client()
    with pytest.raises(SpotifyUnavailable):
        await client.get_track(TRACK_ID)


@respx.mock
async def test_bad_credentials_raises_spotify_unavailable():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401))

    client = _make_client()
    with pytest.raises(SpotifyUnavailable, match="credentials"):
        await client.get_track(TRACK_ID)
