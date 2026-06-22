from __future__ import annotations

from nexttrack.models import Candidate, RecommendationParams, RecommendationResult

# Hardcoded tunable weights for the prototype (req 1.07)
W_SIM: float = 1.0   # similarity contribution
W_TAG: float = 0.5   # tag-overlap contribution


def rank(
    candidates: list[Candidate],
    params: RecommendationParams,
) -> RecommendationResult:
    # Genre lock filter (req 3.17) — drop candidates with no intersection
    if params.genre_lock:
        genre_set = {g.lower() for g in params.genre_lock}
        pool = [
            c for c in candidates
            if any(t.lower() in genre_set for t in c.matched_tags)
        ]
    else:
        pool = list(candidates)

    # Score and sort (req 2.04)
    novelty_w = params.novelty / 100.0
    scored: list[Candidate] = []
    for c in pool:
        score = W_SIM * c.summed_similarity + W_TAG * c.tag_overlap + novelty_w * c.novelty_bonus
        scored.append(c.model_copy(update={"final_score": score}))
    scored.sort(key=lambda c: c.final_score, reverse=True)

    # Artist diversity cap (req 3.18) — applied after sort so we keep the best-scoring tracks
    if params.artist_diversity > 0:
        counts: dict[str, int] = {}
        diverse: list[Candidate] = []
        for c in scored:
            key = c.artist.lower().strip()
            if counts.get(key, 0) < params.artist_diversity:
                diverse.append(c)
                counts[key] = counts.get(key, 0) + 1
        scored = diverse

    return RecommendationResult(
        candidates=scored[: params.length],
        dropped_seeds=[],
        params=params,
    )
