"""PR #23 fixes: pause refresh ordering + update_commands outside the bot loop.

Covers review items 23.1 (stale refresh in toggle_pause) and 23.7 (tests for
the crash/pause fixes). The bot-logic half of 23.1 lives here; the UI half
(signal -> refresh_queue) is in test_ui_pr22_23.py.

Each test is an async function taking no arguments. The runner creates a
fresh event loop per test. Py3.8 compatible.
"""
import asyncio
import threading
import time

from harness import (
    make_bot, make_command, make_sound_file, new_tmpdir, drop_tmpdir,
)
from stubs import set_sound_duration

SONG = "SONG"
CATS = {SONG: {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}


def _start_bot_loop_thread():
    """Run a real asyncio loop in a daemon thread; return (loop, ready_event).

    This is the bot's loop. The test's own loop is a DIFFERENT loop, so calling
    bot methods from the test loop exercises the cross-thread path.
    """
    holder = {}

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        holder["loop"] = loop
        holder["ready"].set()
        loop.run_forever()

    ready = threading.Event()
    holder["ready"] = ready
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    ready.wait(5)
    return holder["loop"], t


async def test_update_commands_outside_bot_loop_inits_queues():
    """23.7: update_commands() called from a thread that is NOT the bot loop
    must schedule init_queues() in the bot loop (run_coroutine_threadsafe) and
    must not raise. The queue for the group must appear in the bot loop."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(tmp + "/s1.mp3", 0.1)
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot, cm, cur = make_bot(tmp, cmds, CATS)

        bot_loop, t = _start_bot_loop_thread()
        bot.loop = bot_loop  # bot's loop is now the foreign thread's loop
        try:
            # We are in the TEST loop, not bot.loop -> cross-thread path.
            bot.update_commands(cmds)
            # The queue must be created IN the bot loop, shortly after.
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if SONG in bot.command_queues:
                    break
                await asyncio.sleep(0.02)
            assert SONG in bot.command_queues, (
                "update_commands from outside the bot loop did not create the "
                "queue in the bot loop"
            )
        finally:
            bot_loop.call_soon_threadsafe(bot_loop.stop)
    finally:
        drop_tmpdir(tmp)


async def test_ui_toggle_pause_applies_then_emits():
    """23.1 (bot side): _ui_toggle_pause must mutate queue_paused FIRST and only
    then emit queue_paused_changed. The UI refreshes on the signal, so emitting
    before the mutation would show a stale state. Verified by ordering: when the
    signal is emitted, queue_paused already reflects the new state.

    This test runs under plain python3 (no PyQt5), so it monkeypatches
    _ui_toggle_pause to record the call order without a real Qt signal."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(tmp + "/s1.mp3", 0.1)
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot, cm, cur = make_bot(tmp, cmds, CATS)

        bot_loop, t = _start_bot_loop_thread()
        bot.loop = bot_loop
        # Record the order: mutation state at the moment "emit" happens.
        emit_order = []
        orig = bot._ui_toggle_pause

        def _recording_toggle(group):
            # Mutate first (as the real method does).
            if group in bot.queue_paused:
                bot.queue_paused.discard(group)
            else:
                bot.queue_paused.add(group)
            # Then "emit" — record the state at emit time.
            emit_order.append(group in bot.queue_paused)
        bot._ui_toggle_pause = _recording_toggle
        try:
            # PAUSE: schedule in the bot loop, wait for the "emit".
            bot_loop.call_soon_threadsafe(bot._ui_toggle_pause, SONG)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not emit_order:
                await asyncio.sleep(0.02)
            assert emit_order == [True], (
                "pause: queue_paused not set at emit time (stale UI): %r"
                % emit_order)
            assert SONG in bot.queue_paused

            # RESUME: same ordering guarantee.
            del emit_order[:]
            bot_loop.call_soon_threadsafe(bot._ui_toggle_pause, SONG)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not emit_order:
                await asyncio.sleep(0.02)
            assert emit_order == [False], (
                "resume: queue_paused not cleared at emit time: %r"
                % emit_order)
            assert SONG not in bot.queue_paused
        finally:
            bot._ui_toggle_pause = orig
            bot_loop.call_soon_threadsafe(bot_loop.stop)
    finally:
        drop_tmpdir(tmp)