from nexttrack.models import Candidate, RecommendationParams, RecommendationResult
from nexttrack.pipeline.rank import rank


def test_rank_returns_recommendation_result():
    c = Candidate(
        artist="Portishead",
        title="Glory Box",
        summed_similarity=0.9,
        tag_overlap=0.5,
        novelty_bonus=0.3,
        final_score=0.0,
        contributing_seeds=["Radiohead/Pyramid Song"],
        matched_tags=["trip-hop"],
    )
    params = RecommendationParams(novelty=50, genre_lock=[], artist_diversity=3, length=10)
    result = rank([c], params)
    assert isinstance(result, RecommendationResult)
