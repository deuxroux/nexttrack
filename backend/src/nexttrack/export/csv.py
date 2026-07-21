import csv
import io
from datetime import datetime
from urllib.parse import quote

from nexttrack.models import RecommendationParams, RecommendationResult, Track


def _spotify_search_url(artist: str, title: str) -> str:
    return (
        f"https://open.spotify.com/search/"
        f"{quote(artist, safe='')}%20{quote(title, safe='')}"
    )


# Can add more of these. start with just spotify and apple music.
def _apple_music_search_url(artist: str, title: str) -> str:
    return (
        f"https://music.apple.com/us/search?term={quote(artist + ' ' + title, safe='')}"
    )


def render_csv(
    result: RecommendationResult,
    seeds: list[Track],
    params: RecommendationParams,
    now: datetime,
) -> tuple[str, str]:
    # serialize RecommendationResult to CSV. Returns (filename, csv_body).
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    filename = (
        f"nexttrack_{date_str}_nov{params.novelty}_div{params.artist_diversity}.csv"
    )

    buf = io.StringIO()

    buf.write(f"# exported: {date_str}T{time_str}Z\n")
    buf.write(f"# date: {date_str}\n")
    buf.write(f"# novelty: {params.novelty}\n")
    buf.write(f"# artist_diversity: {params.artist_diversity}\n")
    genre_str = ", ".join(params.genre_lock) if params.genre_lock else "none"
    buf.write(f"# genre_lock: {genre_str}\n")
    buf.write(f"# length: {params.length}\n")
    seeds_str = "; ".join(f"{s.artist} - {s.title}" for s in seeds)
    buf.write(f"# seeds: {seeds_str}\n")

    writer = csv.writer(buf)
    writer.writerow(
        [
            "rank",
            "artist",
            "title",
            "matched_tags",
            "contributing_seeds",
            "final_score",
            "explanation",
            "spotify_search_url",
            "apple_music_search_url",
        ]
    )

    for rank_i, c in enumerate(result.candidates, start=1):
        writer.writerow(
            [
                rank_i,
                c.artist,
                c.title,
                "; ".join(c.matched_tags),
                "; ".join(c.contributing_seeds),
                f"{c.final_score:.6f}",
                "; ".join(c.explanation),
                _spotify_search_url(c.artist, c.title),
                _apple_music_search_url(c.artist, c.title),
            ]
        )

    return filename, buf.getvalue()
