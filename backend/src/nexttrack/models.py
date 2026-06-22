from pydantic import BaseModel, Field


class Track(BaseModel):
    artist: str
    title: str
    mbid: str | None = None


class RecommendationParams(BaseModel):
    novelty: int = Field(..., ge=0, le=100)
    genre_lock: list[str]
    artist_diversity: int
    length: int


class Candidate(BaseModel):
    artist: str
    title: str
    summed_similarity: float
    tag_overlap: float
    novelty_bonus: float
    final_score: float
    contributing_seeds: list[str]
    matched_tags: list[str]
    explanation: list[str] = []  # non-empty when any contributing seed used a fallback route


class RecommendationResult(BaseModel):
    candidates: list[Candidate]
    dropped_seeds: list[str]
    params: RecommendationParams
