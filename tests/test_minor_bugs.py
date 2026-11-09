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
