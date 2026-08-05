import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis_asyncio
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from nexttrack.cache import LastfmCache
from nexttrack.config import Settings, get_settings
from nexttrack.export.csv import render_csv
from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import (
    Candidate,
    RecommendationParams,
    RecommendationResult,
    SeedProfile,
    StageEvent,
    Track,
    TrackHit,
)
from nexttrack.observability.timing import StageTimings
from nexttrack.pipeline.aggregate import aggregate_streaming, build_seed_profile
from nexttrack.pipeline.rank import rank
from nexttrack.spotify.client import SpotifyClient, SpotifyUnavailable
from nexttrack.spotify.url import parse_track_id

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    http_client = httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=httpx.Timeout(30),
    )
    redis_client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
    cache = LastfmCache(redis_client, ttl=settings.cache_ttl_lastfm_seconds)
    spotify_cache = LastfmCache(redis_client, ttl=settings.cache_ttl_spotify_seconds)
    spotify = SpotifyClient(
        http_client,
        settings.spotify_client_id,
        settings.spotify_client_secret,
        spotify_cache,
    )
    app.state.http_client = http_client
    app.state.redis = redis_client
    app.state.cache = cache
    app.state.spotify_cache = spotify_cache
    app.state.spotify = spotify
    app.state.stage_timings = StageTimings()
    try:
        yield
    finally:
        await http_client.aclose()
        await redis_client.aclose()


app = FastAPI(title="NextTrack", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Read directly from env so importing this module never triggers Settings
    # validation (which requires LASTFM_API_KEY) before fixtures can set it.
    allow_origins=[
        o.strip()
        for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(
            ","
        )
        if o.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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


class ResolveSpotifyRequest(BaseModel):
    url: str


class ErrorBody(BaseModel):
    error: str
    detail: str


class SeedErrorBody(ErrorBody):
    dropped_seeds: list[str]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search", response_model=list[TrackHit])
async def search(
    req: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
    settings: Settings = Depends(get_settings),
) -> list[TrackHit]:
    if len(q.strip()) < 2:
        return []
    lf = LastfmClient(
        req.app.state.http_client, settings.lastfm_api_key, cache=req.app.state.cache
    )
    hits = await lf.search_tracks(q, limit)
    return [TrackHit(**h) for h in hits]


@app.get("/metrics")
async def metrics(req: Request) -> dict:
    cache: LastfmCache = req.app.state.cache
    stage_timings: StageTimings = req.app.state.stage_timings
    return {
        "cache": {
            "hits": cache.hits,
            "misses": cache.misses,
            "hit_rate": cache.hit_rate,
        },
        "timing": stage_timings.summary(),
    }


@app.post("/seed-profile", response_model=SeedProfile)
async def seed_profile(
    body: SeedProfileRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> SeedProfile:
    lf = LastfmClient(
        req.app.state.http_client, settings.lastfm_api_key, cache=req.app.state.cache
    )
    return await build_seed_profile(lf, body.seeds)


@app.post(
    "/recommend",
    response_model=RecommendationResult,
    responses={
        200: {
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        422: {
            "model": SeedErrorBody,
            "description": "No successful seeds or no recommendations survived ranking",
        },
        502: {
            "model": ErrorBody,
            "description": "Last.fm unavailable",
        },
    },
)
async def recommend(
    body: RecommendRequest,
    req: Request,
    output_format: str = Query("json", alias="format"),
    settings: Settings = Depends(get_settings),
) -> RecommendationResult | StreamingResponse | JSONResponse:
    lf = LastfmClient(
        req.app.state.http_client, settings.lastfm_api_key, cache=req.app.state.cache
    )
    stage_timings: StageTimings = req.app.state.stage_timings

    candidates: list[Candidate] = []
    dropped: list[str] = []
    per_stage: dict[str, float] = {}

    try:
        async for item in aggregate_streaming(lf, body.seeds):
            if isinstance(item, StageEvent):
                stage_timings.record(item.stage, item.elapsed_ms)
                per_stage[item.stage] = per_stage.get(item.stage, 0.0) + item.elapsed_ms
            else:
                candidates, dropped = item
    except httpx.HTTPError as exc:
        # covers ConnectError, TimeoutException, and 5xx from Last.fm itself
        logger.warning("lastfm outage during /recommend: %s", exc)
        return JSONResponse(
            status_code=502,
            content={
                "error": "lastfm_unavailable",
                "detail": "Last.fm is not responding. Try again shortly.",
            },
        )

    # if zero successful seeds: every seed hit a dead end
    if len(dropped) == len(body.seeds):
        return JSONResponse(
            status_code=422,
            content={
                "error": "no_successful_seeds",
                "detail": "None of the provided seed tracks could be resolved.",
                "dropped_seeds": dropped,
            },
        )

    result = rank(candidates, dropped, body.params)

    total_ms = sum(per_stage.values())
    logger.info("recommend complete stage_ms=%s total_ms=%.1f", per_stage, total_ms)

    # if zero successful recommendations after ranking/filtering
    if not result.candidates:
        return JSONResponse(
            status_code=422,
            content={
                "error": "no_recommendations",
                "detail": (
                    "No candidates survived ranking and filtering. "
                    "Try loosening genre_lock or novelty settings."
                ),
                "dropped_seeds": dropped,
            },
        )

    if output_format == "csv":
        filename, csv_body = render_csv(
            result, body.seeds, body.params, datetime.now(timezone.utc)
        )
        return StreamingResponse(
            iter([csv_body]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return result


@app.post("/recommend/stream")
async def recommend_stream(
    body: RecommendRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    stage_timings: StageTimings = req.app.state.stage_timings

    async def _stream():
        candidates: list[Candidate] = []
        dropped: list[str] = []
        lf = LastfmClient(
            req.app.state.http_client,
            settings.lastfm_api_key,
            cache=req.app.state.cache,
        )
        per_stage: dict[str, float] = {}

        async for item in aggregate_streaming(lf, body.seeds):
            if isinstance(item, StageEvent):
                stage_timings.record(item.stage, item.elapsed_ms)
                per_stage[item.stage] = per_stage.get(item.stage, 0.0) + item.elapsed_ms
                yield {"event": item.stage, "data": item.model_dump_json()}
                if await req.is_disconnected():
                    return
            else:
                candidates, dropped = item

        result = rank(candidates, dropped, body.params)

        total_ms = sum(per_stage.values())
        logger.info(
            "recommend/stream complete stage_ms=%s total_ms=%.1f", per_stage, total_ms
        )

        yield {"event": "result", "data": result.model_dump_json()}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(_stream())


@app.post("/resolve-spotify-url")
async def resolve_spotify_url(
    body: ResolveSpotifyRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        return JSONResponse(
            status_code=503,
            content={
                "error": "spotify_unavailable",
                "detail": "Spotify credentials not configured",
            },
        )

    track_id = parse_track_id(body.url)
    if track_id is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_url",
                "detail": "Could not extract a Spotify track ID from the provided URL",
            },
        )

    spotify: SpotifyClient = req.app.state.spotify

    try:
        track = await spotify.get_track(track_id)
    except SpotifyUnavailable as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "spotify_unavailable", "detail": str(exc)},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "track_not_found",
                    "detail": f"Spotify track not found: {track_id}",
                },
            )
        return JSONResponse(
            status_code=502,
            content={"error": "spotify_unavailable", "detail": str(exc)},
        )

    artist = track["artists"][0]["name"]
    title = track["name"]
    return JSONResponse(content={"artist": artist, "title": title})
