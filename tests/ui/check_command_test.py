"""Test command (2.0): a dry run from the window - nothing charged or counted."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def body(k):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    w, check, pump = k.w, k.check, k.pump
    row = next(i for i, c in enumerate(w.commands) if c["SoundFile"] and os.path.exists(c["SoundFile"]))
    w.command_repo.update(row, {"Response": "{user} -> {target} #{count}", "Permission": "VIP",
                                "Cost": 50, "Aliases": "!alt"})
    before = dict(w.commands[row])
    seen = []

    def inspect():
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(50, inspect)
            return
        try:
            dlg.message.setText("!alt @bob")
            dlg.user.setText("alice")
            dlg.role.setCurrentText("Subscriber")
            seen.append(("sub", dlg.last["problems"][:], dlg.result.toPlainText()))
            dlg.role.setCurrentText("VIP")
            dlg.points.setValue(10)
            seen.append(("vip-poor", dlg.last["problems"][:], ""))
            dlg.points.setValue(100)
            seen.append(("vip", dlg.last["problems"][:], dlg.result.toPlainText()))
            seen.append(("play", dlg.play_btn.isEnabled(), ""))
        finally:
            dlg.reject()
    w.table.selectRow(row); pump()
    QTimer.singleShot(50, inspect)
    w.test_cmd_btn.click(); pump(200)
    check("the dialog opened from the classic panel", len(seen) == 4, seen)
    if len(seen) == 4:
        check("a subscriber is refused (needs VIP)", any("needs VIP" in p for p in seen[0][1]), seen[0])
        check("not enough points is said", any("costs 50" in p for p in seen[1][1]), seen[1])
        check("a VIP with points: it runs, the reply is shown",
              seen[2][1] == [] and "alice -> bob #%d" % (before["Count"] + 1) in seen[2][2], seen[2])
        check("the sound can be played from it", seen[3][1] is True)
    check("nothing was charged, counted or changed", w.commands[row] == before)

    # themed editor button
    opened = []
    w.apply_theme("sidebar"); pump(300)
    v = w.themed_commands_view
    v.master_list.setCurrentRow(row); pump()
    QTimer.singleShot(50, lambda: (opened.append(QApplication.activeModalWidget()),
                                   QApplication.activeModalWidget() and QApplication.activeModalWidget().reject()))
    v.detail.test_btn.click(); pump(200)
    check("the themed editor opens it too", opened and opened[0] is not None, opened)
    w.apply_theme("classic"); pump(200)


kit.start(body, delay_ms=400)
