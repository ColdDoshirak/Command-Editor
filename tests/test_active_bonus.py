"""Active Bonus: the currency tab had it, nothing paid it (stage 6).

"Active" = wrote in chat since the previous payout. The bot notes every
chatter in the CurrencyManager (memory only); the payout adds the bonus,
prorated like the Regular / Mod bonuses. Default 0; a stored 1 (the old
default, never paid) is reset to 0 once, so no balance changes unasked.

Py3.8 compatible.
"""
import json
import os

from harness import (make_bot, make_real_currency, FakeMessage, FakeChannel,
                     new_tmpdir, drop_tmpdir)

BASE = {"live_payout": 10, "online_interval": 5, "regular_bonus": 0, "mod_bonus": 0,
        "sub_bonus": 1, "offline_hours": False, "accumulation_enabled": True,
        "auto_regular": False, "active_bonus": 5}


async def test_active_chatters_get_the_bonus():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.settings.update(BASE)
        cur.users.update({"talker": {"points": 0, "hours": 0}, "lurker": {"points": 0, "hours": 0}})
        cur.process_currency_update(is_live=True, all_viewers=["talker", "lurker"])   # first tick
        start = {u: cur.users[u]["points"] for u in ("talker", "lurker")}
        cur.note_chat("Talker")
        cur.last_update_time -= 300                                                   # one interval
        cur.process_currency_update(is_live=True, all_viewers=["talker", "lurker"])
        gained = {u: round(cur.users[u]["points"] - start[u], 2) for u in start}
        assert gained == {"talker": 15.0, "lurker": 10.0}, gained
        # quiet since the last payout -> no bonus any more (the test moves the
        # clock back, so move the chat back too)
        cur.last_update_time -= 300
        cur._last_chat["talker"] -= 900
        cur.process_currency_update(is_live=True, all_viewers=["talker", "lurker"])
        assert round(cur.users["talker"]["points"] - start["talker"], 2) == 25.0
    finally:
        drop_tmpdir(tmp)


async def test_no_active_bonus_offline_unless_enabled():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.settings.update(BASE)
        cur.settings.update({"offline_payout": 3, "offline_interval": 15, "offline_active_bonus": False})
        cur.users["talker"] = {"points": 0, "hours": 0}
        cur.process_currency_update(is_live=False, all_viewers=["talker"])
        cur.note_chat("talker")
        cur.last_update_time -= 300
        p = cur.users["talker"]["points"]
        cur.process_currency_update(is_live=False, all_viewers=["talker"])
        assert round(cur.users["talker"]["points"] - p, 2) == 1.0, "offline: no active bonus"
        cur.settings["offline_active_bonus"] = True
        cur.note_chat("talker")
        cur.last_update_time -= 300
        p = cur.users["talker"]["points"]
        cur.process_currency_update(is_live=False, all_viewers=["talker"])
        assert round(cur.users["talker"]["points"] - p, 2) == 2.67, cur.users["talker"]["points"] - p
    finally:
        drop_tmpdir(tmp)


async def test_noting_a_chatter_creates_no_record():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.note_chat("stranger")
        assert "stranger" not in cur.users
    finally:
        drop_tmpdir(tmp)


async def test_old_default_one_is_reset_once():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        path = str(cur.settings_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"active_bonus": 1, "live_payout": 4}, f)
        cur.load_settings()
        assert cur.settings["active_bonus"] == 0 and cur.settings["live_payout"] == 4
        with open(path, encoding="utf-8") as f:
            assert json.load(f)["active_bonus"] == 0, "the reset is written back"
        # after the reset a 1 set on purpose stays
        cur.settings["active_bonus"] = 1
        cur.save_settings()
        cur.load_settings()
        assert cur.settings["active_bonus"] == 1
    finally:
        drop_tmpdir(tmp)


async def test_a_value_set_on_purpose_is_kept_and_new_installs_get_zero():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        path = str(cur.settings_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"active_bonus": 7}, f)
        cur.load_settings()
        assert cur.settings["active_bonus"] == 7
        os.remove(path)
        cur.settings.clear()
        cur.load_settings()
        assert cur.settings["active_bonus"] == 0
    finally:
        drop_tmpdir(tmp)


async def test_the_bot_notes_chatters_and_reports_them():
    from bot.ui_port import BotUi
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        bot, _cm, _ = make_bot(tmp, [], currency=cur)
        seen = []
        ui = BotUi()
        ui.active_viewers = lambda names: seen.append(sorted(names))
        bot.ui = ui
        await bot.event_message(FakeMessage("Alice", "hello", FakeChannel()))
        await bot.event_message(FakeMessage("bob", "hi", FakeChannel()))
        await bot.event_message(FakeMessage("alice", "again", FakeChannel()))
        assert "alice" in cur._last_chat and "bob" in cur._last_chat
        assert seen and seen[-1] == ["alice", "bob"], seen
        assert len(seen) == 2, "reported when somebody new starts chatting, not on every line"
    finally:
        drop_tmpdir(tmp)
