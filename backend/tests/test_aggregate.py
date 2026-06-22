"""Golden test for pipeline/aggregate.py incl two-seed overlap case."""
import httpx
import pytest
import respx

from nexttrack.lastfm.client import BASE_URL, LastfmClient
from nexttrack.models import Track
from nexttrack.pipeline.aggregate import aggregate

API_KEY = "test_key"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _similar_track(
    name: str, artist: str, match: float, playcount: int, mbid: str = ""
) -> dict:
    return {
        "name": name,
        "artist": {"name": artist, "mbid": "", "url": ""},
        "match": match,
        "playcount": playcount,
        "mbid": mbid,
        "streamable": {"#text": "0", "fulltrack": "0"},
        "duration": 240,
        "url": "",
        "image": [],
    }


def _similar_response(tracks: list[dict]) -> dict:
    return {"similartracks": {"track": tracks}}


def _tags_response(artist: str, title: str, tags: list[tuple[str, int]]) -> dict:
    return {
        "toptags": {
            "tag": [{"name": n, "count": c, "url": ""} for n, c in tags],
            "@attr": {"artist": artist, "track": title},
        }
    }


def _route(method: str, artist: str, track: str, body: dict) -> None:
    """Register a track-level respx route (includes 'track' param)."""
    respx.get(
        BASE_URL,
        params={"method": method, "artist": artist, "track": track},
    ).mock(return_value=httpx.Response(200, json=body))


def _artist_route(method: str, artist: str, body: dict) -> None:
    """Register an artist-level respx route (no 'track' param)."""
    respx.get(
        BASE_URL,
        params={"method": method, "artist": artist},
    ).mock(return_value=httpx.Response(200, json=body))


def _artist_tags_response(artist: str, tags: list[tuple[str, int]]) -> dict:
    return {
        "toptags": {
            "tag": [{"name": n, "count": c, "url": ""} for n, c in tags],
            "@attr": {"artist": artist},
        }
    }


def _artist_similar_response(artists: list[tuple[str, float]]) -> dict:
    return {
        "similarartists": {
            "artist": [{"name": n, "match": str(m), "mbid": "", "url": ""} for n, m in artists]
        }
    }


def _artist_top_tracks_response(tracks: list[tuple[str, int]]) -> dict:
    return {
        "toptracks": {
            "track": [{"name": n, "playcount": str(pc), "mbid": "", "url": ""} for n, pc in tracks]
        }
    }


# ---------------------------------------------------------------------------
# Two-seed dataset
#
# Seed A  Radiohead / Pyramid Song   → recommends Glory Box (0.9), Teardrop (0.7)
# Seed B  Dr. Dog / Shadow People    → recommends Glory Box (0.6), Pink Moon (0.5)
#
# Seed tag profile: {alternative, art rock, folk}
#
# ex Candidate tags:
#   Glory Box  → {trip-hop, alternative}   → matched: [alternative]  overlap: 1/3
#   Teardrop   → {trip-hop, electronic}    → matched: []              overlap: 0
#   Pink Moon  → {folk, acoustic}          → matched: [folk]          overlap: 1/3
# ---------------------------------------------------------------------------

SEED_A = Track(artist="Radiohead", title="Pyramid Song")
SEED_B = Track(artist="Dr. Dog", title="Shadow People")


@respx.mock
async def test_two_seed_overlap():
    # getSimilar
    _route("track.getSimilar", "Radiohead", "Pyramid Song", _similar_response([
        _similar_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
        _similar_track("Teardrop",  "Massive Attack", match=0.7, playcount=8_000_000),
    ]))
    _route("track.getSimilar", "Dr. Dog", "Shadow People", _similar_response([
        _similar_track("Glory Box", "Portishead", match=0.6, playcount=5_000_000),
        _similar_track("Pink Moon", "Nick Drake",  match=0.5, playcount=2_000_000),
    ]))

    # getTopTags — seeds
    _route("track.getTopTags", "Radiohead", "Pyramid Song",
           _tags_response("Radiohead", "Pyramid Song", [("alternative", 100), ("art rock", 50)]))
    _route("track.getTopTags", "Dr. Dog", "Shadow People",
           _tags_response("Dr. Dog", "Shadow People", [("alternative", 80), ("folk", 40)]))

    # getTopTags — candidates
    _route("track.getTopTags", "Portishead", "Glory Box",
           _tags_response("Portishead", "Glory Box", [("trip-hop", 100), ("alternative", 60)]))
    _route("track.getTopTags", "Massive Attack", "Teardrop",
           _tags_response("Massive Attack", "Teardrop", [("trip-hop", 90), ("electronic", 70)]))
    _route("track.getTopTags", "Nick Drake", "Pink Moon",
           _tags_response("Nick Drake", "Pink Moon", [("folk", 80), ("acoustic", 50)]))

    async with httpx.AsyncClient() as client:
        candidates = await aggregate(LastfmClient(client, API_KEY), [SEED_A, SEED_B])

    # Three unique candidates after dedup
    assert len(candidates) == 3
    by_title = {c.title: c for c in candidates}

    # --- Glory Box: overlap from both seeds ---
    gb = by_title["Glory Box"]
    assert gb.artist == "Portishead"
    assert gb.summed_similarity == pytest.approx(1.5)          # 0.9 + 0.6
    assert set(gb.contributing_seeds) == {
        "Radiohead/Pyramid Song",
        "Dr. Dog/Shadow People",
    }
    assert gb.matched_tags == ["alternative"]                   # sorted intersection
    assert gb.tag_overlap == pytest.approx(1 / 3)              # 1 of 3 seed tags
    assert gb.novelty_bonus == pytest.approx(0.375)            # 1 - 5M/8M

    # --- Teardrop: single seed, no tag match ---
    td = by_title["Teardrop"]
    assert td.summed_similarity == pytest.approx(0.7)
    assert td.contributing_seeds == ["Radiohead/Pyramid Song"]
    assert td.matched_tags == []
    assert td.tag_overlap == pytest.approx(0.0)
    assert td.novelty_bonus == pytest.approx(0.0)              # max playcount

    # --- Pink Moon: single seed, one tag match ---
    pm = by_title["Pink Moon"]
    assert pm.summed_similarity == pytest.approx(0.5)
    assert pm.contributing_seeds == ["Dr. Dog/Shadow People"]
    assert pm.matched_tags == ["folk"]
    assert pm.tag_overlap == pytest.approx(1 / 3)
    assert pm.novelty_bonus == pytest.approx(0.75)             # 1 - 2M/8M


@respx.mock
async def test_case_insensitive_dedup():
    """Same track with different capitalisation from two seeds merges to one candidate."""
    _route("track.getSimilar", "Radiohead", "Pyramid Song", _similar_response([
        _similar_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
    ]))
    _route("track.getSimilar", "Dr. Dog", "Shadow People", _similar_response([
        _similar_track("glory box", "portishead", match=0.6, playcount=5_000_000),
    ]))
    _route("track.getTopTags", "Radiohead", "Pyramid Song",
           _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]))
    # Dr. Dog track tags are empty — triggers artist.getTopTags fallback
    _route("track.getTopTags", "Dr. Dog", "Shadow People",
           _tags_response("Dr. Dog", "Shadow People", []))
    _artist_route("artist.getTopTags", "Dr. Dog",
                  _artist_tags_response("Dr. Dog", [("indie rock", 60)]))
    # Only one candidate tag call because Glory Box deduplicates
    _route("track.getTopTags", "Portishead", "Glory Box",
           _tags_response("Portishead", "Glory Box", [("alternative", 60)]))

    async with httpx.AsyncClient() as client:
        candidates = await aggregate(LastfmClient(client, API_KEY), [SEED_A, SEED_B])

    assert len(candidates) == 1
    assert candidates[0].summed_similarity == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Fallback explanation (req 2.06 / 2.08)
# ---------------------------------------------------------------------------

@respx.mock
async def test_fallback_seed_explanation_populated():
    """
    When track.getSimilar is empty for a seed, the artist fallback fires.
    Candidates sourced via that seed carry a non-empty explanation.
    """
    seed = Track(artist="Dr. Dog", title="Shadow People")

    # track.getSimilar empty -> triggers artist.getSimilar + artist.getTopTracks
    _route("track.getSimilar", "Dr. Dog", "Shadow People",
           _similar_response([]))
    _artist_route("artist.getSimilar", "Dr. Dog",
                  _artist_similar_response([("Blitzen Trapper", 0.75)]))
    _artist_route("artist.getTopTracks", "Blitzen Trapper",
                  _artist_top_tracks_response([("Furr", 1_000_000)]))

    # Seed tags present -> no tag fallback for seed
    _route("track.getTopTags", "Dr. Dog", "Shadow People",
           _tags_response("Dr. Dog", "Shadow People", [("indie rock", 80)]))

    # Candidate (Blitzen Trapper / Furr) tag lookup
    _route("track.getTopTags", "Blitzen Trapper", "Furr",
           _tags_response("Blitzen Trapper", "Furr", [("indie rock", 50), ("folk", 30)]))

    async with httpx.AsyncClient() as client:
        candidates = await aggregate(LastfmClient(client, API_KEY), [seed])

    assert len(candidates) == 1
    furr = candidates[0]
    assert furr.artist == "Blitzen Trapper"
    assert furr.title == "Furr"
    assert furr.matched_tags == ["indie rock"]         # intersects seed tag profile
    assert len(furr.explanation) > 0
    assert any("artist.getSimilar" in note for note in furr.explanation)


@respx.mock
async def test_primary_seed_has_empty_explanation():
    """Candidates from a seed that used only primary routes have explanation=[]."""
    _route("track.getSimilar", "Radiohead", "Pyramid Song", _similar_response([
        _similar_track("Glory Box", "Portishead", match=0.9, playcount=5_000_000),
    ]))
    _route("track.getTopTags", "Radiohead", "Pyramid Song",
           _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]))
    _route("track.getTopTags", "Portishead", "Glory Box",
           _tags_response("Portishead", "Glory Box", [("alternative", 60)]))

    async with httpx.AsyncClient() as client:
        candidates = await aggregate(LastfmClient(client, API_KEY), [SEED_A])

    assert candidates[0].explanation == []
