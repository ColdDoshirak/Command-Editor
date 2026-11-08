"""Regression tests for the queue rework (v2).

Each test reproduces a bug that existed before the rework:
  - saving Group Settings / toggling a queue left the queue dead
  - "Skip current" in Queue Control skipped the NEXT item
  - removing a pending item stopped the track that was playing
  - pausing re-ordered the queue
  - "!volume 0" did not mute
  - "!volume" during playback deadlocked the bot (threading.Lock over await)
  - "!queue GROUP" sent a multi-line IRC message, "!!cmd" doubled
  - "!clear"/"!volume" failed for mixed-case group names
  - update_commands() from the UI thread touched asyncio objects there

Py3.8 compatible.
"""
import asyncio
import copy
import os
import sys
import threading

from harness import (
    make_bot, make_command, make_sound_file, FakeMessage, FakeChannel,
    FakeCurrencyManager, wait_until, new_tmpdir, drop_tmpdir,
)
from stubs import set_sound_duration

SONG = "SONG"
CATS = {SONG: {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}


def _mixer():
    return sys.modules["pygame"].mixer


def _played():
    return [os.path.basename(str(p)) for _, p in _mixer().Channel(1).play_log]


async def _stop_bot(bot):
    for group in list(bot.queue_processing):
        bot.queue_processing[group] = False
    for group, worker in list(bot.queue_workers.items()):
        if not worker.done():
            worker.cancel()
            try:
                await worker
            except BaseException:
                pass


async def _bot_with_songs(tmp, n=3, dur=0.4, cats=None, mods=("mod",)):
    cmds = []
    for i in range(n):
        name = "s%d.mp3" % i
        make_sound_file(tmp, name)
        set_sound_duration(os.path.join(tmp, name), dur)
        cmds.append(make_command("!s%d" % i, SONG, SoundFile=name))
    users = dict((m, {"points": 0, "is_mod": True}) for m in mods)
    cur = FakeCurrencyManager(users)
    bot, cm, cur = make_bot(tmp, cmds, copy.deepcopy(cats or CATS), currency=cur)

    async def _is_mod(name):
        return name in mods
    bot.is_user_moderator = _is_mod
    return bot, cm, cur


async def _enqueue_all(bot, n):
    for i in range(n):
        await bot.event_message(FakeMessage("u%d" % i, "!s%d" % i, FakeChannel()))


async def test_v2_disable_then_enable_queue_still_plays():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp)
        cats = cm.get_audio_categories()
        cats[SONG]["queue_enabled"] = False
        cm.save_audio_categories(cats)
        bot.update_commands(bot._commands_list)
        cats[SONG]["queue_enabled"] = True
        cm.save_audio_categories(cats)
        bot.update_commands(bot._commands_list)
        await bot.event_message(FakeMessage("a", "!s0", FakeChannel()))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=2)
        assert ok, "queue dead after disable -> enable"
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_disabled_queue_drains_paid_items():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.2)
        await _enqueue_all(bot, 3)
        cats = cm.get_audio_categories()
        cats[SONG]["queue_enabled"] = False
        cm.save_audio_categories(cats)
        await bot.reload_audio_categories()
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) == 3, timeout=4)
        assert ok, "paid items stranded after disabling queue: %r" % _played()
        ok = await wait_until(lambda: bot.queue_workers[SONG].done(), timeout=2)
        assert ok, "worker of a disabled, drained queue must exit"
    finally:
        drop_tmpdir(tmp)


async def test_v2_skip_current_skips_playing_item():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.6)
        await _enqueue_all(bot, 3)
        await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1)
        await asyncio.sleep(0.1)
        assert bot.skip_queue_current(SONG)
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 2, timeout=1)
        assert ok, "skip did not move on to the next item"
        assert _played()[:2] == ["s0.mp3", "s1.mp3"], (
            "skip must stop the CURRENT item and keep the next: %r" % _played())
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_skip_suppresses_response():
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s.mp3")
        set_sound_duration(os.path.join(tmp, "s.mp3"), 0.5)
        cmds = [make_command("!s", SONG, SoundFile="s.mp3", Response="done!")]
        bot, cm, cur = make_bot(tmp, cmds, copy.deepcopy(CATS))
        ch = FakeChannel()
        await bot.event_message(FakeMessage("a", "!s", ch))
        await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1)
        bot.skip_queue_current(SONG)
        await wait_until(lambda: SONG not in bot.queue_current, timeout=2)
        assert "done!" not in ch.sent, "skipped item still sent its response"
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_remove_pending_does_not_stop_current():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.6)
        await _enqueue_all(bot, 3)
        await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1)
        await asyncio.sleep(0.05)
        snap = bot.queue_snapshot(SONG)
        target = [p for p in snap["pending"] if p["command"] == "s2"][0]
        assert bot.remove_from_queue_by_id(SONG, target["id"])
        assert _mixer().Channel(1).get_busy(), "removing a pending item stopped the current track"
        assert [p["command"] for p in bot.queue_snapshot(SONG)["pending"]] == ["s1"]
        assert bot.command_queues[SONG]._unfinished_tasks == 2  # current + s1
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_pause_keeps_order_and_resume_continues():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.1)
        await asyncio.sleep(0.1)  # worker idle
        bot.set_queue_paused(SONG, True)
        await _enqueue_all(bot, 3)
        await asyncio.sleep(0.4)
        order = [c["Command"] for _, c in bot.command_queues[SONG]._queue]
        assert order == ["!s0", "!s1", "!s2"], "pause re-ordered the queue: %r" % order
        assert not _mixer().Channel(1).play_log, "paused queue played something"
        bot.set_queue_paused(SONG, False)
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) == 3, timeout=3)
        assert ok and _played() == ["s0.mp3", "s1.mp3", "s2.mp3"], _played()
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_reorder_and_move():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, n=4, dur=0.1)
        bot.set_queue_paused(SONG, True)
        await asyncio.sleep(0.1)
        await _enqueue_all(bot, 4)
        ids = [p["id"] for p in bot.queue_snapshot(SONG)["pending"]]
        bot.reorder_queue_by_ids(SONG, [ids[3], ids[0]])
        names = [p["command"] for p in bot.queue_snapshot(SONG)["pending"]]
        assert names == ["s3", "s0", "s1", "s2"], names
        bot.move_queue_item(SONG, ids[2], -1)  # s2 up one
        names = [p["command"] for p in bot.queue_snapshot(SONG)["pending"]]
        assert names == ["s3", "s0", "s2", "s1"], names
        assert bot.command_queues[SONG]._unfinished_tasks == 4
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_volume_zero_mutes_group():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.1)
        await bot.event_message(FakeMessage("mod", "!volume SONG 0", FakeChannel()))
        await bot.event_message(FakeMessage("a", "!s0", FakeChannel()))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=2)
        assert ok
        vol = _mixer().Channel(1).last_sound._volume
        assert vol == 0.0, "!volume 0 must mute, played at %r" % vol
        await bot.event_message(FakeMessage("mod", "!volume SONG 40", FakeChannel()))
        assert abs(bot._group_volume_override(SONG) - 0.4) < 1e-9
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


class _StrictLock(object):
    """threading.Lock that fails instead of deadlocking."""

    def __init__(self):
        self._lock = threading.Lock()

    def __enter__(self):
        if not self._lock.acquire(timeout=1.0):
            raise AssertionError("active_sounds_lock deadlock")
        return self

    def __exit__(self, *exc):
        self._lock.release()
        return False


async def test_v2_volume_during_playback_no_deadlock():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.3)
        bot.active_sounds_lock = _StrictLock()
        errors = []

        class SlowChannel(FakeChannel):
            async def send(self, text):
                await asyncio.sleep(0.6)  # the track ends meanwhile
                self.sent.append(text)

        await bot.event_message(FakeMessage("a", "!s0", FakeChannel()))
        await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1)
        ch = SlowChannel()
        try:
            await bot.event_message(FakeMessage("mod", "!volume SONG 40", ch))
        except AssertionError as e:
            errors.append(str(e))
        await asyncio.sleep(0.2)
        assert not errors, errors
        assert ch.sent and "applied to current track" in ch.sent[0], ch.sent
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_queue_listing_single_line_and_limit():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, n=3, dur=3)
        for k in range(40):
            await bot.event_message(FakeMessage("user%02d" % k, "!s%d" % (k % 3), FakeChannel()))
        await wait_until(lambda: SONG in bot.queue_current)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("x", "!queue song", ch))
        msg = ch.sent[-1]
        assert "\n" not in msg, "multi-line IRC message: %r" % msg
        assert len(msg) <= 500, "reply longer than Twitch limit: %d" % len(msg)
        assert "!!" not in msg, "doubled prefix: %r" % msg
        assert "now: !s0" in msg, msg
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_mixed_case_group_commands():
    tmp = new_tmpdir()
    try:
        cats = {"Song": {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}
        make_sound_file(tmp, "s0.mp3")
        set_sound_duration(os.path.join(tmp, "s0.mp3"), 2)
        bot, cm, cur = make_bot(tmp, [make_command("!s0", "Song", SoundFile="s0.mp3")], cats)

        async def _is_mod(name):
            return True
        bot.is_user_moderator = _is_mod
        for _ in range(3):
            await bot.event_message(FakeMessage("a", "!s0", FakeChannel()))
        await wait_until(lambda: "Song" in bot.queue_current)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("mod", "!clear SONG", ch))
        await bot.event_message(FakeMessage("mod", "!volume song 50", ch))
        await bot.event_message(FakeMessage("mod", "!skip sOnG", ch))
        assert "Cleared 2" in ch.sent[0], ch.sent
        assert "set to 50%" in ch.sent[1], ch.sent
        assert "Skipped" in ch.sent[2], ch.sent
        assert set(cm.get_audio_categories()) == {"Song"}, (
            "phantom category created: %r" % list(cm.get_audio_categories()))
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_max_size_change_applies_live():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=2)
        await _enqueue_all(bot, 2)  # 1 playing + 1 pending
        cats = cm.get_audio_categories()
        cats[SONG]["max_queue_size"] = 2
        cm.save_audio_categories(cats)
        await bot.reload_audio_categories()
        ch = FakeChannel()
        await bot.event_message(FakeMessage("late", "!s2", ch))
        assert any("full" in m for m in ch.sent), "new limit not applied: %r" % ch.sent
        assert bot.queue_semaphores[SONG]._value == 0
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_update_commands_from_foreign_thread():
    """The editor calls update_commands() from the Qt thread. Queue objects
    must still be created in (and the worker run on) the bot loop."""
    tmp = new_tmpdir()
    try:
        bot, cm, cur = await _bot_with_songs(tmp, dur=0.1)
        cats = cm.get_audio_categories()
        cats["EXTRA"] = {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 2}
        cm.save_audio_categories(cats)
        make_sound_file(tmp, "x.mp3")
        cmds = list(bot._commands_list) + [make_command("!x", "EXTRA", SoundFile="x.mp3")]
        t = threading.Thread(target=bot.update_commands, args=(cmds,))
        t.start()
        while t.is_alive():
            await asyncio.sleep(0.01)
        ok = await wait_until(lambda: "EXTRA" in bot.command_queues, timeout=2)
        assert ok, "queue for new group not created"
        assert bot.command_queues["EXTRA"]._loop is asyncio.get_event_loop(), (
            "queue bound to the wrong event loop")
        await bot.event_message(FakeMessage("a", "!x", FakeChannel()))
        ok = await wait_until(lambda: len(_mixer().Channel(2).play_log) == 1, timeout=2)
        assert ok, "new group's queue does not play"
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_v2_announce_position_optional():
    tmp = new_tmpdir()
    try:
        cats = copy.deepcopy(CATS)
        cats[SONG]["announce_enqueue"] = True
        bot, cm, cur = await _bot_with_songs(tmp, dur=2, cats=cats)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("a", "!s0", ch))
        await bot.event_message(FakeMessage("b", "!s1", ch))
        assert any("position 2" in m for m in ch.sent), ch.sent
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)
