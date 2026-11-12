"""Timers tab (2.0): edits are saved to config.json at once."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def _saved():
    with open(os.path.join(DATA, "config.json"), encoding="utf-8") as f:
        return json.load(f).get("timers")


def body(k):
    w, check, pump = k.w, k.check, k.pump
    tab = w.timers_tab
    check("Timers tab is there", w.tab_widget.indexOf(tab) == 11, w.tab_widget.indexOf(tab))
    check("no timers at first", tab.table.rowCount() == 0)

    tab.add_timer(); pump()
    on, msg, every, lines, live = tab._rows[0]
    msg.setText("Follow {channel}!"); msg.editingFinished.emit()
    every.setValue(20); lines.setValue(7); live.setChecked(False); pump()
    saved = _saved()
    check("a new timer is saved with its settings",
          saved == [{"enabled": True, "message": "Follow {channel}!", "interval": 20,
                     "min_lines": 7, "live_only": False}], saved)
    check("the bot reads the same", w.config_manager.get_timers() == saved)

    posted = []
    w.twitch_tab.bridge.submit = lambda name, *a, **kw: posted.append((name, a)) or True

    class Bot(object):
        channel = "mychan"
    w.twitch_tab.bot = None
    w.twitch_tab.bridge._bot = Bot()            # only .channel is read
    tab.table.selectRow(0); pump()
    tab.post_selected(); pump()
    check("Post now sends the rendered text", posted == [("send_chat", ("Follow mychan!",))], posted)
    w.twitch_tab.bridge._bot = None

    tab.add_timer(); pump()
    tab.table.selectRow(1); pump()                 # the new, empty one
    tab.remove_selected(); pump()
    check("remove takes the selected one", len(_saved()) == 1 and tab.table.rowCount() == 1
          and _saved()[0]["message"] == "Follow {channel}!", _saved())

    w.apply_theme("sidebar"); pump(300)
    btn = w.sidebar_nav._nav_buttons.get(11) if hasattr(w.sidebar_nav, "_nav_buttons") else None
    if btn is not None:
        btn.click(); pump(200)
    check("sidebar nav opens Timers", w.tab_widget.currentIndex() == 11
          and w.tab_widget.tabText(11) == "Timers", (w.tab_widget.currentIndex(), w.tab_widget.tabText(11)))
    w.apply_theme("classic"); pump(200)
    tab2 = w.timers_tab
    tab2.reload(); pump()
    check("reload shows the saved timer", tab2.table.rowCount() == 1
          and tab2._rows[0][1].text() == "Follow {channel}!")


kit.start(body, delay_ms=400)
