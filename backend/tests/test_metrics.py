# Tests that /metrics gets timing data from /recommend calls.

from unittest.mock import patch

import fakeredis.aioredis
import httpx
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from nexttrack.api import app
from nexttrack.config import get_settings
from nexttrack.lastfm.client import BASE_URL

import pytest


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


def _similar_response(tracks: list[dict]) -> dict:
    return {"similartracks": {"track": tracks}}


def _tags_response(artist: str, title: str, tags: list[tuple[str, int]]) -> dict:
    return {
        "toptags": {
            "tag": [{"name": n, "count": c, "url": ""} for n, c in tags],
            "@attr": {"artist": artist, "track": title},
        }
    }


def _sim_track(name: str, artist: str, match: float, playcount: int) -> dict:
    return {
        "name": name,
        "artist": {"name": artist, "url": ""},
        "match": match,
        "playcount": playcount,
        "streamable": {"#text": "0", "fulltrack": "0"},
        "duration": 240,
        "url": "",
        "image": [],
    }


def _mock_routes():
    respx.get(
        BASE_URL,
        params={
            "method": "track.getSimilar",
            "artist": "Radiohead",
            "track": "Pyramid Song",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json=_similar_response(
                [_sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000)]
            ),
        )
    )
    respx.get(
        BASE_URL,
        params={
            "method": "track.getTopTags",
            "artist": "Radiohead",
            "track": "Pyramid Song",
        },
    ).mock(
        return_value=httpx.Response(
            200,
            json=_tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]),
        )
    )
    respx.get(
        BASE_URL,
        params={
            "method": "track.getTopTags",
            "artist": "Portishead",
            "track": "Glory Box",
        },
    ).mock(
        return_value=httpx.Response(
            200, json=_tags_response("Portishead", "Glory Box", [("trip-hop", 80)])
        )
    )


_PAYLOAD = {
    "seeds": [{"artist": "Radiohead", "title": "Pyramid Song"}],
    "params": {"novelty": 50, "genre_lock": [], "artist_diversity": 5, "length": 10},
}


@respx.mock
async def test_metrics_timing_has_similarity_and_tags_stages():
    _mock_routes()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post("/recommend", json=_PAYLOAD)
        m = await ac.get("/metrics")

    timing = m.json()["timing"]
    assert "similarity" in timing
    assert "tags" in timing


@respx.mock
async def test_metrics_timing_stage_has_required_fields():
    _mock_routes()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post("/recommend", json=_PAYLOAD)
        m = await ac.get("/metrics")

    timing = m.json()["timing"]
    for stage_name in ("similarity", "tags"):
        # confirm order of percentiles
        stage = timing[stage_name]
        assert "p50" in stage
        assert "p95" in stage
        assert "max" in stage
        assert "n" in stage
        assert stage["n"] >= 1
        assert stage["max"] >= 0.0
        assert stage["p50"] <= stage["p95"] <= stage["max"]


@respx.mock
async def test_metrics_stream_also_populates_timing():
    _mock_routes()

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        async with ac.stream("POST", "/recommend/stream", json=_PAYLOAD) as resp:
            assert resp.status_code == 200
            async for _ in resp.aiter_lines():
                pass
        m = await ac.get("/metrics")

    timing = m.json()["timing"]
    assert "similarity" in timing
    assert timing["similarity"]["n"] >= 1
