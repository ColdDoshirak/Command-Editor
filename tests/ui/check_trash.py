"""Trash (2.0): deleted commands come back with Ctrl+Z or from the Trash."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def _disk():
    with open(os.path.join(DATA, "commands.json"), encoding="utf-8") as f:
        return [c["Command"] for c in json.load(f)]


def body(k):
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QMessageBox
    w, check, pump = k.w, k.check, k.pump
    QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.Yes)
    names = [c["Command"] for c in w.commands]
    victim = dict(w.commands[2])

    w.table.selectRow(2); pump()
    w.delete_command(); pump()
    check("deleted from the list and the file", victim["Command"] not in _disk() and len(w.commands) == len(names) - 1)
    check("kept in the trash", len(w.command_trash) == 1
          and w.command_trash.items[0]["command"]["Command"] == victim["Command"])

    # Ctrl+Z inside a text field undoes the text, not the deletion
    w.search_input.setFocus(); w.search_input.setText("abc"); pump()
    QTest.keyClick(w.search_input, Qt.Key_Z, Qt.ControlModifier); pump()
    check("Ctrl+Z in a text field leaves the trash alone", len(w.command_trash) == 1)
    w.search_input.setText(""); pump()

    w.table.setFocus(); pump()
    QTest.keyClick(w.table, Qt.Key_Z, Qt.ControlModifier); pump(200)
    check("Ctrl+Z puts it back where it was", [c["Command"] for c in w.commands] == names
          and _disk() == names, [c["Command"] for c in w.commands])
    check("with everything it had", w.commands[2] == victim)
    check("the trash is empty again", len(w.command_trash) == 0)

    # two deletions, the older one restored from the dialog
    for row in (0, 0):
        w.table.selectRow(row); pump()
        w.delete_command(); pump()
    seen = []

    def use_dialog():
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(50, use_dialog)
            return
        seen.append(dlg.list.count())
        dlg.list.setCurrentRow(1)                    # the older deletion
        dlg.restore()
        seen.append(dlg.list.count())
        dlg.empty()                                  # (question patched to Yes)
        seen.append(dlg.list.count())
        dlg.accept()
    QTimer.singleShot(50, use_dialog)
    w.trash_btn.click(); pump(200)
    check("the dialog lists both, restores one, empties", seen == [2, 1, 0], seen)
    check("the older one is back at its place", w.commands[0]["Command"] == names[0]
          and names[1] not in [c["Command"] for c in w.commands], [c["Command"] for c in w.commands])

    from ui.theme.widgets import _more_menu
    texts = [a.text() for a in _more_menu(w, w).actions()]
    check("the themes' More menu has Undo delete and Trash", "Trash…" in texts
          and "Undo delete (Ctrl+Z)" in texts, texts)


kit.start(body, delay_ms=400)
