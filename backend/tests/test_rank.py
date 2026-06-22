"""Golden tests for pipeline/rank.py — ordering, filters, diversity, truncation."""
import pytest

from nexttrack.models import Candidate, RecommendationParams
from nexttrack.pipeline.rank import W_SIM, W_TAG, rank


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cand(
    artist: str,
    title: str,
    *,
    sim: float,
    novelty_bonus: float,
    tag_overlap: float = 0.0,
    tags: list[str] | None = None,
) -> Candidate:
    return Candidate(
        artist=artist,
        title=title,
        summed_similarity=sim,
        tag_overlap=tag_overlap,
        novelty_bonus=novelty_bonus,
        final_score=0.0,
        contributing_seeds=["seed/track"],
        matched_tags=tags or [],
    )


def _params(**kw) -> RecommendationParams:
    defaults: dict = dict(novelty=50, genre_lock=[], artist_diversity=0, length=50)
    return RecommendationParams(**(defaults | kw))


# ---------------------------------------------------------------------------
# Ordering — novelty sweep
# ---------------------------------------------------------------------------

def test_novelty_0_prefers_similarity():
    """With novelty=0 the novelty_bonus term is zero; highest sim wins."""
    high_sim = _cand("A", "High Sim", sim=0.9, novelty_bonus=0.1)
    high_nov = _cand("B", "High Nov", sim=0.5, novelty_bonus=0.9)
    result = rank([high_nov, high_sim], _params(novelty=0))
    assert result.candidates[0].artist == "A"


def test_novelty_100_flips_order():
    """With novelty=100 the novelty_bonus term dominates; obscure track rises."""
    high_sim = _cand("A", "High Sim", sim=0.9, novelty_bonus=0.1)
    high_nov = _cand("B", "High Nov", sim=0.5, novelty_bonus=0.9)
    result = rank([high_sim, high_nov], _params(novelty=100))
    assert result.candidates[0].artist == "B"


def test_score_formula():
    """final_score matches the documented formula with the exported weights."""
    c = _cand("A", "T", sim=0.8, novelty_bonus=0.6, tag_overlap=0.4)
    novelty = 60
    result = rank([c], _params(novelty=novelty))
    expected = W_SIM * 0.8 + W_TAG * 0.4 + (novelty / 100) * 0.6
    assert result.candidates[0].final_score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Genre lock (req 3.17)
# ---------------------------------------------------------------------------

def test_genre_lock_excludes_non_matching():
    rock = _cand("A", "Rock Track", sim=0.9, novelty_bonus=0.5, tags=["alternative", "rock"])
    jazz = _cand("B", "Jazz Track", sim=0.8, novelty_bonus=0.5, tags=["jazz"])
    result = rank([rock, jazz], _params(genre_lock=["rock"]))
    assert len(result.candidates) == 1
    assert result.candidates[0].artist == "A"


def test_genre_lock_empty_passes_all():
    a = _cand("A", "A", sim=0.9, novelty_bonus=0.5, tags=[])
    b = _cand("B", "B", sim=0.8, novelty_bonus=0.5, tags=["rock"])
    result = rank([a, b], _params(genre_lock=[]))
    assert len(result.candidates) == 2


def test_genre_lock_case_insensitive():
    c = _cand("A", "A", sim=0.9, novelty_bonus=0.5, tags=["Alternative"])
    result = rank([c], _params(genre_lock=["alternative"]))
    assert len(result.candidates) == 1


def test_genre_lock_no_match_returns_empty():
    c = _cand("A", "A", sim=0.9, novelty_bonus=0.5, tags=["classical"])
    result = rank([c], _params(genre_lock=["metal"]))
    assert result.candidates == []


# ---------------------------------------------------------------------------
# Artist diversity (req 3.18)
# ---------------------------------------------------------------------------

def test_artist_diversity_caps_per_artist():
    # Four Radiohead tracks; cap at 2
    rh = [_cand("Radiohead", f"T{i}", sim=0.9 - i * 0.1, novelty_bonus=0.0) for i in range(4)]
    result = rank(rh, _params(artist_diversity=2, length=10))
    radiohead = [c for c in result.candidates if c.artist == "Radiohead"]
    assert len(radiohead) == 2


def test_artist_diversity_keeps_highest_scoring():
    # First two (highest score with novelty=0) should survive
    rh = [_cand("Radiohead", f"T{i}", sim=0.9 - i * 0.1, novelty_bonus=0.0) for i in range(4)]
    result = rank(rh, _params(novelty=0, artist_diversity=2, length=10))
    titles = [c.title for c in result.candidates]
    assert titles == ["T0", "T1"]


def test_artist_diversity_0_means_no_cap():
    rh = [_cand("Radiohead", f"T{i}", sim=0.9, novelty_bonus=0.0) for i in range(5)]
    result = rank(rh, _params(artist_diversity=0, length=10))
    assert len(result.candidates) == 5


def test_artist_diversity_interleaves_artists():
    # Portishead track should survive even though Radiohead ranks higher overall
    rh = [_cand("Radiohead", f"T{i}", sim=0.9 - i * 0.05, novelty_bonus=0.0) for i in range(3)]
    pt = _cand("Portishead", "Glory Box", sim=0.5, novelty_bonus=0.0)
    result = rank(rh + [pt], _params(novelty=0, artist_diversity=1, length=10))
    artists = {c.artist for c in result.candidates}
    assert "Portishead" in artists


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

def test_length_truncates():
    cands = [_cand("A", f"T{i}", sim=float(i), novelty_bonus=0.0) for i in range(10)]
    result = rank(cands, _params(length=3))
    assert len(result.candidates) == 3


def test_length_larger_than_pool_returns_all():
    cands = [_cand("A", f"T{i}", sim=0.5, novelty_bonus=0.0) for i in range(3)]
    result = rank(cands, _params(length=20))
    assert len(result.candidates) == 3


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

def test_params_preserved_in_result():
    params = _params(novelty=42, genre_lock=["rock"], length=5)
    result = rank([], params)
    assert result.params == params


def test_dropped_seeds_is_empty_list():
    result = rank([], _params())
    assert result.dropped_seeds == []


def test_final_score_assigned_on_returned_candidates():
    c = _cand("A", "T", sim=1.0, novelty_bonus=0.0, tag_overlap=0.0)
    result = rank([c], _params(novelty=0))
    assert result.candidates[0].final_score == pytest.approx(W_SIM * 1.0)
