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
