"""Stage 2 in the window: CommandRepository is the only source of truth.

- the classic table is only a view (save never reads it)
- S12: the classic "Command Details" fields save their edits
- an invalid cell value is rolled back, selecting rows writes nothing
- the bot works on copies; its usage counts reach the editor's commands
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def _disk():
    with open("commands.json", encoding="utf-8") as f:
        return json.load(f)


def body(k):
    from PyQt5.QtWidgets import QFileDialog
    w, check, pump = k.w, k.check, k.pump
    w.apply_theme("classic"); pump(200)
    w.tab_widget.setCurrentIndex(0); pump(200)
    repo = w.command_repo
    check("editor list is the repository's list", w.commands is repo.items)
    check("Twitch tab sees the same list", w.twitch_tab.commands_data is repo.items)

    # ---- the table is only a view ------------------------------------------
    w.table.blockSignals(True)
    w.table.item(1, 2).setText("garbage only in the table")
    w.table.blockSignals(False)
    w.save_commands(); pump()
    check("save does not read the table",
          w.commands[1]["Info"] != "garbage only in the table"
          and _disk()[1]["Info"] != "garbage only in the table", w.commands[1]["Info"])
    w.update_table(); pump()

    # ---- invalid cell value is rolled back ---------------------------------------
    w.table.item(1, 7).setText("abc"); pump()   # Cost
    check("invalid Cost rolled back in the cell", w.table.item(1, 7).text() == "0",
          w.table.item(1, 7).text())
    w.table.item(1, 7).setText("25"); pump()
    check("valid cell edit saved", w.commands[1]["Cost"] == 25 and _disk()[1]["Cost"] == 25)

    # ---- selecting rows writes nothing ----------------------------------------------
    events = []
    repo.subscribe(lambda ev, rows: events.append(ev))
    mtime = os.path.getmtime("commands.json")
    for r in (0, 2, 3, 1, 4):
        w.table.selectRow(r); pump(60)
    check("selecting rows changes nothing", events == [] and
          os.path.getmtime("commands.json") == mtime, events)

    # ---- S12: classic detail fields save ------------------------------------------------
    w.table.selectRow(2); pump()
    w.cooldown_spin.setValue(150); pump()
    check("cooldown above 99 saved from the details panel",
          w.commands[2]["Cooldown"] == 150 and _disk()[2]["Cooldown"] == 150, w.commands[2]["Cooldown"])
    w.info_edit.setText("typed in details"); w.info_edit.editingFinished.emit(); pump()
    check("info saved from the details panel", _disk()[2]["Info"] == "typed in details", _disk()[2])
    w.permission_combo.setCurrentText("Moderator"); pump()
    check("permission saved from the details panel", _disk()[2]["Permission"] == "Moderator")
    w.enabled_check.setChecked(False); pump()
    check("enabled saved from the details panel", _disk()[2]["Enabled"] is False)
    new_sound = os.path.join(DATA, "picked.wav")
    fixture.make_wav(new_sound)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **kw: (new_sound, ""))
    w.sound_file_btn.click(); pump()
    check("Browse... saves the sound file", _disk()[2]["SoundFile"] == new_sound, _disk()[2]["SoundFile"])
    check("table shows the panel's edits", w.table.item(2, 5).text() == "150"
          and w.table.item(2, 11).text() == new_sound)

    # ---- add / delete save at once ---------------------------------------------------
    n = len(w.commands)
    w.add_command(); pump()
    check("new command saved at once", len(_disk()) == n + 1 and _disk()[-1]["Command"] == "!new")
    w.table.selectRow(n); pump()
    w.delete_command(); pump()
    check("deleted command gone from disk", len(_disk()) == n)

    # ---- the bot works on copies -----------------------------------------------------
    snap = w.twitch_tab._commands_snapshot()
    check("bot gets copies", snap[0] == w.commands[0] and snap[0] is not w.commands[0])
    snap[0]["Group"] = "BOT-NORMALISED"
    check("bot changes do not reach the editor", w.commands[0]["Group"] != "BOT-NORMALISED")
    before = w.commands[0]["Count"]
    t = threading.Thread(target=w.twitch_tab.bridge.command_used, args=(snap[0],))
    t.start(); t.join(); pump(200)   # as the bot thread does
    check("usage count from the bot thread reaches the editor",
          w.commands[0]["Count"] == before + 1, (before, w.commands[0]["Count"]))
    check("count shown in the table", w.table.item(0, 8).text() == str(before + 1))

    # ---- themed views still edit through the repository ------------------------------
    w.apply_theme("sidebar"); pump(300)
    w.tab_widget.setCurrentIndex(0); pump(200)
    v = w.themed_commands_view
    v.master_list.setCurrentRow(3); pump()
    v.detail.f_cost.setValue(7); pump(600)
    check("themed edit saved through the repository", _disk()[3]["Cost"] == 7, _disk()[3]["Cost"])
    w.apply_theme("classic"); pump(200)
    check("classic table shows the themed edit", w.table.item(3, 7).text() == "7")


kit.start(body, delay_ms=400)
