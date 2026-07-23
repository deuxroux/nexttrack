# NextTrack

Stateless, privacy-preserving music recommendation API.

Nexttrack takes a list of seed tracks and allows for a user to set tunable parameters.
Then it returns ranked recommendations using Last.fm collaborative-filtering similarity plus community tag
re-ranking — without storing any per-user data. CSV export with URL searches for players of choice is provided.

This project was developed for CM3070 coursework, towards a degree from University of London, UK

## Architecture

```
frontend/  React + TypeScript (Vite)
backend/   FastAPI + Pydantic v2, async throughout
  src/nexttrack/
    lastfm/      Last.fm API client (I/O)
    spotify/     Spotify Client Credentials client (I/O)
    pipeline/    Pure aggregation + ranking logic (no I/O)
    export/      CSV serializatio
    api.py       FastAPI routes
    cache.py     Redis-backed cache
    config.py    Settings (env-driven)
docker-compose.yml   Redis + backend (+ frontend, via profile)
```

## Prerequisites

**Option A — Docker (recommended):**
- Docker CLI + Docker Compose
- A container runtime: [Colima](https://github.com/abiosoft/colima) (used in
  this project) or Docker Desktop

**Option B — Local, no containers:**
- Python 3.13 (`.python-version` pinned)
- [`uv`](https://github.com/astral-sh/uv) for Python dependency management
- Node.js 20+ and npm (once frontend work begins)
- A locally running Redis instance

## Setup

1. Clone the repo and copy the environment templates:

   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env   # once frontend exists
   ```

2. Edit `backend/.env` and fill in:
   - `LASTFM_API_KEY` — required. Get one from
     [last.fm/api/account/create](https://www.last.fm/api/account/create).
   - `USER_AGENT_CONTACT` — required. Last.fm's terms require a contact
     email in the User-Agent header.
   - `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` — optional. Used only for Spotify URL track input resolution.
   Leave blank to disable `/resolve-spotify-url`; the rest of the API is unaffected.
   - `CORS_ALLOWED_ORIGINS` — defaults to `http://localhost:5173` (Vite's
     default dev port). Adjust if your frontend runs elsewhere.

## Running with Docker (Colima or Docker Desktop)
Start your container runtime first if it isn't already running:
Either activate docker desktop or Colima:
```bash
colima start          # only if using Colima; skip for Docker Desktop
```

Bring up Redis + backend:

```bash
docker-compose up --build
```

Once frontend work has started and its Dockerfile exists, bring up the full
stack (backend + frontend) with:

```bash
docker-compose --profile full up --build
```

Tear down:

```bash
docker-compose down
# or, if started with --profile full:
docker-compose --profile full down
```

Backend is reachable at `http://localhost:8000`, frontend (once containerized)
at `http://localhost:5173`.

## Running locally without Docker

Terminal 1 — Redis:

```bash
redis-server
```

Terminal 2 — backend:

```bash
cd backend
uv sync
uv run uvicorn nexttrack.api:app --reload
```

Note: when running this way (not via Compose), `REDIS_URL` in `backend/.env`
should point at `redis://localhost:6379/0`, not the `redis://redis:6379/0`
hostname used inside the Docker network.

Terminal 3 — frontend (once it exists):

```bash
cd frontend
npm install
npm run dev
```

## API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness check |
| `/metrics` | GET | Cache hit/miss stats + per-stage timing summary |
| `/seed-profile` | POST | Preview the aggregated tag profile for a set of seeds |
| `/recommend` | POST | Get ranked recommendations. `?format=csv` streams a CSV instead of JSON |
| `/recommend/stream` | POST | Same as `/recommend`, delivered incrementally via SSE |
| `/resolve-spotify-url` | POST | Resolve a pasted Spotify track URL to an `{artist, title}` pair |

Full request/response schemas are available at `http://localhost:8000/docs`
(Swagger UI) while the backend is running, and exported to
[`docs/openapi.json`](docs/openapi.json) for frontend codegen.

## Testing

```bash
cd backend
uv run ruff format --check .
uv run ruff check src/nexttrack/ tests/
uv run pytest -v
```

All three must pass before any commit.

## Developer verification checklist

Run this end-to-end check to manually verify performance and feel.

### A. Static checks for pytest/ruff

```bash
cd backend
uv run ruff format --check .
uv run ruff check src/nexttrack/ tests/
uv run pytest -q
```
All green before proceeding.

### B. Boot the stack

```bash
docker-compose up --build
```
Confirm in the logs:
- Redis reports `Ready to accept connections`
- Backend builds without error
- Backend logs `Uvicorn running on http://0.0.0.0:8000`

### C. Health + metrics smoke test

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/metrics | jq
```
`/health` returns `{"status":"ok"}`. `/metrics` returns cache + timing
structure (timing will be empty until `/recommend` has been called at least
once).

### D. Swagger UI walkthrough

Open `http://localhost:8000/docs` and manually exercise, in order:

1. `POST /seed-profile` with 2–3 real tracks. can use test fixture json file for examples.
2. `POST /recommend` with the same seeds. Check `pool_exhausted` in the
   response (should be `false` for a normal request). Check backend logs for
   the `recommend complete stage_ms=... total_ms=...` line.
3. `POST /recommend?format=csv` — confirm the response includes the
   `#`-prefixed header rows and all nine columns. Save it as a `.csv` file
   and open it in a spreadsheet to confirm it parses cleanly.
4. `POST /recommend/stream` — Swagger doesn't render SSE well; use curl
   instead, from the repo root:

   ```bash
   curl -N -X POST http://localhost:8000/recommend/stream \
        -H 'Content-Type: application/json' \
        -d @backend/scripts/sample_request.json
   ```
   (from `backend/`, drop the `backend/` prefix: `-d @scripts/sample_request.json`)

   Confirm incremental delivery multiple `event:` lines expected.
5. `POST /resolve-spotify-url` with a real Spotify track URL. Repeat the same
   call — the second response should be near-instant (cache hit).

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

### G. Clean reboot

```bash
docker-compose down
docker-compose up -d
```
Confirm the stack comes back up with no manual intervention

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
the backend change that caused them to change — they're derived artifacts,
not independent source of truth, and should never drift from the backend
that generated them.

**Do not hand-edit `frontend/src/api/schema.d.ts`.** It is fully
regenerated by step 2 above; any manual edits will be silently overwritten
the next time someone runs the script.


## Environment variables
### BACKEND
| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LASTFM_API_KEY` | Yes | — | Last.fm API authentication |
| `USER_AGENT_CONTACT` | Yes | — | Contact email in User-Agent header (Last.fm ToS) |
| `SPOTIFY_CLIENT_ID` | No | `""` | Enables `/resolve-spotify-url` |
| `SPOTIFY_CLIENT_SECRET` | No | `""` | Enables `/resolve-spotify-url` |
| `CORS_ALLOWED_ORIGINS` | No | `http://localhost:5173` | Comma-separated list of allowed frontend origins |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Overridden to `redis://redis:6379/0` inside Docker Compose |

See `backend/.env.example` for the canonical, always-current list.

### FRONTEND
[TO BE FILLED]

## Playlist export

CSV exports (`/recommend?format=csv`) include a Spotify search URL and an
Apple Music search URL per track for manual playlist creation.
CSV results can also be imported into an integrated playlist importer for
 streaming services using a third-party tool such as
[Soundiiz](https://soundiiz.com) or [TuneMyMusic](https://www.tunemymusic.com).
This step is optional and outside NextTrack's latest scope. the CSV format is
simply compatible with these tools' import functionality.

## Tech stack

- **Backend:** Python 3.13, FastAPI, Pydantic v2, httpx, Redis,
  `sse-starlette`, `uv`, `ruff`
- **Testing:** `pytest`, `pytest-asyncio` (auto mode), `respx`, `fakeredis`,
  `hypothesis`
- **Frontend:** React, TypeScript, Vite, `openapi-fetch`
- **Infrastructure:** Docker Compose, Redis 7





## License
MIT License

Copyright (c) 2026 Vineet Erasala. Created for an Academic project — CM3070.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

