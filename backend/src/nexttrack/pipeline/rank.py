from nexttrack.models import Candidate, RecommendationParams, RecommendationResult

# Tunable weights for recco algorithm (req 1.07)
# W_SIM and W_TAG control relative weighting *within* the relevance component.
W_SIM: float = 1.0
W_TAG: float = 0.5

_W_TOTAL: float = W_SIM + W_TAG  # normalisation denominator for relevance


def rank(
    candidates: list[Candidate],
    dropped_seeds: list[str],
    params: RecommendationParams,
) -> RecommendationResult:
    # Genre lock filter (req 3.17)
    if params.genre_lock:
        genre_set = {g.lower() for g in params.genre_lock}
        pool = [
            c for c in candidates if any(t.lower() in genre_set for t in c.matched_tags)
        ]
    else:
        pool = list(candidates)

    # Score and sort convex novelty/relevance blend (req 2.04)
    # final = (1-alpha)*relevance + alpha*novelty_bonus
    # --> ORIGINAL relevance = (W_SIM*norm_sim + W_TAG*tag_overlap) / W_TOTAL
    #  with normalization norm_sim  = summed_similarity / max_sim  (max-normalised across pool)
    alpha = params.novelty / 100.0
    max_sim = max((c.summed_similarity for c in pool), default=1.0) or 1.0
    scored: list[Candidate] = []
    for c in pool:
        norm_sim = c.summed_similarity / max_sim
        relevance = (W_SIM * norm_sim + W_TAG * c.tag_overlap) / _W_TOTAL
        score = (1.0 - alpha) * relevance + alpha * c.novelty_bonus
        scored.append(c.model_copy(update={"final_score": score}))
    scored.sort(key=lambda c: c.final_score, reverse=True)

    # artist diversity cap applied after sort
    counts: dict[str, int] = {}
    diverse: list[Candidate] = []
    for c in scored:
        key = c.artist.lower().strip()
        if counts.get(key, 0) < params.artist_diversity:
            diverse.append(c)
            counts[key] = counts.get(key, 0) + 1
    scored = diverse

    # Fallback D: notice when the pool couldn't fill the requested length
    pool_exhausted = len(scored) < params.length

    return RecommendationResult(
        candidates=scored[: params.length],
        dropped_seeds=dropped_seeds,
        params=params,
        pool_exhausted=pool_exhausted,
    )
