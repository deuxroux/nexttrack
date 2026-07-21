import asyncio
import time

import httpx

from nexttrack.cache import LastfmCache


class SpotifyUnavailable(Exception):
    """Raised when Spotify is unreachable"""


class SpotifyClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        cache: LastfmCache,
    ) -> None:
        self._client = http_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache = cache
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    async def _acquire_token(self) -> None:
        try:
            resp = await self._client.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
            )
        except httpx.HTTPError as exc:
            raise SpotifyUnavailable(f"token request failed: {exc}") from exc

        if resp.status_code == 401:
            raise SpotifyUnavailable("invalid Spotify client credentials")
        if resp.status_code >= 500:
            raise SpotifyUnavailable(
                f"Spotify token endpoint returned {resp.status_code}"
            )
        resp.raise_for_status()

        body = resp.json()
        self._access_token = body["access_token"]
        self._expires_at = time.monotonic() + float(body["expires_in"])

    async def _ensure_token(self) -> str:
        if self._access_token and time.monotonic() < self._expires_at - 60:
            return self._access_token
        await self._acquire_token()
        assert self._access_token is not None
        return self._access_token

    async def get_track(self, track_id: str) -> dict:
        # Return the Spotify track object for track_id.
        # Raises SpotifyUnavailable network/auth/server errors, also bad track.
        key = f"spotify:v1:track:{track_id}"
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        data = await self._fetch_track(track_id, retry_auth=True)
        await self._cache.set(key, data)
        return data

    async def _fetch_track(self, track_id: str, *, retry_auth: bool) -> dict:
        token = await self._ensure_token()

        try:
            resp = await self._client.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise SpotifyUnavailable(f"track request failed: {exc}") from exc

        if resp.status_code == 401 and retry_auth:
            self._access_token = None
            self._expires_at = 0.0
            return await self._fetch_track(track_id, retry_auth=False)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "1"))
            await asyncio.sleep(retry_after)
            try:
                resp = await self._client.get(
                    f"https://api.spotify.com/v1/tracks/{track_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise SpotifyUnavailable(
                    f"track request failed after 429 retry: {exc}"
                ) from exc
            if resp.status_code == 429:
                raise SpotifyUnavailable(
                    "rate limited by Spotify; max retries exceeded"
                )

        if resp.status_code >= 500:
            raise SpotifyUnavailable(
                f"Spotify track endpoint returned {resp.status_code}"
            )

        resp.raise_for_status()
        return resp.json()
