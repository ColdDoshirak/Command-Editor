"""Step 3.1: one pipeline for custom commands, queued commands and !random.

- cooldown race: the cooldown was set only after the reply was sent, so two
  quick calls both ran (and both paid)
- !random played past the group's queue/channel, did not refund and did
  not count the use

Py3.8 compatible.
"""
import asyncio
import os
import sys

from harness import (make_bot, make_command, make_sound_file, FakeMessage, FakeCurrencyManager,
                     wait_until, new_tmpdir, drop_tmpdir)
from stubs import set_sound_duration

from core.system_commands import DEFAULT_SYSTEM_COMMANDS

SONG = "SONG"
CATS = {SONG: {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}


class SlowChannel(object):
    def __init__(self, delay=0.2):
        self.sent = []
        self.delay = delay

    async def send(self, text):
        await asyncio.sleep(self.delay)
        self.sent.append(text)


def _random_sys(group):
    d = next(dict(x) for x in DEFAULT_SYSTEM_COMMANDS if x["command"] == "!random")
    d.update(enabled=True, was_manually_enabled=True, random_group=group, cooldown=0,
             user_cooldown=0, show_picked_command=False)
    return d


def _mixer():
    return sys.modules["pygame"].mixer


async def _stop(bot):
    for g in list(bot.queue_processing):
        bot.queue_processing[g] = False
    for w in list(bot.queue_workers.values()):
        w.cancel()
        try:
            await w
        except BaseException:
            pass


async def test_cooldown_race_two_quick_calls_run_once():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!hi", Response="hello", Cooldown=1, Cost=5)
        cur = FakeCurrencyManager({"a": {"points": 100}, "b": {"points": 100}})
        bot, _cm, _ = make_bot(tmp, [cmd], currency=cur)
        ch = SlowChannel()
        await asyncio.gather(bot.event_message(FakeMessage("a", "!hi", ch)),
                             bot.event_message(FakeMessage("b", "!hi", ch)))
        assert sum("hello" in s for s in ch.sent) == 1, ch.sent
        assert cur.get_points("a") + cur.get_points("b") == 195, "only one call may pay"
        assert cmd["Count"] == 1, cmd["Count"]
    finally:
        drop_tmpdir(tmp)


async def test_failed_command_rolls_back_cooldown_and_refunds():
    tmp = new_tmpdir()
    try:
        # sound file missing -> the command can't run
        cmd = make_command("!fx", SoundFile=os.path.join(tmp, "missing.mp3"), Cooldown=1, Cost=5)
        cur = FakeCurrencyManager({"a": {"points": 10}})
        bot, _cm, _ = make_bot(tmp, [cmd], currency=cur)
        await bot.event_message(FakeMessage("a", "!fx", SlowChannel(0)))
        assert cur.get_points("a") == 10, "refunded"
        assert "fx" not in bot.global_cooldowns, "a failed command must not start the cooldown"
    finally:
        drop_tmpdir(tmp)


async def test_random_uses_the_group_queue_and_counts():
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "song.mp3")
        set_sound_duration(os.path.join(tmp, "song.mp3"), 0.3)
        cmd = make_command("!song", SONG, SoundFile="song.mp3")
        bot, cm, _ = make_bot(tmp, [cmd], CATS)
        cm.save_system_commands([_random_sys(SONG)])
        await bot.event_message(FakeMessage("a", "!random", SlowChannel(0)))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, 2)
        assert ok, "!random must play on the group's channel through its queue"
        await wait_until(lambda: cmd["Count"] == 1, 2)
        assert cmd["Count"] == 1, cmd["Count"]
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_random_response_command_counts_and_respects_cost():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!joke", "FUN", Response="ha", Cost=50)
        cur = FakeCurrencyManager({"a": {"points": 10}})
        bot, cm, _ = make_bot(tmp, [cmd], currency=cur)
        cm.save_system_commands([_random_sys("FUN")])
        ch = SlowChannel(0)
        await bot.event_message(FakeMessage("a", "!random", ch))
        assert not any(s == "ha" or s.endswith("ha") for s in ch.sent), ch.sent
        assert any("Not enough points" in s for s in ch.sent), ch.sent
        cur.users["a"]["points"] = 100
        await bot.event_message(FakeMessage("a", "!random", ch))
        assert cmd["Count"] == 1 and cur.get_points("a") == 50, (cmd["Count"], cur.get_points("a"))
    finally:
        drop_tmpdir(tmp)
