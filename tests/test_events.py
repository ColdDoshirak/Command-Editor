"""Step 3.5 / S7: raid and sub rewards from USERNOTICE.

Py3.8 compatible.
"""
import asyncio

from harness import make_bot, FakeChannel, new_tmpdir, drop_tmpdir, make_real_currency

from bot.events import usernotice_rewards

SETTINGS = {"raid_points": 10, "raid_points_per_viewer": 1, "sub_points": 20,
            "gift_sub_points": 15, "mass_sub_points": 3}


async def test_raid_reward_formula():
    r = usernotice_rewards({"msg-id": "raid", "login": "raider", "display-name": "Raider",
                            "msg-param-viewerCount": "42"}, SETTINGS)
    assert [(x.user, x.points) for x in r] == [("raider", 52.0)], r
    assert "Raider" in r[0].chat and "42" in r[0].chat


async def test_sub_tiers_and_prime():
    for plan, pts in (("1000", 20), ("2000", 40), ("3000", 100), ("Prime", 20)):
        r = usernotice_rewards({"msg-id": "resub", "login": "fan", "msg-param-sub-plan": plan}, SETTINGS)
        assert [(x.user, x.points, x.subscriber) for x in r] == [("fan", pts, True)], (plan, r)


async def test_gift_sub_rewards_recipient_and_gifter():
    r = usernotice_rewards({"msg-id": "subgift", "login": "santa",
                            "msg-param-recipient-user-name": "Lucky", "msg-param-sub-plan": "1000"},
                           SETTINGS)
    assert sorted((x.user, x.points) for x in r) == [("lucky", 15.0), ("santa", 3.0)], r
    anon = usernotice_rewards({"msg-id": "anonsubgift", "login": "ananonymousgifter",
                               "msg-param-recipient-user-name": "lucky"}, SETTINGS)
    assert [(x.user, x.points) for x in anon] == [("lucky", 15.0)], anon


async def test_no_reward_events_and_zero_settings():
    assert usernotice_rewards({"msg-id": "submysterygift", "login": "santa",
                               "msg-param-mass-gift-count": "5"}, SETTINGS) == []
    assert usernotice_rewards({"msg-id": "announcement", "login": "x"}, SETTINGS) == []
    assert usernotice_rewards({"msg-id": "raid", "login": "r", "msg-param-viewerCount": "3"},
                              {"raid_points": 0, "raid_points_per_viewer": 0}) == []


async def test_bot_pays_rewards_on_raw_usernotice():
    tmp = new_tmpdir()
    try:
        cur = make_real_currency(tmp)
        cur.settings.update(SETTINGS)
        bot, _cm, _ = make_bot(tmp, [], currency=cur)
        assert hasattr(bot, "event_raw_usernotice"), "twitchio calls event_raw_usernotice"
        ch = FakeChannel()
        await bot.event_raw_usernotice(ch, {"msg-id": "raid", "login": "raider",
                                            "msg-param-viewerCount": "5"})
        await bot.event_raw_usernotice(ch, {"msg-id": "sub", "login": "fan",
                                            "msg-param-sub-plan": "2000"})
        assert cur.users["raider"]["points"] == 15, cur.users.get("raider")
        assert cur.users["fan"]["points"] == 40 and cur.users["fan"].get("is_subscriber"), cur.users.get("fan")
        assert len(ch.sent) == 2 and "рейд" in ch.sent[0], ch.sent
    finally:
        drop_tmpdir(tmp)


async def test_dead_twitchio1_handlers_removed():
    tmp = new_tmpdir()
    try:
        bot, _cm, _ = make_bot(tmp, [])
        for name in ("event_raid", "event_subscription"):
            assert not hasattr(bot, name), name
    finally:
        drop_tmpdir(tmp)
