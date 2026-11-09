"""Step 1.4 / S6: ranks live in CurrencyManager.

CurrencyManager.ranks used to be always [] (data/ranks.json was never read),
so ranks were never assigned and !points said "Unranked". The Ranks tab
saved unsorted ranks, while promotion assumes ascending thresholds.

Py3.8 compatible.
"""
import json
import os

from harness import new_tmpdir, drop_tmpdir, make_real_currency

RANKS = [
    {"name": "Gold", "required": 500, "group": "Viewer", "description": "", "color": "#ffd700"},
    {"name": "Bronze", "required": 10, "group": "Viewer", "description": "", "color": "#cd7f32"},
    {"name": "Silver", "required": "100", "group": "Viewer", "description": "", "color": "#c0c0c0"},
]


def _write_ranks(tmp, ranks):
    os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
    with open(os.path.join(tmp, "data", "ranks.json"), "w", encoding="utf-8") as f:
        json.dump(ranks, f)


def _currency_with_ranks(tmp, ranks=RANKS):
    _write_ranks(tmp, ranks)
    cur = make_real_currency(tmp)
    cur.settings["rank_type"] = "Points"
    cur.settings["regular_bonus"] = 0
    return cur


async def test_ranks_loaded_and_sorted_at_start():
    tmp = new_tmpdir()
    try:
        cur = _currency_with_ranks(tmp)
        assert [r["name"] for r in cur.ranks] == ["Bronze", "Silver", "Gold"], cur.ranks
        assert cur.ranks[1]["required"] == 100, "thresholds must be numbers"
    finally:
        drop_tmpdir(tmp)


async def test_points_assign_rank_and_points_message_shows_it():
    tmp = new_tmpdir()
    try:
        cur = _currency_with_ranks(tmp)
        cur.users["viewer"] = {"points": 0, "hours": 0, "last_seen": 0}
        cur.add_points("viewer", 150)
        assert cur.users["viewer"].get("rank") == "Silver", cur.users["viewer"]
        cur.settings["response"] = "$username [$rank]"
        assert cur.format_currency_message("viewer") == "viewer [Silver]"
    finally:
        drop_tmpdir(tmp)


async def test_set_ranks_saves_sorted_and_rechecks_users():
    tmp = new_tmpdir()
    try:
        cur = _currency_with_ranks(tmp)
        cur.users["viewer"] = {"points": 150, "hours": 0, "last_seen": 0, "rank": "Silver"}
        cur.set_ranks([
            {"name": "Elite", "required": 120, "group": "Viewer"},
            {"name": "Newbie", "required": 0, "group": "Viewer"},
        ])
        assert [r["name"] for r in cur.ranks] == ["Newbie", "Elite"]
        assert cur.users["viewer"]["rank"] == "Elite", cur.users["viewer"]
        with open(os.path.join(tmp, "data", "ranks.json"), encoding="utf-8") as f:
            assert [r["name"] for r in json.load(f)] == ["Newbie", "Elite"]
    finally:
        drop_tmpdir(tmp)


async def test_rank_type_hours_uses_hours():
    tmp = new_tmpdir()
    try:
        cur = _currency_with_ranks(tmp)
        cur.settings["rank_type"] = "Hours"
        cur.users["viewer"] = {"points": 1000, "hours": 12, "last_seen": 0}
        cur.check_rank_promotion("viewer")
        assert cur.users["viewer"].get("rank") == "Bronze", cur.users["viewer"]
    finally:
        drop_tmpdir(tmp)


# ---- step 1.5: one schema for currency setting keys -------------------------
async def test_currency_settings_legacy_keys_migrated():
    tmp = new_tmpdir()
    try:
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        settings_file = os.path.join(tmp, "data", "currency_settings.json")
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump({"name": "Coins", "on_raid": 10, "raid_points": 10, "raid_payout": 33,
                       "follow_payout": 7, "sub_event_payout": 12, "mass_sub_payout": 4,
                       "host_payout": 2, "on_follow": 10}, f)
        cur = make_real_currency(tmp)
        cur.load_settings()
        s = cur.settings
        assert (s["raid_points"], s["follow_points"], s["sub_points"],
                s["mass_sub_points"], s["host_points"]) == (33, 7, 12, 4, 2), s
        for old in ("on_raid", "raid_payout", "follow_payout", "on_follow", "sub_event_payout",
                    "mass_sub_payout", "host_payout", "on_sub", "mass_sub_gift", "on_host"):
            assert old not in s, old
        with open(settings_file, encoding="utf-8") as f:
            on_disk = json.load(f)
        assert on_disk.get("raid_points") == 33 and "raid_payout" not in on_disk, on_disk
        assert cur.get_currency_name() == "Coins"
    finally:
        drop_tmpdir(tmp)
