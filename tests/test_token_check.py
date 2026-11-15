"""Checking the Twitch token before connecting (2.0, bot/token_check.py).

Py3.8 compatible. No network: the validate endpoint is a fake.
"""
from bot import token_check


def _fetch(status, data, seen=None):
    async def fetch(url, headers, timeout):
        if seen is not None:
            seen.append((url, headers))
        return status, data
    return fetch


GOOD = {"client_id": "cid123", "login": "streamer", "user_id": "42",
        "scopes": ["chat:read", "chat:edit", "moderator:read:chatters", "moderation:read"],
        "expires_in": 5000000}


async def test_the_validate_request():
    seen = []
    status, data = await token_check.validate("oauth:abc", fetch=_fetch(200, GOOD, seen))
    assert status == 200 and data == GOOD
    url, headers = seen[0]
    assert url == "https://id.twitch.tv/oauth2/validate"
    assert headers == {"Authorization": "OAuth abc"}, "the oauth: prefix is dropped"


async def test_no_token_is_invalid_without_asking():
    seen = []
    assert await token_check.validate("  ", fetch=_fetch(200, GOOD, seen)) == (401, None)
    assert not seen


async def test_network_error_is_unknown_not_a_crash():
    async def broken(url, headers, timeout):
        raise OSError("no network")
    assert await token_check.validate("abc", fetch=broken) == (0, None)
    info = await token_check.check("abc", "streamer", fetch=broken)
    assert info["state"] == "unknown"


async def test_the_streamers_token_with_every_scope():
    info = await token_check.check("abc", "#Streamer", fetch=_fetch(200, GOOD))
    assert info["state"] == "ok" and info["login"] == "streamer"
    assert info["client_id"] == "cid123"
    assert info["is_broadcaster"] is True, "channel name: case and # do not matter"
    assert info["missing"] == []
    assert info["expires_in"] == 5000000 and not info["expires_soon"]


async def test_a_bot_accounts_token_missing_scopes():
    data = dict(GOOD, login="mybot", scopes=["chat:read", "chat:edit"], expires_in=3600)
    info = token_check.analyze(200, data, "streamer")
    assert info["is_broadcaster"] is False
    assert info["missing"] == ["moderator:read:chatters", "moderation:read"]
    assert info["expires_soon"] is True


async def test_rejected_and_odd_answers():
    assert token_check.analyze(401, {"status": 401, "message": "invalid access token"}, "x")["state"] == "invalid"
    assert token_check.analyze(500, None, "x")["state"] == "unknown"
    assert token_check.analyze(200, "garbage", "x")["state"] == "unknown"
    never = token_check.analyze(200, dict(GOOD, expires_in=0), "streamer")
    assert never["expires_in"] == 0 and not never["expires_soon"], "0 = does not expire"
    app = token_check.analyze(200, {"client_id": "c", "scopes": [], "expires_in": 100}, "streamer")
    assert app["state"] == "ok" and app["is_broadcaster"] is False, "an app token is nobody's"
    assert len(app["missing"]) == len(token_check.SCOPES)


async def test_the_bot_takes_the_tokens_client_id():
    from bot.helix import HelixClient
    headers = {"Client-ID": None, "Authorization": "Bearer abc"}

    class Bot(object):
        _helix_headers = headers
    from bot.twitch_bot import TwitchBot
    bot = Bot()
    TwitchBot.set_client_id(bot, "cid123")
    assert headers["Client-ID"] == "cid123"
    TwitchBot.set_client_id(bot, "")
    assert headers["Client-ID"] == "cid123", "an empty id does not erase the known one"
    seen = []

    async def fetch(url, params, hdrs):
        seen.append(hdrs["Client-ID"])
        return 200, {"data": []}
    await HelixClient(lambda: headers, fetch=fetch).get("users", login="x")
    assert seen == ["cid123"], "Helix requests go out with it"
