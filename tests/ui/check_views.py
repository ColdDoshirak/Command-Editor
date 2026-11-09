"""Sys.Commands themed view, Settings tab in classic, Spreadsheet
inspector, latest-backup card colour, re-linking a moved sound folder."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA, moved_sounds=True)
kit = uikit.boot(DATA, OUT)


def body(k):
    w, check, pump, shot = k.w, k.check, k.pump, k.shot
    from PyQt5.QtCore import QCoreApplication, QEvent
    from PyQt5.QtWidgets import QFrame, QMessageBox

    pump(1600)  # start-up sound check runs from a 1500 ms QTimer
    sounds = [c.get("SoundFile", "") for c in w.commands if c.get("SoundFile")]
    check("moved sounds re-linked on start",
          sounds and all(os.path.exists(s) and "snd_moved" in s for s in sounds), sounds[:2])
    with open("commands.json", encoding="utf-8") as f:
        disk = json.load(f)
    check("re-link saved to commands.json",
          all("snd_moved" in c.get("SoundFile", "") for c in disk if c.get("SoundFile")))

    # ---- classic: Settings tab ------------------------------------------
    idx = w.tab_widget.indexOf(w.settings_tab)
    check("classic has Settings tab", idx == 11 and w.tab_widget.count() == 12,
          (idx, w.tab_widget.count()))
    w.tab_widget.setCurrentIndex(idx); pump(300)
    before = w.allow_interruption_check.isChecked()
    w.settings_tab._bindings[0][0].toggle(); pump()
    check("classic settings drives checkbox", w.allow_interruption_check.isChecked() != before)
    w.settings_tab._bindings[0][0].toggle(); pump()
    shot("views_classic_settings")
    check("classic fix-paths button", hasattr(w, "fix_paths_btn"))

    # ---- latest backup card ---------------------------------------------
    w.backup_tab.create(); w.backup_tab.refresh(); pump(200)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); pump(100)
    frames = [f for f in w.backup_tab.findChildren(QFrame) if f.objectName() == "latestBackup"]
    check("latest backup card found", len(frames) == 1, len(frames))
    if frames:
        ss = frames[0].styleSheet()
        check("latest backup: no fixed white bg",
              "#f9fff9" not in ss and "QFrame#latestBackup" in ss, ss)

    # ---- midnight: Sys.Commands master/detail ----------------------------
    w.apply_theme("midnight"); pump(300)
    w.tab_widget.setCurrentIndex(1); pump(400)
    sv = w.themed_tab_views["Sys.Commands"].content
    check("midnight sys view is master/detail",
          sv is not None and type(sv).__name__ == "SysCommandsView"
          and not w.sys_commands_tab.isVisible())
    n = len(w.sys_commands_tab.system_commands)
    check("sys list shows all", sv.list.count() == n, (sv.list.count(), n))
    vol_row = [i for i, c in enumerate(sv.cmds) if c["command"] == "!volume"][0]
    sv._select(vol_row); sv._populate(vol_row); pump()
    check("volume extras visible",
          sv.f_default.isVisibleTo(sv) and not sv.f_random.isVisibleTo(sv))
    sv.f_default.setEditText("MUSIC"); sv.f_cd.setValue(3); pump(700)
    saved = [c for c in w.config_manager.load_system_commands() if c["command"] == "!volume"][0]
    check("sys edit saved (default_group, cooldown)",
          saved.get("default_group") == "MUSIC" and saved.get("cooldown") == 3, saved)
    check("classic table synced", w.sys_commands_tab.table.item(vol_row, 6).text() == "3")
    check("original name read-only", sv.f_name.isReadOnly())
    shot("views_midnight_sys_volume")

    pts_row = [i for i, c in enumerate(sv.cmds) if c["command"] == "!points"][0]
    sv._select(pts_row); sv._populate(pts_row)
    sv._duplicate(); pump()
    new_row = len(sv.cmds) - 1
    check("duplicate created & selected", sv._row == new_row and sv.cmds[new_row]["is_duplicate"])
    sv.f_name.setText("!money"); pump(700)
    check("duplicate renamed", sv.cmds[new_row].get("command_name") == "!money",
          sv.cmds[new_row].get("command_name"))
    sv.f_name.setText("!top"); pump(700)
    check("duplicate name validated", sv.cmds[new_row].get("command_name") == "!money"
          and "already exists" in sv.error.text(), sv.error.text())
    shot("views_midnight_sys_dup")
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.Yes)
    try:
        sv._remove(); pump()
    finally:
        QMessageBox.question = orig_q
    check("duplicate removed", len(sv.cmds) == n, len(sv.cmds))
    w.tab_widget.setCurrentIndex(10); pump(400)
    shot("views_midnight_backups")

    # ---- spreadsheet inspector ------------------------------------------
    w.apply_theme("spreadsheet"); pump(300)
    w.tab_widget.setCurrentIndex(0); pump(300)
    s = w.themed_commands_view
    check("spreadsheet has inspector", s.detail.isVisibleTo(s))
    s.select_from_table(2); pump()
    check("inspector follows selection", s.detail.row == 2, s.detail.row)
    s.detail.f_info.setText("from inspector"); pump(600)
    r = s.dense.currentRow()
    check("inspector edit saved", w.commands[2]["Info"] == "from inspector", w.commands[2]["Info"])
    check("inspector edit shown in table", s.dense.item(r, s._col["Info"]).text() == "from inspector")
    s.dense.item(r, s._col["Cost"]).setText("33"); pump()
    check("table edit shown in inspector", s.detail.f_cost.value() == 33, s.detail.f_cost.value())
    s.select_from_table(0); pump()
    check("inspector switches row",
          s.detail.row == 0 and s.detail.f_cost.value() == w.commands[0]["Cost"])
    shot("views_spreadsheet_inspector")
    s.details_btn.click(); pump()
    check("inspector can be hidden", not s.detail.isVisibleTo(s))
    s.details_btn.click(); pump()
    w.tab_widget.setCurrentIndex(1); pump(300)
    check("spreadsheet sys = classic table", w.themed_tab_views["Sys.Commands"].content is None)

    # ---- sidebar view ---------------------------------------------------
    w.apply_theme("sidebar"); pump(300)
    w.tab_widget.setCurrentIndex(0); pump(300)
    v = w.themed_commands_view
    v.master_list.setCurrentRow(1); pump()
    v.detail.f_cd.setValue(9); pump(600)
    w.save_commands()
    check("sidebar edit via shared editor", w.commands[1]["Cooldown"] == 9 and v._row == 1)

    # ---- missing sound is flagged, fixer dialog builds -------------------
    w.commands[1]["SoundFile"] = "Z:/nowhere/x.wav"; w.update_table(); pump()
    v.master_list.setCurrentRow(1); pump()
    check("missing sound flagged", v.detail.missing_lab.isVisibleTo(v.detail))
    from ui.sound_relink import make_relink_dialog
    dlg = make_relink_dialog(w)
    check("fixer lists missing", dlg.table.rowCount() == 1, dlg.table.rowCount())
    dlg.show(); pump(300)
    shot("views_fix_dialog", dlg)
    dlg.close()

    for t in ("midnight", "classic", "spreadsheet", "sidebar", "classic"):
        w.apply_theme(t); pump(150)
    check("round trip: 12 tabs", w.tab_widget.count() == 12, w.tab_widget.count())
    check("round trip: sys tab back in classic",
          w.tab_widget.indexOf(w.sys_commands_tab) == 1, w.tab_widget.indexOf(w.sys_commands_tab))
    w.tab_widget.setCurrentIndex(1); pump(200)
    check("classic sys tab visible", w.sys_commands_tab.isVisible())


kit.start(body, delay_ms=300)
