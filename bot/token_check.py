"""Check the Twitch token before connecting (2.0).

GET https://id.twitch.tv/oauth2/validate answers whose token it is, which
application issued it (the Client ID), its scopes and how long it lives.
Without the check a missing scope or a token of another account only showed
up as an error line in the log: the viewers list silently fell back to the
chatters, moderators came from badges only.

validate() never raises: it returns (status, json), (0, None) when Twitch
could not be reached. analyze() turns the answer into a plain dict for the
window. No Qt here.

Python 3.8 compatible.
"""
import asyncio

VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TIMEOUT = 5.0

# scope -> what stops working without it (keys the window translates)
SCOPES = (
    ("chat:read", "chat"),
    ("chat:edit", "answers"),
    ("moderator:read:chatters", "viewers"),
    ("moderation:read", "moderators"),
)

EXPIRES_SOON = 7 * 24 * 3600     # warn when less than a week is left


def bare_token(token):
    token = str(token or "").strip()
    return token[6:] if token.lower().startswith("oauth:") else token


async def _aiohttp_fetch(url, headers, timeout):
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.get(url, headers=headers) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = None
            return resp.status, data


async def validate(token, fetch=None, timeout=TIMEOUT):
    """(status, json) of the validate endpoint; (0, None) on a network error.
    fetch: async (url, headers, timeout) -> (status, json), for tests."""
    token = bare_token(token)
    if not token:
        return 401, None
    fetch = fetch or _aiohttp_fetch
    try:
        return await asyncio.wait_for(
            fetch(VALIDATE_URL, {"Authorization": "OAuth " + token}, timeout), timeout + 1)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print("Token check failed: %s" % e)
        return 0, None


def analyze(status, data, channel):
    """What the window shows about the token.

    state: "ok" - Twitch knows the token; "invalid" - expired / revoked /
    garbage (connecting is pointless); "unknown" - Twitch did not answer
    (connect as before, nothing is known)."""
    info = {"state": "unknown", "login": "", "user_id": "", "client_id": "",
            "scopes": [], "missing": [], "is_broadcaster": None,
            "expires_in": None, "expires_soon": False}
    if status == 401:
        info["state"] = "invalid"
        return info
    if status != 200 or not isinstance(data, dict):
        return info
    scopes = [str(s) for s in (data.get("scopes") or [])]
    login = str(data.get("login") or "").lower()
    try:
        expires = int(data.get("expires_in"))
    except (TypeError, ValueError):
        expires = None
    channel = str(channel or "").strip().lstrip("#").lower()
    info.update({
        "state": "ok",
        "login": login,
        "user_id": str(data.get("user_id") or ""),
        "client_id": str(data.get("client_id") or ""),
        "scopes": scopes,
        "missing": [s for s, _what in SCOPES if s not in scopes],
        # an app token has no login: it is nobody's, so not the streamer's
        "is_broadcaster": bool(login) and login == channel,
        # 0 = a token that does not expire
        "expires_in": expires,
        "expires_soon": expires is not None and 0 < expires < EXPIRES_SOON,
    })
    return info


async def check(token, channel, fetch=None):
    status, data = await validate(token, fetch=fetch)
    return analyze(status, data, channel)
