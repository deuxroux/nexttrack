# Statelessness Verification readme

This guide explains how to confirm no state is maintained-- true anonymity.

It is recommended to Run each check with the server running locally (`uv run uvicorn nexttrack.api:app --reload`).

The bash commands for each step can be run, with expected outcome proving statelessness at end. All have been verified during development.

## 1. No Set-Cookie on any endpoint

Assert that none of the API endpoints returns a `Set-Cookie` header.

```bash
curl -sv http://localhost:8000/health 2>&1 | grep -i set-cookie
curl -sv http://localhost:8000/metrics 2>&1 | grep -i set-cookie
curl -sv -X POST http://localhost:8000/seed-profile \
     -H 'Content-Type: application/json' \
     -d '{  "seeds": [
    {"artist": "Radiohead",      "title": "Pyramid Song"},
    {"artist": "Portishead",     "title": "Glory Box"},
    {"artist": "Massive Attack", "title": "Teardrop"}
  ]}' 2>&1 | grep -i set-cookie
curl -sv -X POST http://localhost:8000/recommend \
     -H 'Content-Type: application/json' \
     -d '{  "seeds": [
    {"artist": "Radiohead",      "title": "Pyramid Song"},
    {"artist": "Portishead",     "title": "Glory Box"},
    {"artist": "Massive Attack", "title": "Teardrop"}
  ],"params":{"novelty":50,"genre_lock":[],"artist_diversity":3,"length":10}}' \
     2>&1 | grep -i set-cookie
curl -sv -N -X POST http://localhost:8000/recommend/stream \
     -H 'Content-Type: application/json' \
     -d '{  "seeds": [
    {"artist": "Radiohead",      "title": "Pyramid Song"},
    {"artist": "Portishead",     "title": "Glory Box"},
    {"artist": "Massive Attack", "title": "Teardrop"}
  ],"params":{"novelty":50,"genre_lock":[],"artist_diversity":3,"length":10}}' \
     2>&1 | grep -i set-cookie
curl -sv -X POST http://localhost:8000/resolve-spotify-url \
     -H 'Content-Type: application/json' \
     -d '{"url":"not-a-url"}' 2>&1 | grep -i set-cookie
```

**Expected output:** _(empty -- no Set-Cookie headers on any endpoint)_


---

## 2. Redis contains only track/query-keyed cache entries

No key in Redis should be outside the `lastfm:v1:` or `spotify:v1:` namespaces.

```bash
redis-cli --scan | grep -Ev '^(lastfm|spotify):v1:'
```

**Expected output:** _(empty -- no user-scoped keys)_



## 3. Every Redis key has a positive TTL

All cache keys must expire. A TTL of -1 indicates a key with no expiry (persistent),
which would be a statelessness violation.

```bash
redis-cli --scan | while read key; do
  ttl=$(redis-cli TTL "$key")
  echo "$ttl $key"
done | sort -n | head -20
```

**Expected output:** _(all TTLs > 0; no -1 values)_


## 4. SpotifyClient token is in-process only

The Spotify Client Credentials token is intentionally held in-process on the
`SpotifyClient` instance (`app.state.spotify`). Verify it is NOT written to Redis.

```bash
redis-cli --scan | grep -i 'spotify.*token'
```

**Expected output:** _(empty -- token lives only in memory, expires when the process does)_
