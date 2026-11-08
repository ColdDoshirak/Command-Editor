"""Stage 0 bug reproductions (docs/refactor-plan.md, section 4).

C1  Permission of custom commands was never checked.
C3  is_user_moderator (Helix + blocking requests) ran for every system
    command, even "Everyone" ones, and for chatters whose IRC tags already
    say they are a moderator.

Py3.8 compatible.
"""
import asyncio

from harness import (
    make_bot, make_command, FakeMessage, FakeChannel, FakeCurrencyManager,
    new_tmpdir, drop_tmpdir,
)


def _spy_mod(bot, result=False):
    calls = []

    async def spy(name):
        calls.append(name)
        return result
    bot.is_user_moderator = spy
    return calls


def _sys(name, permission):
    return {"command": name, "permission": permission, "response": "", "enabled": True,
            "info": "", "group": "SYSTEM", "cooldown": 0, "user_cooldown": 0, "cost": 0,
            "usage": "Chat", "is_original": True}


def _msg(user, text, ch, **author):
    m = FakeMessage(user, text, ch)
    for k, v in author.items():
        setattr(m.author, k, v)
    return m


async def test_c1_moderator_command_denied_for_viewer():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!modonly", Permission="Moderator", Response="secret")
        bot, _cm, _cur = make_bot(tmp, [cmd])
        _spy_mod(bot, result=False)
        ch = FakeChannel()
        await bot.event_message(_msg("viewer", "!modonly", ch))
        await asyncio.sleep(0.05)
        assert not any("secret" in s for s in ch.sent), ch.sent
        assert cmd["Count"] == 0, cmd["Count"]
    finally:
        drop_tmpdir(tmp)


async def test_c1_admin_command_denied_for_viewer():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!adm", Permission="Admin", Response="secret")
        bot, _cm, _cur = make_bot(tmp, [cmd])
        _spy_mod(bot, result=False)
        ch = FakeChannel()
        await bot.event_message(_msg("viewer", "!adm", ch))
        await asyncio.sleep(0.05)
        assert not any("secret" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_c1_moderator_command_allowed_for_mod():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!modonly", Permission="Moderator", Response="secret")
        bot, _cm, _cur = make_bot(tmp, [cmd])
        _spy_mod(bot, result=True)
        ch = FakeChannel()
        await bot.event_message(_msg("mod", "!modonly", ch))
        await asyncio.sleep(0.05)
        assert any("secret" in s for s in ch.sent), ch.sent
        assert cmd["Count"] == 1, cmd["Count"]
    finally:
        drop_tmpdir(tmp)


async def test_c1_denied_command_keeps_points_and_cooldown():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!modonly", Permission="Moderator", Response="secret",
                           Cost=10, Cooldown=5)
        cur = FakeCurrencyManager({"viewer": {"points": 50}})
        bot, _cm, _cur = make_bot(tmp, [cmd], currency=cur)
        _spy_mod(bot, result=False)
        await bot.event_message(_msg("viewer", "!modonly", FakeChannel()))
        assert cur.get_points("viewer") == 50, cur.get_points("viewer")
        assert "modonly" not in bot.global_cooldowns, bot.global_cooldowns
    finally:
        drop_tmpdir(tmp)


async def test_c3_everyone_command_skips_moderator_lookup():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!hi", Response="hello")
        bot, cm, _cur = make_bot(tmp, [cmd])
        cm.save_system_commands([_sys("!points", "Everyone")])
        calls = _spy_mod(bot)
        ch = FakeChannel()
        await bot.event_message(_msg("viewer", "!hi", ch))
        try:
            # FakeCurrencyManager cannot run !points itself; only the
            # permission step before it matters here
            await bot.event_message(_msg("viewer", "!points", ch))
        except AttributeError:
            pass
        await asyncio.sleep(0.05)
        assert calls == [], calls
    finally:
        drop_tmpdir(tmp)


async def test_c3_mod_badge_skips_moderator_lookup():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!modonly", Permission="Moderator", Response="secret")
        bot, _cm, _cur = make_bot(tmp, [cmd])
        calls = _spy_mod(bot, result=False)
        ch = FakeChannel()
        await bot.event_message(_msg("somemod", "!modonly", ch, is_mod=True))
        await asyncio.sleep(0.05)
        assert calls == [], calls
        assert any("secret" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_c3_excluded_moderator_still_denied_with_badge():
    tmp = new_tmpdir()
    try:
        cmd = make_command("!modonly", Permission="Moderator", Response="secret")
        bot, cm, _cur = make_bot(tmp, [cmd])
        _spy_mod(bot, result=False)
        cm.get_excluded_moderators = lambda: ["badmod"]
        ch = FakeChannel()
        await bot.event_message(_msg("badmod", "!modonly", ch, is_mod=True))
        await asyncio.sleep(0.05)
        assert not any("secret" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_c3_moderator_system_command_denied_for_viewer():
    tmp = new_tmpdir()
    try:
        bot, cm, cur = make_bot(tmp, [], currency=FakeCurrencyManager({"target": {"points": 5}}))
        cm.save_system_commands([_sys("!add_points", "Moderator")])
        calls = _spy_mod(bot, result=False)
        ch = FakeChannel()
        await bot.event_message(_msg("viewer", "!add_points @target 100", ch))
        await asyncio.sleep(0.05)
        assert calls == ["viewer"], calls
        assert cur.get_points("target") == 5, cur.get_points("target")
        assert any("permission" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


# ---- S1: !give -------------------------------------------------------------
async def _give(tmp, users, text, sender="alice", regular_bonus=0):
    from harness import make_real_currency
    cur = make_real_currency(tmp)
    cur.settings["regular_bonus"] = regular_bonus
    for name, data in users.items():
        cur.users[name] = dict({"points": 0, "hours": 0, "last_seen": 0}, **data)
    bot, cm, _ = make_bot(tmp, [], currency=cur)
    cm.save_system_commands([_sys("!give", "Everyone")])
    ch = FakeChannel()
    await bot.event_message(_msg(sender, text, ch))
    return cur, ch


async def test_s1_give_failed_credit_keeps_sender_points():
    tmp = new_tmpdir()
    try:
        cur, _ch = await _give(tmp, {"alice": {"points": 100}, "bob": {"points": 49999990}},
                               "!give @bob 50")
        assert cur.users["alice"]["points"] == 100, cur.users["alice"]
        assert cur.users["bob"]["points"] == 49999990, cur.users["bob"]
    finally:
        drop_tmpdir(tmp)


async def test_s1_give_to_self_creates_nothing():
    tmp = new_tmpdir()
    try:
        cur, _ch = await _give(tmp, {"alice": {"points": 100, "is_regular": True}},
                               "!give @alice 10", regular_bonus=5)
        assert cur.users["alice"]["points"] == 100, cur.users["alice"]
    finally:
        drop_tmpdir(tmp)


async def test_s1_give_moves_points_without_bonus():
    tmp = new_tmpdir()
    try:
        cur, ch = await _give(tmp, {"alice": {"points": 100}, "bob": {"points": 1, "is_regular": True}},
                              "!give @bob 30", regular_bonus=5)
        assert cur.users["alice"]["points"] == 70, cur.users["alice"]
        assert cur.users["bob"]["points"] == 31, cur.users["bob"]
        assert any("gave" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_s1_give_to_unknown_user_is_refused():
    tmp = new_tmpdir()
    try:
        cur, _ch = await _give(tmp, {"alice": {"points": 100}}, "!give @nobodyy 30")
        assert cur.users["alice"]["points"] == 100, cur.users["alice"]
        assert "nobodyy" not in cur.users, cur.users.get("nobodyy")
    finally:
        drop_tmpdir(tmp)
