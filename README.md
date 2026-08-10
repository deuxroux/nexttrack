# NextTrack

Stateless, privacy-preserving music recommendation API.

Nexttrack takes a list of seed tracks and allows for a user to set tunable parameters.
Then it returns ranked recommendations using Last.fm collaborative-filtering similarity plus community tag
re-ranking — without storing any per-user data. CSV export with URL searches for players of choice is provided.

This project was developed for CM3070 coursework, towards a degree from University of London, UK

## Architecture

```
.env                     Single environment file for both services (filled at time of hosting)
docker-compose.yml       Redis + backend + frontend

backend/                 Python, FastAPI, Pydantic v2, async structure
  src/nexttrack/
    lastfm/              Last.fm API client, with I/O, rate limiting, fallbacks
    spotify/             Spotify Client Credentials client for URL resolution only
    pipeline/            Aggregation and ranking
    export/              CSV serialisation
    observability/       Per-stage timing ring buffers
    api.py               FastAPI routes
    cache.py             Redis-backed cache logic
    config.py            Settings, env-driven with fallbacks
  scripts/               quick use scripts for use in testing and dev
  tests/                 pytest suite

frontend/                React + TypeScript (Vite)
  src/
    api/                 openapi-fetch client
    hooks/               State and I/O hooks for backend comms
    components/          UI components with CSS Modules
    styles/global.css    Global Design tokens and base styles
    test/                Testing suite for frontend

docs/
  openapi.json                     Generated OpenAPI spec (frontend codegen input)
  statelessness_verification.md    Reproducible privacy verification procedure
```
---
## Prerequisites

**Option A — Docker (recommended):**
- Docker with Compose v2 (`docker compose` command)
- A container runtime: [Colima](https://github.com/abiosoft/colima) was used in
  development. Could use Docker Desktop or Docker Engine for hosted versions

**Option B — Local, no containers:**
- Python 3.13 (pinned)
- [`uv`](https://github.com/astral-sh/uv) for Python dependency management
- Node.js 22+ and npm
- A locally running Redis instance
---
## Setup

NextTrack uses **one environment file**, at the repository root, shared by both
services.

1. Clone the repository and create your environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in the two required values:
   - **`LASTFM_API_KEY`** If needed get one at
     [last.fm/api/account/create](https://www.last.fm/api/account/create).
   - **`USER_AGENT_CONTACT`** — a contact email, ideally from key registration. Last.fm's API terms require an
     identifying User-Agent on outbound requests.
   Everything else has a working default, but I highly recommend getting a `SPOTIFY_CLIENT_ID` and
   `SPOTIFY_CLIENT_SECRET`. Leaving them blank disables URL retrieval for user QoL. Omitting will break
   `POST /resolve-spotify-url` (which returns `503`) but affects nothing else.

your `.env` should be git-ignored. If forking or developing on your own, Confirm before staging anything:

```bash
git check-ignore -v .env
```
---

## Running with Docker

### Start up:
Start your container runtime first if it isn't already running:
Activate Docker Engine. In the case of Colima:
```bash
colima start
```

Bring up the full stack — Redis, backend, and frontend:

```bash
docker compose up --build
```

**Note:** depending on your docker setup you may need to ensure CLI tools are up to date. while still active, v1 language should also work:

```bash
docker-compose up --build
```

### Access:
- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>


### Tear down:

```bash
docker compose down          # add -v to also drop the Redis cache volume
```


## API endpoints

To Use API endpoints alone, ensure the backend is up at a minimum. The following exposed endpoints relate to the recommendation engine and metadata alone.

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness check |
| `/search` | GET | Last.fm track typeahead (`?q=`, `?limit=`) |
| `/metrics` | GET | Cache hit/miss counts and per-stage timing percentiles |
| `/seed-profile` | POST | Aggregated tag profile for a seed set, used to populate genre-lock suggestions |
| `/recommend` | POST | Ranked recommendations as JSON; `?format=csv` returns a CSV attachment instead |
| `/recommend/stream` | POST | Same pipeline, delivered incrementally over Server-Sent Events |
| `/resolve-spotify-url` | POST | Resolve a pasted Spotify track URL to `{artist, title}` |

Full request/response schemas are served at <http://localhost:8000/docs> while the
backend runs, and exported to [`docs/openapi.json`](docs/openapi.json) for frontend
codegen.

Server Sent Events (SSE) were implemented for user affordance since otherwise POST /recommend
 is fully blocking. the stream modifier emits progress in multiple stages, helpful for UX.

**SSE  on `/recommend/stream`**, in order:

| Event | Payload | Meaning |
|---|---|---|
| `similarity` | `seeds_done`, `seeds_total`, `elapsed_ms` | One per seed, as similarity lookup completes |
| `tags` | `candidates`, `elapsed_ms` | Deduplication and candidate tag enrichment complete |
| `result` | `RecommendationResult` | Final ranked list |
| `error` | `error`, `detail`, `dropped_seeds` | Terminal failure — see below |
| `done` | `{}` | Stream complete |

A stream ends with either `result` + `done` or `error` + `done`, never both. The
`error` codes are `no_successful_seeds`, `no_recommendations`, and
`lastfm_unavailable`, matching the JSON bodies returned by `POST /recommend`.

---

## Recommendation Architecture

**Candidate generation.** For each seed, `track.getSimilar` supplies candidates with
similarity scores and `track.getTopTags` supplies a tag profile. Two fallbacks apply:

- **Fallback A** — if `track.getSimilar` returns empty, fall back to `artist.getSimilar`
combined with each similar artist's top tracks. The same substitution applies to tags via
 `artist.getTopTags`. Fallback use is recorded in each affected candidate's `explanation` field.
- **Fallback B** — if both the track- and artist-level routes come back empty, the
  seed is dropped and reported in `dropped_seeds`.

**Deduplication.** Candidates are keyed by case-normalised `(artist, title)`, with
similarity scores summed when several seeds recommend the same track. Seeds
themselves are excluded from their own output.

**Ranking.** Each candidate is scored as a convex blend of relevance and novelty:

```
relevance = (W_SIM · norm_sim + W_TAG · tag_overlap) / (W_SIM + W_TAG)
score     = (1 − α) · relevance + α · novelty_bonus        where α = novelty / 100
```

`norm_sim` is summed similarity max-normalised across the surviving pool,
`tag_overlap` is the fraction of the seed tag profile a candidate matches, and
`novelty_bonus` is `1 − playcount / max_playcount` over the pool. `W_SIM` and
`W_TAG` are defined in `pipeline/rank.py`.

**Filtering**, applied in order after scoring: genre lock, artist-diversity cap
 application,then truncation to the requested length.  When filtering leaves
 fewer tracks than requested, `pool_exhausted` is set and the UI shows a notice.

---

## Testing
For good hygeine, all tests must pass before any commit.

Backend:
```bash
cd backend
uv run ruff format --check .
uv run ruff check src/nexttrack/ tests/
uv run pytest -q
```

Frontend:
```bash
cd frontend
npm run lint
npm run test
npm run build
```

Backend tests run against committed Last.fm fixtures (past pulls from api calls) via
 `respx` and a `fakeredis`instance, so no network access or API key is needed.
 Frontend tests use Vitest with Testing Library and jsdom.

**About `backend/tests/fixtures/`.** Files here are live test inputs. Not all may be used.
 All are regenerable with `scripts/prototype_fixture.py`, which requires a live API key.

---

## API Usage Tutorial

Run this end-to-end check to manually verify performance, especially if only using backend API.

### A. Boot the stack

Use "Running with Docker" section as a guide.
```bash
docker compose up --build
```
Confirm in the logs:
- Redis reports `Ready to accept connections`
- Backend builds without error
- Backend logs `Uvicorn running on http://0.0.0.0:8000`

### B. Health and Metrics Check

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/metrics | jq
```
`/health` returns `{"status":"ok"}`. `/metrics` returns cache + timing
structure (timing will be empty until `/recommend` has been called at least
once).

### C. Swagger UI walkthrough

Open `http://localhost:8000/docs` and manually exercise, in order:

1. `POST /seed-profile` with 2–3 real tracks. can use test fixture json file for examples.
2. `POST /recommend` with the same seeds. Check `pool_exhausted` in the
   response (should be `false` for a normal request). Check backend logs for
   the `recommend complete stage_ms=... total_ms=...` line.
3. `POST /recommend?format=csv` — confirm the response includes the
   `#`-prefixed header rows and all nine columns. Save it as a `.csv` file
   and open it in a spreadsheet to confirm it parses cleanly.
4. `POST /resolve-spotify-url` with a real Spotify track URL. Repeat the same
   call again. the second response should be near-instant (cache proof).

### D. SSE streaming from CLI
Can't really be done from Swagger UI. try CLI to verify.
   ```bash
   curl -N -X POST http://localhost:8000/recommend/stream \
        -H 'Content-Type: application/json' \
        -d @backend/scripts/sample_request.json
   ```
   (from `backend/`, drop the `backend/` prefix: `-d @scripts/sample_request.json`)

   Confirm incremental delivery multiple `event:` lines expected.


### E. Error-branch checks

```bash
# no_successful_seeds — expect 422
curl -s -X POST http://localhost:8000/recommend \
     -H 'Content-Type: application/json' \
     -d '{"seeds":[{"artist":"asdkjhaskdjh","title":"nonsense12345"}],"params":{"novelty":50,"artist_diversity":3,"length":10,"genre_lock":[]}}'

# no_recommendations — expect 422 (genre_lock guarantees zero matches)
curl -s -X POST http://localhost:8000/recommend \
     -H 'Content-Type: application/json' \
     -d '{"seeds":[{"artist":"Radiohead","title":"Karma Police"}],"params":{"novelty":50,"artist_diversity":3,"length":10,"genre_lock":["polka"]}}'
```

### F. Statelessness verification

```bash
# No Set-Cookie on any response
curl -v http://localhost:8000/health 2>&1 | grep -i set-cookie
curl -v -X POST http://localhost:8000/recommend \
     -H 'Content-Type: application/json' \
     -d @backend/scripts/sample_request.json 2>&1 | grep -i set-cookie
# both should produce no output

# Only known cache-key prefixes present in Redis
docker-compose exec redis redis-cli --scan | grep -Ev '^(lastfm|spotify):v1:'
# should produce no output

# Every key has a TTL (nothing persisted indefinitely)
docker-compose exec redis redis-cli --scan | while read -r key; do
  echo "$key: $(docker-compose exec redis redis-cli TTL "$key")"
done
```

## Keeping frontend types in sync with the backend

Whenever the backend's request/response models change (new endpoint, new
field, changed validation), regenerate the OpenAPI export and the frontend's
generated types together, in this order:

1. With the backend running locally (`http://localhost:8000`):

```bash
   curl -s http://localhost:8000/openapi.json | jq > docs/openapi.json
```

2. Regenerate the frontend's TypeScript types from that file:

```bash
   cd frontend
   npm run gen:api-types
```

Commit `docs/openapi.json` and `frontend/src/api/schema.d.ts` together with
the backend change since hey're derived artifacts.



## Playlist export

CSV exports (`POST /recommend?format=csv`) (or using export CSV button in provided UI):
- produces file named for the run, for example `nexttrack_2026-08-09_nov60_div3.csv`, with
`#`-prefixed comment rows recording the export timestamp, every parameter value, and
the full seed list — so any exported list is reproducible from the file alone.
- Columns: `rank`, `artist`, `title`, `matched_tags`, `contributing_seeds`,
`final_score`, `explanation`, `spotify_search_url`, `apple_music_search_url`.
- include a Spotify search URL and an Apple Music search URL per track for manual playlist creation.
- CSV results can also be imported into an integrated playlist importer for
 streaming services using a third-party tool such as [Soundiiz](https://soundiiz.com) or
  [TuneMyMusic](https://www.tunemymusic.com). This step is optional and outside NextTrack's
  latest scope. the CSV format is compatible with these tools' import functionality.

## Tech stack

- **Backend** — Python 3.13, FastAPI, Pydantic v2, httpx, Redis,
  `sse-starlette`, `uv`, `ruff`
- **Backend testing** — `pytest`, `pytest-asyncio` (auto mode), `respx`,
  `fakeredis`, `hypothesis`
- **Frontend** — React 19, TypeScript, Vite, CSS Modules, `openapi-fetch`,
  `@microsoft/fetch-event-source`, `@tabler/icons-react`, `oxlint`
- **Frontend testing** — Vitest, Testing Library, jsdom
- **Infrastructure** — Docker Compose, Redis 7

**Data sources.** Last.fm is the sole primary source for similarity and tags. Spotify
is used only through the Client Credentials flow, to resolve a pasted track URL to an
artist and title — there is no user-facing Spotify authentication and no playlist
write access.



## License
MIT License. See [License](LICENSE) File.

