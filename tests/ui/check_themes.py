"""Themed Commands views (sidebar / spreadsheet / midnight / classic):
edits survive save_commands(), selection is kept, search filters, the tab
set is restored after theme round trips."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def body(k):
    w, check, pump, shot = k.w, k.check, k.pump, k.shot

    # ---- sidebar: edit row 3, selection must stay on row 3 --------------
    w.apply_theme("sidebar"); pump()
    v = w.themed_commands_view
    v.master_list.setCurrentRow(2); pump()
    check("sidebar select row 3", v._row == 2, "row=%s" % v._row)
    v.detail.f_cd.setValue(7); pump(500)
    check("sidebar edit keeps row", v._row == 2, "row=%s" % v._row)
    v.detail.f_info.setText("info edited"); pump(500)
    v.detail.f_response.setPlainText("line1\nline2"); pump(500)
    v.detail.f_volume.setValue(42); pump(500)
    v.detail.f_perm.setCurrentText("Moderator"); pump(200)
    # save_commands re-reads the classic table: edits must survive it
    w.save_commands(); pump()
    cmd = w.commands[2]
    check("cooldown survives save", cmd["Cooldown"] == 7, cmd["Cooldown"])
    check("info survives save", cmd["Info"] == "info edited", cmd["Info"])
    check("response survives save", cmd["Response"] == "line1\nline2", repr(cmd["Response"]))
    check("volume int 0-100", cmd["Volume"] == 42 and isinstance(cmd["Volume"], int), cmd["Volume"])
    check("permission", cmd["Permission"] == "Moderator", cmd["Permission"])
    with open("commands.json", encoding="utf-8") as f:
        disk = json.load(f)[2]
    check("written to commands.json", disk["Cooldown"] == 7 and disk["Volume"] == 42, disk)
    check("volume label not 10000%", "10000" not in v.detail.f_volume_lab.text(),
          v.detail.f_volume_lab.text())
    w.commands[0]["Count"] = 99
    w.save_commands(); pump()
    check("count survives save", w.commands[0]["Count"] == 99, w.commands[0]["Count"])
    v.search_edit.setText("multi"); pump()
    check("sidebar search filters", v.master_list.count() == 1, v.master_list.count())
    v.search_edit.setText(""); pump()
    shot("themes_sidebar_commands")

    idx = w.tab_widget.indexOf(w.settings_tab)
    check("settings tab exists", idx == uikit.settings_index(w), idx)
    w.tab_widget.setCurrentIndex(idx); pump(300)
    before = w.allow_interruption_check.isChecked()
    sp = w.settings_tab.original_tab
    sp._bindings[0][0].toggle(); pump()
    check("settings proxy drives classic checkbox", w.allow_interruption_check.isChecked() != before)
    sp._bindings[0][0].toggle(); pump()
    shot("themes_sidebar_settings")
    for i, n in ((7, "queue"), (6, "groups")):
        w.tab_widget.setCurrentIndex(i); pump(300)
        shot("themes_sidebar_" + n)

    # ---- spreadsheet ----------------------------------------------------
    w.apply_theme("spreadsheet"); pump()
    s = w.themed_commands_view
    s.select_from_table(1); pump()
    s.dense.item(s.dense.currentRow(), s._col["Cost"]).setText("15"); pump()
    s.dense.item(s.dense.currentRow(), s._col["Volume"]).setText("55%"); pump()
    w.save_commands(); pump()
    check("spreadsheet cost survives save", w.commands[1]["Cost"] == 15, w.commands[1]["Cost"])
    check("spreadsheet volume", w.commands[1]["Volume"] == 55, w.commands[1]["Volume"])
    check("spreadsheet keeps selection", s._selected_idx() == 1, s._selected_idx())
    s.search_edit.setText("song"); pump()
    check("spreadsheet search filters", 0 < s.dense.rowCount() < len(w.commands), s.dense.rowCount())
    s.search_edit.setText(""); pump()
    check("spreadsheet group editable", bool(s.dense.item(0, s._col["Group"]).flags() & 0x2))
    w.tab_widget.setCurrentIndex(0); pump(200)
    shot("themes_spreadsheet_commands")

    # ---- midnight -------------------------------------------------------
    w.apply_theme("midnight"); pump(300)
    check("midnight nav", w.sidebar_nav is not None and w.sidebar_nav.isVisible())
    check("now playing bar", getattr(w, "now_playing_bar", None) is not None)
    for i, n in ((0, "commands"), (2, "twitch"), (7, "queue"), (6, "groups"),
                 (13, "settings"), (3, "currency"), (11, "timers"), (12, "stats")):
        w.tab_widget.setCurrentIndex(i); pump(300)
        shot("themes_midnight_" + n)

    # ---- back to classic ------------------------------------------------
    w.apply_theme("classic"); pump(300)
    check("classic: settings tab", w.tab_widget.indexOf(w.settings_tab) == uikit.settings_index(w))
    check("classic: all tabs", w.tab_widget.count() == uikit.tab_count(w), w.tab_widget.count())
    check("classic: no nav", w.sidebar_nav is None)
    check("classic: no now bar", getattr(w, "now_playing_bar", None) is None)
    check("classic: tab stylesheet reset", w.group_settings_tab.styleSheet() == "")
    for i, n in ((7, "queue"), (6, "groups")):
        w.tab_widget.setCurrentIndex(i); pump(300)
        shot("themes_classic_" + n)
    for t in ("midnight", "sidebar", "spreadsheet", "classic"):
        w.apply_theme(t); pump(150)
    check("theme round trip", w.tab_widget.count() == uikit.tab_count(w), w.tab_widget.count())


kit.start(body, delay_ms=800)
