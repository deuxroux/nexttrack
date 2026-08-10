# test for pipeline/aggregate.py  two-seed overlap case. should deduplicate.
import httpx
import pytest
import respx

from nexttrack.lastfm.client import BASE_URL, LastfmClient
from nexttrack.models import Candidate, SeedProfile, StageEvent, TagCount, Track
from nexttrack.pipeline.aggregate import (
    aggregate,
    aggregate_streaming,
    build_seed_profile,
)

API_KEY = "test_key"


# Fixturing
# ---------------------------------------------------------------------------


def _similar_track(name: str, artist: str, match: float, playcount: int) -> dict:
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
            "artist": [{"name": n, "match": str(m), "url": ""} for n, m in artists]
        }
    }


def _artist_top_tracks_response(tracks: list[tuple[str, int]]) -> dict:
    return {
        "toptracks": {
            "track": [{"name": n, "playcount": str(pc), "url": ""} for n, pc in tracks]
        }
    }


# ---------------------------------------------------------------------------
# Two-seed dataset. some verified matches from trial and error
#
# Seed A  Radiohead / Pyramid Song recommends Glory Box (0.9), Teardrop (0.7)
# Seed B  Dr. Dog / Shadow People  recommends Glory Box (0.6), Pink Moon (0.5)
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
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
                _similar_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getSimilar",
        "Dr. Dog",
        "Shadow People",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.6, playcount=5_000_000
                ),
                _similar_track(
                    "Pink Moon", "Nick Drake", match=0.5, playcount=2_000_000
                ),
            ]
        ),
    )

    # getTopTags (seeds)
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

    # getTopTags candidates
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response(
            "Portishead", "Glory Box", [("trip-hop", 100), ("alternative", 60)]
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
    _route(
        "track.getTopTags",
        "Nick Drake",
        "Pink Moon",
        _tags_response("Nick Drake", "Pink Moon", [("folk", 80), ("acoustic", 50)]),
    )

    async with httpx.AsyncClient() as client:
        candidates, dropped = await aggregate(
            LastfmClient(client, API_KEY), [SEED_A, SEED_B]
        )

    assert dropped == []
    # should be only three unique candidates after dedup
    assert len(candidates) == 3
    by_title = {c.title: c for c in candidates}

    # Glory Box is the overlap from both seeds
    gb = by_title["Glory Box"]
    assert gb.artist == "Portishead"
    assert gb.summed_similarity == pytest.approx(1.5)  # 0.9 + 0.6
    assert set(gb.contributing_seeds) == {
        "Radiohead/Pyramid Song",
        "Dr. Dog/Shadow People",
    }
    assert gb.matched_tags == ["alternative"]
    assert gb.tag_overlap == pytest.approx(1 / 3)
    assert gb.novelty_bonus == pytest.approx(0.375)
    # Radiohead/Pyramid Song contributed the higher match (0.9 vs 0.6)
    assert gb.explanation[0] == "top seed: Radiohead/Pyramid Song"
    assert gb.explanation[1] == "matched tags: alternative"

    # --- Teardrop: single seed, no tag match ---
    td = by_title["Teardrop"]
    assert td.summed_similarity == pytest.approx(0.7)
    assert td.contributing_seeds == ["Radiohead/Pyramid Song"]
    assert td.matched_tags == []
    assert td.tag_overlap == pytest.approx(0.0)
    assert td.novelty_bonus == pytest.approx(0.0)  # confirm max playcount
    assert td.explanation == [
        "top seed: Radiohead/Pyramid Song"
    ]  # no matched tags line

    # --- Pink Moon: single seed, one tag match ---
    pm = by_title["Pink Moon"]
    assert pm.summed_similarity == pytest.approx(0.5)
    assert pm.contributing_seeds == ["Dr. Dog/Shadow People"]
    assert pm.matched_tags == ["folk"]
    assert pm.tag_overlap == pytest.approx(1 / 3)
    assert pm.novelty_bonus == pytest.approx(0.75)  # 1 - 2M/8M
    assert pm.explanation == ["top seed: Dr. Dog/Shadow People", "matched tags: folk"]


@respx.mock
async def test_case_insensitive_dedup():
    # Same track with different exact spelling from two seeds still need to merge to one
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getSimilar",
        "Dr. Dog",
        "Shadow People",
        _similar_response(
            [
                _similar_track(
                    "glory box", "portishead", match=0.6, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        "Radiohead",
        "Pyramid Song",
        _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]),
    )
    # Dr. Dog track tags are empty should triggers artist.getTopTags fallback
    _route(
        "track.getTopTags",
        "Dr. Dog",
        "Shadow People",
        _tags_response("Dr. Dog", "Shadow People", []),
    )
    _artist_route(
        "artist.getTopTags",
        "Dr. Dog",
        _artist_tags_response("Dr. Dog", [("indie rock", 60)]),
    )
    # Only one candidate tag call because Glory Box deduplicates
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("alternative", 60)]),
    )

    async with httpx.AsyncClient() as client:
        candidates, dropped = await aggregate(
            LastfmClient(client, API_KEY), [SEED_A, SEED_B]
        )

    assert dropped == []
    assert len(candidates) == 1
    assert candidates[0].summed_similarity == pytest.approx(1.5)


# Fallback explanation
# ---------------------------------------------------------------------------


@respx.mock
async def test_fallback_seed_explanation_populated():
    # if track.getSimilar is empty for a seed, the artist fallback fires and needs to populate explantion
    seed = Track(artist="Dr. Dog", title="Shadow People")

    # track.getSimilar empty -> triggers artist.getSimilar + artist.getTopTracks
    _route("track.getSimilar", "Dr. Dog", "Shadow People", _similar_response([]))
    _artist_route(
        "artist.getSimilar",
        "Dr. Dog",
        _artist_similar_response([("Blitzen Trapper", 0.75)]),
    )
    _artist_route(
        "artist.getTopTracks",
        "Blitzen Trapper",
        _artist_top_tracks_response([("Furr", 1_000_000)]),
    )

    # Seed tags present -> no tag fallback for seed
    _route(
        "track.getTopTags",
        "Dr. Dog",
        "Shadow People",
        _tags_response("Dr. Dog", "Shadow People", [("indie rock", 80)]),
    )

    # Candidate (Blitzen Trapper / Furr) tag lookup
    _route(
        "track.getTopTags",
        "Blitzen Trapper",
        "Furr",
        _tags_response("Blitzen Trapper", "Furr", [("indie rock", 50), ("folk", 30)]),
    )

    async with httpx.AsyncClient() as client:
        candidates, dropped = await aggregate(LastfmClient(client, API_KEY), [seed])

    assert dropped == []
    assert len(candidates) == 1
    furr = candidates[0]
    assert furr.artist == "Blitzen Trapper"
    assert furr.title == "Furr"
    assert furr.matched_tags == ["indie rock"]  # intersects seed tag profile
    assert furr.explanation[0] == "top seed: Dr. Dog/Shadow People"
    assert furr.explanation[1] == "matched tags: indie rock"
    assert any("artist.getSimilar" in note for note in furr.explanation)


@respx.mock
async def test_primary_seed_has_correct_explanation():
    # Candidates from a seed that used only primary routes have explanation=[].
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        "Radiohead",
        "Pyramid Song",
        _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("alternative", 60)]),
    )

    async with httpx.AsyncClient() as client:
        candidates, dropped = await aggregate(LastfmClient(client, API_KEY), [SEED_A])

    assert dropped == []
    # Primary route: no fallback notes, but structured lines are always present
    assert candidates[0].explanation[0] == "top seed: Radiohead/Pyramid Song"
    assert candidates[0].explanation[1] == "matched tags: alternative"
    assert len(candidates[0].explanation) == 2  # no fallback notes appended


# Fallback B — dropped seeds (req 2.07)
# ---------------------------------------------------------------------------


@respx.mock
async def test_fallback_b_seed_dropped_when_both_routes_empty():
    """
    A seed whose track.getSimilar AND artist.getSimilar both return nothing
    must appear in dropped_seeds and contribute zero candidates.
    """
    seed = Track(artist="Zxqvbw", title="Ploknmf")
    seed_key = "Zxqvbw/Ploknmf"

    # Primary track.getSimilar empty -> triggers artist fallback
    _route("track.getSimilar", "Zxqvbw", "Ploknmf", _similar_response([]))
    # Fallback A: artist.getSimilar also empty -> Fallback B fires
    _artist_route("artist.getSimilar", "Zxqvbw", _artist_similar_response([]))

    async with httpx.AsyncClient() as client:
        candidates, dropped = await aggregate(LastfmClient(client, API_KEY), [seed])

    assert dropped == [seed_key]  # confirm seed number dropped
    assert candidates == []  # confirm 0 candidates with zero seeds.


@respx.mock
async def test_fallback_b_mixed_seeds_only_bad_one_dropped():
    # tst one good seed and one nonsense seed, only the nonsense seed is dropped; the good seed still produces.
    good_seed = Track(artist="Radiohead", title="Pyramid Song")
    bad_seed = Track(artist="Zxqvbw", title="Ploknmf")

    # Good seed: primary route succeeds
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        "Radiohead",
        "Pyramid Song",
        _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response("Portishead", "Glory Box", [("alternative", 60)]),
    )

    # Bad seed: both track and artist routes return nothing
    _route(
        "track.getSimilar", "Zxqvbw", "Ploknmf", _similar_response([])
    )  # dummy giberish
    _artist_route("artist.getSimilar", "Zxqvbw", _artist_similar_response([]))

    async with httpx.AsyncClient() as client:
        candidates, dropped = await aggregate(
            LastfmClient(client, API_KEY), [good_seed, bad_seed]
        )

    assert dropped == ["Zxqvbw/Ploknmf"]  # confirm dropped seed
    assert len(candidates) == 1  # confirm only one track (defined above) remains
    assert candidates[0].title == "Glory Box"  # confirm title


# Streaming variant
# ---------------------------------------------------------------------------


@respx.mock
async def test_aggregate_streaming_event_ordering():
    # Two-seed setup matching test_two_seed_overlap
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
                _similar_track(
                    "Teardrop", "Massive Attack", match=0.7, playcount=8_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getSimilar",
        "Dr. Dog",
        "Shadow People",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.6, playcount=5_000_000
                ),
                _similar_track(
                    "Pink Moon", "Nick Drake", match=0.5, playcount=2_000_000
                ),
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
    _route(
        "track.getTopTags",
        "Portishead",
        "Glory Box",
        _tags_response(
            "Portishead", "Glory Box", [("trip-hop", 100), ("alternative", 60)]
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
    _route(
        "track.getTopTags",
        "Nick Drake",
        "Pink Moon",
        _tags_response("Nick Drake", "Pink Moon", [("folk", 80), ("acoustic", 50)]),
    )

    events: list[StageEvent] = []
    final: tuple[list[Candidate], list[str]] | None = None

    async with httpx.AsyncClient() as client:
        async for item in aggregate_streaming(
            LastfmClient(client, API_KEY), [SEED_A, SEED_B]
        ):
            if isinstance(item, StageEvent):
                events.append(item)
            else:
                final = item

    # Two similarity events (one per seed) then one tags event; in that order
    assert len(events) == 3
    sim_events = [e for e in events if e.stage == "similarity"]
    tags_events = [e for e in events if e.stage == "tags"]
    assert len(sim_events) == 2
    assert len(tags_events) == 1

    # similarity events count up correctly
    assert sim_events[0].seeds_done == 1
    assert sim_events[0].seeds_total == 2
    assert sim_events[1].seeds_done == 2
    assert sim_events[1].seeds_total == 2

    # tags event shows 3 unique candidates)
    assert tags_events[0].candidates == 3

    # tags event arrives after both similarity events
    tags_index = events.index(tags_events[0])
    assert all(events.index(e) < tags_index for e in sim_events)

    # final tuple is a well-formed result
    assert final is not None
    result_candidates, dropped = final
    assert dropped == []
    assert len(result_candidates) == 3


# build_seed_profile
# ---------------------------------------------------------------------------


@respx.mock
async def test_build_seed_profile_shared_tag_has_seed_count_two() -> None:
    # Two seeds sharing "alternative"; each also contributes one unique tag.
    # Shared tag must sort first (seed_count=2); unique tags follow alphabetically.
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getSimilar",
        "Dr. Dog",
        "Shadow People",
        _similar_response(
            [
                _similar_track(
                    "Pink Moon", "Nick Drake", match=0.5, playcount=2_000_000
                ),
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

    async with httpx.AsyncClient() as client:
        profile = await build_seed_profile(
            LastfmClient(client, API_KEY), [SEED_A, SEED_B]
        )

    assert isinstance(profile, SeedProfile)
    assert profile.total_seeds == 2
    assert profile.dropped_seeds == []

    tag_map = {t.name: t.seed_count for t in profile.tags}
    assert tag_map["alternative"] == 2
    assert tag_map["art rock"] == 1
    assert tag_map["folk"] == 1

    # sort order: seed_count descending
    assert profile.tags[0] == TagCount(name="alternative", seed_count=2)
    assert profile.tags[1] == TagCount(name="art rock", seed_count=1)
    assert profile.tags[2] == TagCount(name="folk", seed_count=1)


@respx.mock
async def test_build_seed_profile_fallback_b_seed_dropped() -> None:
    # Bad seed has both track.getSimilar and artist.getSimilar return empty.
    good_seed = Track(artist="Radiohead", title="Pyramid Song")
    bad_seed = Track(artist="Zxqvbw", title="Ploknmf")

    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        "Radiohead",
        "Pyramid Song",
        _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]),
    )

    _route("track.getSimilar", "Zxqvbw", "Ploknmf", _similar_response([]))
    _artist_route("artist.getSimilar", "Zxqvbw", _artist_similar_response([]))

    async with httpx.AsyncClient() as client:
        profile = await build_seed_profile(
            LastfmClient(client, API_KEY), [good_seed, bad_seed]
        )

    assert profile.dropped_seeds == ["Zxqvbw/Ploknmf"]
    assert profile.total_seeds == 2  # original input, not post-drop count
    assert len(profile.tags) == 1
    assert profile.tags[0] == TagCount(name="alternative", seed_count=1)


@respx.mock
async def test_build_seed_profile_all_succeed_dropped_seeds_empty() -> None:
    # When every seed resolves successfully, dropped_seeds is empty; length matches must be correct
    _route(
        "track.getSimilar",
        "Radiohead",
        "Pyramid Song",
        _similar_response(
            [
                _similar_track(
                    "Glory Box", "Portishead", match=0.9, playcount=5_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getSimilar",
        "Dr. Dog",
        "Shadow People",
        _similar_response(
            [
                _similar_track(
                    "Pink Moon", "Nick Drake", match=0.5, playcount=2_000_000
                ),
            ]
        ),
    )
    _route(
        "track.getTopTags",
        "Radiohead",
        "Pyramid Song",
        _tags_response("Radiohead", "Pyramid Song", [("alternative", 100)]),
    )
    _route(
        "track.getTopTags",
        "Dr. Dog",
        "Shadow People",
        _tags_response("Dr. Dog", "Shadow People", [("indie rock", 80)]),
    )

    async with httpx.AsyncClient() as client:
        profile = await build_seed_profile(
            LastfmClient(client, API_KEY), [SEED_A, SEED_B]
        )

    #confirm no dropped seeds and only 2 seeds provided.
    assert profile.dropped_seeds == []
    assert profile.total_seeds == 2
