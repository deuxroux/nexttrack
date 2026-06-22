import httpx
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from nexttrack.config import Settings, get_settings
from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import RecommendationParams, RecommendationResult, Track
from nexttrack.pipeline.aggregate import aggregate
from nexttrack.pipeline.rank import rank

app = FastAPI(title="NextTrack", version="0.1.0")


class RecommendRequest(BaseModel):
    seeds: list[Track]
    params: RecommendationParams


#TODO put status checks in for spotify, last.fm, etc. for internal debugging.
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/recommend", response_model=RecommendationResult)
async def recommend(
    request: RecommendRequest,
    settings: Settings = Depends(get_settings),
) -> RecommendationResult:
    async with httpx.AsyncClient() as client:
        lf = LastfmClient(client, settings.lastfm_api_key)
        candidates = await aggregate(lf, request.seeds)
    return rank(candidates, request.params)
