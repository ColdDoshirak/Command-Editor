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


# ---- S3: no payout for the time the bot was not watching --------------------
def _payout_currency(tmp):
    from harness import make_real_currency
    cur = make_real_currency(tmp)
    cur.settings.update({"accumulation_enabled": True, "live_payout": 10, "online_interval": 5,
                         "regular_bonus": 0, "mod_bonus": 0})
    cur.users["viewer"] = {"points": 0, "hours": 0, "last_seen": 0}
    return cur


async def test_s3_normal_tick_is_prorated():
    import time
    tmp = new_tmpdir()
    try:
        cur = _payout_currency(tmp)
        cur.last_update_time = time.time() - 60   # one 60-second tick
        cur.process_currency_update(is_live=True, all_viewers=["viewer"])
        assert cur.users["viewer"]["points"] == 2.0, cur.users["viewer"]
        assert abs(cur.users["viewer"]["hours"] - round(1 / 60, 2)) < 1e-9, cur.users["viewer"]
    finally:
        drop_tmpdir(tmp)


async def test_s3_gap_after_downtime_pays_no_backlog():
    import time
    tmp = new_tmpdir()
    try:
        cur = _payout_currency(tmp)
        cur.last_update_time = time.time() - 3 * 3600   # bot was off for 3 hours
        cur.process_currency_update(is_live=True, all_viewers=["viewer"])
        assert cur.users["viewer"]["points"] <= 2.0, cur.users["viewer"]
        assert cur.users["viewer"]["hours"] == 0, cur.users["viewer"]
    finally:
        drop_tmpdir(tmp)


# ---- S4: users file survives a crash in the middle of a save ----------------
async def test_s4_interrupted_save_keeps_previous_file():
    import builtins
    import json
    import os
    from harness import make_real_currency
    tmp = new_tmpdir()
    real_open = builtins.open
    try:
        cur = make_real_currency(tmp)
        cur.users = {"alice": {"points": 100, "hours": 0, "last_seen": 0}}
        assert cur.save_users(force=True)
        target = os.path.abspath(str(cur.users_file))

        class HalfWriter(object):
            """Writes half of the text, then the 'power goes out'."""
            def __init__(self, f):
                self.f = f
            def write(self, text):
                self.f.write(text[:len(text) // 2])
                self.f.flush()
                raise OSError("simulated crash")
            def __getattr__(self, name):
                return getattr(self.f, name)
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                self.f.close()

        def crashing_open(file, mode="r", *a, **kw):
            f = real_open(file, mode, *a, **kw)
            p = os.path.abspath(str(file))
            if "w" in mode and os.path.dirname(p) == os.path.dirname(target):
                return HalfWriter(f)
            return f

        cur.users["alice"]["points"] = 5
        builtins.open = crashing_open
        try:
            cur.save_users(force=True)
        finally:
            builtins.open = real_open
        with real_open(target, encoding="utf-8") as f:
            data = json.load(f)
        assert data["alice"]["points"] == 100, data
        leftovers = [n for n in os.listdir(os.path.dirname(target)) if n.endswith(".tmp")]
        assert leftovers == [], leftovers
        assert cur._save_pending, "a failed save must stay pending"
    finally:
        builtins.open = real_open
        drop_tmpdir(tmp)


# ---- S9: !volume for a group without a queue --------------------------------
async def test_s9_group_volume_applies_without_queue():
    import os
    import sys
    from harness import make_sound_file
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "fx.mp3")
        cmd = make_command("!fx", "FX", SoundFile=os.path.join(tmp, "fx.mp3"), Volume=100)
        cats = {"FX": {"queue_enabled": False, "audio_channel": 2}}
        bot, _cm, _cur = make_bot(tmp, [cmd], audio_categories=cats,
                                  currency=FakeCurrencyManager({"mod": {"points": 0, "is_mod": True}}))
        await bot.event_message(_msg("mod", "!volume FX 25", FakeChannel()))
        await bot.event_message(_msg("viewer", "!fx", FakeChannel()))
        ch = sys.modules["pygame"].mixer.Channel(2)
        assert ch.play_log, "sound did not play"
        vol = ch.last_sound._volume
        assert abs(vol - 0.25) < 1e-9, "group volume ignored, played at %r" % vol
    finally:
        drop_tmpdir(tmp)


# ---- first start in an empty folder / damaged config.json -------------------
async def test_first_run_writes_default_config():
    import json
    import os
    from core import paths
    from config_manager import ConfigManager
    tmp = new_tmpdir()
    try:
        paths.set_app_dir(tmp)
        cm = ConfigManager()
        cfg_file = os.path.join(tmp, "config.json")
        assert os.path.exists(cfg_file), os.listdir(tmp)
        with open(cfg_file, encoding="utf-8") as f:
            assert json.load(f).get("format_version") == "2.0"
        cm.config["sound"]["volume"] = 0.3
        assert cm.default_config["sound"]["volume"] == 1.0, \
            "defaults must not share nested dicts with the live config"
    finally:
        drop_tmpdir(tmp)


async def test_damaged_config_is_kept_aside():
    import os
    from core import paths
    from config_manager import ConfigManager
    tmp = new_tmpdir()
    try:
        paths.set_app_dir(tmp)
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
            f.write('{"theme": "midnight", ')
        ConfigManager()
        kept = [n for n in os.listdir(tmp) if n.startswith("config.json.corrupt")]
        assert len(kept) == 1, os.listdir(tmp)
        with open(os.path.join(tmp, kept[0]), encoding="utf-8") as f:
            assert "midnight" in f.read()
    finally:
        drop_tmpdir(tmp)


# ---- S2: regular bonus only on timed payouts (decision 2, option A) ---------
async def test_s2_add_points_has_no_regular_bonus():
    tmp = new_tmpdir()
    try:
        cur = _payout_currency(tmp)
        cur.settings["regular_bonus"] = 5
        cur.users["viewer"]["is_regular"] = True
        cur.add_points("viewer", 10)       # refund / transfer / manual add
        assert cur.users["viewer"]["points"] == 10, cur.users["viewer"]
    finally:
        drop_tmpdir(tmp)


async def test_s2_timed_payout_gets_bonus_once():
    import time
    tmp = new_tmpdir()
    try:
        cur = _payout_currency(tmp)          # 10 points per 5 minutes
        cur.settings["regular_bonus"] = 5    # +5 per 5 minutes for regulars
        cur.users["viewer"]["is_regular"] = True
        cur.last_update_time = time.time() - 300   # exactly one interval
        cur.process_currency_update(is_live=True, all_viewers=["viewer"])
        assert abs(cur.users["viewer"]["points"] - 15) < 0.05, cur.users["viewer"]
    finally:
        drop_tmpdir(tmp)
