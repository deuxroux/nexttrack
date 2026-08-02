import asyncio
from collections import deque
from dataclasses import dataclass
from nexttrack.cache import LastfmCache

import time
import httpx

BASE_URL = "https://ws.audioscrobbler.com/2.0/"

# hard code defaults
_ARTIST_SIMILAR_LIMIT = 5  # similar artists limit; if track.getSimilar is empty
_ARTIST_TRACKS_LIMIT = 10  # top tracks per similar artist in fallback
_RATE_LIMIT = 5  # max outbound Last.fm requests per second


# aggregation specific models only. others in the models.py file
@dataclass
class SimilarTracksResult:
    tracks: list[dict]
    fallback_used: bool = False
    fallback_note: str = ""


@dataclass
class TopTagsResult:
    tags: list[dict]
    fallback_used: bool = False
    fallback_note: str = ""


class LastfmClient:
    # reminder: api key is not exposed. requires an individual's key in a separate env file.
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        cache: LastfmCache | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._cache = cache
        self._request_times: deque[float] = deque(maxlen=_RATE_LIMIT)

    async def _fetch(self, **params) -> dict:
        # Enforce <=_RATE_LIMIT requests/second via sliding-window throttle
        if len(self._request_times) == _RATE_LIMIT:
            gap = 1.0 - (time.monotonic() - self._request_times[0])
            if gap > 0:
                await asyncio.sleep(gap)
        self._request_times.append(time.monotonic())

        resp = await self._client.get(
            BASE_URL,
            params={
                "api_key": self._api_key,
                "format": "json",
                "autocorrect": "1",
                **params,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # public fns aggregate track-level meta data routes with fallbacks

    async def get_similar_tracks(self, artist: str, title: str) -> SimilarTracksResult:
        if self._cache is not None:
            cached = await self._cache.get(LastfmCache.key_similar(artist, title))
            if cached is not None:
                return SimilarTracksResult(
                    tracks=cached["tracks"],
                    fallback_used=cached.get("fallback_used", False),
                    fallback_note=cached.get("fallback_note", ""),
                )

        data = await self._fetch(
            method="track.getSimilar", artist=artist, track=title, limit=50
        )
        raw = data.get("similartracks", {}).get("track", [])
        if raw:
            parsed = self._parse_similar_tracks(raw)
            if self._cache is not None:
                await self._cache.set(
                    LastfmCache.key_similar(artist, title), {"tracks": parsed}
                )
            return SimilarTracksResult(tracks=parsed)

        result = await self._fallback_artist_similar(artist, title)
        if self._cache is not None:
            await self._cache.set(
                LastfmCache.key_similar(artist, title),
                {
                    "tracks": result.tracks,
                    "fallback_used": True,
                    "fallback_note": result.fallback_note,
                },
            )
        return result

    async def get_top_tags(self, artist: str, title: str) -> TopTagsResult:
        if self._cache is not None:
            cached = await self._cache.get(LastfmCache.key_toptags(artist, title))
            if cached is not None:
                return TopTagsResult(
                    tags=cached["tags"],
                    fallback_used=cached.get("fallback_used", False),
                    fallback_note=cached.get("fallback_note", ""),
                )

        data = await self._fetch(method="track.getTopTags", artist=artist, track=title)
        raw = data.get("toptags", {}).get("tag", [])
        if raw:
            parsed = self._parse_tags(raw)
            if self._cache is not None:
                await self._cache.set(
                    LastfmCache.key_toptags(artist, title), {"tags": parsed}
                )
            return TopTagsResult(tags=parsed)

        result = await self._fallback_artist_top_tags(artist, title)
        if self._cache is not None:
            await self._cache.set(
                LastfmCache.key_toptags(artist, title),
                {
                    "tags": result.tags,
                    "fallback_used": True,
                    "fallback_note": result.fallback_note,
                },
            )
        return result

    async def search_tracks(self, query: str, limit: int = 8) -> list[dict]:
        if self._cache is not None:
            cached = await self._cache.get(LastfmCache.key_search(query, limit))
            if cached is not None:
                return cached["hits"]

        data = await self._fetch(method="track.search", track=query, limit=limit)
        raw = data.get("results", {}).get("trackmatches", {}).get("track", [])
        if isinstance(raw, dict):
            raw = [raw]
        elif not isinstance(raw, list):
            raw = []

        hits = [self._parse_search_track(t) for t in raw]

        if self._cache is not None:
            await self._cache.set(LastfmCache.key_search(query, limit), {"hits": hits})

        return hits

    # private data parsers. all private funtions with _

    @staticmethod
    def _parse_similar_tracks(raw: list[dict]) -> list[dict]:
        return [
            {
                "name": t["name"],
                "artist": t["artist"]["name"],
                "match": float(t["match"]),
                "playcount": int(t["playcount"]),
            }
            for t in raw
        ]

    @staticmethod
    def _parse_tags(raw: list[dict]) -> list[dict]:
        return [{"name": t["name"], "count": int(t["count"])} for t in raw]

    @staticmethod
    def _parse_search_track(t: dict) -> dict:
        images = {
            img["size"]: img["#text"] for img in t.get("image", []) if "#text" in img
        }
        image_url: str | None = None
        for size in ("extralarge", "large", "medium", "small"):
            url = images.get(size, "")
            if url:
                image_url = url
                break
        return {"artist": t["artist"], "title": t["name"], "image": image_url}

    #  artist.getSimilar + artist.getTopTracks fallback

    async def _fallback_artist_similar(
        self, artist: str, title: str
    ) -> SimilarTracksResult:
        data = await self._fetch(
            method="artist.getSimilar", artist=artist, limit=_ARTIST_SIMILAR_LIMIT
        )
        similar = data.get("similarartists", {}).get("artist", [])
        tracks: list[dict] = []
        for sa in similar:
            sa_match = float(sa["match"])
            for t in await self._artist_top_tracks(sa["name"]):
                tracks.append(
                    {
                        "name": t["name"],
                        "artist": sa["name"],
                        "match": sa_match,
                        "playcount": t["playcount"],
                    }
                )
        return SimilarTracksResult(
            tracks=tracks,
            fallback_used=True,
            fallback_note=(
                f"track.getSimilar empty for {artist!r}/{title!r}; used artist.getSimilar"
            ),
        )

    async def _artist_top_tracks(self, artist: str) -> list[dict]:
        data = await self._fetch(
            method="artist.getTopTracks", artist=artist, limit=_ARTIST_TRACKS_LIMIT
        )
        raw = data.get("toptracks", {}).get("track", [])
        return [{"name": t["name"], "playcount": int(t["playcount"])} for t in raw]

    #  artist.getTopTags fallback

    async def _fallback_artist_top_tags(self, artist: str, title: str) -> TopTagsResult:
        data = await self._fetch(method="artist.getTopTags", artist=artist)
        raw = data.get("toptags", {}).get("tag", [])
        return TopTagsResult(
            tags=self._parse_tags(raw),
            fallback_used=True,
            fallback_note=(
                f"track.getTopTags empty for {artist!r}/{title!r}; used artist.getTopTags"
            ),
        )
