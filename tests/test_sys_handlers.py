"""Stage 6.1: what every system command answers in chat.

Written before execute_system_command (one 250-line if/elif) was split into
handlers (bot/system_handlers.py) - the answers must stay the same.

Py3.8 compatible.
"""
import time
from datetime import datetime, timedelta, timezone

from harness import make_bot, make_real_currency, FakeMessage, FakeChannel, new_tmpdir, drop_tmpdir


def _sys(name, permission="Everyone", **kw):
    d = {"command": name, "permission": permission, "response": "", "enabled": True,
         "info": "", "group": "SYSTEM", "cooldown": 0, "user_cooldown": 0, "cost": 0,
         "usage": "Chat", "is_original": True}
    d.update(kw)
    return d


async def _setup(tmp, sys_cmds, users=None):
    cur = make_real_currency(tmp)
    cur.settings["cooldown"] = 0
    cur.users.update(users or {})
    bot, cm, _ = make_bot(tmp, [], currency=cur)
    cm.save_system_commands(sys_cmds)

    async def is_mod(name):
        return name == "modguy"
    bot.is_user_moderator = is_mod
    return bot, cur


async def _say(bot, user, text):
    ch = FakeChannel()
    await bot.event_message(FakeMessage(user, text, ch))
    return ch.sent


async def test_points_and_top():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [_sys("!points"), _sys("!top")],
                                {"alice": {"points": 30, "hours": 1}, "bob": {"points": 70, "hours": 2}})
        out = await _say(bot, "alice", "!points")
        assert len(out) == 1 and "alice" in out[0].lower() and "30" in out[0], out
        out = await _say(bot, "alice", "!top")
        assert out == ["Top 5 users: 1. bob (70) | 2. alice (30)"], out
    finally:
        drop_tmpdir(tmp)


async def test_top_with_no_users():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [_sys("!top")])
        cur.users.clear()
        out = await _say(bot, "alice", "!top")
        assert out == ["@alice: No users found in currency system."], out
    finally:
        drop_tmpdir(tmp)


async def test_add_and_remove_points():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [_sys("!add_points", "Moderator"), _sys("!remove_points", "Moderator")],
                                {"modguy": {"points": 0, "hours": 0}, "bob": {"points": 10, "hours": 0}})
        assert await _say(bot, "modguy", "!add_points @Bob 5") == \
            ["@bob received 5.00 points from @modguy. New balance: 15.00"]
        assert await _say(bot, "modguy", "!add_points bob") == ["@modguy: Usage: !add_points @username amount"]
        assert await _say(bot, "modguy", "!add_points bob x") == \
            ["@modguy: Invalid amount format. Use numbers only."]
        assert await _say(bot, "modguy", "!add_points bob -3") == ["@modguy: Amount must be greater than 0"]
        assert await _say(bot, "modguy", "!remove_points @bob 4") == \
            ["@modguy removed 4.00 points from @bob. New balance: 11.00"]
        assert await _say(bot, "modguy", "!remove_points bob 100") == \
            ["@modguy: User @bob only has 11.00 points, cannot remove 100.00"]
        assert await _say(bot, "modguy", "!remove_points bob") == \
            ["@modguy: Usage: !remove_points @username amount"]
        assert cur.users["bob"]["points"] == 11
    finally:
        drop_tmpdir(tmp)


async def test_give():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [_sys("!give")],
                                {"alice": {"points": 50, "hours": 0}, "bob": {"points": 0, "hours": 0}})
        assert await _say(bot, "alice", "!give @bob 20") == ["@alice gave 20.00 points to @bob!"]
        assert await _say(bot, "alice", "!give bob 999") == ["@alice: You don't have enough points (30.00)"]
        assert await _say(bot, "alice", "!give ghost 1") == ["@alice: User @ghost not found."]
        assert await _say(bot, "alice", "!give alice 1") == ["@alice: You can't give points to yourself."]
        assert await _say(bot, "alice", "!give bob x") == ["@alice: Invalid amount format."]
        assert await _say(bot, "alice", "!give") == ["@alice: Usage: !give @username amount"]
        assert cur.users["bob"]["points"] == 20 and cur.users["alice"]["points"] == 30
    finally:
        drop_tmpdir(tmp)


async def test_uptime():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [_sys("!uptime")])
        bot.is_live = False
        assert await _say(bot, "alice", "!uptime") == ["@alice: Stream is currently offline."]
        bot.is_live = True
        start = datetime.now(timezone.utc) - timedelta(hours=1, minutes=2, seconds=3)
        bot.stream_start_time = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        out = await _say(bot, "alice", "!uptime")
        assert len(out) == 1 and out[0].startswith("@alice: Stream uptime: 1h 2m"), out
    finally:
        drop_tmpdir(tmp)


async def test_renamed_copy_works_like_the_original():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [
            _sys("!top"),
            dict(_sys("!top"), command_name="!leaders", is_original=False, is_duplicate=True),
            dict(_sys("!give"), command_name="!pay", is_original=False, is_duplicate=True),
        ], {"bob": {"points": 7, "hours": 0}, "alice": {"points": 5, "hours": 0}})
        assert await _say(bot, "alice", "!leaders") == ["Top 5 users: 1. bob (7) | 2. alice (5)"]
        assert await _say(bot, "alice", "!pay bob 2") == ["@alice gave 2.00 points to @bob!"]
    finally:
        drop_tmpdir(tmp)


async def test_points_cooldown_from_currency_settings():
    tmp = new_tmpdir()
    try:
        bot, cur = await _setup(tmp, [_sys("!points")], {"alice": {"points": 1, "hours": 0}})
        cur.settings["cooldown"] = 60
        assert len(await _say(bot, "alice", "!points")) == 1
        out = await _say(bot, "alice", "!points")
        assert len(out) == 1 and "cooldown" in out[0], out
    finally:
        drop_tmpdir(tmp)
