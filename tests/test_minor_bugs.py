"""Remaining medium/minor bugs from the plan (section 4), after stage 5.

Py3.8 compatible.
"""
from harness import (make_bot, make_real_currency, FakeMessage, FakeChannel,
                     new_tmpdir, drop_tmpdir)


async def test_reading_a_balance_creates_no_user():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.users["alice"] = {"points": 10, "hours": 1}
        assert cur.get_points("nobody") == 0 and cur.get_hours("nobody") == 0
        assert "nobody" not in cur.users, "a read must not add a viewer"
        assert cur.get_points("Alice") == 10
    finally:
        drop_tmpdir(tmp)


async def test_mod_command_with_a_typo_creates_no_user():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.users["modguy"] = {"points": 0, "hours": 0, "is_mod": True}
        bot, _cm, _ = make_bot(tmp, [], currency=cur)

        async def is_mod(name):
            return name == "modguy"
        bot.is_user_moderator = is_mod
        ch = FakeChannel()
        await bot.event_message(FakeMessage("modguy", "!remove_points @tpyo 5", ch))
        assert "tpyo" not in cur.users, (sorted(cur.users), ch.sent)
    finally:
        drop_tmpdir(tmp)


async def test_currency_backup_not_on_every_accrual():
    import os
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        for _ in range(5):
            cur.process_currency_update(is_live=True, active_viewers=["a"], all_viewers=["a", "b"])
        files = [n for n in os.listdir(str(cur.backup_dir)) if n.endswith(".json")]
        assert len(files) <= 1, "one backup per 30 minutes, got %d: %s" % (len(files), files)
    finally:
        drop_tmpdir(tmp)


async def test_history_auto_backup_skips_unchanged_commands():
    import os
    from core import paths
    from core.history_manager import HistoryManager
    from harness import make_command
    tmp = new_tmpdir()
    try:
        paths.set_app_dir(tmp)
        hm = HistoryManager(max_backups=5)
        cmds = [make_command("!a"), make_command("!b")]
        assert hm.save_backup_if_changed(cmds) is True
        for _ in range(4):                       # auto-save ticks, nothing edited
            assert hm.save_backup_if_changed(cmds) is None
        assert len(hm.get_backups()) == 1, "identical auto-save copies push real versions out"
        cmds[0]["Response"] = "edited"
        assert hm.save_backup_if_changed(cmds) is True
        assert len(hm.get_backups()) == 2
        assert hm.save_backup(cmds) is True and len(hm.get_backups()) == 3, \
            "a manual backup is always written"
    finally:
        drop_tmpdir(tmp)


async def test_update_check_compares_versions_properly():
    from core.version import is_newer, parse, APP_VERSION
    assert parse("V1.1.6a") is not None and parse("V1.2.0-Beta3") is not None
    assert is_newer("V1.2.0", "V1.1.6a")
    assert not is_newer("V1.1.6a", "V1.2.0"), "an older tag is not an update"
    assert not is_newer("V1.2.0", "V1.2.0")
    assert is_newer("V1.2.0", "V1.2.0-Beta3"), "the release is newer than its beta"
    assert is_newer("V1.2.0-Beta3", "V1.2.0-Beta2")
    assert not is_newer("V1.2.0-Beta3", "V1.2.0")
    assert not is_newer("V1.2.0", APP_VERSION), "2.0 is not asked to go back to 1.2"
    assert is_newer("V2.0.0", APP_VERSION)
    assert not is_newer("nightly", "V1.2.0"), "unparseable tag: no prompt"


async def test_about_tab_uses_the_shared_version_check():
    import os
    from harness import REPO_DIR
    with open(os.path.join(REPO_DIR, "ui", "about_tab.py"), encoding="utf-8") as f:
        src = f.read()
    assert "V1.1.6a" not in src and "APP_VERSION" in src and "is_newer" in src


async def test_rank_promotion_does_not_take_the_file_lock_under_users_lock():
    """add_points (UI thread: watch-time payout) promoted a rank and saved while
    holding users_lock -> waited for the file lock; save_users in the other
    thread holds the file lock and waits for users_lock: both froze."""
    import threading
    from core import storage
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.set_ranks([{"name": "Low", "required": 0}, {"name": "High", "required": 100}])
        cur.users["bob"] = {"points": 50, "hours": 0, "rank": "Low"}
        file_lock = storage.lock_for(cur.users_file)
        file_lock.acquire()                       # "the bot thread is writing the file"
        try:
            t = threading.Thread(target=lambda: cur.add_points("bob", 100), daemon=True)
            t.start()
            t.join(0.5)
            got = cur.users_lock.acquire(timeout=1.0)  # what that writer needs next
            if got:
                cur.users_lock.release()
        finally:
            file_lock.release()
        t.join(5)
        assert got, "lock order users_lock -> file lock: deadlock with a concurrent save"
        assert cur.users["bob"]["rank"] == "High" and cur._save_pending
    finally:
        drop_tmpdir(tmp)


async def test_paying_for_a_command_does_not_save_under_users_lock():
    import threading
    from core import storage
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.users["bob"] = {"points": 50, "hours": 0}
        file_lock = storage.lock_for(cur.users_file)
        file_lock.acquire()
        result = []
        try:
            t = threading.Thread(target=lambda: result.append(cur.pay_for_command("bob", 10)), daemon=True)
            t.start()
            t.join(0.5)
            got = cur.users_lock.acquire(timeout=1.0)
            if got:
                cur.users_lock.release()
        finally:
            file_lock.release()
        t.join(5)
        assert got, "pay_for_command saved while holding users_lock"
        assert result == [True] and cur.users["bob"]["points"] == 40
        with open(str(cur.users_file), encoding="utf-8") as f:
            import json
            assert json.load(f)["bob"]["points"] == 40, "the payment is still saved at once"
        assert cur.pay_for_command("nobody", 5) is False and "nobody" not in cur.users
    finally:
        drop_tmpdir(tmp)


async def test_nothing_writes_to_disk_under_users_lock():
    """Lock order is file lock -> users_lock (save_users). Writing under
    users_lock inverts it: a deadlock with a save from the other thread."""
    import ast
    import os
    from harness import REPO_DIR
    writes = {"save_users", "enhanced_save_users", "create_backup", "save_ranks",
              "set_ranks", "recheck_all_ranks", "save_currency_users", "atomic_write_json",
              "atomic_write_text"}
    bad = []
    for rel in ("core/currency_manager.py", "bot/system_handlers.py", "bot/twitch_bot.py",
                "bot/dispatcher.py", "core/backups.py"):
        src = open(os.path.join(REPO_DIR, rel), encoding="utf-8").read()
        for w in ast.walk(ast.parse(src)):
            if isinstance(w, ast.With) and any("users_lock" in ast.dump(i.context_expr) for i in w.items):
                for c in ast.walk(w):
                    if isinstance(c, ast.Call) and getattr(c.func, "attr", None) in writes:
                        bad.append("%s:%d %s" % (rel, c.lineno, c.func.attr))
    assert not bad, bad
