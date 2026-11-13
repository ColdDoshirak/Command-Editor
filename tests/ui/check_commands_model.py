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

    # ---- the table is a view over the repository (step 4.4) ---------------------
    from PyQt5.QtWidgets import QTableWidget
    model = w.table.model()

    def cell(r, c):
        return model.index(r, c).data()
    check("classic table is a model view over the repository",
          not isinstance(w.table, QTableWidget) and getattr(model, "repo", None) is repo)
    check("cells show the repository",
          cell(1, 0) == w.commands[1]["Command"] and cell(1, 7) == str(w.commands[1]["Cost"]),
          (cell(1, 0), cell(1, 7)))

    # ---- invalid cell value is rolled back ---------------------------------------
    model.setData(model.index(1, 7), "abc"); pump()   # Cost
    check("invalid Cost not stored, cell shows the stored value",
          w.commands[1]["Cost"] == 0 and cell(1, 7) == "0", cell(1, 7))
    model.setData(model.index(1, 7), "25"); pump()
    check("valid cell edit saved", w.commands[1]["Cost"] == 25 and _disk()[1]["Cost"] == 25)
    # as the user does it: open the cell editor, type, Enter
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
    idx = model.index(1, 5)                                    # Cooldown
    w.table.setCurrentIndex(idx); w.table.edit(idx); pump()
    ed = QApplication.focusWidget()
    ed.selectAll() if hasattr(ed, "selectAll") else None
    QTest.keyClicks(ed, "42"); QTest.keyClick(ed, Qt.Key_Return); pump()
    check("cell typed by the user is saved", w.commands[1]["Cooldown"] == 42
          and _disk()[1]["Cooldown"] == 42 and cell(1, 5) == "42", (w.commands[1]["Cooldown"], cell(1, 5)))
    repo.update(1, {"Info": "changed elsewhere"}); pump()
    check("repository edits appear without a redraw call", cell(1, 2) == "changed elsewhere",
          cell(1, 2))

    # ---- search survives model resets -------------------------------------------------
    w.search_input.setText(w.commands[0]["Command"]); pump()
    hidden = [r for r in range(model.rowCount()) if w.table.isRowHidden(r)]
    repo.add({"Command": "!zzz_not_matching"}); pump()
    hidden2 = [r for r in range(model.rowCount()) if w.table.isRowHidden(r)]
    check("search filter re-applied after a reset",
          hidden and model.rowCount() - 1 in hidden2 and set(hidden) <= set(hidden2), (hidden, hidden2))
    repo.remove(model.rowCount() - 1)
    w.search_input.setText(""); pump()
    check("clearing the search shows every row",
          not any(w.table.isRowHidden(r) for r in range(model.rowCount())))

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
    check("table shows the panel's edits", cell(2, 5) == "150"
          and cell(2, 11) == new_sound)

    # ---- add / delete save at once ---------------------------------------------------
    n = len(w.commands)
    w.add_command(); pump()
    check("new command saved at once", len(_disk()) == n + 1 and _disk()[-1]["Command"] == "!new")
    from PyQt5.QtWidgets import QMessageBox
    asked = []
    orig_q = QMessageBox.question
    try:
        QMessageBox.question = staticmethod(lambda *a, **kw: asked.append(a[2]) or QMessageBox.No)
        w.table.selectRow(n); pump()
        w.delete_command(); pump()
        check("delete asks first, naming the command", asked and "!new" in asked[0], asked)
        check("answer No keeps the command", len(_disk()) == n + 1 and len(w.commands) == n + 1)
        QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.Yes)
        w.delete_command(); pump()
        check("deleted command gone from disk", len(_disk()) == n)
    finally:
        QMessageBox.question = orig_q

    # ---- Play Sound (step 4.3): no helper thread, button reset in the UI thread -------
    row = next(i for i, c in enumerate(w.commands) if c["SoundFile"] and os.path.exists(c["SoundFile"]))
    w.table.selectRow(row); pump()
    threads = threading.active_count()
    w.play_sound_btn.click(); pump(50)
    check("preview: playing", w.play_sound_btn.text() == "Stop Sound", w.play_sound_btn.text())
    check("preview: no helper thread", threading.active_count() == threads,
          (threads, threading.active_count()))
    pump(1200)                                   # fixture sounds are 0.3 s
    check("preview: button reset after the sound ends", w.play_sound_btn.text() == "Play Sound",
          w.play_sound_btn.text())
    w.play_sound_btn.click(); pump(50)
    w.play_sound_btn.click(); pump(50)
    check("preview: second press stops", w.play_sound_btn.text() == "Play Sound"
          and not w.preview.is_playing())
    import pygame
    from bot.audio import PREVIEW_CHANNEL, GROUP_CHANNELS
    pump(300)                                    # let the fade-out finish
    w.play_sound_btn.click(); pump(50)
    check("preview plays on its own mixer channel, not the bot's shared 0",
          PREVIEW_CHANNEL >= GROUP_CHANNELS and pygame.mixer.get_num_channels() > PREVIEW_CHANNEL
          and pygame.mixer.Channel(PREVIEW_CHANNEL).get_busy() and not pygame.mixer.Channel(0).get_busy())
    w.play_sound_btn.click(); pump(300)
    try:
        pygame.mixer.Channel(GROUP_CHANNELS - 1)
        ok32 = True
    except IndexError:
        ok32 = False
    check("the highest group channel Group Settings offers exists", ok32)

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
    check("count shown in the table", cell(0, 8) == str(before + 1))

    # ---- themed views still edit through the repository ------------------------------
    w.apply_theme("sidebar"); pump(300)
    w.tab_widget.setCurrentIndex(0); pump(200)
    v = w.themed_commands_view
    v.master_list.setCurrentRow(3); pump()
    v.detail.f_cost.setValue(7); pump(600)
    check("themed edit saved through the repository", _disk()[3]["Cost"] == 7, _disk()[3]["Cost"])
    w.apply_theme("classic"); pump(200)
    check("classic table shows the themed edit", cell(3, 7) == "7")

    # ---- permission ladder in the window (2.0) -----------------------------------------
    from core.permissions import LEVELS
    items = [w.permission_combo.itemText(i) for i in range(w.permission_combo.count())]
    check("permission list has every level", items == LEVELS, items)
    repo.update(4, {"Permission": "Editor"})        # a Streamlabs spelling
    w.table.selectRow(4); pump()
    check("Streamlabs 'Editor' shown as Moderator", w.permission_combo.currentText() == "Moderator",
          w.permission_combo.currentText())
    check("selecting the row did not rewrite it", w.commands[4]["Permission"] == "Editor")
    w.config_manager.moderators_config["admins"] = ["boss"]
    w.twitch_tab.channel_input.setText("mychannel")
    w.twitch_tab.update_moderators_display_only(); pump()
    shown = [w.twitch_tab.moderators_list_widget.item(i).text()
             for i in range(w.twitch_tab.moderators_list_widget.count())]
    check("admins listed on the Twitch tab", shown[:2] == ["[Admin] mychannel", "[Admin] boss"], shown)
    w.apply_theme("sidebar"); pump(300)
    panel = getattr(w.settings_tab, "original_tab", w.settings_tab)
    check("Settings: moderators are admins by default", panel.mods_admin_switch.isChecked()
          and w.config_manager.get_moderators_are_admins())
    panel.mods_admin_switch.setChecked(False); pump()
    import json as _json
    with open(str(w.config_manager.moderators_file), encoding="utf-8") as f:
        saved = _json.load(f).get("moderators_are_admins")
    check("turning it off is saved", saved is False and not w.config_manager.get_moderators_are_admins(), saved)
    panel.mods_admin_switch.setChecked(True); pump()
    w.apply_theme("classic"); pump(200)


    # ---- aliases field (2.0) -----------------------------------------------------------
    w.apply_theme("classic"); pump(200)
    w.table.selectRow(1); pump()
    w.aliases_edit.setText("!alias1, alias2"); w.aliases_edit.editingFinished.emit(); pump()
    check("classic: aliases saved", w.commands[1].get("Aliases") == "!alias1, alias2"
          and _disk()[1].get("Aliases") == "!alias1, alias2", w.commands[1].get("Aliases"))
    w.apply_theme("sidebar"); pump(300)
    v = w.themed_commands_view
    v.master_list.setCurrentRow(1); pump()
    check("themed editor shows the aliases", v.detail.f_aliases.text() == "!alias1, alias2",
          v.detail.f_aliases.text())
    v.detail.f_aliases.setText("!other"); v.detail.flush(); pump()
    check("themed editor saves the aliases", _disk()[1].get("Aliases") == "!other", _disk()[1].get("Aliases"))
    w.apply_theme("classic"); pump(200)


kit.start(body, delay_ms=400)
