"""Regression tests for B3 (_temp command pollution) and B4 (config written
from two threads without a lock / non-atomic writes).

B3: the bot must never inject a fake '_temp' command into the shared
commands list when lazy-initializing a queue for a group whose queue is
enabled in audio_categories but which has no command in the current list.

B4: config.json must survive concurrent saves from the UI thread and the
bot thread (valid JSON, no lost updates), and config backups must not be
created on every single save.

Py3.8 compatible.
"""
import asyncio
import json
import os
import threading

from harness import (  # noqa: F401
    make_bot, make_command, make_sound_file, make_config_manager,
    FakeMessage, FakeChannel, wait_until, new_tmpdir, drop_tmpdir,
)
from stubs import set_sound_duration

SONG = "SONG"
CATS = {SONG: {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}


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


# ---------------------------------------------------------------------------
# B3
# ---------------------------------------------------------------------------

async def test_b3_lazy_queue_no_temp_when_group_absent_from_commands():
    """[B3] Queue group present in audio_categories but ABSENT from the
    commands list: the bot must initialize the queue WITHOUT appending a
    '_temp' command to the shared list, and the command must still process."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot, cm, cur = make_bot(tmp, cmds, CATS)

        # Simulate the UI replacing the commands list object (update_commands
        # after a save). The bot must keep working on the NEW list and must
        # not pollute it.
        new_list = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot.update_commands(new_list)
        assert bot._commands_list is new_list

        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        # Queue must process the command.
        await wait_until(lambda: len(bot.command_queues[SONG]._queue) == 0, timeout=5)

        bad = [c for c in bot._commands_list if c.get("Command") == "_temp"]
        assert not bad, "bot injected _temp into the shared commands list: %r" % bad
        assert bot._commands_list is new_list, "bot replaced the commands list object"
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_b3_commands_json_not_polluted():
    """[B3] After processing a queued command, saving the commands list must
    not write a '_temp' entry into commands.json."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot, cm, cur = make_bot(tmp, cmds, CATS)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        await wait_until(lambda: len(bot.command_queues[SONG]._queue) == 0, timeout=5)

        # UI saves the commands list to disk.
        cm.save_commands(bot._commands_list)
        with open(cm.commands_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        names = [c.get("Command") for c in saved]
        assert "_temp" not in names, "commands.json polluted with _temp: %r" % names
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


# ---------------------------------------------------------------------------
# B4
# ---------------------------------------------------------------------------

async def test_b4_concurrent_config_saves_stay_valid():
    """[B4] UI thread and bot thread saving config concurrently must produce
    a valid config.json with no lost updates (no torn json.dump)."""
    tmp = new_tmpdir()
    try:
        cm = make_config_manager(tmp)
        N_THREADS = 6
        OPS = 150
        barrier = threading.Barrier(N_THREADS)

        def saver(tid):
            barrier.wait()
            for i in range(OPS):
                # Interleave two distinct writers: volume + group volume.
                cm.set_volume(0.1 + (tid % 9) / 10.0)
                cm.set_group_volume("G%d" % tid, 0.5)

        th = [threading.Thread(target=saver, args=(t,)) for t in range(N_THREADS)]
        for t in th:
            t.start()
        for t in th:
            t.join()

        # The file on disk must be valid JSON (atomic write + lock).
        with open(cm.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), "config.json is not a dict"
        # Every group written by a thread must be present (no lost updates).
        cats = data.get("audio_categories", {})
        for t in range(N_THREADS):
            assert "G%d" % t in cats, "group G%d lost from config" % t
            assert cats["G%d" % t].get("volume") == 0.5
        # No leftover temp file.
        assert not os.path.exists(str(cm.config_file) + ".tmp"), "tmp file left behind"
    finally:
        drop_tmpdir(tmp)


async def test_b4_backup_not_created_on_every_save():
    """[B4] Repeated saves within the backup interval must not create a new
    config backup each time (disk used to fill with config_*.json copies)."""
    tmp = new_tmpdir()
    try:
        cm = make_config_manager(tmp)
        cm.save_config()  # first save -> one backup
        backups_after_first = len(list(cm.backup_dir.glob("config_*.json")))
        assert backups_after_first == 1, "expected 1 backup after first save"

        for _ in range(20):
            cm.set_volume(0.5)  # 20 more saves within the interval

        backups_after_many = len(list(cm.backup_dir.glob("config_*.json")))
        assert backups_after_many == 1, (
            "backup created on every save: %d backups after 21 saves"
            % backups_after_many
        )
    finally:
        drop_tmpdir(tmp)


async def test_b4_config_reload_after_concurrent_saves():
    """[B4] The config written under concurrency must be loadable by a fresh
    process (corruption would break startup)."""
    tmp = new_tmpdir()
    try:
        cm = make_config_manager(tmp)
        barrier = threading.Barrier(4)

        def saver(tid):
            barrier.wait()
            for i in range(60):
                cm.set_group_volume("H%d" % tid, 0.25)

        th = [threading.Thread(target=saver, args=(t,)) for t in range(4)]
        for t in th:
            t.start()
        for t in th:
            t.join()

        # Read the file exactly as a fresh startup would.
        with open(cm.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        cats = data.get("audio_categories", {})
        for t in range(4):
            assert "H%d" % t in cats, "group H%d missing after reload" % t
            assert cats["H%d" % t].get("volume") == 0.25
    finally:
        drop_tmpdir(tmp)