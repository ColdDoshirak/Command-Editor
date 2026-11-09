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
