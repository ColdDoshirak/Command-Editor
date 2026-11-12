"""2.0 features (stage 7), the parts that run without a window.

Py3.8 compatible.
"""
import os
import subprocess
import sys

from harness import new_tmpdir, drop_tmpdir, REPO_DIR

# The lock is tried in separate processes: another test module replaces
# PyQt5 with a stub inside this process.
_PROBE = r'''
import sys, time, os
sys.path.insert(0, %r)
from ui.single_instance import acquire
lock = acquire(sys.argv[1])
print("LOCKED" if lock is not None else "BUSY", flush=True)
mode = sys.argv[2]
if mode == "crash":
    os._exit(0)          # dies without unlocking (a crash)
if mode == "hold":
    time.sleep(30)
'''


def _start(tmp, folder, mode):
    script = os.path.join(tmp, "probe.py")
    if not os.path.exists(script):
        with open(script, "w", encoding="utf-8") as f:
            f.write(_PROBE % REPO_DIR)
    p = subprocess.Popen([sys.executable, script, folder, mode], stdout=subprocess.PIPE)
    return p, p.stdout.readline().decode().strip()


def _probe(tmp, folder):
    p, state = _start(tmp, folder, "probe")
    p.wait(30)
    return state


async def test_second_instance_on_the_same_data_is_refused():
    tmp = new_tmpdir()
    data = os.path.join(tmp, "data")
    other = os.path.join(tmp, "other")
    holder = None
    try:
        holder, state = _start(tmp, data, "hold")
        assert state == "LOCKED", state
        assert _probe(tmp, data) == "BUSY", "another live program uses this data folder"
        assert _probe(tmp, other) == "LOCKED", "a different data folder is fine"
    finally:
        if holder is not None:
            holder.kill()
            holder.wait()
        drop_tmpdir(tmp)


async def test_lock_left_by_a_crash_does_not_block_the_next_start():
    tmp = new_tmpdir()
    data = os.path.join(tmp, "data")
    try:
        p, state = _start(tmp, data, "crash")
        p.wait(30)
        assert state == "LOCKED"
        assert os.path.exists(os.path.join(data, "command_editor.lock")), "the crash left its lock"
        assert _probe(tmp, data) == "LOCKED", "the owner is gone: its lock is stale"
    finally:
        drop_tmpdir(tmp)


# ---- permission ladder ---------------------------------------------------------

def _perm_bot(tmp, users=None, admins=None, mods_api=()):
    from harness import make_bot, make_real_currency
    cur = make_real_currency(tmp)
    cur.users.update(users or {})
    bot, cm, _ = make_bot(tmp, [], currency=cur)
    if admins is not None:
        cm.moderators_config["admins"] = list(admins)

    async def api_mod(name):
        return name in mods_api
    bot.is_user_moderator = api_mod
    return bot, cm


def _msg(name, **badges):
    from harness import FakeMessage, FakeChannel
    m = FakeMessage(name, "!x", FakeChannel())
    for k, v in badges.items():
        setattr(m.author, k, v)
    return m


async def test_permission_ladder():
    tmp = new_tmpdir()
    try:
        bot, cm = _perm_bot(tmp, users={"reg": {"points": 0, "hours": 0, "is_regular": True}},
                            admins=["trusted"], mods_api=("apimod",))
        people = {
            "nobody": _msg("nobody"),
            "reg": _msg("reg"),
            "sub": _msg("sub", is_subscriber=True),
            "vip": _msg("vip", is_vip=True),
            "badgemod": _msg("badgemod", is_mod=True),
            "apimod": _msg("apimod"),
            "trusted": _msg("trusted"),
            "testchan": _msg("testchan"),               # the channel owner
        }
        want = {  # the highest level each one may use
            "nobody": "Everyone", "reg": "Regular", "sub": "Subscriber", "vip": "VIP",
            "badgemod": "Moderator", "apimod": "Moderator", "trusted": "Admin", "testchan": "Admin",
        }
        from core.permissions import LEVELS
        for who, msg in people.items():
            allowed = [lvl for lvl in LEVELS if await bot.has_permission(msg, lvl)]
            top = LEVELS.index(want[who])
            assert allowed == LEVELS[:top + 1], (who, allowed)
    finally:
        drop_tmpdir(tmp)


async def test_admin_is_no_longer_any_moderator_and_excluded_mods_lose_mod():
    tmp = new_tmpdir()
    try:
        bot, cm = _perm_bot(tmp, mods_api=("apimod",))
        assert await bot.has_permission(_msg("apimod"), "Moderator")
        assert not await bot.has_permission(_msg("apimod"), "Admin"), "Admin = owner + admins list"
        cm.moderators_config["excluded_moderators"] = ["badgemod"]
        assert not await bot.has_permission(_msg("badgemod", is_mod=True), "Moderator")
        assert await bot.has_permission(_msg("badgemod", is_mod=True, is_vip=True), "VIP"), \
            "excluded from moderators, still a VIP"
    finally:
        drop_tmpdir(tmp)


async def test_streamlabs_spellings():
    from core.permissions import rank, name_of
    assert name_of("Subscriber") == "Subscriber" and name_of("caster") == "Admin"
    assert name_of("Editor") == "Moderator" and name_of("regular") == "Regular"
    assert rank("something odd") == 0


async def test_subscriber_command_refused_for_a_viewer():
    from harness import make_bot, make_command, FakeChannel, FakeMessage
    tmp = new_tmpdir()
    try:
        cmd = make_command("!subonly", Response="hi sub", Permission="Subscriber")
        bot, _cm, _ = make_bot(tmp, [cmd])
        ch = FakeChannel()
        await bot.event_message(FakeMessage("viewer", "!subonly", ch))
        assert not any("hi sub" in s for s in ch.sent), ch.sent
        m = FakeMessage("fan", "!subonly", ch)
        m.author.is_subscriber = True
        await bot.event_message(m)
        assert any("hi sub" in s for s in ch.sent), ch.sent
    finally:
        drop_tmpdir(tmp)


# ---- variables and aliases --------------------------------------------------------

async def test_render_variables():
    import random
    from core.variables import render
    values = {"user": "alice", "target": "bob", "args": "bob 5", "1": "bob", "2": "5",
              "count": 3, "points": lambda: "12.5", "currency": "coins", "channel": "chan"}
    out = render("{user} -> {target}: {2} ({args}) #{count} {points} {currency} @{channel}", values)
    assert out == "alice -> bob: 5 (bob 5) #3 12.5 coins @chan", out
    rng = random.Random(7)
    rolls = {render("{random:1-6}", {}, rng=rng) for _ in range(200)}
    assert rolls == {str(i) for i in range(1, 7)}, rolls
    assert render("{random:5-5}", {}) == "5"
    for keep in ("{unknown}", "{random:x}", "{3}", "{ not a var }", "{}", "json {\"a\": 1}"):
        assert render(keep, {"1": "x"}) == keep, keep
    assert render("{USER}!", values) == "alice!", "case-insensitive names"


async def test_command_response_uses_variables():
    from harness import make_bot, make_command, make_real_currency, FakeChannel, FakeMessage
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.users["alice"] = {"points": 12.5, "hours": 0}
        cmd = make_command("!hug", Response="{user} hugs {target}! ({count}, {points} {currency}) {2}", Count=4)
        bot, _cm, _ = make_bot(tmp, [cmd], currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!hug @Bob tightly", ch))
        name = cur.get_currency_name() if hasattr(cur, "get_currency_name") else "points"
        assert ch.sent == ["alice hugs Bob! (5, 12.5 %s) tightly" % name], ch.sent
        ch.sent[:] = []
        await bot.event_message(FakeMessage("alice", "!hug", ch))
        assert ch.sent[0].startswith("alice hugs alice!"), ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_aliases_run_the_same_command():
    from harness import make_bot, make_command, FakeChannel, FakeMessage
    tmp = new_tmpdir()
    try:
        cmd = make_command("!song", Response="playing", Aliases="!music, tune  !Track", Cooldown=0)
        other = make_command("!tune2", Response="other")
        bot, _cm, _ = make_bot(tmp, [cmd, other])
        ch = FakeChannel()
        for text in ("!music", "!tune", "!track", "!song", "!tune2"):
            await bot.event_message(FakeMessage("u", text, ch))
        assert ch.sent == ["playing"] * 4 + ["other"], ch.sent
        assert bot._commands_list[0]["Count"] == 4, "the uses count on the command itself"
    finally:
        drop_tmpdir(tmp)


async def test_queued_command_response_uses_variables():
    import os as _os
    from harness import (make_bot, make_command, make_sound_file, FakeChannel, FakeMessage,
                         wait_until)
    from stubs import set_sound_duration
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s.mp3")
        set_sound_duration(_os.path.join(tmp, "s.mp3"), 0.05)
        cmd = make_command("!req", "SONG", SoundFile="s.mp3", Response="{user} queued {args} #{count}")
        bot, _cm, _ = make_bot(tmp, [cmd], {"SONG": {"queue_enabled": True, "audio_channel": 1}})
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!req never gonna", ch))
        assert await wait_until(lambda: ch.sent and any("queued" in s for s in ch.sent), 3), ch.sent
        assert "alice queued never gonna #1" in ch.sent, ch.sent
        for w in list(bot.queue_workers.values()):
            w.cancel()
    finally:
        drop_tmpdir(tmp)


# ---- hotkey actions (the bot side) ---------------------------------------------------

async def test_hotkey_actions_on_the_bot():
    import os as _os
    import sys as _sys
    from harness import make_bot, make_command, make_sound_file, FakeChannel, FakeMessage, wait_until
    from stubs import set_sound_duration
    tmp = new_tmpdir()
    try:
        for n in ("a.mp3", "b.mp3"):
            make_sound_file(tmp, n)
            set_sound_duration(_os.path.join(tmp, n), 5.0)
        cmds = [make_command("!a", "SONG", SoundFile="a.mp3"), make_command("!b", "SONG", SoundFile="b.mp3")]
        bot, _cm, _ = make_bot(tmp, cmds, {"SONG": {"queue_enabled": True, "audio_channel": 1}})
        ch = FakeChannel()
        await bot.event_message(FakeMessage("u", "!a", ch))
        await bot.event_message(FakeMessage("u", "!b", ch))
        assert await wait_until(lambda: "SONG" in bot.queue_current, 2)
        first = bot.queue_current["SONG"]["item"]
        assert bot.hotkey_skip() == 1, "one queue was playing"
        assert await wait_until(lambda: bot.queue_current.get("SONG", {}).get("item") not in (None, first), 3)
        assert bot.hotkey_toggle_pause() is True and "SONG" in bot.queue_paused
        assert bot.hotkey_toggle_pause() is False and "SONG" not in bot.queue_paused
        bot.hotkey_stop_all()
        mixer = _sys.modules["pygame"].mixer
        assert "SONG" in bot.queue_paused, "the panic button also pauses the queues"
        assert not mixer.Channel(1).get_busy(), "and stops what plays"
        for w in list(bot.queue_workers.values()):
            w.cancel()
    finally:
        drop_tmpdir(tmp)
