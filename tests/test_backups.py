"""Step 4.3: full system backups live in core/backups.py (no Qt).

Also two fixes found while moving the code:
- the backup file contained the Twitch token (config.twitch_config was the
  whole twitch_config.json); restore only ever used the channel
- restoring ranks assigned the list directly: users' ranks were not
  recalculated for the restored thresholds

Py3.8 compatible.
"""
import json
import os
import threading
import time

from harness import (make_config_manager, make_real_currency, make_command,
                     new_tmpdir, drop_tmpdir)

from core import backups


def _setup(tmp):
    cm = make_config_manager(tmp)
    tw = cm.get_twitch_config()
    tw.update({"access_token": "SECRET-TOKEN", "refresh_token": "SECRET-REFRESH",
               "client_id": "cid", "channel": "mychan"})
    cm.get_twitch_config = lambda: dict(tw)
    cur = make_real_currency(tmp)
    cur.users.update({"alice": {"points": 50, "hours": 1}, "bob": {"points": 500, "hours": 9}})
    cur.set_ranks([{"name": "Rookie", "required": 0}, {"name": "Pro", "required": 400}])
    return cm, cur


async def test_backup_has_no_twitch_token():
    tmp = new_tmpdir()
    try:
        cm, cur = _setup(tmp)
        store = backups.FullBackups(os.path.join(tmp, "full"))
        data = store.collect([make_command("!a")], currency=cur, config=cm)
        path = store.create(data)
        with open(str(path), encoding="utf-8") as f:
            text = f.read()
        assert "SECRET" not in text, "the Twitch token must not be written into a backup"
        assert json.loads(text)["config"]["twitch_config"] == {"channel": "mychan"}
    finally:
        drop_tmpdir(tmp)


async def test_create_list_and_cleanup():
    tmp = new_tmpdir()
    try:
        cm, cur = _setup(tmp)
        store = backups.FullBackups(os.path.join(tmp, "full"))
        made = []
        for i in range(4):          # same second: names must not collide
            made.append(store.create(store.collect([make_command("!c%d" % i)], currency=cur, config=cm)))
            os.utime(str(made[-1]), (time.time() + i, time.time() + i))
        assert len(set(str(p) for p in made)) == 4, made
        entries = store.entries()
        assert [e["path"] for e in entries] == list(reversed(made)), "newest first"
        e = entries[0]
        assert e["meta"]["commands_count"] == 1 and e["meta"]["users_count"] == 2, e["meta"]
        assert e["size_text"].endswith(("B", "KB", "MB")), e["size_text"]
        removed = store.cleanup(keep=2)
        assert len(removed) == 2 and len(store.entries()) == 2
        left = sorted(os.listdir(os.path.join(tmp, "full")))
        assert len(left) == 4 and sum(n.endswith(".meta") for n in left) == 2, left
    finally:
        drop_tmpdir(tmp)


async def test_restore_users_ranks_moderators_config():
    tmp = new_tmpdir()
    try:
        cm, cur = _setup(tmp)
        store = backups.FullBackups(os.path.join(tmp, "full"))
        data = {
            "commands": [make_command("!r1"), make_command("!r2")],
            "currency_users": {"carol": {"points": 300, "hours": 2}},
            "ranks": [{"name": "Low", "required": 0}, {"name": "Mid", "required": 200}],
            "moderators": {"manual": ["modmax"], "excluded": ["exguy"]},
            "config": {"volume": 0.3, "twitch_config": {"channel": "otherchan"}},
        }
        out = store.restore(data, currency=cur, config=cm)
        assert [c["Command"] for c in out["commands"]] == ["!r1", "!r2"]
        assert set(cur.users) == {"carol"}
        with open(str(cur.users_file), encoding="utf-8") as f:
            assert json.load(f)["carol"]["points"] == 300, "restored users are written to disk"
        assert [r["name"] for r in cur.ranks] == ["Low", "Mid"]
        assert cur.users["carol"].get("rank") == "Mid", "ranks recalculated for restored thresholds"
        assert "modmax" in cm.get_manual_moderators() and "exguy" in cm.get_excluded_moderators()
        assert cm.get_volume() == 0.3
        assert out["ranks"] and out["users"] == 1 and out["moderators"] and out["config"]
    finally:
        drop_tmpdir(tmp)


async def test_collect_while_the_bot_changes_users():
    tmp = new_tmpdir()
    try:
        cm, cur = _setup(tmp)
        store = backups.FullBackups(os.path.join(tmp, "full"))
        stop = []

        def churn():
            i = 0
            while not stop:
                with cur.users_lock:
                    cur.users["u%d" % (i % 500)] = {"points": i}
                    if i % 3 == 0:
                        cur.users.pop("u%d" % ((i + 7) % 500), None)
                i += 1
        t = threading.Thread(target=churn)
        t.start()
        try:
            for _ in range(30):
                store.collect([], currency=cur, config=cm)   # must not raise
        finally:
            stop.append(1)
            t.join()
    finally:
        drop_tmpdir(tmp)
