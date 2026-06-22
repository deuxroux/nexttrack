from nexttrack.models import Candidate, RecommendationParams, RecommendationResult, Track


def test_track_shape():
    t = Track(artist="Radiohead", title="Pyramid Song", mbid=None)
    assert t.artist == "Radiohead"
    assert t.title == "Pyramid Song"
    assert t.mbid is None


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
