"""Green tests: current queue behavior that must keep working after the fix.

Each test is an async function taking no arguments. The runner creates a
fresh event loop per test. Py3.8 compatible.
"""
import os
import sys
import time

from harness import (
    make_bot, make_command, make_sound_file, FakeMessage, FakeChannel,
    wait_until, new_tmpdir, drop_tmpdir,
)
from stubs import set_sound_duration, PYGAME

SONG = "SONG"
CATS = {SONG: {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}


def _mixer():
    return sys.modules["pygame"].mixer


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


async def test_queue_processes_sequentially():
    """Two queued sounds must play one after another, not in parallel."""
    tmp = new_tmpdir()
    try:
        for name in ("s1.mp3", "s2.mp3"):
            make_sound_file(tmp, name)
            set_sound_duration(os.path.join(tmp, name), 0.3)
        cmds = [
            make_command("!s1", SONG, SoundFile="s1.mp3"),
            make_command("!s2", SONG, SoundFile="s2.mp3"),
        ]
        bot, cm, cur = make_bot(tmp, cmds, CATS)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("bob", "!s2", ch))

        ok = await wait_until(lambda: len(bot.command_queues[SONG]._queue) == 0, timeout=5)
        assert ok, "queue did not drain in time"

        log = _mixer().Channel(1).play_log
        assert len(log) == 2, "expected 2 plays, got %d" % len(log)
        gap = log[1][0] - log[0][0]
        assert gap >= 0.25, "sounds overlapped: second started %.3fs after first" % gap
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_refund_on_full_queue():
    """When max_queue_size is reached, the command is rejected and points refunded."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.3)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 1, "audio_channel": 1}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Cost=5)]
        cur = None
        from harness import FakeCurrencyManager
        cur = FakeCurrencyManager({"alice": {"points": 50}})
        bot, cm, cur = make_bot(tmp, cmds, cats, currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("alice", "!s1", ch))

        assert len(bot.command_queues[SONG]._queue) == 1, "second item must be rejected"
        # Item 1 was legitimately charged (50-5=45); item 2 was rejected and
        # refunded, so the balance must be back to 45, not 40.
        assert cur.get_points("alice") == 45, "points must be refunded, got %s" % cur.get_points("alice")
        assert any("refunded" in m for m in ch.sent), "no refund message: %r" % ch.sent
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_clear_releases_semaphore():
    """!clear must drain the queue AND release the size semaphore."""
    tmp = new_tmpdir()
    try:
        for name in ("s1.mp3", "s2.mp3", "s3.mp3"):
            make_sound_file(tmp, name)
            set_sound_duration(os.path.join(tmp, name), 0.3)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 2, "audio_channel": 1}}
        cmds = [
            make_command("!s1", SONG, SoundFile="s1.mp3"),
            make_command("!s2", SONG, SoundFile="s2.mp3"),
            make_command("!s3", SONG, SoundFile="s3.mp3"),
        ]
        from harness import FakeCurrencyManager
        cur = FakeCurrencyManager({"mod": {"points": 0, "is_mod": True}})
        bot, cm, cur = make_bot(tmp, cmds, cats, currency=cur)
        ch = FakeChannel()
        # Pause the worker so items pile up deterministically.
        bot.queue_processing[SONG] = False
        for w in list(bot.queue_workers.values()):
            w.cancel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("bob", "!s2", ch))
        assert len(bot.command_queues[SONG]._queue) == 2

        await bot.event_message(FakeMessage("mod", "!clear SONG", ch))
        assert len(bot.command_queues[SONG]._queue) == 0, "queue not cleared"
        assert any("Cleared 2" in m for m in ch.sent), "no clear confirmation: %r" % ch.sent

        # Semaphore must be free again: a new command is accepted.
        await bot.event_message(FakeMessage("alice", "!s3", ch))
        assert len(bot.command_queues[SONG]._queue) == 1, "semaphore not released after clear"
    finally:
        drop_tmpdir(tmp)


async def test_skip_unblocks_worker():
    """!skip stops the current sound and the worker moves to the next item."""
    tmp = new_tmpdir()
    try:
        for name in ("s1.mp3", "s2.mp3"):
            make_sound_file(tmp, name)
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 2.0)
        set_sound_duration(os.path.join(tmp, "s2.mp3"), 0.1)
        cmds = [
            make_command("!s1", SONG, SoundFile="s1.mp3"),
            make_command("!s2", SONG, SoundFile="s2.mp3"),
        ]
        from harness import FakeCurrencyManager
        cur = FakeCurrencyManager({"mod": {"points": 0, "is_mod": True}})
        bot, cm, cur = make_bot(tmp, cmds, CATS, currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("bob", "!s2", ch))

        started = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=3)
        assert started, "first sound never started"
        await bot.event_message(FakeMessage("mod", "!skip SONG", ch))

        # The worker must pick up the second item promptly after the skip.
        done = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 2, timeout=3)
        assert done, "worker stuck after !skip (second sound never played)"
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_persist_snapshot_saved():
    """With persist_queue on, the remaining queue is saved after each item."""
    tmp = new_tmpdir()
    try:
        for name in ("s1.mp3", "s2.mp3"):
            make_sound_file(tmp, name)
            set_sound_duration(os.path.join(tmp, name), 0.2)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 0,
                       "audio_channel": 1, "persist_queue": True}}
        cmds = [
            make_command("!s1", SONG, SoundFile="s1.mp3"),
            make_command("!s2", SONG, SoundFile="s2.mp3"),
        ]
        bot, cm, cur = make_bot(tmp, cmds, cats)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("bob", "!s2", ch))

        ok = await wait_until(
            lambda: len(cm.config.get("queue_persistence", {}).get(SONG, [])) == 1,
            timeout=5,
        )
        assert ok, "persisted snapshot not written after first item"
        items = cm.config["queue_persistence"][SONG]
        assert items[0]["author"] == "bob", "wrong item persisted: %r" % items
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_queue_listing_command():
    """!queue GROUP lists pending items (position, author, command)."""
    tmp = new_tmpdir()
    try:
        for name in ("s1.mp3", "s2.mp3"):
            make_sound_file(tmp, name)
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.5)
        set_sound_duration(os.path.join(tmp, "s2.mp3"), 0.1)
        cmds = [
            make_command("!s1", SONG, SoundFile="s1.mp3"),
            make_command("!s2", SONG, SoundFile="s2.mp3"),
        ]
        from harness import FakeCurrencyManager
        cur = FakeCurrencyManager({"mod": {"points": 0, "is_mod": True}})
        bot, cm, cur = make_bot(tmp, cmds, CATS, currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("bob", "!s2", ch))
        await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=3)

        await bot.event_message(FakeMessage("mod", "!queue SONG", ch))
        listing = [m for m in ch.sent if "bob" in m and "!s2" in m]
        assert listing, "no queue listing for pending item: %r" % ch.sent
        # The pending item must still be in the queue after the listing.
        assert len(bot.command_queues[SONG]._queue) == 1, "listing drained the queue"
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_volume_command_saves_group_volume():
    """!volume GROUP N persists the group volume to config."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        from harness import FakeCurrencyManager
        cur = FakeCurrencyManager({"mod": {"points": 0, "is_mod": True}})
        bot, cm, cur = make_bot(tmp, cmds, CATS, currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("mod", "!volume SONG 50", ch))
        vol = cm.config["audio_categories"][SONG].get("volume")
        assert vol == 0.5, "group volume not saved, got %r" % vol
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_cooldown_applied_for_queued_commands():
    """Cooldowns are enforced at enqueue time for queued commands."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Cooldown=1)]
        bot, cm, cur = make_bot(tmp, cmds, CATS)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await bot.event_message(FakeMessage("bob", "!s1", ch))
        assert len(bot.command_queues[SONG]._queue) == 1, "cooldown not enforced"
        assert any("cooldown" in m for m in ch.sent), "no cooldown message: %r" % ch.sent
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)