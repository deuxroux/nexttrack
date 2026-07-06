import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexttrack.config import Settings, get_settings
from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import RecommendationParams, RecommendationResult, Track
from nexttrack.pipeline.aggregate import aggregate
from nexttrack.pipeline.rank import rank

#create fast API for debugging and viewing. will compliment later UI implementation
app = FastAPI(title="NextTrack", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = []
    for err in exc.errors():
        loc = " -> ".join(str(p) for p in err["loc"] if p != "body")
        messages.append(f"{loc}: {err['msg']}")
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request parameters", "details": messages},
    )


class RecommendRequest(BaseModel):
    seeds: list[Track]
    params: RecommendationParams


#TODO put status checks in for spotify, last.fm, etc. for internal debugging.
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


#/recommend route
@app.post("/recommend", response_model=RecommendationResult)
async def recommend(
    request: RecommendRequest,
    settings: Settings = Depends(get_settings),
) -> RecommendationResult:
    async with httpx.AsyncClient() as client:
        lf = LastfmClient(client, settings.lastfm_api_key)
        candidates, dropped = await aggregate(lf, request.seeds)
    return rank(candidates, dropped, request.params)
