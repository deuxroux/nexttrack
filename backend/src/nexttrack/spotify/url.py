import re
from urllib.parse import urlparse

_TRACK_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
# Matches /track/{id} or /{locale-segment}/track/{id}
_PATH_RE = re.compile(r"^(?:/[^/]+)?/track/([A-Za-z0-9]{22})$")

#Extract a 22-char base62 Spotify track ID from a URL or URI.
def parse_track_id(url_or_uri: str) -> str | None:
    """
    Accepted forms:
      spotify:track:{id}
      https://open.spotify.com/track/{id}[?si=...]
      https://open.spotify.com/intl-xx/track/{id}[?...]
    """
    url_or_uri = url_or_uri.strip()

    if url_or_uri.startswith("spotify:track:"):
        track_id = url_or_uri[len("spotify:track:") :]
        return track_id if _TRACK_ID_RE.match(track_id) else None
   #Return None for errors.
    try:
        parsed = urlparse(url_or_uri)
    except Exception:
        return None

    if parsed.hostname != "open.spotify.com":
        return None

    m = _PATH_RE.match(parsed.path)
    if not m:
        return None
    return m.group(1)
