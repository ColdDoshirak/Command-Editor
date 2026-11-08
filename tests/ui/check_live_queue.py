"""Real GUI + real TwitchBot in its own thread (network stubbed) + real
pygame audio: queue tab, remove/move/skip/pause, !volume during a track,
Group Settings save while playing."""
import asyncio
import os
import sys
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
NAMES = fixture.queue_set(DATA)
kit = uikit.boot(DATA, OUT)


class FakeChannel(object):
    def __init__(self, delay=0.0):
        self.sent = []
        self.delay = delay

    async def send(self, text):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(text)


def msg(user, text, ch=None):
    return SimpleNamespace(author=SimpleNamespace(name=user), content=text,
                           channel=ch or FakeChannel(), echo=False)


box = {}


def run_bot(w):
    """Like TwitchTab.run_bot, without connecting to Twitch."""
    from twitch_bot import TwitchBot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot = TwitchBot(channel="testchan", config_manager=w.config_manager,
                    currency_manager=w.currency_manager)
    bot.update_commands(w.commands)

    async def is_mod(name):
        return True
    bot.is_user_moderator = is_mod

    async def ready():
        bot.loop = asyncio.get_event_loop()
        bot.init_queues()
        bot.initialized_event.set()
    loop.run_until_complete(ready())
    box["bot"] = bot
    box["loop"] = loop
    loop.run_forever()


def body(k):
    import pygame
    w, check, pump, shot = k.w, k.check, k.pump, k.shot
    threading.Thread(target=run_bot, args=(w,), daemon=True).start()
    t0 = time.time()
    while "bot" not in box and time.time() - t0 < 10:
        pump(50)
    bot, loop = box["bot"], box["loop"]
    try:
        _body(k, bot, loop, pygame)
    finally:
        loop.call_soon_threadsafe(loop.stop)


def _body(k, bot, loop, pygame):
    w, check, pump, shot = k.w, k.check, k.pump, k.shot
    w.twitch_tab.bot = bot

    def send(m):
        return asyncio.run_coroutine_threadsafe(bot.event_message(m), loop).result(5)

    def pending():
        return [p["command"] for p in bot.queue_snapshot("SONG")["pending"]]

    for i, n in enumerate(NAMES):
        send(msg("viewer%d" % i, "!" + n))
    pump(500)
    ch1 = pygame.mixer.Channel(1)
    check("real audio playing on channel 1", ch1.get_busy())
    snap = bot.queue_snapshot("SONG")
    check("first item is current",
          snap["current"] and snap["current"]["command"] == "alpha", snap["current"])
    check("4 pending", len(snap["pending"]) == 4, len(snap["pending"]))

    w.tab_widget.setCurrentIndex(7); pump(700)
    qc = w.queue_control_tab
    check("queue tab shows now playing", qc.now_title.text() == "!alpha", qc.now_title.text())
    check("queue tab lists pending", qc.queue_list.count() == 4, qc.queue_list.count())
    shot("live_midnight_queue")

    qc.queue_list.setCurrentRow(2)  # delta
    qc.remove_selected(); pump(400)
    check("remove pending keeps current playing",
          ch1.get_busy() and bot.queue_snapshot("SONG")["current"]["command"] == "alpha")
    check("delta removed", pending() == ["bravo", "charlie", "echo"], pending())

    qc.queue_list.setCurrentRow(2)
    qc.move_selected(-1); pump(400)
    check("move up", pending() == ["bravo", "echo", "charlie"], pending())

    # !volume during playback with a slow chat channel (real threading.Lock)
    slow = FakeChannel(delay=1.0)
    fut = asyncio.run_coroutine_threadsafe(
        bot.event_message(msg("mod", "!volume SONG 30", slow)), loop)
    pump(1300)
    try:
        fut.result(3)
        alive = asyncio.run_coroutine_threadsafe(asyncio.sleep(0, result=True), loop).result(2)
    except Exception:
        alive = False
    check("!volume during track: loop alive (no deadlock)", alive)
    check("!volume reply", slow.sent and "30%" in slow.sent[0], slow.sent)

    cur_before = bot.queue_snapshot("SONG")["current"]
    qc.skip_current(); pump(500)
    cur_after = bot.queue_snapshot("SONG")["current"]
    check("skip moves to next",
          cur_before and cur_after and cur_after["command"] != cur_before["command"],
          (cur_before, cur_after))

    qc.toggle_pause(); pump(300)
    order = pending()
    t1 = time.time()
    while bot.queue_snapshot("SONG")["current"] and time.time() - t1 < 7:
        pump(100)
    pump(400)
    check("paused: nothing playing",
          bot.queue_snapshot("SONG")["current"] is None and not ch1.get_busy())
    check("paused: order kept", pending() == order, order)
    shot("live_midnight_paused")

    qc.toggle_pause(); pump(800)
    playing = bot.queue_snapshot("SONG")["current"]
    w.group_settings_tab.refresh_groups()
    w.group_settings_tab.save_settings(); pump(600)
    now = bot.queue_snapshot("SONG")["current"]
    check("save settings keeps track playing",
          ch1.get_busy() and playing is not None and now is not None
          and now["id"] == playing["id"], (playing, now))
    check("worker alive after save", not bot.queue_workers["SONG"].done())

    for n in NAMES[:3]:
        send(msg("late_" + n, "!" + n))
    w.tab_widget.setCurrentIndex(0); pump(700)
    shot("live_midnight_commands_bar")
    for t in ("sidebar", "classic"):
        w.apply_theme(t); w.tab_widget.setCurrentIndex(7); pump(700)
        shot("live_%s_queue" % t)
    w.save_commands()
    played = sum(c.get("Count", 0) for c in w.commands)
    check("usage counts recorded", played >= 2, played)


kit.start(body, delay_ms=800)
