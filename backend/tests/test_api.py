# API testing-- full integration
import json
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from nexttrack.api import app
from nexttrack.config import get_settings
from nexttrack.lastfm.client import BASE_URL
from nexttrack.models import RecommendationResult, SeedProfile, TagCount


# monkeypatch used for env variable setting in absence at test time
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


# Shared  helpers  based on test_aggregate.py.
# -----------------------------------------------------

#define generic data structures
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


def _route(method: str, artist: str, track: str, body: dict) -> None:
    respx.get(
        BASE_URL,
        params={"method": method, "artist": artist, "track": track},
    ).mock(return_value=httpx.Response(200, json=body))


def _artist_route(method: str, artist: str, body: dict) -> None:
    respx.get(
        BASE_URL,
        params={"method": method, "artist": artist},
    ).mock(return_value=httpx.Response(200, json=body))


def _artist_similar_response(artists: list[tuple[str, float]]) -> dict:
    return {
        "similarartists": {
            "artist": [{"name": n, "match": str(m), "url": ""} for n, m in artists]
        }
    }


# Tests for api routes
# ---------------------------------------------------------------------------


async def test_health() -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@respx.mock
async def test_recommend_200_and_valid_result() -> None:
    # confirm POST /recommend returns 200 and a deserializable RecommendationResult.
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    # getSimilar for  single seed
    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
                _sim_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )

    # getTopTags should return seed + candidates
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response(
            "Portishead", "Glory Box", [("alternative", 60), ("trip-hop", 40)]
        ),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response(
            "Massive Attack", "Teardrop", [("trip-hop", 90), ("electronic", 70)]
        ),
    )

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/recommend",
            json={
                "seeds": [{"artist": seed_artist, "title": seed_title}],
                "params": {
                    "novelty": 50,
                    "genre_lock": [],
                    "artist_diversity": 5,
                    "length": 10,
                },
            },
        )

    assert r.status_code == 200
    result = RecommendationResult.model_validate(r.json())
    assert len(result.candidates) == 2
    # Glory Box has higher score: sim=0.9, matched alternative tag_overlap=1.0
    assert result.candidates[0].title == "Glory Box"


# Seed input cap validation (min=1, max=50)
# ---------------------------------------------------------------------------


async def test_recommend_empty_seeds_returns_422() -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/recommend",
            json={
                "seeds": [],
                "params": {"novelty": 50, "artist_diversity": 5, "length": 10},
            },
        )
    assert r.status_code == 422
    body = r.json()
    assert "error" in body
    assert any("seeds" in d for d in body["details"])


async def test_recommend_too_many_seeds_returns_422() -> None:
    seeds = [{"artist": f"Artist{i}", "title": f"Track{i}"} for i in range(51)]
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/recommend",
            json={
                "seeds": seeds,
                "params": {"novelty": 50, "artist_diversity": 5, "length": 10},
            },
        )
    assert r.status_code == 422
    body = r.json()
    assert "error" in body
    assert any("seeds" in d for d in body["details"])


# Streaming endpoint
# ---------------------------------------------------------------------------


@respx.mock
async def test_recommend_stream_event_order_and_result() -> None:
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
                _sim_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response(
            "Portishead", "Glory Box", [("alternative", 60), ("trip-hop", 40)]
        ),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response(
            "Massive Attack", "Teardrop", [("trip-hop", 90), ("electronic", 70)]
        ),
    )

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {
            "novelty": 50,
            "genre_lock": [],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    received: list[tuple[str, str]] = []
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        async with ac.stream("POST", "/recommend/stream", json=payload) as resp:
            assert resp.status_code == 200
            current_event: str | None = None
            current_data: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    current_data = line[len("data:") :].strip()
                elif line == "" and current_event is not None:
                    received.append((current_event, current_data or ""))
                    current_event = None
                    current_data = None
            if current_event is not None:
                received.append((current_event, current_data or ""))

    event_names = [ev for ev, _ in received]

    # required events are all present
    assert "similarity" in event_names
    assert "tags" in event_names
    assert "result" in event_names
    assert "done" in event_names

    # ordering: similarity < tags < result < done
    assert event_names.index("similarity") < event_names.index("tags")
    assert event_names.index("tags") < event_names.index("result")
    assert event_names.index("result") < event_names.index("done")

    # result parses as a valid RecommendationResult with the expected ranking
    result_data = next(data for ev, data in received if ev == "result")
    result = RecommendationResult.model_validate(json.loads(result_data))
    assert len(result.candidates) == 2
    assert result.candidates[0].title == "Glory Box"


# /seed-profile endpoint
# ---------------------------------------------------------------------------


@respx.mock
async def test_seed_profile_happy_path() -> None:
    # Two seeds sharing "alternative". unique tags verify sort order.
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
            ]
        ),
    )
    _route(
        "track.getSimilar",
        "Dr. Dog",
        "Shadow People",
        _similar_response(
            [
                _sim_track("Pink Moon", "Nick Drake", match=0.5, playcount=2_000_000),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        "Radiohead",
        "Pyramid Song",
        _tags_response(
            "Radiohead", "Pyramid Song", [("alternative", 100), ("art rock", 50)]
        ),
    )
    _route(
        "track.getTopTags",
        "Dr. Dog",
        "Shadow People",
        _tags_response("Dr. Dog", "Shadow People", [("alternative", 80), ("folk", 40)]),
    )

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/seed-profile",
            json={
                "seeds": [
                    {"artist": "Radiohead", "title": "Pyramid Song"},
                    {"artist": "Dr. Dog", "title": "Shadow People"},
                ]
            },
        )

    assert r.status_code == 200
    profile = SeedProfile.model_validate(r.json())
    assert profile.total_seeds == 2
    assert profile.dropped_seeds == []

    tag_map = {t.name: t.seed_count for t in profile.tags}
    assert tag_map["alternative"] == 2
    assert tag_map["art rock"] == 1
    assert tag_map["folk"] == 1

    # sort: desc seed_count, then alpha on name
    assert profile.tags[0] == TagCount(name="alternative", seed_count=2)
    assert profile.tags[1] == TagCount(name="art rock", seed_count=1)
    assert profile.tags[2] == TagCount(name="folk", seed_count=1)


@respx.mock
async def test_seed_profile_fallback_b_seed_dropped() -> None:
    # Seed whose track.getSimilar and artist.getSimilar both return empty lands
    # in dropped_seeds; total_seeds still reflects the original input count.
    _route("track.getSimilar", "Zxqvbw", "Ploknmf", _similar_response([]))
    _artist_route("artist.getSimilar", "Zxqvbw", _artist_similar_response([]))

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/seed-profile",
            json={"seeds": [{"artist": "Zxqvbw", "title": "Ploknmf"}]},
        )

    assert r.status_code == 200
    profile = SeedProfile.model_validate(r.json())
    assert profile.dropped_seeds == ["Zxqvbw/Ploknmf"]
    assert profile.tags == []
    assert profile.total_seeds == 1

#test bad api logic handling for direct calls. no seeds case
async def test_seed_profile_empty_seeds_returns_422() -> None:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post("/seed-profile", json={"seeds": []})
    assert r.status_code == 422

#too many seeds case
async def test_seed_profile_too_many_seeds_returns_422() -> None:
    seeds = [{"artist": f"Artist{i}", "title": f"Track{i}"} for i in range(51)] #go one above 50
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post("/seed-profile", json={"seeds": seeds})
    assert r.status_code == 422


@respx.mock
async def test_seed_profile_statelessness_recommend_unaffected() -> None:
   #confirms Calling /seed-profile before /recommend shares no state.

    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    # Routes for both /seed-profile and /recommend. each call hits Last.fm
    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
                _sim_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("alternative", 60)]),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response("Massive Attack", "Teardrop", [("trip-hop", 90)]),
    )

    payload_seeds = [{"artist": seed_artist, "title": seed_title}]

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        sp = await ac.post("/seed-profile", json={"seeds": payload_seeds})
        rec = await ac.post(
            "/recommend",
            json={
                "seeds": payload_seeds,
                "params": {
                    "novelty": 50,
                    "genre_lock": [],
                    "artist_diversity": 5,
                    "length": 10,
                },
            },
        )

    #confirm hits
    assert sp.status_code == 200
    assert rec.status_code == 200
    # /recommend returns a valid, correctly ranked result regardless of the
    # prior /seed-profile call — proves no shared mutable state exists.
    result = RecommendationResult.model_validate(rec.json())
    assert len(result.candidates) == 2
    assert result.candidates[0].title == "Glory Box"


# Cache integration tests


@respx.mock
async def test_cache_hit_on_second_recommend() -> None:
    # Two identical POST /recommend calls should not poll last.fm
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
                _sim_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response(
            "Portishead", "Glory Box", [("alternative", 60), ("trip-hop", 40)]
        ),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response(
            "Massive Attack", "Teardrop", [("trip-hop", 90), ("electronic", 70)]
        ),
    )

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {
            "novelty": 50,
            "genre_lock": [],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r1 = await ac.post("/recommend", json=payload)
        calls_after_first = len(respx.calls)

        r2 = await ac.post("/recommend", json=payload)
        calls_after_second = len(respx.calls)

        m = await ac.get("/metrics")

    #confirm both response with 200, are identical, and cache hit registered.
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert calls_after_second == calls_after_first
    metrics_body = m.json()
    assert metrics_body["cache"]["hits"] > 0


@respx.mock
async def test_cache_hit_on_second_recommend_stream() -> None:
    # Same as above but for the SSE streaming endpoint.
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
                _sim_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response(
            "Portishead", "Glory Box", [("alternative", 60), ("trip-hop", 40)]
        ),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response(
            "Massive Attack", "Teardrop", [("trip-hop", 90), ("electronic", 70)]
        ),
    )

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {
            "novelty": 50,
            "genre_lock": [],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    async def consume_stream(ac: httpx.AsyncClient) -> list[str]:
        events: list[str] = []
        async with ac.stream("POST", "/recommend/stream", json=payload) as resp:
            assert resp.status_code == 200
            current_event: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line == "" and current_event is not None:
                    events.append(current_event)
                    current_event = None
            if current_event is not None:
                events.append(current_event)
        return events

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        events1 = await consume_stream(ac)
        calls_after_first = len(respx.calls)

        events2 = await consume_stream(ac)
        calls_after_second = len(respx.calls)

        m = await ac.get("/metrics")

    assert "result" in events1
    assert "result" in events2
    assert calls_after_second == calls_after_first
    metrics_body = m.json()
    assert metrics_body["cache"]["hits"] > 0


@respx.mock
async def test_metrics_endpoint() -> None:
    # Warm the cache with one /recommend call then again. then assert /metrics reports counters
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("alternative", 60)]),
    )

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {
            "novelty": 50,
            "genre_lock": [],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",  # httpx test suite dummy required for asgit
    ) as ac:
        await ac.post("/recommend", json=payload)  # populates cache-- should all miss
        await ac.post(
            "/recommend", json=payload
        )  # serves from cache, all should be hits now.
        r = await ac.get("/metrics")

    assert r.status_code == 200
    body = r.json()["cache"]
    assert isinstance(body["hits"], int)  # confirm exists and is in reasonable bounds
    assert isinstance(body["misses"], int)
    assert isinstance(body["hit_rate"], float)
    assert body["hits"] > 0
    assert body["misses"] > 0
    assert 0.0 < body["hit_rate"] < 1.0


# CSV export via format=csv parameter

@respx.mock
async def test_recommend_lastfm_outage_returns_502() -> None:
    respx.get(BASE_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/recommend",
            json={
                "seeds": [{"artist": "Radiohead", "title": "Pyramid Song"}],
                "params": {
                    "novelty": 50,
                    "genre_lock": [],
                    "artist_diversity": 5,
                    "length": 10,
                },
            },
        )
    assert r.status_code == 502
    assert r.json()["error"] == "lastfm_unavailable"


@respx.mock
async def test_recommend_all_seeds_dropped_returns_422() -> None:
    _route("track.getSimilar", "Unknown", "Ghost Track", _similar_response([]))
    _artist_route("artist.getSimilar", "Unknown", _artist_similar_response([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/recommend",
            json={
                "seeds": [{"artist": "Unknown", "title": "Ghost Track"}],
                "params": {
                    "novelty": 50,
                    "genre_lock": [],
                    "artist_diversity": 5,
                    "length": 10,
                },
            },
        )
    assert r.status_code == 422
    assert r.json()["error"] == "no_successful_seeds"
    assert r.json()["dropped_seeds"] == ["Unknown/Ghost Track"]


@respx.mock
async def test_recommend_genre_lock_no_matches_returns_422() -> None:
    # Seed and candidate both carry trip-hop; genre_lock=["metal"] filters everything out
    _route(
        "track.getSimilar",
        "Portishead",
        "Glory Box",
        _similar_response(
            [_sim_track("Teardrop", "Massive Attack", match=0.9, playcount=5_000_000)]
        ),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("trip-hop", 100)]),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response("Massive Attack", "Teardrop", [("trip-hop", 90)]),
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(
            "/recommend",
            json={
                "seeds": [{"artist": "Portishead", "title": "Glory Box"}],
                "params": {
                    "novelty": 50,
                    "genre_lock": ["metal"],
                    "artist_diversity": 5,
                    "length": 10,
                },
            },
        )
    assert r.status_code == 422
    assert r.json()["error"] == "no_recommendations"


@respx.mock
async def test_recommend_stream_lastfm_outage_emits_error_event() -> None:
    respx.get(BASE_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    payload = {
        "seeds": [{"artist": "Radiohead", "title": "Pyramid Song"}],
        "params": {
            "novelty": 50,
            "genre_lock": [],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    received: list[tuple[str, str]] = []
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        async with ac.stream("POST", "/recommend/stream", json=payload) as resp:
            assert resp.status_code == 200
            current_event: str | None = None
            current_data: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    current_data = line[len("data:") :].strip()
                elif line == "" and current_event is not None:
                    received.append((current_event, current_data or ""))
                    current_event = None
                    current_data = None
            if current_event is not None:
                received.append((current_event, current_data or ""))

    event_names = [ev for ev, _ in received]
    assert "error" in event_names
    error_data = json.loads(next(d for ev, d in received if ev == "error"))
    assert error_data["error"] == "lastfm_unavailable"


@respx.mock
async def test_recommend_stream_no_successful_seeds_emits_error_event() -> None:
    _route("track.getSimilar", "Unknown", "Ghost Track", _similar_response([]))
    _artist_route("artist.getSimilar", "Unknown", _artist_similar_response([]))
    payload = {
        "seeds": [{"artist": "Unknown", "title": "Ghost Track"}],
        "params": {
            "novelty": 50,
            "genre_lock": [],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    received: list[tuple[str, str]] = []
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        async with ac.stream("POST", "/recommend/stream", json=payload) as resp:
            assert resp.status_code == 200
            current_event: str | None = None
            current_data: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    current_data = line[len("data:") :].strip()
                elif line == "" and current_event is not None:
                    received.append((current_event, current_data or ""))
                    current_event = None
                    current_data = None
            if current_event is not None:
                received.append((current_event, current_data or ""))

    event_names = [ev for ev, _ in received]
    assert "error" in event_names
    error_data = json.loads(next(d for ev, d in received if ev == "error"))
    assert error_data["error"] == "no_successful_seeds"


@respx.mock
async def test_recommend_stream_no_recommendations_emits_error_event() -> None:
    # trip-hop candidate with genre_lock=["metal"] shouldn't survive ranking
    _route(
        "track.getSimilar",
        "Portishead",
        "Glory Box",
        _similar_response(
            [_sim_track("Teardrop", "Massive Attack", match=0.9, playcount=5_000_000)]
        ),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("trip-hop", 100)]),
    )
    _route(
        "track.getTopTags",
        "Massive Attack",
        "Teardrop",
        _tags_response("Massive Attack", "Teardrop", [("trip-hop", 90)]),
    )
    payload = {
        "seeds": [{"artist": "Portishead", "title": "Glory Box"}],
        "params": {
            "novelty": 50,
            "genre_lock": ["metal"],
            "artist_diversity": 5,
            "length": 10,
        },
    }

    received: list[tuple[str, str]] = []
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        async with ac.stream("POST", "/recommend/stream", json=payload) as resp:
            assert resp.status_code == 200
            current_event: str | None = None
            current_data: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    current_data = line[len("data:") :].strip()
                elif line == "" and current_event is not None:
                    received.append((current_event, current_data or ""))
                    current_event = None
                    current_data = None
            if current_event is not None:
                received.append((current_event, current_data or ""))

    event_names = [ev for ev, _ in received]
    assert "error" in event_names
    error_data = json.loads(next(d for ev, d in received if ev == "error"))
    assert error_data["error"] == "no_recommendations"


@respx.mock
async def test_recommend_csv_format() -> None:
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    _route(
        "track.getSimilar",
        seed_artist,
        seed_title,
        _similar_response(
            [
                _sim_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        seed_artist,
        seed_title,
        _tags_response(seed_artist, seed_title, [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("alternative", 60)]),
    )

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {
            "novelty": 60,
            "genre_lock": [],
            "artist_diversity": 3,
            "length": 10,
        },
    }

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post("/recommend?format=csv", json=payload)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "nexttrack_" in r.headers["content-disposition"]
    assert ".csv" in r.headers["content-disposition"]

    body_text = r.text
    first_line = body_text.splitlines()[0]
    assert first_line.startswith("#"), f"Expected comment header, got: {first_line!r}"
