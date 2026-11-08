"""Shared setup for the UI checks: real CommandEditor window, real Qt,
real pygame, data in a throw-away folder, no network.

A check script calls ``boot(data_dir, out_dir)`` *after* it has written its
fixture into data_dir, then ``kit.start(run)``. Results are printed as
``PASS  name`` / ``FAIL  name  detail`` lines; run_ui.py collects them.

Py3.8 compatible.
"""
import os
import sys
import time
import traceback

TESTS_UI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTS_UI))


def _disable_network():
    import requests

    def _no_net(*a, **k):
        raise requests.ConnectionError("network disabled in UI checks")

    requests.get = _no_net
    requests.post = _no_net
    requests.request = _no_net
    requests.Session.request = _no_net


class Kit(object):
    def __init__(self, data_dir, out_dir, size=(1360, 820)):
        self.data_dir = os.path.abspath(data_dir)
        self.out_dir = os.path.abspath(out_dir) if out_dir else None
        self.results = []
        # Data folder = data_dir (core.paths reads the env var). Working
        # directory = data_dir too, so the one-time migration from the cwd
        # never copies the developer's files into the fixture.
        os.environ["COMMAND_EDITOR_HOME"] = self.data_dir
        os.chdir(self.data_dir)
        if REPO not in sys.path:
            sys.path.insert(0, REPO)
        _disable_network()

        from PyQt5.QtWidgets import QApplication
        import pygame
        pygame.mixer.init()
        self.app = QApplication.instance() or QApplication(sys.argv)
        import command_editor
        self.w = command_editor.CommandEditor()
        self.w.resize(*size)
        self.w.show()

    # -- helpers -------------------------------------------------------------
    def check(self, name, cond, detail=""):
        self.results.append(("PASS" if cond else "FAIL", name, detail))

    def pump(self, ms=150):
        t = time.time()
        while time.time() - t < ms / 1000.0:
            self.app.processEvents()
            time.sleep(0.005)

    def shot(self, name, widget=None):
        if self.out_dir:
            (widget or self.w).grab().save(os.path.join(self.out_dir, name + ".png"))

    # -- run -----------------------------------------------------------------
    def start(self, body, delay_ms=500):
        from PyQt5.QtCore import QTimer

        def _run():
            try:
                body(self)
            except Exception:
                self.results.append(("FAIL", "exception", traceback.format_exc()))
            self.report()
            self.app.quit()

        QTimer.singleShot(delay_ms, _run)
        self.app.exec_()

    def report(self):
        out = sys.__stdout__
        for status, name, detail in self.results:
            line = "%s  %s" % (status, name)
            if status == "FAIL" and detail != "":
                line += "  " + str(detail).replace("\n", "\n      ")
            out.write(line + "\n")
        out.flush()


def boot(data_dir, out_dir, **kw):
    return Kit(data_dir, out_dir, **kw)


def args():
    """(data_dir, out_dir) from the command line; out_dir may be absent."""
    if len(sys.argv) < 2:
        sys.stderr.write("usage: %s <data_dir> [screenshots_dir]\n" % sys.argv[0])
        sys.exit(2)
    return sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
