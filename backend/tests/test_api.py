"""Integration test for api.py"""
import json
from unittest.mock import AsyncMock, patch

import httpx
import respx
from httpx import ASGITransport

from nexttrack.api import app
from nexttrack.lastfm.client import BASE_URL
from nexttrack.models import RecommendationResult

# Shared  helpers  based on test_aggregate.py.
# ----------------------------------------------------------------------

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
    #confirm POST /recommend returns 200 and a deserializable RecommendationResult.
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    # getSimilar for  single seed
    _route("track.getSimilar", seed_artist, seed_title, _similar_response([
        _sim_track("Glory Box",  "Portishead",     match=0.9, playcount=5_000_000),
        _sim_track("Teardrop",   "Massive Attack", match=0.7, playcount=8_000_000),
    ]))

    # getTopTags should return seed + candidates
    _route("track.getTopTags", seed_artist, seed_title,
           _tags_response(seed_artist, seed_title, [("alternative", 100)]))
    _route("track.getTopTags", "Portishead",     "Glory Box",
           _tags_response("Portishead",     "Glory Box",  [("alternative", 60), ("trip-hop", 40)]))
    _route("track.getTopTags", "Massive Attack", "Teardrop",
           _tags_response("Massive Attack", "Teardrop",   [("trip-hop", 90), ("electronic", 70)]))

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

    _route("track.getSimilar", seed_artist, seed_title, _similar_response([
        _sim_track("Glory Box",  "Portishead",     match=0.9, playcount=5_000_000),
        _sim_track("Teardrop",   "Massive Attack", match=0.7, playcount=8_000_000),
    ]))
    _route("track.getTopTags", seed_artist, seed_title,
           _tags_response(seed_artist, seed_title, [("alternative", 100)]))
    _route("track.getTopTags", "Portishead",     "Glory Box",
           _tags_response("Portishead",     "Glory Box",  [("alternative", 60), ("trip-hop", 40)]))
    _route("track.getTopTags", "Massive Attack", "Teardrop",
           _tags_response("Massive Attack", "Teardrop",   [("trip-hop", 90), ("electronic", 70)]))

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {"novelty": 50, "genre_lock": [], "artist_diversity": 5, "length": 10},
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
                    current_event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    current_data = line[len("data:"):].strip()
                elif line == "" and current_event is not None:
                    received.append((current_event, current_data or ""))
                    current_event = None
                    current_data = None
            # flush any final event not followed by a blank line
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


@respx.mock
async def test_recommend_stream_disconnect_cuts_last_fm_calls() -> None:
    # Registers all possible routes for a single-seed request (seed lookups +
    # candidate tag fetches). Simulates client disconnect immediately after the
    # first StageEvent is forwarded. Asserts that the two candidate tag calls
    # (which happen after the disconnect boundary) are never made.
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    _route("track.getSimilar", seed_artist, seed_title, _similar_response([
        _sim_track("Glory Box",  "Portishead",     match=0.9, playcount=5_000_000),
        _sim_track("Teardrop",   "Massive Attack", match=0.7, playcount=8_000_000),
    ]))
    _route("track.getTopTags", seed_artist, seed_title,
           _tags_response(seed_artist, seed_title, [("alternative", 100)]))
    # These two routes must NOT be reached after disconnect
    _route("track.getTopTags", "Portishead",     "Glory Box",
           _tags_response("Portishead",     "Glory Box",  [("alternative", 60)]))
    _route("track.getTopTags", "Massive Attack", "Teardrop",
           _tags_response("Massive Attack", "Teardrop",   [("trip-hop", 90)]))

    payload = {
        "seeds": [{"artist": seed_artist, "title": seed_title}],
        "params": {"novelty": 50, "genre_lock": [], "artist_diversity": 5, "length": 10},
    }

    received: list[str] = []
    # Patch is_disconnected to return True on every call so the generator exits
    # immediately after yielding the first StageEvent (similarity).
    with patch("starlette.requests.Request.is_disconnected", AsyncMock(return_value=True)):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            async with ac.stream("POST", "/recommend/stream", json=payload) as resp:
                assert resp.status_code == 200
                current_event: str | None = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line == "" and current_event is not None:
                        received.append(current_event)
                        current_event = None
                if current_event is not None:
                    received.append(current_event)

    # Only the similarity event escapes before the generator returns on disconnect
    assert received == ["similarity"]
    assert "result" not in received
    assert "done" not in received

    # Seed lookups (getSimilar + seed getTopTags) were already in-flight;
    # the two candidate getTopTags calls were never reached.
    assert len(respx.calls) == 2
