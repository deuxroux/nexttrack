import fakeredis.aioredis
import pytest

from nexttrack.cache import LastfmCache


@pytest.fixture
async def cache() -> LastfmCache:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return LastfmCache(fake, ttl=3600)


# confirm indexing is correct
async def test_get_miss_returns_none_and_increments_misses(cache: LastfmCache) -> None:
    assert await cache.get("lastfm:v1:similar:foo:bar") is None #foobar used as dummy code
    assert cache.misses == 1
    assert cache.hits == 0 #no hits for this param should exist


# confirm allocation
async def test_set_then_get_returns_value_and_increments_hits(
    cache: LastfmCache,
) -> None:
    key = LastfmCache.key_similar("Radiohead", "Pyramid Song")
    payload = {"tracks": [{"name": "x", "artist": "y", "match": 0.9, "playcount": 100}]}
    await cache.set(key, payload)
    got = await cache.get(key)
    assert got == payload
    assert cache.hits == 1
    assert cache.misses == 0


async def test_key_normalization_case_and_whitespace(cache: LastfmCache) -> None:
    k1 = LastfmCache.key_similar("Radiohead", "Pyramid Song")
    k2 = LastfmCache.key_similar("  RADIOHEAD  ", "  pyramid song  ")
    assert k1 == k2


async def test_hit_rate_computed_correctly(cache: LastfmCache) -> None:
    await cache.get("missing:a")
    await cache.get("missing:b")
    await cache.set("present:c", {"v": 1})
    await cache.get("present:c")
    assert cache.hit_rate == pytest.approx(1 / 3)
