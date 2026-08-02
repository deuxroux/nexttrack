# Logic for Redis Cache of Last.fm responses

import json

import redis.asyncio as redis_asyncio


def _norm(s: str) -> str:
    return s.lower().strip()


class LastfmCache:
    def __init__(self, redis: redis_asyncio.Redis, ttl: int) -> None:
        self._redis = redis
        self._ttl = ttl
        self.hits: int = 0
        self.misses: int = 0

    @staticmethod
    def key_similar(artist: str, title: str) -> str:
        return f"lastfm:v1:similar:{_norm(artist)}:{_norm(title)}"

    @staticmethod
    def key_toptags(artist: str, title: str) -> str:
        return f"lastfm:v1:toptags:{_norm(artist)}:{_norm(title)}"

    @staticmethod
    def key_search(query: str, limit: int) -> str:
        return f"lastfm:v1:search:{_norm(query)}:{limit}"

    async def get(self, key: str) -> dict | None:
        raw = await self._redis.get(key)
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(raw)

    async def set(self, key: str, value: dict) -> None:
        await self._redis.set(key, json.dumps(value), ex=self._ttl)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
