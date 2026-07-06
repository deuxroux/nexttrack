import pytest
from pydantic import ValidationError

from nexttrack.models import Candidate, RecommendationParams, RecommendationResult, Track


def test_track_shape():
    t = Track(artist="Radiohead", title="Pyramid Song", mbid=None)
    assert t.artist == "Radiohead"
    assert t.title == "Pyramid Song"
    assert t.mbid is None


#confirm data type matches model with simple artist check. manually verified response.
def test_recommendation_result_shape():
    c = Candidate(
        artist="Portishead",
        title="Glory Box",
        summed_similarity=0.9,
        tag_overlap=0.5,
        novelty_bonus=0.3,
        final_score=0.8,
        contributing_seeds=["Radiohead/Pyramid Song"],
        matched_tags=["trip-hop"],
    )
    params = RecommendationParams(novelty=50, genre_lock=[], artist_diversity=3, length=10)
    r = RecommendationResult(candidates=[c], dropped_seeds=[], params=params)
    assert len(r.candidates) == 1
    assert r.candidates[0].artist == "Portishead"


def test_recommendation_params_defaults():
    # genre_lock defaults to []; length defaults to 10
    p = RecommendationParams(novelty=50, artist_diversity=5, length=10)
    assert p.genre_lock == []
    assert p.length == 10


@pytest.mark.parametrize("field,value", [
    ("artist_diversity", 0),   # below ge=1
    ("artist_diversity", 11),  # above le=10
    ("length", 4),             # below ge=5
    ("length", 51),            # above le=50
    ("novelty", -1),           # below ge=0
    ("novelty", 101),          # above le=100
])
def test_recommendation_params_rejects_out_of_range(field: str, value: int) -> None:
    valid: dict = dict(novelty=50, artist_diversity=5, length=10)
    with pytest.raises(ValidationError):
        RecommendationParams(**{**valid, field: value})
