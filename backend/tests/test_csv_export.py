import csv
import re
from datetime import datetime, timezone

from hypothesis import given
from hypothesis import strategies as st

from nexttrack.export.csv import render_csv
from nexttrack.models import (
    Candidate,
    RecommendationParams,
    RecommendationResult,
    Track,
)

# test fixtures
_NOW = datetime(2026, 7, 12, 14, 30, 0, tzinfo=timezone.utc)

_EXPECTED_COLUMNS = [
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


def _candidate(artist: str = "Portishead", title: str = "Glory Box") -> Candidate:
    return Candidate(
        artist=artist,
        title=title,
        summed_similarity=0.9,
        tag_overlap=0.8,
        novelty_bonus=0.5,
        final_score=0.85,
        contributing_seeds=["Radiohead/Pyramid Song"],
        matched_tags=["trip-hop", "electronic"],
        explanation=[],
    )


def _params(novelty: int = 60, artist_diversity: int = 3) -> RecommendationParams:
    return RecommendationParams(
        novelty=novelty,
        genre_lock=[],
        artist_diversity=artist_diversity,
        length=10,
    )


def _result(candidates=None) -> RecommendationResult:
    return RecommendationResult(
        candidates=candidates or [_candidate()],
        dropped_seeds=[],
        params=_params(),
    )


def _seeds() -> list[Track]:
    return [Track(artist="Radiohead", title="Pyramid Song")]


def _parse_csv(csv_body: str) -> tuple[list[str], list[list[str]]]:
    """Split comment lines from CSV data and parse the data rows."""
    data_lines = [line for line in csv_body.splitlines() if not line.startswith("#")]
    reader = csv.reader(data_lines)
    header = next(reader)
    rows = list(reader)
    return header, rows


# ---------------------------------------------------------------------------
# Column contract
# ---------------------------------------------------------------------------


def test_columns_exact_match():
    _, csv_body = render_csv(_result(), _seeds(), _params(), _NOW)
    header, _ = _parse_csv(csv_body)
    assert header == _EXPECTED_COLUMNS


# ---------------------------------------------------------------------------
# Header comment rows
# ---------------------------------------------------------------------------


def test_header_comments_present():
    _, csv_body = render_csv(_result(), _seeds(), _params(), _NOW)
    comments = [line for line in csv_body.splitlines() if line.startswith("# ")]
    joined = "\n".join(comments)

    assert "2026-07-12" in joined
    assert "novelty: 60" in joined
    assert "artist_diversity: 3" in joined
    assert "Radiohead" in joined  # seed artist in header
    assert "Pyramid Song" in joined  # seed title in header


def test_first_lines_are_comments():
    _, csv_body = render_csv(_result(), _seeds(), _params(), _NOW)
    first_line = csv_body.splitlines()[0]
    assert first_line.startswith("#")


def test_genre_lock_in_header():
    params = RecommendationParams(
        novelty=40, genre_lock=["trip-hop", "jazz"], artist_diversity=2, length=5
    )
    result = RecommendationResult(
        candidates=[_candidate()], dropped_seeds=[], params=params
    )
    _, csv_body = render_csv(result, _seeds(), params, _NOW)
    comments = "\n".join(line for line in csv_body.splitlines() if line.startswith("#"))
    assert "trip-hop" in comments
    assert "jazz" in comments


# ---------------------------------------------------------------------------
# Filename format verified with date information


def test_filename_format():
    filename, _ = render_csv(_result(), _seeds(), _params(), _NOW)
    assert re.match(r"^nexttrack_\d{4}-\d{2}-\d{2}_nov\d+_div\d+\.csv$", filename)


def test_filename_encodes_params():
    filename, _ = render_csv(
        _result(), _seeds(), _params(novelty=75, artist_diversity=7), _NOW
    )
    assert "nov75" in filename
    assert "div7" in filename
    assert "2026-07-12" in filename


# ---------------------------------------------------------------------------
# Search URLs. Assume spotify and apple music based on current correct search terms.


def test_spotify_search_url_populated():
    _, csv_body = render_csv(_result(), _seeds(), _params(), _NOW)
    header, rows = _parse_csv(csv_body)
    idx = header.index("spotify_search_url")
    for row in rows:
        url = row[idx]
        assert url.startswith("https://open.spotify.com/search/")
        assert len(url) > 40


def test_apple_music_search_url_populated():
    _, csv_body = render_csv(_result(), _seeds(), _params(), _NOW)
    header, rows = _parse_csv(csv_body)
    idx = header.index("apple_music_search_url")
    for row in rows:
        url = row[idx]
        assert url.startswith("https://music.apple.com/us/search?term=")
        assert len(url) > 40


def test_search_urls_are_ascii_encoded():
    # we can't have hanging spaces-- will mess up return url.
    params = _params()
    candidate = _candidate(artist="Sigur Ros", title="Ara batur")
    result = RecommendationResult(
        candidates=[candidate], dropped_seeds=[], params=params
    )
    _, csv_body = render_csv(result, _seeds(), params, _NOW)
    header, rows = _parse_csv(csv_body)
    surl_idx = header.index("spotify_search_url")
    aurl_idx = header.index("apple_music_search_url")
    row = rows[0]
    assert row[surl_idx].isascii()
    assert row[aurl_idx].isascii()


# ---------------------------------------------------------------------------
# confirm Rank column properly populates sequentially.


def test_rank_column_is_sequential():
    candidates = [_candidate("Artist A", "Track A"), _candidate("Artist B", "Track B")]
    result = RecommendationResult(
        candidates=candidates, dropped_seeds=[], params=_params()
    )
    _, csv_body = render_csv(result, _seeds(), _params(), _NOW)
    header, rows = _parse_csv(csv_body)
    rank_idx = header.index("rank")
    assert [int(r[rank_idx]) for r in rows] == [1, 2]


# ---------------------------------------------------------------------------
# StringIO check. Hypothesis library used to check at bounds of system.


@given(
    novelty=st.integers(min_value=0, max_value=100),
    artist_diversity=st.integers(min_value=1, max_value=10),
)
def test_csv_parses_cleanly_for_any_params(novelty: int, artist_diversity: int) -> None:
    params = RecommendationParams(
        novelty=novelty, genre_lock=[], artist_diversity=artist_diversity, length=10
    )
    result = _result()
    filename, csv_body = render_csv(result, _seeds(), params, _NOW)

    assert filename.endswith(".csv")
    assert f"nov{novelty}" in filename
    assert f"div{artist_diversity}" in filename

    header, rows = _parse_csv(csv_body)
    assert header == _EXPECTED_COLUMNS
    assert len(rows) == 1
