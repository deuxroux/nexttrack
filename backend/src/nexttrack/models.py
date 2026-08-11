from pydantic import BaseModel, Field

# data structure shapes and reps across the app found here.


class Track(BaseModel):
    artist: str
    title: str


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
    explanation: list[
        str
    ] = []


class TrackHit(BaseModel):
    artist: str
    title: str
    image: str | None = None


class StageEvent(BaseModel):
    stage: str
    seeds_done: int | None = None
    seeds_total: int | None = None
    candidates: int | None = None
    elapsed_ms: float = 0.0


class TagCount(BaseModel):
    name: str
    seed_count: int


class SeedProfile(BaseModel):
    tags: list[TagCount]  # sorted desc by seed_count, ties broken alpha by name
    dropped_seeds: list[str]
    total_seeds: int  # includes dropped seeds


class RecommendationResult(BaseModel):
    candidates: list[Candidate]
    dropped_seeds: list[str]
    params: RecommendationParams  # nested details from params that contributed
    pool_exhausted: bool = False  # flip true if fewer candidates existed than params.length after filtering
