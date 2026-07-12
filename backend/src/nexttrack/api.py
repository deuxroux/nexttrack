from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis_asyncio
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from nexttrack.cache import LastfmCache
from nexttrack.config import Settings, get_settings
from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import Candidate, RecommendationParams, RecommendationResult, SeedProfile, StageEvent, Track
from nexttrack.pipeline.aggregate import aggregate, aggregate_streaming, build_seed_profile
from nexttrack.pipeline.rank import rank

#lifespan manager using ASGI
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http_client = httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=httpx.Timeout(30),
    )
    redis_client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
    cache = LastfmCache(redis_client, ttl=settings.cache_ttl_lastfm_seconds)
    app.state.http_client = http_client
    app.state.redis = redis_client
    app.state.cache = cache
    try:
        yield
    finally:
        await http_client.aclose()
        await redis_client.aclose()


#create fast API for debugging and viewing. will compliment later UI implementation
app = FastAPI(title="NextTrack", version="0.1.0", lifespan=lifespan)


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


class SeedProfileRequest(BaseModel):
    seeds: list[Track] = Field(..., min_length=1, max_length=50)


#TODO put status checks in for spotify, last.fm, etc. for internal debugging.
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics(req: Request) -> dict:
    cache: LastfmCache = req.app.state.cache
    return {
        "cache": {
            "enabled": True,
            "hits": cache.hits,
            "misses": cache.misses,
            "hit_rate": cache.hit_rate,
        }
    }


@app.post("/seed-profile", response_model=SeedProfile)
async def seed_profile(
    body: SeedProfileRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> SeedProfile:
    lf = LastfmClient(req.app.state.http_client, settings.lastfm_api_key, cache=req.app.state.cache)
    return await build_seed_profile(lf, body.seeds)


#/recommend route
@app.post("/recommend", response_model=RecommendationResult)
async def recommend(
    body: RecommendRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> RecommendationResult:
    lf = LastfmClient(req.app.state.http_client, settings.lastfm_api_key, cache=req.app.state.cache)
    candidates, dropped = await aggregate(lf, body.seeds)
    return rank(candidates, dropped, body.params)


@app.post("/recommend/stream")
async def recommend_stream(
    body: RecommendRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    async def _stream():
        candidates: list[Candidate] = []
        dropped: list[str] = []
        lf = LastfmClient(req.app.state.http_client, settings.lastfm_api_key, cache=req.app.state.cache)
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
