"""Twitch Helix API over aiohttp (step 3.3).

The bot used the synchronous `requests` library: get_user_id and
get_channel_moderators ran it right inside the bot's event loop (the queue,
!skip and chat froze for up to 5 s per call), and the broadcaster id was
fetched in TwitchBot.__init__ with no timeout at all. aiohttp is already a
dependency of twitchio.

HelixClient.get() never raises: it returns (status, json) and (0, None) when
the request failed, so callers keep their fallbacks. The transport can be
replaced in tests (HelixClient(fetch=...)).

Python 3.8 compatible.
"""
import asyncio

API = "https://api.twitch.tv/helix/"
TIMEOUT = 5.0


class HelixClient(object):
    def __init__(self, headers_provider, fetch=None, timeout=TIMEOUT):
        self._headers = headers_provider   # () -> dict (token may change)
        self._fetch = fetch                # async (url, params, headers) -> (status, json)
        self._timeout = timeout
        self._session = None
        self.calls = 0

    async def _aiohttp_fetch(self, url, params, headers):
        import aiohttp
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout))
        async with self._session.get(url, params=params, headers=headers) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = None
            return resp.status, data

    async def get(self, path, **params):
        headers = self._headers() or {}
        auth = str(headers.get("Authorization", "") or "")
        token = auth.split(" ", 1)[1].strip() if " " in auth else ""
        if not headers.get("Client-ID") or not token:
            return 0, None  # no credentials: don't even try
        self.calls += 1
        fetch = self._fetch or self._aiohttp_fetch
        try:
            return await asyncio.wait_for(fetch(API + path.lstrip("/"), params, headers),
                                          self._timeout + 1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("Helix %s failed: %s" % (path, e))
            return 0, None

    async def close(self):
        if self._session is not None and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None


def logins(data, key="user_login"):
    """Lower-case logins from a Helix list response."""
    out = []
    for item in (data or {}).get("data", []) or []:
        name = str(item.get(key, "") or "").strip().lower()
        if name:
            out.append(name)
    return out
