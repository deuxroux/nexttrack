"""Req 1.07 CLI Wiring possible"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import httpx  # noqa: E402

from nexttrack.lastfm.client import LastfmClient  # noqa: E402
from nexttrack.models import RecommendationParams, Track  # noqa: E402
from nexttrack.pipeline.aggregate import aggregate  # noqa: E402
from nexttrack.pipeline.rank import rank  # noqa: E402

SEEDS = [
    Track(artist="Radiohead", title="Pyramid Song"),
    Track(artist="Dr. Dog", title="Shadow People"),
    Track(artist="Death Cab for Cutie", title="Title and Registration"),
]

PARAMS = RecommendationParams(
    novelty=40,
    genre_lock=[],
    artist_diversity=2,
    length=10,
)


async def main() -> None:
    api_key = os.environ.get("LASTFM_API_KEY", "")
    if not api_key:
        raise SystemExit("LASTFM_API_KEY not set — add it to backend/.env")

    print(f"Seeds: {', '.join(f'{s.artist} / {s.title}' for s in SEEDS)}")
    print(f"Params: novelty={PARAMS.novelty} genre_lock={PARAMS.genre_lock} "
          f"diversity={PARAMS.artist_diversity} length={PARAMS.length}\n")

    async with httpx.AsyncClient(timeout=15.0) as client:
        lf = LastfmClient(client, api_key)
        candidates = await aggregate(lf, SEEDS)

    result = rank(candidates, PARAMS)

    print(f"Top {len(result.candidates)} recommendations:\n")
    for i, c in enumerate(result.candidates, 1):
        tags = ", ".join(c.matched_tags) or "-"
        print(
            f"{i:2}. {c.artist} — {c.title}\n"
            f"    score={c.final_score:.3f}  "
            f"sim={c.summed_similarity:.2f}  "
            f"tag={c.tag_overlap:.2f}  "
            f"novelty={c.novelty_bonus:.2f}\n"
            f"    seeds: {', '.join(c.contributing_seeds)}\n"
            f"    tags:  {tags}"
        )


if __name__ == "__main__":
    asyncio.run(main())
