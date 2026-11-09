"""Step 3.2 / S8: queue commands are ordinary system commands.

!queue/!skip/!clear/!volume used to be intercepted before the Sys.Commands
settings: Enabled, permission, cooldown and cost did not apply, and
duplicates of them did nothing.

Py3.8 compatible.
"""
import asyncio
import os

from harness import (make_bot, make_command, make_sound_file, FakeMessage, FakeChannel,
                     FakeCurrencyManager, wait_until, new_tmpdir, drop_tmpdir)
from stubs import set_sound_duration

from core.system_commands import merge_with_defaults, DEFAULT_SYSTEM_COMMANDS

SONG = "SONG"
CATS = {SONG: {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1}}


def _sys(name, **kw):
    base = next(dict(d) for d in DEFAULT_SYSTEM_COMMANDS if d["command"] == name)
    base.update(kw)
    return base


async def _bot(tmp, sys_cmds=None, users=None):
    cmds = []
    for i in range(2):
        make_sound_file(tmp, "s%d.mp3" % i)
        set_sound_duration(os.path.join(tmp, "s%d.mp3" % i), 5.0)
        cmds.append(make_command("!s%d" % i, SONG, SoundFile="s%d.mp3" % i))
    cur = FakeCurrencyManager(users or {"mod": {"points": 0, "is_mod": True}})
    bot, cm, _ = make_bot(tmp, cmds, CATS, currency=cur)
    if sys_cmds is not None:
        cm.save_system_commands(sys_cmds)
    return bot, cm, cur


async def _stop(bot):
    for g in list(bot.queue_processing):
        bot.queue_processing[g] = False
    for w in list(bot.queue_workers.values()):
        w.cancel()
        try:
            await w
        except BaseException:
            pass


async def test_s8_disabled_queue_command_does_nothing():
    tmp = new_tmpdir()
    try:
        bot, _cm, _ = await _bot(tmp, [_sys("!queue", enabled=False)])
        ch = FakeChannel()
        await bot.event_message(FakeMessage("viewer", "!queue", ch))
        assert ch.sent == [], ch.sent
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_s8_queue_command_cost_and_cooldown_apply():
    tmp = new_tmpdir()
    try:
        # flag set: a cooldown chosen after the one-time 2.0 reset
        bot, _cm, cur = await _bot(tmp, [_sys("!queue", cost=5, cooldown=1,
                                             settings_apply_since_2_0=True)],
                                   users={"viewer": {"points": 7}})
        ch = FakeChannel()
        await bot.event_message(FakeMessage("viewer", "!queue", ch))
        assert cur.get_points("viewer") == 2, cur.get_points("viewer")
        await bot.event_message(FakeMessage("viewer", "!queue", ch))
        assert cur.get_points("viewer") == 2, "second call is on cooldown, must not charge"
        assert any("cooldown" in s for s in ch.sent), ch.sent
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_s8_skip_permission_from_settings():
    tmp = new_tmpdir()
    try:
        bot, _cm, _ = await _bot(tmp, [_sys("!skip", permission="Everyone")],
                                 users={"viewer": {"points": 0}})
        await bot.event_message(FakeMessage("viewer", "!s0", FakeChannel()))
        await wait_until(lambda: bot.queue_snapshot(SONG)["current"] is not None, 2)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("viewer", "!skip SONG", ch))
        assert any("Skipped" in s for s in ch.sent), ch.sent
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_s8_skip_default_is_moderator_only():
    tmp = new_tmpdir()
    try:
        bot, _cm, _ = await _bot(tmp, None, users={"viewer": {"points": 0}})
        ch = FakeChannel()
        await bot.event_message(FakeMessage("viewer", "!skip", ch))
        assert any("permission" in s for s in ch.sent), ch.sent
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_s8_duplicate_of_skip_works():
    tmp = new_tmpdir()
    try:
        dup = _sys("!skip", command_name="!next", is_duplicate=True, is_original=False)
        bot, _cm, _ = await _bot(tmp, [_sys("!skip"), dup])
        await bot.event_message(FakeMessage("viewer", "!s0", FakeChannel()))
        await wait_until(lambda: bot.queue_snapshot(SONG)["current"] is not None, 2)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("mod", "!next SONG", ch))
        assert any("Skipped" in s for s in ch.sent), ch.sent
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_s8_works_without_system_commands_file():
    tmp = new_tmpdir()
    try:
        bot, _cm, _ = await _bot(tmp, None)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("mod", "!volume SONG 30", ch))
        assert any("30%" in s for s in ch.sent), ch.sent
        await _stop(bot)
    finally:
        drop_tmpdir(tmp)


async def test_s8_queue_cooldowns_reset_once():
    stored = [_sys("!queue", cooldown=5, user_cooldown=10), _sys("!points", cooldown=5)]
    merged, changed = merge_with_defaults(stored)
    q = next(c for c in merged if c["command"] == "!queue")
    p = next(c for c in merged if c["command"] == "!points")
    assert changed and (q["cooldown"], q["user_cooldown"]) == (0, 0), q
    assert p["cooldown"] == 5, "other commands keep their cooldowns"
    q["cooldown"] = 3   # the user sets a cooldown later
    again, _ = merge_with_defaults(merged)
    assert next(c for c in again if c["command"] == "!queue")["cooldown"] == 3
    assert len([c for c in again if c["command"] == "!queue"]) == 1
    assert {c["command"] for c in again} >= {d["command"] for d in DEFAULT_SYSTEM_COMMANDS}
