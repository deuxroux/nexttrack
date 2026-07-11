import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from nexttrack.config import Settings, get_settings
from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import Candidate, RecommendationParams, RecommendationResult, StageEvent, Track
from nexttrack.pipeline.aggregate import aggregate, aggregate_streaming
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
    seeds: list[Track] = Field(..., min_length=1, max_length=50)
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


@app.post("/recommend/stream")
async def recommend_stream(
    body: RecommendRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    async def _stream():
        candidates: list[Candidate] = []
        dropped: list[str] = []
        async with httpx.AsyncClient() as client:
            lf = LastfmClient(client, settings.lastfm_api_key)
            async for item in aggregate_streaming(lf, body.seeds):
                if isinstance(item, StageEvent):
                    yield {"event": item.stage, "data": item.model_dump_json()}
                    if await req.is_disconnected():
                        return
                else:
                    candidates, dropped = item
        result = rank(candidates, dropped, body.params)
        yield {"event": "result", "data": result.model_dump_json()}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(_stream())
