"""Stats tab (2.0)."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def body(k):
    w, check, pump = k.w, k.check, k.pump
    tab = w.stats_tab
    check("Stats tab is there", w.tab_widget.tabText(w.tab_widget.indexOf(tab)) == "Stats")
    cur = w.currency_manager
    with cur.users_lock:
        cur.users.clear()
        cur.users.update({"alice": {"points": 120.5, "hours": 3}, "bob": {"points": 30, "hours": 9},
                          "carol": {"points": 5, "hours": 1}})
    st = cur.stats
    old = (date.today() - timedelta(days=3)).isoformat()
    st.days[old] = {"earned": 100, "rewards": 0, "spent": 10, "given": 0, "commands": {"!hello": 5}}
    st.record("earned", 12.5)
    st.record("spent", 4)
    st.record("given", 2)
    st.record("command", name="!hello")
    st.record("command", name="!new")
    w.command_repo.update(0, {"Count": 40})
    w.twitch_tab.active_users = ["alice", "bob"]

    w.tab_widget.setCurrentWidget(tab); pump(300)
    tab.period.setCurrentIndex(0); pump()          # today
    vals = {k: v.text() for k, v in tab.values.items()}
    check("today's points", vals["earned"] == "12.5" and vals["spent"] == "4" and vals["given"] == "2", vals)
    check("now: held, viewers, chatting", vals["circulation"] == "155.5" and vals["viewers"] == "3"
          and vals["active"] == "2", vals)
    rows = [[tab.commands_table.item(r, c).text() for c in range(3)]
            for r in range(tab.commands_table.rowCount())]
    check("commands: period and all time", rows[0][0] in ("!hello", "!new") and
          ["!hello", "1", "40"] in rows, rows)
    tab.period.setCurrentIndex(1); pump()          # 7 days
    check("7 days include the older day", tab.values["earned"].text() == "112.5"
          and ["!hello", "6", "40"] in [[tab.commands_table.item(r, c).text() for c in range(3)]
                                       for r in range(tab.commands_table.rowCount())])
    check("top by points", tab.points_table.item(0, 0).text() == "alice"
          and tab.points_table.item(0, 1).text() == "120.5")
    check("top by hours", tab.hours_table.item(0, 0).text() == "bob")
    w.apply_theme("sidebar"); pump(300)
    w.apply_theme("classic"); pump(200)
    check("tab survives theme switches", w.tab_widget.indexOf(w.stats_tab) == 12)


kit.start(body, delay_ms=400)
