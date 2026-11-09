"""Step 3.3: Helix over aiohttp, moderator cache.

Py3.8 compatible.
"""
import asyncio
import time

from harness import make_bot, FakeCurrencyManager, new_tmpdir, drop_tmpdir

from bot import twitch_bot
from bot.helix import HelixClient


class FakeHelix(object):
    """Records calls; answers from a table {path: (status, json)}."""

    def __init__(self, answers, delay=0.0):
        self.answers = answers
        self.delay = delay
        self.calls = []

    async def __call__(self, url, params, headers):
        path = url.split("/helix/", 1)[1]
        self.calls.append((path, dict(params)))
        if self.delay:
            await asyncio.sleep(self.delay)
        ans = self.answers.get(path, (500, None))
        if isinstance(ans, Exception):
            raise ans
        return ans


def _bot_with(tmp, answers, delay=0.0, users=None):
    bot, cm, cur = make_bot(tmp, [], currency=FakeCurrencyManager(users or {}))
    fake = FakeHelix(answers, delay)
    bot._helix = HelixClient(lambda: {"Client-ID": "cid", "Authorization": "Bearer tok"}, fetch=fake)
    return bot, fake


async def test_no_requests_library_in_the_bot():
    assert not hasattr(twitch_bot, "requests"), "the bot must not use the blocking requests library"


async def test_broadcaster_id_and_chatters():
    tmp = new_tmpdir()
    try:
        bot, fake = _bot_with(tmp, {
            "users": (200, {"data": [{"id": "123", "login": "testchan"}]}),
            "chat/chatters": (200, {"data": [{"user_login": "Alice"}, {"user_login": "bob"}]}),
        })
        assert await bot._ensure_broadcaster_id() == "123"
        assert await bot.get_all_viewers() == ["alice", "bob"]
        assert ("chat/chatters", {"broadcaster_id": "123", "moderator_id": "123"}) in fake.calls
    finally:
        drop_tmpdir(tmp)


async def test_helix_failure_falls_back_and_never_raises():
    tmp = new_tmpdir()
    try:
        bot, _fake = _bot_with(tmp, {"users": OSError("network down")})
        assert await bot._ensure_broadcaster_id() is None
        bot.active_users = {"someone"}
        assert await bot.get_all_viewers() == ["someone"]
        assert await bot.check_if_live() is False
    finally:
        drop_tmpdir(tmp)


async def test_moderator_list_is_cached():
    tmp = new_tmpdir()
    try:
        bot, fake = _bot_with(tmp, {
            "users": (200, {"data": [{"id": "123"}]}),
            "moderation/moderators": (200, {"data": [{"user_login": "modguy"}]}),
        })
        await bot._ensure_broadcaster_id()
        assert await bot.is_user_moderator("modguy") is True
        assert await bot.is_user_moderator("viewer1") is False
        assert await bot.is_user_moderator("viewer2") is False
        n = sum(1 for p, _ in fake.calls if p == "moderation/moderators")
        assert n == 1, "moderators fetched %d times; cached for a few minutes" % n
        bot._mods_cache_time = time.time() - 10 * 60   # cache expired
        await bot.is_user_moderator("viewer3")
        assert sum(1 for p, _ in fake.calls if p == "moderation/moderators") == 2
    finally:
        drop_tmpdir(tmp)


async def test_slow_helix_does_not_block_the_loop():
    tmp = new_tmpdir()
    try:
        bot, _fake = _bot_with(tmp, {"users": (200, {"data": [{"id": "1"}]}),
                                     "moderation/moderators": (200, {"data": []})}, delay=0.5)
        await bot._ensure_broadcaster_id()
        ticks = []

        async def ticker():
            for _ in range(8):
                ticks.append(time.monotonic())
                await asyncio.sleep(0.05)
        await asyncio.gather(bot.get_channel_moderators(), ticker())
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        assert max(gaps) < 0.2, "loop blocked for %.2fs" % max(gaps)
    finally:
        drop_tmpdir(tmp)
