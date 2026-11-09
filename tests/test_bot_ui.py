"""Step 4.2: the bot reports to the window through one Qt-free object
(bot.ui_port.BotUi); the window talks to the bot only through
ui/bot_bridge.py.

Py3.8 compatible.
"""
import asyncio
import os
import re

from harness import (make_bot, make_command, make_real_currency, FakeMessage, FakeChannel,
                     FakeCurrencyManager, new_tmpdir, drop_tmpdir, REPO_DIR)

from bot.ui_port import BotUi


class RecordingUi(BotUi):
    def __init__(self):
        self.calls = []

    def chat(self, text):
        self.calls.append(("chat", text))

    def all_viewers(self, viewers):
        self.calls.append(("all_viewers", list(viewers)))

    def active_viewers(self, viewers):
        self.calls.append(("active_viewers", list(viewers)))

    def stream_status(self, is_live):
        self.calls.append(("stream_status", is_live))

    def moderators(self, mods):
        self.calls.append(("moderators", list(mods)))

    def command_used(self, cmd):
        self.calls.append(("command_used", cmd["Command"]))


def _read(rel):
    with open(os.path.join(REPO_DIR, rel), encoding="utf-8") as f:
        return f.read()


async def test_bot_has_one_ui_port():
    tmp = new_tmpdir()
    try:
        bot, _cm, _ = make_bot(tmp, [])
        assert isinstance(bot.ui, BotUi), "the bot reports through bot.ui"
        for old in ("signal_handler", "message_callback", "on_command_used"):
            assert not hasattr(bot, old), "old channel to the window still there: " + old
    finally:
        drop_tmpdir(tmp)


async def test_chat_lines_and_command_use_reach_the_ui():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!hi", Response="hello")
        bot, _cm, _ = make_bot(tmp, [cmd])
        ui = RecordingUi()
        bot.ui = ui
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!hi", ch))
        assert ("chat", "alice: !hi") in ui.calls, ui.calls
        assert ("command_used", "!hi") in ui.calls, ui.calls
        bot._ui_message("service line")
        assert ("chat", "service line") in ui.calls, ui.calls
    finally:
        drop_tmpdir(tmp)


async def test_usernotice_reward_line_reaches_the_ui():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.settings.update({"raid_points": 10, "raid_points_per_viewer": 1})
        bot, _cm, _ = make_bot(tmp, [], currency=cur)
        ui = RecordingUi()
        bot.ui = ui
        await bot.event_raw_usernotice(FakeChannel(), {"msg-id": "raid", "login": "raider",
                                                       "msg-param-viewerCount": "5"})
        assert any(k == "chat" and "raider" in v for k, v in ui.calls), ui.calls
    finally:
        drop_tmpdir(tmp)


async def test_a_failing_ui_never_breaks_a_command():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!hi", Response="hello")
        bot, _cm, _ = make_bot(tmp, [cmd], currency=FakeCurrencyManager())

        class Broken(BotUi):
            def chat(self, text):
                raise RuntimeError("window gone")

            def command_used(self, cmd):
                raise RuntimeError("window gone")
        bot.ui = Broken()
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!hi", ch))
        assert any("hello" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_bot_code_has_no_qt():
    for rel in ["bot/" + n for n in sorted(os.listdir(os.path.join(REPO_DIR, "bot")))
                                    if n.endswith(".py")]:
        src = _read(rel)
        assert "PyQt5" not in src, rel + " imports Qt"
        assert ".emit(" not in src, rel + " emits Qt signals itself"


# UI modules that may hold a reference to the bot. Only the bridge may
# schedule work on the bot loop.
UI_MODULES = ["command_editor.py"] + ["ui/" + n for n in sorted(os.listdir(os.path.join(REPO_DIR, "ui")))
                                     if n.endswith(".py") and n != "bot_bridge.py"]


async def test_only_the_bridge_touches_the_bot_loop():
    pat = re.compile(r"run_coroutine_threadsafe|call_soon_threadsafe")
    bad = [rel for rel in UI_MODULES if os.path.exists(os.path.join(REPO_DIR, rel))
           and pat.search(_read(rel))]
    assert not bad, "schedule bot work through ui/bot_bridge.py, not directly: %s" % bad
    assert pat.search(_read("ui/bot_bridge.py"))
