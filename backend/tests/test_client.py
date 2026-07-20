import json
import time
from pathlib import Path

import httpx
import pytest
import respx
import fakeredis.aioredis

from nexttrack.cache import LastfmCache
from nexttrack.lastfm.client import BASE_URL, LastfmClient

FIXTURES = Path(__file__).parent / "fixtures"
API_KEY = "test_key"


# track.getSimilar primary route
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_similar_tracks_shape():
    fixture = json.loads(
        (FIXTURES / "get_similar__radiohead__pyramid_song.json").read_text()
    )
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=fixture))

    async with httpx.AsyncClient() as client:
        result = await LastfmClient(client, API_KEY).get_similar_tracks(
            "Radiohead", "Pyramid Song"
        )

    assert result.fallback_used is False
    assert len(result.tracks) == 50
    first = result.tracks[0]
    assert first["name"] == "You and Whose Army?"
    assert first["artist"] == "Radiohead"
    assert isinstance(first["match"], float)
    assert isinstance(first["playcount"], int)


# track.getSimilar fallback to artist.getSimilar + artist.getTopTracks
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_similar_tracks_fallback_on_empty():
    # Empty track.getSimilar triggers artist should fallbac to top artist tracks
    respx.get(BASE_URL, params={"method": "track.getSimilar"}).mock(
        return_value=httpx.Response(200, json={"similartracks": {"track": []}})
    )
    respx.get(BASE_URL, params={"method": "artist.getSimilar"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "similarartists": {"artist": [{"name": "Portishead", "match": "0.85"}]}
            },
        )
    )
    respx.get(BASE_URL, params={"method": "artist.getTopTracks"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "toptracks": {"track": [{"name": "Glory Box", "playcount": "5000000"}]}
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result = await LastfmClient(client, API_KEY).get_similar_tracks(
            "Dr. Dog", "Shadow People"
        )

    assert result.fallback_used is True
    assert "artist.getSimilar" in result.fallback_note
    assert len(result.tracks) == 1
    t = result.tracks[0]
    assert t["name"] == "Glory Box"
    assert t["artist"] == "Portishead"
    assert t["match"] == 0.85
    assert isinstance(t["playcount"], int)


@respx.mock
async def test_get_similar_tracks_fallback_empty_artists_returns_empty():
    # confirm f artist.getSimilar also returns nothing, result is empty but fallback_used = true.
    respx.get(BASE_URL, params={"method": "track.getSimilar"}).mock(
        return_value=httpx.Response(200, json={"similartracks": {"track": []}})
    )
    respx.get(BASE_URL, params={"method": "artist.getSimilar"}).mock(
        return_value=httpx.Response(200, json={"similarartists": {"artist": []}})
    )

    async with httpx.AsyncClient() as client:
        result = await LastfmClient(client, API_KEY).get_similar_tracks(
            "Nobody", "Unknown"
        )

    assert result.fallback_used is True
    assert result.tracks == []


# track.getTopTags primary route
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_top_tags_shape():
    fixture = json.loads(
        (FIXTURES / "get_top_tags__radiohead__pyramid_song.json").read_text()
    )
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=fixture))

    async with httpx.AsyncClient() as client:
        result = await LastfmClient(client, API_KEY).get_top_tags(
            "Radiohead", "Pyramid Song"
        )

    assert result.fallback_used is False
    assert len(result.tags) == 10
    first = result.tags[0]
    assert first["name"] == "alternative"
    assert first["count"] == 100
    assert isinstance(first["count"], int)


# confirm track.getTopTags fallback to artist.getTopTags
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_top_tags_fallback_on_empty():
    # Empty track.getTopTags triggers artist.getTopTags fallback.
    respx.get(BASE_URL, params={"method": "track.getTopTags"}).mock(
        return_value=httpx.Response(200, json={"toptags": {"tag": []}})
    )
    respx.get(BASE_URL, params={"method": "artist.getTopTags"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "toptags": {"tag": [{"name": "indie rock", "count": "75", "url": ""}]}
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result = await LastfmClient(client, API_KEY).get_top_tags(
            "Dr. Dog", "Shadow People"
        )

    assert result.fallback_used is True
    assert "artist.getTopTags" in result.fallback_note
    assert len(result.tags) == 1
    assert result.tags[0]["name"] == "indie rock"
    assert result.tags[0]["count"] == 75


@respx.mock
async def test_get_top_tags_fallback_empty_artist_tags_returns_empty():
    # If artist tags also empty, result is empty with fallback_used True.
    respx.get(BASE_URL, params={"method": "track.getTopTags"}).mock(
        return_value=httpx.Response(200, json={"toptags": {"tag": []}})
    )
    respx.get(BASE_URL, params={"method": "artist.getTopTags"}).mock(
        return_value=httpx.Response(200, json={"toptags": {"tag": []}})
    )

    async with httpx.AsyncClient() as client:
        result = await LastfmClient(client, API_KEY).get_top_tags(
            "Dr. Dog", "Shadow People"
        )

    assert result.fallback_used is True
    assert result.tags == []


# Confirm Rate limiter enforces <=5 req/s
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("n_requests", [6])
async def test_rate_limit_enforces_five_per_second(n_requests: int):
    # Six sequential requests must take >=1.0s under the 5 req/s limiter.
    fixture = json.loads(
        (FIXTURES / "get_top_tags__radiohead__pyramid_song.json").read_text()
    )
    respx.get(BASE_URL).mock(return_value=httpx.Response(200, json=fixture))

    async with httpx.AsyncClient() as client:
        lf = LastfmClient(client, API_KEY)
        t0 = time.monotonic()
        for _ in range(n_requests):
            await lf.get_top_tags("Radiohead", "Pyramid Song")
        elapsed = time.monotonic() - t0

    # 6 requests at <=5 req/s must span at least 1 full second
    assert elapsed >= 1.0, (
        f"Expected >=1.0s for {n_requests} requests, got {elapsed:.3f}s"
    )


# Confirm Cache  features
# ---------------------------------------------------------------------------


# create fake cache
@pytest.fixture
async def cache() -> LastfmCache:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return LastfmCache(fake, ttl=3600)


# don't check lastfm if cached
@respx.mock
async def test_cache_hit_skips_lastfm_fetch(cache: LastfmCache) -> None:
    route = respx.get(BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "similartracks": {
                    "track": [
                        {
                            "name": "T",
                            "artist": {"name": "A"},
                            "match": "0.9",
                            "playcount": "100",
                        }
                    ]
                }
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = LastfmClient(http, "test_key", cache=cache)
        await client.get_similar_tracks("Radiohead", "Pyramid Song")
        first_count = route.call_count
        await client.get_similar_tracks("Radiohead", "Pyramid Song")
        assert route.call_count == first_count, "second call must not hit Last.fm"
    assert cache.hits >= 1


# if disabled path works
@respx.mock
async def test_cache_none_disables_caching_cleanly() -> None:
    route = respx.get(BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "similartracks": {
                    "track": [
                        {
                            "name": "T",
                            "artist": {"name": "A"},
                            "match": "0.9",
                            "playcount": "100",
                        }
                    ]
                }
            },
        )
    )
    async with httpx.AsyncClient() as http:
        client = LastfmClient(http, "test_key")  # no cache
        await client.get_similar_tracks("Radiohead", "Pyramid Song")
        await client.get_similar_tracks("Radiohead", "Pyramid Song")
        assert route.call_count == 2, "both calls must hit Last.fm when cache disabled"
