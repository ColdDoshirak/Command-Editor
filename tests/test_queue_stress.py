"""Stress tests: 100 concurrent viewers hammering the queue.

Simulates the real use case (a stream with ~100 active viewers) that the
small unit tests do not cover:
  - FIFO order under 100 concurrent messages
  - exactly-once charging at scale
  - queue-limit semaphore correctness under a flood (refunds, no permit leak)
  - !queue listing racing with an active flood

Py3.8 compatible (no walrus, no PEP 585/604).
"""
import asyncio
import os
import sys

from harness import (
    make_bot, make_command, make_sound_file, FakeMessage, FakeChannel,
    FakeCurrencyManager, wait_until, new_tmpdir, drop_tmpdir,
)
from stubs import set_sound_duration

SONG = "SONG"
N_USERS = 100
COST = 10
START_POINTS = 100


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


def _make_users(n):
    users = {}
    for i in range(n):
        users["user%03d" % i] = {"points": START_POINTS}
    return users


def _make_commands(tmp, n):
    cmds = []
    for i in range(n):
        name = "stress%03d.mp3" % i
        make_sound_file(tmp, name)
        set_sound_duration(os.path.join(tmp, name), 0.1)
        cmds.append(make_command("!s%03d" % i, SONG,
                                 SoundFile=name, Cost=COST))
    return cmds


async def test_stress_100_users_fifo_and_charging():
    """100 viewers send paid commands at once: FIFO order, charged exactly
    once each, queue fully drained, no deadlock."""
    tmp = new_tmpdir()
    try:
        cmds = _make_commands(tmp, N_USERS)
        cur = FakeCurrencyManager(_make_users(N_USERS))
        bot, cm, cur = make_bot(tmp, cmds, {SONG: {"queue_enabled": True,
                                                   "max_queue_size": 0,
                                                   "audio_channel": 1}},
                                currency=cur)
        ch = FakeChannel()
        # Fire all 100 messages concurrently (the flood).
        await asyncio.gather(*[
            bot.event_message(FakeMessage("user%03d" % i, "!s%03d" % i, ch))
            for i in range(N_USERS)
        ])
        drained = await wait_until(
            lambda: len(bot.command_queues[SONG]._queue) == 0, timeout=25)
        assert drained, "queue did not drain after 100 commands"
        # Give the worker a beat to finish bookkeeping on the last item.
        await asyncio.sleep(0.05)

        log = _mixer().Channel(1).play_log
        assert len(log) == N_USERS, (
            "expected %d plays, got %d" % (N_USERS, len(log)))
        # FIFO: playback order must match submission order.
        paths = [os.path.basename(p) for _, p in log]
        expected = ["stress%03d.mp3" % i for i in range(N_USERS)]
        assert paths == expected, (
            "FIFO order violated; first mismatch at %d: %r vs %r" % (
                next(i for i, (a, b) in enumerate(zip(paths, expected))
                     if a != b), paths[:5], expected[:5]))
        # Exactly-once charging: 100 - 10 = 90 for every user.
        for i in range(N_USERS):
            pts = cur.get_points("user%03d" % i)
            assert pts == START_POINTS - COST, (
                "user%03d charged wrong: %s (expected %d)" % (
                    i, pts, START_POINTS - COST))
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_stress_queue_limit_refunds_under_flood():
    """Queue limit 5, flood of 100: exactly 5 get in, 95 are refunded,
    and the semaphore has no leaked permits afterwards."""
    tmp = new_tmpdir()
    try:
        cmds = _make_commands(tmp, N_USERS)
        cur = FakeCurrencyManager(_make_users(N_USERS))
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 5,
                       "audio_channel": 1}}
        bot, cm, cur = make_bot(tmp, cmds, cats, currency=cur)
        ch = FakeChannel()
        await asyncio.gather(*[
            bot.event_message(FakeMessage("user%03d" % i, "!s%03d" % i, ch))
            for i in range(N_USERS)
        ])
        drained = await wait_until(
            lambda: len(bot.command_queues[SONG]._queue) == 0
            and bot.queue_semaphores[SONG]._value == 5, timeout=25)
        assert drained, "queue did not drain / permits not released"
        await asyncio.sleep(0.05)

        log = _mixer().Channel(1).play_log
        assert len(log) == 5, (
            "expected exactly 5 plays (queue limit), got %d" % len(log))
        # The 5 that got in were charged once; the 95 rejected were refunded.
        played = set(os.path.basename(p) for _, p in log)
        charged = 0
        refunded = 0
        for i in range(N_USERS):
            pts = cur.get_points("user%03d" % i)
            if pts == START_POINTS - COST:
                charged += 1
            elif pts == START_POINTS:
                refunded += 1
            else:
                assert False, (
                    "user%03d has %s points (double charge or missing refund)"
                    % (i, pts))
        assert charged == 5, "expected 5 charged, got %d" % charged
        assert refunded == N_USERS - 5, (
            "expected %d refunded, got %d" % (N_USERS - 5, refunded))
        # No semaphore permit leak: all 5 permits are available again.
        sem = bot.queue_semaphores[SONG]
        assert sem._value == 5, (
            "semaphore leaked permits: value %d, expected 5" % sem._value)
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_stress_queue_listing_under_flood():
    """!queue spam while 50 commands are being processed: the listing must
    never corrupt the queue (size/counter/items stay consistent)."""
    tmp = new_tmpdir()
    try:
        cmds = _make_commands(tmp, 50)
        users = _make_users(50)
        users["mod"] = {"points": 0, "is_mod": True}
        cur = FakeCurrencyManager(users)
        bot, cm, cur = make_bot(tmp, cmds, {SONG: {"queue_enabled": True,
                                                   "max_queue_size": 0,
                                                   "audio_channel": 1}},
                                currency=cur)
        ch = FakeChannel()
        await asyncio.gather(*[
            bot.event_message(FakeMessage("user%03d" % i, "!s%03d" % i, ch))
            for i in range(50)
        ])
        # Hammer !queue while the worker is mid-flight.
        for _ in range(20):
            await bot.event_message(FakeMessage("mod", "!queue SONG", ch))
            await asyncio.sleep(0.02)

        drained = await wait_until(
            lambda: len(bot.command_queues[SONG]._queue) == 0
            and bot.command_queues[SONG]._unfinished_tasks == 0, timeout=25)
        assert drained, "queue did not drain after listing spam"
        await asyncio.sleep(0.05)
        q = bot.command_queues[SONG]
        # Internal consistency: counter must agree with qsize (in 3.8 both
        # track pending items; after full drain both are 0).
        assert q.qsize() == 0, "queue not empty: %d" % q.qsize()
        assert q._unfinished_tasks == 0, (
            "unfinished_tasks not zero after drain: %d" % q._unfinished_tasks)
        log = _mixer().Channel(1).play_log
        assert len(log) == 50, (
            "expected 50 plays, got %d (listing lost items?)" % len(log))
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)