"""OBS overlay (2.0): Settings -> OBS overlay starts a local server that shows
the bot's queues and the recent commands."""
import json
import os
import socket
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


class FakeBot(object):
    is_running = True
    is_live = True
    loop = None

    def __init__(self):
        self.ui = None
        self.command_queues = {"SONG": None}
        self.queue_paused = set()

    def queue_snapshot(self, group):
        return {"current": {"command": "song", "user": "alice", "started": time.time() - 65},
                "pending": [{"id": 1, "user": "bob", "command": "next"}],
                "paused": False, "max": 0, "free": None, "enabled": True}

    def queue_pending_count(self, group):
        return 1


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get_json(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def body(k):
    w, check, pump = k.w, k.check, k.pump
    check("off by default", not w.overlay.running() and w.overlay_url() == "")
    w.apply_theme("sidebar"); pump(300)
    panel = getattr(w.settings_tab, "original_tab", w.settings_tab)
    check("settings page has the overlay card", hasattr(panel, "overlay_switch"))

    port = _free_port()
    panel.overlay_port.setValue(port)
    panel.overlay_switch.setChecked(True); pump(300)
    url = w.overlay_url()
    check("enabled: the URL is shown", url == "http://127.0.0.1:%d/" % port
          and panel.overlay_url.text() == url, (url, panel.overlay_url.text(), w.overlay.error))
    with open(os.path.join(DATA, "config.json"), encoding="utf-8") as f:
        check("saved to config.json", json.load(f).get("overlay") == {"enabled": True, "port": port})

    with urllib.request.urlopen(url, timeout=5) as r:
        page = r.read().decode("utf-8")
    check("the page is served", "state.json" in page and "<html" in page)

    w.twitch_tab.bot = FakeBot()
    t = threading.Thread(target=w.twitch_tab.bridge.command_run, args=("!hi", "carol"))
    t.start(); t.join()                          # as the bot thread does
    pump(800)                                    # the window pushes every 0.5 s
    st = _get_json(url + "state.json")
    check("now playing from the bot", st["now"] and st["now"][0]["user"] == "alice"
          and st["now"][0]["elapsed"] >= 60, st["now"])
    check("the queue", st["queues"][0]["pending"] == [{"command": "!next", "user": "bob"}], st["queues"])
    check("recent commands with the viewer", st["recent"] == [{"command": "!hi", "user": "carol"}],
          st["recent"])
    check("connected / live", st["connected"] and st["live"])
    w.twitch_tab.bot = None

    # a port another program holds
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    try:
        panel.overlay_port.setValue(busy)
        panel.overlay_port.editingFinished.emit(); pump(300)
        check("a busy port is reported", not w.overlay.running()
              and "Could not start" in panel.overlay_status.text(), panel.overlay_status.text())
    finally:
        blocker.close()

    panel.overlay_switch.setChecked(False); pump(200)
    check("disabled: stopped", not w.overlay.running() and panel.overlay_url.text() == "")
    w.apply_theme("classic"); pump(200)


kit.start(body, delay_ms=400)
