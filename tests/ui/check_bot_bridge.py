"""C4 / step 4.2: the window and the bot meet only in ui/bot_bridge.py.

A fake bot runs on a real asyncio loop in its own thread (as TwitchTab.run_bot
does). Everything the window asks of the bot must run in that thread;
everything the bot reports must reach the widgets in the UI thread.
"""
import asyncio
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


class FakeBot(object):
    """Only what the window calls; records the thread of every call."""

    def __init__(self, loop):
        self.loop = loop
        self.ui = None
        self.channel = "testchan"
        self.nick = "botnick"
        self.is_running = True
        self.active_users = ["fallback"]
        self.queue_paused = set()
        self.command_queues = {"SONG": None}
        self.viewers_error = None
        self.calls = []

    def _rec(self, name, *args):
        self.calls.append((name, threading.current_thread().name) + args)

    async def get_all_viewers(self):
        self._rec("get_all_viewers")
        if self.viewers_error is not None:
            raise self.viewers_error
        return ["bob", "alice"]

    async def check_if_live(self):
        self._rec("check_if_live")
        return True

    async def send_chat(self, text):
        self._rec("send_chat", text)
        return True

    async def get_channel_moderators(self):
        self._rec("get_channel_moderators")
        return []

    async def reload_audio_categories(self):
        self._rec("reload_audio_categories")

    def update_commands(self, commands):
        self._rec("update_commands", len(commands))

    def set_interruption(self, enabled):
        self._rec("set_interruption", enabled)

    def set_show_interruption_message(self, enabled):
        self._rec("set_show_interruption_message", enabled)

    def queue_snapshot(self, group):
        return {"current": None, "pending": [], "paused": group in self.queue_paused,
                "max": 0, "free": None, "enabled": True}

    def queue_pending_count(self, group):
        return 0

    def set_queue_paused(self, group, paused):
        self._rec("set_queue_paused", group, paused)

    def stop(self):
        self._rec("stop")
        self.is_running = False


def body(k):
    from PyQt5.QtCore import Qt
    w, check, pump = k.w, k.check, k.pump
    tab = w.twitch_tab
    main = threading.current_thread()

    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, name="bot-loop", daemon=True)
    t.start()
    bot = FakeBot(loop)

    def ran(name):
        return [c for c in bot.calls if c[0] == name]

    def only_in_loop(name):
        got = ran(name)
        return bool(got) and all(c[1] == "bot-loop" for c in got)

    try:
        tab.bot = bot
        check("attached bot reports to the bridge", bot.ui is tab.bridge)

        # ---- window asks, bot answers --------------------------------------------------
        seen = []

        def spy(**kw):
            seen.append((threading.current_thread(), sorted(kw.get("all_viewers") or [])))
        w.currency_manager.process_currency_update = spy

        tab.refresh_viewers(); pump(300)
        check("viewers: requested in the bot thread", only_in_loop("get_all_viewers"), bot.calls)
        check("viewers: applied once, in the UI thread",
              seen == [(main, ["alice", "bob"])], seen)
        items = [tab.all_viewers_list.item(i).text() for i in range(tab.all_viewers_list.count())]
        check("viewers: list widget filled", items == ["alice", "bob"], items)

        seen[:] = []
        bot.viewers_error = RuntimeError("helix")
        tab.refresh_viewers(); pump(300)
        check("viewers: failed request falls back to active users, in the UI thread",
              seen == [(main, ["fallback"])], seen)
        bot.viewers_error = None

        tab.check_connection(); pump(300)
        check("check connection: asked in the bot thread", only_in_loop("check_if_live"), bot.calls)
        check("check connection: status shown", "LIVE" in tab.stream_status.text(),
              tab.stream_status.text())

        tab.message_input.setText("hello chat")
        tab.send_message(); pump(300)
        check("send message: sent from the bot thread",
              only_in_loop("send_chat") and ran("send_chat")[0][2] == "hello chat", bot.calls)
        check("send message: input cleared and echoed",
              tab.message_input.text() == "" and "botnick: hello chat" in tab.chat_display.toPlainText())

        # ---- bot reports, window shows -------------------------------------------------
        got = []
        tab.bridge.chat_line.connect(lambda s: got.append((threading.current_thread(), s)))
        loop.call_soon_threadsafe(bot.ui.chat, "line from the bot")
        loop.call_soon_threadsafe(bot.ui.stream_status, False)
        loop.call_soon_threadsafe(bot.ui.all_viewers, ["zed"])
        pump(300)
        check("bot chat line arrives in the UI thread", got == [(main, "line from the bot")], got)
        check("bot chat line shown", "line from the bot" in tab.chat_display.toPlainText())
        check("bot stream status shown", "OFFLINE" in tab.stream_status.text(), tab.stream_status.text())
        check("bot viewer list shown", tab.all_viewers_list.count() == 1
              and tab.all_viewers_list.item(0).text() == "zed")
        loop.call_soon_threadsafe(bot.ui.active_viewers, ["talker"])
        pump(300)
        check("active chatters reach the tab", tab.active_users == ["talker"]
              and tab.active_viewers_list.count() == 1, tab.active_users)

        # ---- settings and edits reach the running bot through its loop -----------------
        w.on_interruption_toggle(Qt.Checked)
        w.on_show_message_toggle(Qt.Unchecked)
        w.update_commands()
        tab.reload_bot_audio_categories()
        pump(300)
        for name in ("set_interruption", "set_show_interruption_message",
                     "update_commands", "reload_audio_categories"):
            check("%s runs in the bot thread" % name, only_in_loop(name), bot.calls)

        q = w.queue_control_tab
        q.group_combo.addItem("SONG", "SONG")   # this fixture has no queue groups
        q.group_combo.setCurrentIndex(q.group_combo.count() - 1); pump(100)
        q.toggle_pause(); pump(300)
        check("queue tab: pause runs in the bot thread", only_in_loop("set_queue_paused"), bot.calls)

        # ---- disconnect -------------------------------------------------------------------
        tab.disconnect(); pump(200)
        check("disconnect stops the bot and detaches it",
              ran("stop") and tab.bot is None and bot.ui is not tab.bridge, (bot.calls[-1:], bot.ui))
        n = len(bot.calls)
        check("no bot: nothing is scheduled", tab.bridge.call("set_interruption", True) is False
              and tab.bridge.submit("check_if_live") is False)
        tab.refresh_viewers(); tab.check_connection(); tab.reload_bot_audio_categories()
        pump(200)
        check("no bot: window actions are harmless", len(bot.calls) == n, bot.calls[n:])
    finally:
        tab.bot = None
        loop.call_soon_threadsafe(loop.stop)
        t.join(2)


kit.start(body, delay_ms=400)
