"""Step 1.4 / S6 in the window: the Ranks tab edits the ranks the currency
system uses; a new rank is assigned to viewers right away."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
os.makedirs(os.path.join(DATA, "data"), exist_ok=True)
fixture.write_json(os.path.join(DATA, "data"), "ranks.json",
                   [{"name": "Gold", "required": 500, "group": "Viewer"},
                    {"name": "Bronze", "required": 10, "group": "Viewer"}])
fixture.write_json(DATA, "users_currency.json",
                   {"viewer": {"points": 150, "hours": 0, "last_seen": 0}})
kit = uikit.boot(DATA, OUT)


def body(k):
    w, check, pump = k.w, k.check, k.pump
    tab, cur = w.ranks_tab, w.currency_manager
    check("tab and currency share one ranks list", tab.ranks is cur.ranks)
    check("ranks loaded at start (sorted)", [r["name"] for r in cur.ranks] == ["Bronze", "Gold"],
          cur.ranks)
    names = [tab.ranks_table.item(i, 0).text() for i in range(tab.ranks_table.rowCount())]
    check("tab shows the loaded ranks", names == ["Bronze", "Gold"], names)

    # what RanksTab.add_rank does after its dialogs
    tab.ranks.append({"name": "Silver", "required": 100, "group": "Viewer",
                      "description": "", "color": "#c0c0c0"})
    tab.save_ranks(); tab.populate_table(); pump()
    names = [tab.ranks_table.item(i, 0).text() for i in range(tab.ranks_table.rowCount())]
    check("new rank shown in order", names == ["Bronze", "Silver", "Gold"], names)
    check("viewer gets the new rank at once", cur.users["viewer"].get("rank") == "Silver",
          cur.users["viewer"])
    with open(os.path.join(DATA, "data", "ranks.json"), encoding="utf-8") as f:
        check("ranks.json saved sorted", [r["name"] for r in json.load(f)] == ["Bronze", "Silver", "Gold"])
    # step 1.5: the currency tab writes the keys the bot reads
    ctab = w.currency_tab
    ctab.raid_payout_input.setValue(42); pump()
    ctab.follow_payout_input.setValue(3); pump()
    check("raid reward saved as raid_points", cur.settings.get("raid_points") == 42,
          {k: cur.settings.get(k) for k in ("raid_points", "raid_payout")})
    check("follow reward saved as follow_points", cur.settings.get("follow_points") == 3)
    check("no legacy keys written", "raid_payout" not in cur.settings and "follow_payout" not in cur.settings)
    with open(os.path.join(DATA, "data", "currency_settings.json"), encoding="utf-8") as f:
        on_disk = json.load(f)
    check("currency_settings.json uses the shared keys",
          on_disk.get("raid_points") == 42 and "raid_payout" not in on_disk, on_disk)

    w.apply_theme("midnight"); pump(200)
    w.tab_widget.setCurrentIndex(5); pump(300)
    k.shot("ranks_midnight")
    check("ranks tab still shares the list after theme switch", w.ranks_tab.ranks is cur.ranks)


kit.start(body, delay_ms=400)
