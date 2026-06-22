"""Integration test for api.py"""
import httpx
import respx
from httpx import ASGITransport

from nexttrack.api import app
from nexttrack.lastfm.client import BASE_URL
from nexttrack.models import RecommendationResult

# ---------------------------------------------------------------------------
# Shared  helpers  based on test_aggregate.py
# ---------------------------------------------------------------------------

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
        "artist": {"name": artist, "mbid": "", "url": ""},
        "match": match,
        "playcount": playcount,
        "mbid": "",
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


# ---------------------------------------------------------------------------
# Tests
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
    """POST /recommend returns 200 and a deserializable RecommendationResult."""
    seed_artist, seed_title = "Radiohead", "Pyramid Song"

    # getSimilar for the single seed
    _route("track.getSimilar", seed_artist, seed_title, _similar_response([
        _sim_track("Glory Box",  "Portishead",     match=0.9, playcount=5_000_000),
        _sim_track("Teardrop",   "Massive Attack", match=0.7, playcount=8_000_000),
    ]))

    # getTopTags — seed + candidates
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
                    "artist_diversity": 0,
                    "length": 10,
                },
            },
        )

    assert r.status_code == 200
    result = RecommendationResult.model_validate(r.json())
    assert len(result.candidates) == 2
    # Glory Box has higher score: sim=0.9, matched "alternative" (tag_overlap=1.0)
    assert result.candidates[0].title == "Glory Box"
