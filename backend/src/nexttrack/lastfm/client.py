import asyncio
from collections import deque
from dataclasses import dataclass
import time

import httpx

BASE_URL = "https://ws.audioscrobbler.com/2.0/"

_ARTIST_SIMILAR_LIMIT = 5   # similar artists to fetch when track.getSimilar is empty
_ARTIST_TRACKS_LIMIT = 10   # top tracks per similar artist in fallback
_RATE_LIMIT = 5             # max outbound Last.fm requests per second


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
    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key
        # Sliding window: tracks timestamps of the last _RATE_LIMIT requests
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
            params={"api_key": self._api_key, "format": "json", "autocorrect": "1", **params},
        )
        resp.raise_for_status()
        return resp.json()

    # ---- public: track-level routes with artist fallback ----

    async def get_similar_tracks(self, artist: str, title: str) -> SimilarTracksResult:
        """track.getSimilar; falls back to artist.getSimilar + artist.getTopTracks if empty."""
        data = await self._fetch(method="track.getSimilar", artist=artist, track=title, limit=50)
        raw = data.get("similartracks", {}).get("track", [])
        if raw:
            return SimilarTracksResult(tracks=self._parse_similar_tracks(raw))
        return await self._fallback_artist_similar(artist, title)

    async def get_top_tags(self, artist: str, title: str) -> TopTagsResult:
        """track.getTopTags; falls back to artist.getTopTags if empty."""
        data = await self._fetch(method="track.getTopTags", artist=artist, track=title)
        raw = data.get("toptags", {}).get("tag", [])
        if raw:
            return TopTagsResult(tags=self._parse_tags(raw))
        return await self._fallback_artist_top_tags(artist, title)

    # ---- private: parsers ----

    @staticmethod
    def _parse_similar_tracks(raw: list[dict]) -> list[dict]:
        return [
            {
                "name": t["name"],
                "artist": t["artist"]["name"],
                "match": float(t["match"]),
                "playcount": int(t["playcount"]),
                "mbid": t.get("mbid") or None,
            }
            for t in raw
        ]

    @staticmethod
    def _parse_tags(raw: list[dict]) -> list[dict]:
        return [{"name": t["name"], "count": int(t["count"])} for t in raw]

    # ---- private: artist.getSimilar + artist.getTopTracks fallback ----

    async def _fallback_artist_similar(self, artist: str, title: str) -> SimilarTracksResult:
        data = await self._fetch(
            method="artist.getSimilar", artist=artist, limit=_ARTIST_SIMILAR_LIMIT
        )
        similar = data.get("similarartists", {}).get("artist", [])
        tracks: list[dict] = []
        for sa in similar:
            sa_match = float(sa["match"])
            for t in await self._artist_top_tracks(sa["name"]):
                tracks.append({
                    "name": t["name"],
                    "artist": sa["name"],
                    "match": sa_match,
                    "playcount": t["playcount"],
                    "mbid": t["mbid"],
                })
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
        return [
            {"name": t["name"], "playcount": int(t["playcount"]), "mbid": t.get("mbid") or None}
            for t in raw
        ]

    # ---- private: artist.getTopTags fallback ----

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
