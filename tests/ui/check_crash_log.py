"""Stage 0.5 in the real window: an exception in a Qt slot is written to
command_editor_crash.log and does not close the app; the previous run's
log is shifted to .1 instead of being deleted."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
with open(os.path.join(DATA, "command_editor.log"), "w", encoding="utf-8") as f:
    f.write("previous run\n")

# what command_editor.py's __main__ does before the window exists
sys.path.insert(0, uikit.REPO)
import app_log  # noqa: E402
app_log.install_crash_handlers(DATA)
kit = uikit.boot(DATA, OUT, catch_slot_errors=False)
app_log.install_qt_message_handler()


def body(k):
    from PyQt5.QtCore import QTimer
    check, pump = k.check, k.pump
    log = os.path.join(DATA, "command_editor.log")
    with open(log + ".1", encoding="utf-8") as f:
        check("previous run's log kept as .1", "previous run" in f.read())

    def broken_slot():
        raise ZeroDivisionError("slot boom for the crash log")
    QTimer.singleShot(0, broken_slot)
    pump(400)
    check("app still running after a slot exception", k.w.isVisible())
    crash = os.path.join(DATA, app_log.CRASH_LOG_NAME)
    text = open(crash, encoding="utf-8").read() if os.path.exists(crash) else ""
    check("slot exception written to crash log",
          "slot boom for the crash log" in text and "Traceback" in text, text[-500:])
    k.w.apply_theme("midnight"); pump(200)
    check("window still usable", k.w.tab_widget.count() == 12, k.w.tab_widget.count())


kit.start(body, delay_ms=400)
