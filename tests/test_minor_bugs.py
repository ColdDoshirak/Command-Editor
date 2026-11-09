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
