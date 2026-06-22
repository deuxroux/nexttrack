from nexttrack.lastfm.client import LastfmClient
from nexttrack.models import Candidate, Track


def _norm_key(artist: str, title: str) -> tuple[str, str]:
    return artist.lower().strip(), title.lower().strip()


async def aggregate(lf: LastfmClient, seeds: list[Track]) -> list[Candidate]:
    # Phase 1: fetch similar tracks + seed tag profile; record any fallback notes per seed
    seed_tracks: dict[str, list[dict]] = {}
    sim_fallback: dict[str, str] = {}   # seed_key -> fallback note (if similar-tracks fell back)
    tag_fallback: dict[str, str] = {}   # seed_key -> fallback note (if top-tags fell back)
    seed_tag_profile: set[str] = set()

    for seed in seeds:
        seed_key = f"{seed.artist}/{seed.title}"

        sim_result = await lf.get_similar_tracks(seed.artist, seed.title)
        seed_tracks[seed_key] = sim_result.tracks
        if sim_result.fallback_used:
            sim_fallback[seed_key] = sim_result.fallback_note

        tags_result = await lf.get_top_tags(seed.artist, seed.title)
        if tags_result.fallback_used:
            tag_fallback[seed_key] = tags_result.fallback_note
        for tag in tags_result.tags:
            seed_tag_profile.add(tag["name"])

    # Phase 2: dedup by normalised (artist, title), summing match scores
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
                    "contributing_seeds": [],
                }
            pool[key]["summed_similarity"] += float(t["match"])
            pool[key]["contributing_seeds"].append(seed_key)

    # Phase 3: compute novelty_bonus denominator
    max_playcount = max((e["playcount"] for e in pool.values()), default=1)

    # Phase 4: fetch candidate top tags; compute matched_tags, tag_overlap, novelty_bonus
    candidates: list[Candidate] = []
    for entry in pool.values():
        tags_result = await lf.get_top_tags(entry["artist"], entry["title"])
        candidate_tag_names = {t["name"] for t in tags_result.tags}
        matched = sorted(candidate_tag_names & seed_tag_profile)
        tag_overlap = len(matched) / len(seed_tag_profile) if seed_tag_profile else 0.0
        novelty_bonus = 1.0 - entry["playcount"] / max_playcount

        # Req 2.08: collect fallback notes from any contributing seed (deduplicated)
        seen_notes: set[str] = set()
        explanation: list[str] = []
        for seed_key in entry["contributing_seeds"]:
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
                contributing_seeds=entry["contributing_seeds"],
                matched_tags=matched,
                explanation=explanation,
            )
        )

    return candidates
