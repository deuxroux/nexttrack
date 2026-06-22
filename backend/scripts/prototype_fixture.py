import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load from backend/.env
load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.environ["LASTFM_API_KEY"]
BASE_URL = "https://ws.audioscrobbler.com/2.0/"
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


SEEDS = [
    {"artist": "Radiohead","title": "Pyramid Song"},
    {"artist": "Dr. Dog", "title": "Shadow People"},
    {"artist": "Death Cab for Cutie", "title": "Title and Registration"},
    {"artist": "Massive Attack", "title": "Teardrop"},
]


async def fetch(client: httpx.AsyncClient, method: str, params: dict) -> dict:
    response = await client.get(
        BASE_URL,
        params={"method": method, "api_key": API_KEY, "format": "json",
                "autocorrect": "1", **params},
        headers={"User-Agent": "NextTrack/0.1 erasalav@gmail.com"},
    )
    response.raise_for_status()
    return response.json()


async def capture_seed(client: httpx.AsyncClient, artist: str, title: str) -> None:
    slug = f"{artist.lower().replace(' ', '_')}__{title.lower().replace(' ', '_')}"

    # track.getSimilar
    similar = await fetch(client, "track.getSimilar",
                          {"artist": artist, "track": title, "limit": 50})
    out_similar = FIXTURES_DIR / f"get_similar__{slug}.json"
    out_similar.write_text(json.dumps(similar, indent=2))
    track_count = len(similar.get("similartracks", {}).get("track", []))
    print(f"  getSimilar  [{artist} / {title}] → {track_count} tracks → {out_similar.name}")

    # track.getTopTags
    tags = await fetch(client, "track.getTopTags",
                       {"artist": artist, "track": title})
    out_tags = FIXTURES_DIR / f"get_top_tags__{slug}.json"
    out_tags.write_text(json.dumps(tags, indent=2))
    tag_count = len(tags.get("toptags", {}).get("tag", []))
    print(f"  getTopTags  [{artist} / {title}] → {tag_count} tags  → {out_tags.name}")


async def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing fixtures to {FIXTURES_DIR}\n")
    async with httpx.AsyncClient(timeout=10.0) as client:
        for seed in SEEDS:
            print(f"Fetching: {seed['artist']} / {seed['title']}")
            await capture_seed(client, seed["artist"], seed["title"])
            # stay well under Last.fm's 5 req/s limit
            await asyncio.sleep(0.5)
    print("\nDone. Commit these files; never run against live Last.fm in tests.")


if __name__ == "__main__":
    asyncio.run(main())
