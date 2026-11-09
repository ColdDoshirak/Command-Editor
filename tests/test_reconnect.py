"""Step 0.3 / C2: reconnecting is left to twitchio (decision 4, option A).

The old self-made reconnect cleared initialized_event and did not set it
again on several paths (and its checks looked for `self._ws`, which
twitchio 2.10 does not have), so the bot went silent for good. Now the bot
only watches the connection and tells the UI; twitchio reconnects itself.

Py3.8 compatible.
"""
import asyncio
from types import SimpleNamespace

from harness import make_bot, make_command, FakeMessage, FakeChannel, new_tmpdir, drop_tmpdir
from bot.ui_port import BotUi


class _FakeConnection(object):
    def __init__(self):
        self.alive = True
        self.is_ready = asyncio.Event()
        self.is_ready.set()

    @property
    def is_alive(self):
        return self.alive


def _ui(bot):
    said = []
    ui = BotUi()
    ui.chat = said.append
    bot.ui = ui
    return said


async def test_c2_connection_loss_never_silences_the_bot():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!hi", Response="hello")
        bot, _cm, _cur = make_bot(tmp, [cmd])
        said = _ui(bot)
        conn = _FakeConnection()
        bot._connection = conn
        bot.is_running = True
        bot._watch_interval = 0.02
        watcher = asyncio.ensure_future(bot._check_connection())
        try:
            await asyncio.sleep(0.1)
            conn.alive = False
            conn.is_ready.clear()
            await asyncio.sleep(0.15)
            assert any("lost" in s.lower() for s in said), said
            assert bot.initialized_event.is_set(), "the bot must keep handling chat"
            conn.alive = True
            conn.is_ready.set()
            await asyncio.sleep(0.15)
            assert any("restored" in s.lower() for s in said), said
            ch = FakeChannel()
            await asyncio.wait_for(bot.event_message(FakeMessage("viewer", "!hi", ch)), 2)
            assert any("hello" in s for s in ch.sent), ch.sent
        finally:
            bot.is_running = False
            watcher.cancel()
            try:
                await watcher
            except BaseException:
                pass
    finally:
        drop_tmpdir(tmp)


async def test_c2_twitch_reconnect_request_keeps_bot_ready():
    tmp = new_tmpdir()
    try:
        bot, _cm, _cur = make_bot(tmp, [])
        said = _ui(bot)
        await bot.event_reconnect()
        assert bot.initialized_event.is_set()
        assert any("reconnect" in s.lower() for s in said), said
    finally:
        drop_tmpdir(tmp)


async def test_c2_no_self_made_reconnect_left():
    tmp = new_tmpdir()
    try:
        bot, _cm, _cur = make_bot(tmp, [])
        for name in ("_reconnect", "_create_new_loop_and_reconnect"):
            assert not hasattr(bot, name), name
    finally:
        drop_tmpdir(tmp)
