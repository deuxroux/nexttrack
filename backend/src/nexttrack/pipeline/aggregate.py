import time
from collections.abc import AsyncIterator

from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import Candidate, SeedProfile, StageEvent, TagCount, Track


def _norm_key(artist: str, title: str) -> tuple[str, str]:
    return artist.lower().strip(), title.lower().strip()


async def aggregate_streaming(
    lf: LastfmClient, seeds: list[Track]
) -> AsyncIterator[StageEvent | tuple[list[Candidate], list[str]]]:
    seed_tracks: dict[str, list[dict]] = {}
    sim_fallback: dict[str, str] = {}
    tag_fallback: dict[str, str] = {}
    seed_tag_profile: set[str] = set()
    dropped_seeds: list[str] = []
    seeds_total = len(seeds)

    # Phase 1: per-seed similarity + seed-tag lookups
    for i, seed in enumerate(seeds, 1):
        seed_key = f"{seed.artist}/{seed.title}"
        t0 = time.monotonic()

        sim_result = await lf.get_similar_tracks(seed.artist, seed.title)

        # Req 2.07 (Fallback B): drop seed if both primary and artist fallback give nothing
        if sim_result.fallback_used and not sim_result.tracks:
            dropped_seeds.append(seed_key)
            yield StageEvent(
                stage="similarity",
                seeds_done=i,
                seeds_total=seeds_total,
                elapsed_ms=(time.monotonic() - t0) * 1000,
            )
            continue

        seed_tracks[seed_key] = sim_result.tracks
        if sim_result.fallback_used:
            sim_fallback[seed_key] = sim_result.fallback_note

        tags_result = await lf.get_top_tags(seed.artist, seed.title)
        if tags_result.fallback_used:
            tag_fallback[seed_key] = tags_result.fallback_note
        for tag in tags_result.tags:
            seed_tag_profile.add(tag["name"])

        yield StageEvent(
            stage="similarity",
            seeds_done=i,
            seeds_total=seeds_total,
            elapsed_ms=(time.monotonic() - t0) * 1000,
        )

    # Phase 2: dedup by normalised (artist, title), summing match scores
    t0 = time.monotonic()
    seed_norm_keys: set[tuple[str, str]] = {
        _norm_key(seed.artist, seed.title) for seed in seeds
    }
    pool: dict[tuple[str, str], dict] = {}

    for seed_key, tracks in seed_tracks.items():
        for t in tracks:
            key = _norm_key(t["artist"], t["name"])
            if key in seed_norm_keys:  # req 2.05: exclude seeds from recommendations
                continue
            if key not in pool:
                pool[key] = {
                    "artist": t["artist"],
                    "title": t["name"],
                    "summed_similarity": 0.0,
                    "playcount": t["playcount"],
                    "seed_matches": {},  # seed_key -> accumulated match score
                }
            pool[key]["summed_similarity"] += float(t["match"])
            pool[key]["seed_matches"][seed_key] = pool[key]["seed_matches"].get(
                seed_key, 0.0
            ) + float(t["match"])

    # Phase 3: fetch candidate top tags; compute matched_tags, tag_overlap,
    # novelty_bonus, and explanations. Timer started in Phase 2 continues here
    # so elapsed_ms on the "tags" event covers both dedup and candidate I/O.
    max_playcount = max((e["playcount"] for e in pool.values()), default=1)
    pool_size = len(pool)

    candidates: list[Candidate] = []
    for entry in pool.values():
        tags_result = await lf.get_top_tags(entry["artist"], entry["title"])
        candidate_tag_names = {t["name"] for t in tags_result.tags}
        matched = sorted(candidate_tag_names & seed_tag_profile)
        tag_overlap = len(matched) / len(seed_tag_profile) if seed_tag_profile else 0.0
        novelty_bonus = 1.0 - entry["playcount"] / max_playcount

        # Rebuild contributing_seeds from seed_matches for the Candidate field
        seed_matches: dict[str, float] = entry["seed_matches"]
        contributing_seeds = list(seed_matches.keys())
        primary_seed = max(seed_matches, key=seed_matches.__getitem__)

        # Req 2.08: structured explanation before any fallback notes
        explanation: list[str] = [f"top seed: {primary_seed}"]
        if matched:
            explanation.append(f"matched tags: {', '.join(matched)}")

        seen_notes: set[str] = set()
        for seed_key in contributing_seeds:
            for note in (sim_fallback.get(seed_key), tag_fallback.get(seed_key)):
                if note is not None and note not in seen_notes:
                    explanation.append(note)
                    seen_notes.add(note)

        candidates.append(
            Candidate(
                artist=entry["artist"],
                title=entry["title"],
                summed_similarity=entry["summed_similarity"],
                tag_overlap=tag_overlap,
                novelty_bonus=novelty_bonus,
                final_score=0.0,
                contributing_seeds=contributing_seeds,
                matched_tags=matched,
                explanation=explanation,
            )
        )

    yield StageEvent(
        stage="tags",
        candidates=pool_size,
        elapsed_ms=(time.monotonic() - t0) * 1000,
    )

    yield candidates, dropped_seeds


async def build_seed_profile(lf: LastfmClient, seeds: list[Track]) -> SeedProfile:
    tag_counts: dict[str, int] = {}  # tag name -> number of seeds that carry it
    dropped_seeds: list[str] = []

    for seed in seeds:
        seed_key = f"{seed.artist}/{seed.title}"

        sim_result = await lf.get_similar_tracks(seed.artist, seed.title)

        # Fallback B: both track- and artist-level similarity returned empty -- drop seed
        if sim_result.fallback_used and not sim_result.tracks:
            dropped_seeds.append(seed_key)
            continue

        tags_result = await lf.get_top_tags(seed.artist, seed.title)
        for tag in tags_result.tags:
            name = tag["name"]
            tag_counts[name] = tag_counts.get(name, 0) + 1

    sorted_tags = sorted(
        [TagCount(name=name, seed_count=count) for name, count in tag_counts.items()],
        key=lambda t: (-t.seed_count, t.name),
    )

    return SeedProfile(
        tags=sorted_tags,
        dropped_seeds=dropped_seeds,
        total_seeds=len(seeds),
    )


async def aggregate(
    lf: LastfmClient, seeds: list[Track]
) -> tuple[list[Candidate], list[str]]:
    candidates: list[Candidate] = []
    dropped: list[str] = []
    async for item in aggregate_streaming(lf, seeds):
        if isinstance(item, tuple):
            candidates, dropped = item
    return candidates, dropped
