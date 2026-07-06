from pydantic import BaseModel, Field

#data representations in this file

class Track(BaseModel):
    artist: str
    title: str
    mbid: str | None = None


class RecommendationParams(BaseModel):
    novelty: int = Field(..., ge=0, le=100)
    genre_lock: list[str] = Field(default_factory=list)
    artist_diversity: int = Field(..., ge=1, le=10)
    length: int = Field(10, ge=5, le=50)


class Candidate(BaseModel):
    artist: str
    title: str
    summed_similarity: float
    tag_overlap: float
    novelty_bonus: float
    final_score: float
    contributing_seeds: list[str]
    matched_tags: list[str]
    explanation: list[str] = []  # non-empty if any contributing seed used a fallback route


class RecommendationResult(BaseModel):
    candidates: list[Candidate]
    dropped_seeds: list[str]
    params: RecommendationParams #nested details from params that contributed.
