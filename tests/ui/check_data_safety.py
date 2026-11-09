"""Data safety in the editor window.

S10  load_file / restore_backup / full restore replaced self.commands with a
     new list; the themed view and the Twitch tab kept the old one, so edits
     went into a command that was no longer saved.
S5   full restore wrote the restored currency only if a save was pending.
C5   closeEvent "deduplicated" commands by name: a second !new vanished.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def _disk_commands():
    with open("commands.json", encoding="utf-8") as f:
        return json.load(f)


def body(k):
    from PyQt5.QtWidgets import QFileDialog, QMessageBox
    w, check, pump = k.w, k.check, k.pump
    QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **kw: QMessageBox.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **kw: QMessageBox.Ok)

    w.apply_theme("sidebar"); pump(300)
    w.tab_widget.setCurrentIndex(0); pump(200)
    original = w.commands

    def edit_row0_via_view(info):
        v = w.themed_commands_view
        v.master_list.setCurrentRow(0); pump()
        v.detail.f_info.setText(info); pump(600)
        w.save_commands(); pump()

    def same_list_everywhere(tag):
        check("%s: editor keeps one command list" % tag, w.commands is original)
        check("%s: Twitch tab sees the same list" % tag, w.twitch_tab.commands_data is w.commands)

    # ---- load_file --------------------------------------------------------
    abcomg = os.path.join(DATA, "import.abcomg")
    with open(abcomg, "w", encoding="utf-8") as f:
        json.dump([fixture.command("!imported1", Response="a"),
                   fixture.command("!imported2", Response="b")], f)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **kw: (abcomg, ""))
    w.load_file(); pump(300)
    check("load_file: commands loaded",
          [c["Command"] for c in w.commands] == ["!imported1", "!imported2"],
          [c["Command"] for c in w.commands])
    same_list_everywhere("load_file")
    edit_row0_via_view("after load")
    check("load_file: themed edit is saved",
          _disk_commands()[0].get("Info") == "after load", _disk_commands()[0])

    # ---- restore_backup (history) ----------------------------------------
    backup = os.path.join(DATA, "history_backup.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump([fixture.command("!restored", Response="r")], f)
    w.history_manager.restore_backup = lambda p: json.load(open(p, encoding="utf-8"))
    w.history_tab.restore(backup); pump(300)
    check("restore_backup: commands restored",
          [c["Command"] for c in w.commands] == ["!restored"], [c["Command"] for c in w.commands])
    same_list_everywhere("restore_backup")
    edit_row0_via_view("after restore")
    check("restore_backup: themed edit is saved",
          _disk_commands()[0].get("Info") == "after restore", _disk_commands()[0])

    # ---- full (comprehensive) restore: commands + currency ---------------
    full = os.path.join(DATA, "full_backup.json")
    with open(full, "w", encoding="utf-8") as f:
        json.dump({"commands": [fixture.command("!full1"), fixture.command("!full2")],
                   "currency_users": {"alice": {"points": 777, "hours": 1}}}, f)
    w.currency_manager._save_pending = False
    w.backup_tab.restore(full); pump(400)
    check("full restore: commands restored",
          [c["Command"] for c in w.commands] == ["!full1", "!full2"],
          [c["Command"] for c in w.commands])
    same_list_everywhere("full restore")
    users_file = str(w.currency_manager.users_file)
    with open(users_file, encoding="utf-8") as f:
        users = json.load(f)
    check("full restore: currency written to disk (S5)",
          users.get("alice", {}).get("points") == 777, users)
    edit_row0_via_view("after full")
    check("full restore: themed edit is saved",
          _disk_commands()[0].get("Info") == "after full", _disk_commands()[0])

    # ---- C6: the auth dialog updates the config the app actually uses -----
    from ui.twitch_auth import TwitchAuthDialog
    dlg = TwitchAuthDialog(w.twitch_tab)
    dlg.client_id_edit.setText("cid-new")
    dlg.access_token_edit.setText("tok-new")
    dlg.refresh_token_edit.setText("ref-new")
    dlg.save_tokens(); pump()
    live = w.twitch_tab.config_manager.get_twitch_config()
    check("auth dialog: running app sees the new token (C6)",
          live.get("access_token") == "tok-new" and live.get("client_id") == "cid-new",
          {k: live.get(k) for k in ("access_token", "client_id")})
    check("auth dialog: one ConfigManager", dlg.config_manager is w.twitch_tab.config_manager)
    with open("twitch_config.json", encoding="utf-8") as f:
        check("auth dialog: token written to disk", json.load(f).get("access_token") == "tok-new")

    # ---- C5: two commands with the same name survive closing --------------
    w.commands.append(fixture.command("!full1", Response="second copy"))
    w.update_table(); w.refresh_themed_commands(); w.save_commands(); pump()
    w.close(); pump(300)
    names = [c["Command"] for c in _disk_commands()]
    check("close keeps commands with the same name (C5)",
          names == ["!full1", "!full2", "!full1"], names)


kit.start(body, delay_ms=400)
