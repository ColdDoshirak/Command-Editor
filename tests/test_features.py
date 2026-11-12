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


# ---- OBS overlay --------------------------------------------------------------------

def _get(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")


async def test_overlay_server_serves_page_and_state():
    import json
    import socket
    from core.overlay import OverlayServer
    from core.overlay_page import PAGE
    srv = OverlayServer(PAGE)
    try:
        assert srv.start(0), srv.error
        base = "http://127.0.0.1:%d" % srv.port
        status, ctype, body = _get(base + "/")
        assert status == 200 and "text/html" in ctype and "state.json" in body
        srv.update({"connected": True, "live": True, "now": [{"group": "SONG", "command": "!a",
                                                              "user": "alice", "elapsed": 5}],
                    "queues": [], "recent": [{"command": "!hi", "user": "bob"}]})
        status, ctype, body = _get(base + "/state.json")
        st = json.loads(body)
        assert status == 200 and "json" in ctype and st["now"][0]["user"] == "alice", st
        # a busy port is reported, not crashed on
        busy = srv.port
        other = OverlayServer(PAGE)
        assert not other.start(busy) and other.error, other.error
        srv.stop()
        assert not srv.running()
        s = socket.socket()
        assert s.connect_ex(("127.0.0.1", busy)) != 0, "stopped server no longer listens"
        s.close()
    finally:
        srv.stop()


async def test_overlay_snapshot_from_the_bot_queues():
    import os as _os
    from core.overlay import snapshot_from_bot
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
        await bot.event_message(FakeMessage("alice", "!a", ch))
        await bot.event_message(FakeMessage("bob", "!b", ch))
        assert await wait_until(lambda: "SONG" in bot.queue_current, 2)
        st = snapshot_from_bot(bot, recent=[{"command": "!x", "user": "c"}] * 30)
        assert st["now"] == [{"group": "SONG", "command": "!a", "user": "alice", "elapsed": 0}], st["now"]
        assert st["queues"][0]["pending"] == [{"command": "!b", "user": "bob"}], st["queues"]
        assert len(st["recent"]) == 10
        assert snapshot_from_bot(None)["connected"] is False
        for w in list(bot.queue_workers.values()):
            w.cancel()
    finally:
        drop_tmpdir(tmp)


async def test_overlay_page_script_renders():
    """Run the page's JavaScript in Node with a fake DOM (skipped without Node)."""
    import json
    import re
    import shutil
    from core.overlay_page import PAGE
    node = shutil.which("node")
    if not node:
        return
    script = re.search(r"<script>(.*)</script>", PAGE, re.S).group(1)
    state = {"connected": True, "live": True,
             "now": [{"group": "SONG", "command": "!a<b>", "user": "alice", "elapsed": 65}],
             "queues": [{"group": "SONG", "paused": True, "pending": [{"command": "!b", "user": "bob"}],
                         "more": 3}],
             "recent": [{"command": "!x", "user": "u1"}, {"command": "!y", "user": "u2"}]}
    harness_js = """
var els = {now: {}, queue: {}, recent: {}};
var document = {getElementById: function (id) { return els[id]; },
                body: {style: {setProperty: function () {}}}};
var location = {search: "?show=now,queue"};
var fetched = 0;
function fetch() { fetched++; return {then: function () { return {then: function () {
  return {catch: function () { return {then: function () {}}; }}; }}; }}; }
function setTimeout() {}
%s
render(%s);
console.log(JSON.stringify({now: els.now.innerHTML, queue: els.queue.innerHTML,
                            recentClass: els.recent.className, fetched: fetched}));
""" % (script, json.dumps(state))
    tmp = new_tmpdir()
    try:
        path = os.path.join(tmp, "page.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(harness_js)
        out = subprocess.run([node, path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
        res = json.loads(out.stdout.decode("utf-8").strip().splitlines()[-1])
        assert "1:05" in res["now"] and "alice" in res["now"], res["now"]
        assert "&lt;b&gt;" in res["now"] and "<b>" not in res["now"], "names are escaped"
        assert "(paused)" in res["queue"] and "+3 more" in res["queue"] and "bob" in res["queue"]
        assert "hidden" in res["recentClass"], "?show= hides the other blocks"
        assert res["fetched"] == 1, "polls state.json"
    finally:
        drop_tmpdir(tmp)


# ---- timers ---------------------------------------------------------------------------

async def test_timer_schedule():
    from core.timers import TimerClock
    t0 = 1000.0
    timers = [{"message": "Follow the channel!", "interval": 10, "min_lines": 3, "live_only": True},
              {"message": "Discord: x", "interval": 5, "min_lines": 0, "live_only": False},
              {"message": "", "interval": 1, "min_lines": 0},                      # empty: never
              {"message": "off", "interval": 1, "min_lines": 0, "enabled": False}]
    clock = TimerClock(t0, lines=0)

    def due(minutes, lines, live=True):
        return [t["message"] for _k, t in clock.due(timers, t0 + minutes * 60, lines, live)]
    assert due(0, 100) == [], "nothing right after connecting"
    assert due(5, 0) == ["Discord: x"]
    assert due(10, 2) == ["Discord: x"], "only 2 chat lines: the follow timer waits"
    assert due(10, 3) == ["Follow the channel!", "Discord: x"]
    assert due(10, 3, live=False) == ["Discord: x"], "live only"
    key, t = clock.due(timers, t0 + 600, 3, True)[0]
    clock.sent(key, t0 + 600, 3)
    assert "Follow the channel!" not in due(15, 10), "10 minutes since its post"
    assert "Follow the channel!" not in due(20, 5), "only 2 lines since its post"
    assert "Follow the channel!" in due(20, 6)


async def test_bot_posts_timers():
    from core.timers import TimerClock
    from harness import make_bot, FakeChannel, FakeMessage
    tmp = new_tmpdir()
    try:
        bot, cm, _ = make_bot(tmp, [])
        cm.config["timers"] = [{"message": "Hi from {channel} {random:7-7}", "interval": 1,
                                "min_lines": 2, "live_only": False}]
        ch = FakeChannel()
        bot._timer_channel = lambda: ch
        bot._timer_clock = TimerClock(0, 0)
        bot.is_live = False
        for _ in range(2):
            await bot.event_message(FakeMessage("viewer", "hello", FakeChannel()))
        await bot._timers_tick(now=120)
        assert ch.sent == ["Hi from testchan 7"], ch.sent
        await bot._timers_tick(now=150)
        assert ch.sent == ["Hi from testchan 7"], "not again before the interval"
    finally:
        drop_tmpdir(tmp)


# ---- "Test command" dry run ------------------------------------------------------------

async def test_simulate_a_command():
    from core.command_test import simulate
    from harness import make_command
    cmd = make_command("!hug", Response="{user} hugs {target}!\n \nThat was hug #{count}", Count=2,
                       Permission="Subscriber", Cost=10, Aliases="!cuddle", SoundFile="C:/no/such.wav")
    r = simulate(cmd, "!cuddle @Bob", user="alice", role="VIP", points=25)
    assert r["matches"] and r["allowed"] and r["enough_points"], r
    assert r["lines"] == ["alice hugs Bob!", None, "That was hug #3"], r["lines"]
    assert r["sound"] and not r["sound_ok"] and any("not found" in p for p in r["problems"])
    r = simulate(cmd, "!hug", user="newbie", role="Everyone", points=3, exists=lambda p: True)
    assert not r["allowed"] and not r["enough_points"], r
    assert any("needs Subscriber" in p for p in r["problems"]) and any("costs 10" in p for p in r["problems"])
    r = simulate(cmd, "!other", role="Admin", points=99, exists=lambda p: True)
    assert not r["matches"] and r["problems"][0].startswith("The message does not call"), r
    assert simulate(dict(cmd, Enabled=False), "!hug", role="Admin", points=99,
                    exists=lambda p: True)["problems"] == ["The command is disabled"]
