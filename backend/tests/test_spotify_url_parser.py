import re

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from nexttrack.spotify.url import parse_track_id

# A real-shaped but synthetic track ID (22 base62 chars)
_SAMPLE_ID = "4iV5W9uYEdYUVa79Axb7Rh"

_BASE62 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
_valid_id = st.text(alphabet=_BASE62, min_size=22, max_size=22)


#  happy-path cases
# ---------------------------------------------------------------------------


def test_plain_https_url():
    assert parse_track_id(f"https://open.spotify.com/track/{_SAMPLE_ID}") == _SAMPLE_ID


def test_spotify_uri():
    assert parse_track_id(f"spotify:track:{_SAMPLE_ID}") == _SAMPLE_ID


# Explicit reject cases
# ---------------------------------------------------------------------------

#confirm tracks
def test_artist_url_rejected():
    assert parse_track_id(f"https://open.spotify.com/artist/{_SAMPLE_ID}") is None


def test_album_url_rejected():
    assert parse_track_id(f"https://open.spotify.com/album/{_SAMPLE_ID}") is None


def test_spotify_album_uri_rejected():
    assert parse_track_id(f"spotify:album:{_SAMPLE_ID}") is None


def test_wrong_domain_rejected():
    assert parse_track_id(f"https://music.apple.com/track/{_SAMPLE_ID}") is None


def test_random_string_rejected():
    assert parse_track_id("not a url at all") is None


def test_empty_string_rejected():
    assert parse_track_id("") is None

# IDs must be exactly 22 chars
def test_short_track_id_rejected():
    assert parse_track_id("https://open.spotify.com/track/shortid") is None


def test_long_track_id_rejected():
    assert parse_track_id(f"https://open.spotify.com/track/{_SAMPLE_ID}moreChars") is None


# Hypothesis property tests for bounds
# -------------------------------------------------------------------

@given(
    track_id=_valid_id,
    locale=st.from_regex(r"intl-[a-z]{2,4}", fullmatch=True),
)
def test_intl_url_roundtrips(track_id: str, locale: str) -> None:
    url = f"https://open.spotify.com/{locale}/track/{track_id}"
    assert parse_track_id(url) == track_id

@given(track_id=_valid_id)
def test_spotify_uri_roundtrips(track_id: str) -> None:
    assert parse_track_id(f"spotify:track:{track_id}") == track_id
